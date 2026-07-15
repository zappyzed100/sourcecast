# check_guard_corpus.py — guard迂回コーパスの再生チェッカ + probe事前照会（契約: .guardrails/GUARDRAILS.md §2）
#
# 呼び出し（§7.1: 必ず uv 経由）:
#   uv run scripts/check_guard_corpus.py                  … コーパス再生（門番の回帰テスト）
#   uv run scripts/check_guard_corpus.py --probe "<cmd>"  … 事前照会（このコマンドは通るか）
#     ※ probe は dev.py の動詞としても配線済み: uv run scripts/dev.py probe "<cmd>"（§12.1）
#
# コーパス再生:
#   tests/guard_corpus.tsv（1行 = `期待<TAB>コマンド文字列` または
#   `期待<TAB>前提<TAB>コマンド文字列`・期待 ∈ DENY/ALLOW・前提 ∈ dirty/clean。
#   空行・コメント行・書式不正は不可＝内部エラー。コーパスが黙って痩せるのを防ぐ）
#   の各行から {"tool_input":{"command": …}} を組み立て、guard_git_bypass.py へ
#   stdin で流し、exit 2=DENY / 0=ALLOW を期待と照合する。
#   前提列（v2.5・Phase 14）: 作業消失ガードの dirty 条件付き規則を再生するための列。
#   前提付きの行は一時 git リポジトリ（dirty=未コミット変更あり / clean=変更なし）を
#   カレントにして guard を呼ぶ——外側の GIT_* 環境（フック実行中の git が設定する）と
#   CLAUDE_PROJECT_DIR はフィクスチャ側へ差し替える（外のリポジトリ状態に依存しない）。
#   guard は絶対パスで呼ぶこと——cwd をフィクスチャへ差し替えるため、相対パスで渡すと
#   guard 自身が見つからず「起動できない」がそのまま DENY 扱いに化けて誤判定になる
#   （v2.23 是正時に実際に踏んだ罠）。
#   exit 0 = 全行一致（サマリ1行） / exit 1 = 不一致あり（1違反1行・stderr・§3.3 形式）
#   / exit 2 = 内部エラー（コーパス消失・書式不正・guard の想定外 exit 等）
#
# probe:
#   stdout に `ALLOW`（exit 0）または `DENY guard: <ブロック理由>`（exit 1）。
#   exit 2 は内部エラーに予約（dev.py の終了コード契約と整合 — §12.1）。
#   コーパス再生と**同一経路**で guard を呼ぶ——probe の判定 = 実際の PreToolUse の判定。
#
# v2.23（G11・言語移行）: guard_git_bypass 本体が bash→Python になったため、コーパス
# 再生も `sys.executable` で直接起動する（本スクリプト自体が `uv run` 配下で動いている
# ため、venv の python は既に解決済み——再度 `uv run` を経由すると1行ごとにその
# 解決コストを払う。実測: `uv run python` 経由は全74行1.3〜2秒・`sys.executable`
# 直接は0.4〜1.5秒）。**本番の PreToolUse フック（.claude/settings.json）側は
# 単発起動のみなので `uv run python` のまま**——§7.1 の「Python は必ず uv 経由」を
# 保つ（bash/jq のような前提ツール解決は不要になった——json/re は標準ライブラリ）。
#
# 性能予算: コーパス全行で10秒以内（§7.7・v2.22で2秒→実測是正のまま維持。v2.23の
# 言語移行で実測は1〜2秒まで縮んだが、予算自体は環境差の余白を残して据え置く）。
# 並列度は os.cpu_count() から自動導出（v2.6 — 標準ライブラリで Windows 含め動くため、
# ユーザー入力も調査スクリプトも不要。上限は32→12に是正——Windows実機のベンチで
# 8並列を境に頭打ちと判明・旧上限32は逆効果だった）。

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import repo_scan as rs  # noqa: E402

GUARD_REL = ".claude/hooks/guard_git_bypass.py"
CORPUS_REL = "tests/guard_corpus.tsv"
EXPECTED_VALUES = ("DENY", "ALLOW")
PRECONDITION_VALUES = ("dirty", "clean")  # 前提列（Phase 14）
TIMEOUT_SEC = 10  # 1行あたりの保険（ハングした guard を静かに待たない — G11）


def resolve_tool(name: str, why: str) -> str:
    """PATH 上のツールを解決する。不在は明示エラー（§7.2: 静かなスキップ禁止）。"""
    path = shutil.which(name)
    if path is None:
        raise rs.ScanError(
            f"{name} が見つからない。{why}"
        )
    return path


def run_guard(guard: Path, command: str, cwd: Path | None = None) -> tuple[str, str]:
    """guard を PreToolUse と同じ形（stdin JSON）で1回呼ぶ。

    `sys.executable` で直接起動する（本スクリプト自身が `uv run` 配下——venv の
    python は既に解決済みのため、1行ごとに `uv run` を再度挟むコストを払わない。
    本番の PreToolUse フックは単発起動なので `uv run python` のまま — v2.23）。
    返り値は (判定, stderr先頭行)。判定は exit 2 → "DENY" / exit 0 → "ALLOW" /
    それ以外 → "EXIT{N}"（guard 契約外の終了コード。§2 の fail-closed 契約では
    起き得ない値なので、コーパス再生では必ず不一致として表面化する）。
    cwd を渡すと（前提列の再生 — Phase 14）そのフィクスチャをカレントにし、
    GIT_* / CLAUDE_PROJECT_DIR をフィクスチャ側へ差し替えて呼ぶ——外側の
    リポジトリ状態・フック実行環境に判定が依存しないようにする。guard は絶対パスで
    渡すこと（呼び出し側の契約——cwd 差し替え時に相対パスだと guard 自身が
    見つからず誤判定になる）。
    """
    payload = json.dumps({"tool_input": {"command": command}}, ensure_ascii=False)
    # 違反ログ（§3.6）は常に抑止する——コーパス再生の DENY 期待行（約40行）と probe の
    # 事前照会は「実際に門が止めた事象」ではない。抑止しないと再生のたびに偽の迂回試行が
    # ledger へ積もり、頻度データ（soft→hard 昇格の実測）が計測不能になる。
    if cwd is not None:
        env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        env["CLAUDE_PROJECT_DIR"] = str(cwd)
    else:
        env = dict(os.environ)
    env["GUARDRAILS_LEDGER_SUPPRESS"] = "1"
    try:
        proc = subprocess.run(
            [sys.executable, str(guard)],
            input=payload.encode("utf-8"),
            capture_output=True,
            timeout=TIMEOUT_SEC,
            cwd=None if cwd is None else str(cwd),
            env=env,
        )
    except subprocess.TimeoutExpired:
        raise rs.ScanError(f"guard が {TIMEOUT_SEC} 秒以内に返らない: {command!r}")
    except OSError as exc:
        raise rs.ScanError(f"guard を起動できない: {exc}")
    stderr = proc.stderr.decode("utf-8", "replace").strip().splitlines()
    first = stderr[0] if stderr else ""
    if proc.returncode == 2:
        return "DENY", first
    if proc.returncode == 0:
        return "ALLOW", first
    return f"EXIT{proc.returncode}", first


def load_corpus(path: Path) -> list[tuple[int, str, str | None, str]]:
    """(行番号, 期待, 前提 or None, コマンド) のリスト。空行・書式不正は内部エラー（fail-closed）。

    行は `期待<TAB>コマンド`（前提なし）または `期待<TAB>前提<TAB>コマンド`
    （前提 ∈ dirty/clean — Phase 14 の dirty 条件付き規則の再生用）。
    コマンド内のタブは非対応（書式不正扱い——コーパスが黙って化けるのを防ぐ）。
    """
    if not path.is_file():
        raise rs.ScanError(f"コーパスが無い: {CORPUS_REL}（門番の回帰テストの正本 — §2）")
    rows: list[tuple[int, str, str | None, str]] = []
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.read().splitlines()
    for n, line in enumerate(lines, 1):
        if not line.strip():
            raise rs.ScanError(
                f"コーパス書式不正 {CORPUS_REL} 行{n}: 空行は不可"
                "（1行 = `期待<TAB>[前提<TAB>]コマンド`・期待 ∈ DENY/ALLOW・前提 ∈ dirty/clean — §2）")
        parts = line.split("\t")
        pre: str | None = None
        if len(parts) == 2:
            expected, command = parts
        elif len(parts) == 3:
            expected, pre, command = parts
            if pre not in PRECONDITION_VALUES:
                raise rs.ScanError(
                    f"コーパス書式不正 {CORPUS_REL} 行{n}: 前提は dirty/clean のみ: {line!r}（§2）")
        else:
            raise rs.ScanError(
                f"コーパス書式不正 {CORPUS_REL} 行{n}: {line!r}"
                "（1行 = `期待<TAB>[前提<TAB>]コマンド`・期待 ∈ DENY/ALLOW・前提 ∈ dirty/clean — §2）")
        if expected not in EXPECTED_VALUES or not command.strip():
            raise rs.ScanError(
                f"コーパス書式不正 {CORPUS_REL} 行{n}: {line!r}"
                "（1行 = `期待<TAB>[前提<TAB>]コマンド`・期待 ∈ DENY/ALLOW・前提 ∈ dirty/clean — §2）")
        rows.append((n, expected, pre, command))
    if not rows:
        raise rs.ScanError(f"コーパスが空: {CORPUS_REL}（0行のコーパスは門番を検査しない）")
    return rows


def make_fixture(base: Path, dirty: bool) -> Path:
    """前提列用の一時 git リポジトリ（clean=コミット済みで無変更 / dirty=未コミット変更あり）。

    外側の GIT_* 環境（フック実行中に git が設定する GIT_DIR / GIT_INDEX_FILE 等）を
    持ち込むと外のリポジトリを操作してしまうため、必ず落として呼ぶ。
    """
    d = base / ("dirty" if dirty else "clean")
    d.mkdir()
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}

    def g(*args: str) -> None:
        proc = subprocess.run(["git", "-C", str(d), *args], capture_output=True, env=env)
        if proc.returncode != 0:
            raise rs.ScanError(
                f"前提フィクスチャの作成に失敗: git {' '.join(args)}: "
                f"{proc.stderr.decode('utf-8', 'replace').strip()}")

    g("init", "-q")
    g("config", "user.email", "corpus@example.invalid")
    g("config", "user.name", "guard-corpus")
    g("config", "commit.gpgsign", "false")
    with open(d / "f.txt", "w", encoding="utf-8", newline="\n") as f:
        f.write("clean\n")
    g("add", "f.txt")
    g("commit", "-q", "-m", "init")
    if dirty:
        with open(d / "f.txt", "w", encoding="utf-8", newline="\n") as f:
            f.write("dirty\n")
    return d


def replay(guard: Path, rows: list[tuple[int, str, str | None, str]]) -> int:
    started = time.monotonic()
    fixtures: dict[str, Path] = {}
    with tempfile.TemporaryDirectory(prefix="guard-corpus-") as tmp:
        if any(pre for _, _, pre, _ in rows):
            # 前提列（Phase 14）はフィクスチャの git 状態が判定材料——git が要る
            resolve_tool("git", "前提列（dirty/clean）の再生フィクスチャ作成に必要")
            base = Path(tmp)
            fixtures["clean"] = make_fixture(base, dirty=False)
            fixtures["dirty"] = make_fixture(base, dirty=True)
        # 行ごとに python を1回起動するため、逐次では起動回数×数十msが積む。
        # 行間に依存は無い（guard は無状態・フィクスチャは読み取りのみ）ので並列に流す。
        # 並列度は実機のコア数から自動導出する（v2.6 — G11。os.cpu_count() は標準
        # ライブラリで Windows 含め動く＝ユーザー入力・調査スクリプトは不要）。
        # 下限8（少コア機でも待ち時間を重ねる）・上限12（v2.22で32→12に実測是正:
        # 32コア機Windowsでベンチ実測した結果、8並列を境に頭打ち・24並列ではむしろ悪化。
        # v2.23で guard 本体が bash→Python になった後も再ベンチし、傾向は同じ
        # （コア数比例ではなく子プロセス起動自体の固定コストが律速）ため上限は維持——
        # 予算超過の第一容疑者は常にプロセス起動回数 — §7.7）。
        workers = min(12, max(8, 2 * (os.cpu_count() or 4)), len(rows))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            actuals = list(pool.map(
                lambda r: run_guard(guard, r[3], cwd=fixtures.get(r[2] or "")), rows))
    mismatches = 0
    for (n, expected, pre, command), (actual, _reason) in zip(rows, actuals):
        if actual != expected:
            mismatches += 1
            where = f"[{pre}] " if pre else ""
            print(f"HARD:guard-corpus-mismatch 行{n}: 期待{expected} 実際{actual}: {where}{command}",
                  file=sys.stderr)
    elapsed = int((time.monotonic() - started) * 1000)
    if mismatches:
        print(f"\ncheck-guard-corpus: 不一致 {mismatches} 件/{len(rows)} 行。門番の改修が"
              "過去に塞いだ迂回を開け直していないか、コーパスの期待値と guard 本体"
              "（.guardrails/GUARDRAILS.md §2）を同一コミットで揃える。", file=sys.stderr)
        return 1
    print(f"[guard-corpus] 全{len(rows)}行 PASS (+{elapsed}ms)")
    return 0


def probe(guard: Path, command: str) -> int:
    actual, reason = run_guard(guard, command)
    if actual == "ALLOW":
        print("ALLOW")
        return 0
    if actual == "DENY":
        print(f"DENY guard: {reason or 'ブロック（理由の出力なし）'}")
        return 1
    raise rs.ScanError(f"guard が契約外の終了コードを返した（{actual}）。"
                       "§2 の契約は exit 2=ブロック / exit 0=許可のみ")


def main(argv: list[str]) -> int:
    rs.reconfigure_stdio()
    ap = argparse.ArgumentParser(
        description="guard迂回コーパスの再生チェッカ + probe事前照会（.guardrails/GUARDRAILS.md §2）")
    ap.add_argument("--probe", metavar="CMD",
                    help="コーパスを再生せず、このコマンド1つを事前照会する")
    args = ap.parse_args(argv)

    root = rs.repo_root()
    guard = root / GUARD_REL
    if not guard.is_file():
        raise rs.ScanError(f"guard 本体が無い: {GUARD_REL}（§2。missing-required でも検出される）")

    if args.probe is not None:
        if not args.probe.strip():
            raise rs.ScanError("probe のコマンドが空")
        return probe(guard, args.probe)
    return replay(guard, load_corpus(root / CORPUS_REL))


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except rs.ScanError as exc:
        print(f"check_guard_corpus: 内部エラー: {exc}", file=sys.stderr)
        sys.exit(2)
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as exc:  # 想定外も exit 2（§7.5 と同義。exit 1 は不一致に予約）
        print(f"check_guard_corpus: 内部エラー: {exc!r}", file=sys.stderr)
        sys.exit(2)
