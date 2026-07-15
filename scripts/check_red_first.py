# check_red_first.py — red-first 証明: fix の同梱テストが親コミットで赤だったことの機械証明（契約: .guardrails/GUARDRAILS.md §5）
#
# 呼び出し（§7.1: 必ず uv 経由。CI の red-first ジョブとローカルで同じ）:
#   uv run scripts/check_red_first.py [--soft] [--base <rev>] [--head <rev>]
#     --base 既定 origin/main（CI は PR の base SHA を渡す）／--head 既定 HEAD
#     --soft = 表示のみモード: 違反を SOFT: で列挙して exit 0。
#              決定点③は v2.9 で required に確定——出荷 CI は --soft を付けない（違反は
#              exit 1 で赤）。--soft はロールバック手段として残置（§5・Phase 21）
#   exit 0 = 違反なし（--soft・未配線の不発・fix なしを含む）
#   exit 1 = 違反あり（--soft では返さない） / exit 2 = 内部エラー
#
# やること（§5・Phase 18）: --base..--head のマージ以外の `fix:` コミット毎に、
#   ① そのコミットで**追加**されたテストファイル（repo_scan.TEST_PATH_PATTERNS）を列挙
#   ② 親コミットを一時 worktree へ checkout（**リポジトリ直下**に作る——node/npx の
#      モジュール解決は親ディレクトリを遡るため、主チェックアウトの node_modules が
#      worktree からそのまま見える。残骸は .gitignore のキット区画 `.red-first-*/` が吸収）
#   ③ 追加テストのみコミットの内容で worktree へコピー（バイト忠実——エンコーディング非依存）
#   ④ 採用列の「単一テストファイル実行」（repo_scan.SINGLE_TEST_COMMAND / SINGLE_TEST_CWD。
#      "{file}" トークンが cwd 相対パスに展開される——dev.py の "{args}" と同じ流儀）で実行
#   ⑤ **少なくとも1つが赤**（非0）なら証明成立。全部緑なら `red-first-green` を
#      1コミット1行で報告する（検査2 fix⇔テスト対の「同梱」を「再現の証明」へ引き上げる — G10）
#
# 免除・対象外（いずれも1行で見える——静かなスキップの禁止 §7.2）:
#   - コミット本文に `RED-FIRST-EXEMPT: 理由` 行 → 免除（逃げ道の意味論は検査2と同一）。
#     **理由は必須**——理由の無い免除は不成立として通常判定を続行（v2.9・乱用監視の
#     機械化部分。人間側の監視＝理由の具体性・頻度の点検はレビュー規約 — ルート AGENTS.md §8）
#   - 追加テストの無い fix（既存テストへの追記は単離できない——同梱自体は検査2が担保済み）
#   - SINGLE_TEST_CWD の配線外にあるテスト（単一スロット＝複数言語構成の副言語側）
#   - 親の無い初回コミット／親 worktree に実行ディレクトリが無い
#   - TEST_PATH_PATTERNS または SINGLE_TEST_COMMAND が未充填 → 全体が不発（列充填で有効化 §12.7）
#
# 近似は仕様（§7.4）: 「非0 = 赤」。親で実行エラーになるテスト（fix と同時に足した
#   ヘルパへ依存する等）も赤と数える——親が fix を欠く事実の現れとして寛大側に倒す。
#   ハング（TIMEOUT_SEC 超過）は赤の証明にならないため内部エラーで止める（Fail Loudly）。

from __future__ import annotations

import argparse
import os
import posixpath
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import repo_scan as rs  # noqa: E402

FILE_TOKEN = "{file}"
EXEMPT_PREFIX = "RED-FIRST-EXEMPT:"
TIMEOUT_SEC = 300  # 単一テストファイル1回あたりの保険（無限に待つ CI ＝最悪の出戻り — G11）


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(["git", "-C", str(root), *args], capture_output=True, check=False)
    except OSError as exc:
        raise rs.ScanError(f"git を起動できない: {exc}")


def _git_ok(root: Path, *args: str) -> bytes:
    proc = _git(root, *args)
    if proc.returncode != 0:
        raise rs.ScanError(
            f"git {' '.join(args)} が失敗: {proc.stderr.decode('utf-8', 'replace').strip()}")
    return proc.stdout


def resolve_rev(root: Path, rev: str, role: str) -> str:
    proc = _git(root, "rev-parse", "--verify", "-q", f"{rev}^{{commit}}")
    if proc.returncode != 0:
        raise rs.ScanError(
            f"{role} を解決できない: {rev!r}（例: --base origin/main / --base main。"
            "CI では PR の base SHA を渡し、checkout は fetch-depth: 0 で全履歴を取る — §5）")
    return proc.stdout.decode("utf-8", "replace").strip()


def fix_commits(root: Path, base: str, head: str) -> list[str]:
    """base..head のマージ以外のコミット（古い順）。"""
    out = _git_ok(root, "rev-list", "--no-merges", "--reverse", f"{base}..{head}")
    return [s for s in out.decode("utf-8", "replace").split() if s]


def commit_message(root: Path, sha: str) -> list[str]:
    return _git_ok(root, "log", "-1", "--format=%B", sha).decode("utf-8", "replace").splitlines()


def added_test_files(root: Path, sha: str) -> list[str]:
    out = _git_ok(root, "diff", "--name-only", "--diff-filter=A", "-z", f"{sha}^", sha)
    added = [p for p in out.decode("utf-8", "replace").split("\0") if p]
    return sorted(p for p in added if rs.is_test_file(p))


def splice_file(cmd: list[str], rel_to_cwd: str) -> list[str]:
    """"{file}" トークンをパスへ展開（無ければ末尾に連結——dev.py と同じ流儀 §12.1）。"""
    if FILE_TOKEN in cmd:
        return [rel_to_cwd if part == FILE_TOKEN else part for part in cmd]
    return cmd + [rel_to_cwd]


def run_single_test(worktree: Path, rel: str, resolved0: str) -> int:
    """worktree 上でテスト1ファイルを実行し exit code を返す（非0 = 赤の近似 — §7.4）。"""
    cwd = worktree / rs.SINGLE_TEST_CWD if rs.SINGLE_TEST_CWD else worktree
    rel_to_cwd = posixpath.relpath(rel, rs.SINGLE_TEST_CWD) if rs.SINGLE_TEST_CWD else rel
    cmd = splice_file(list(rs.SINGLE_TEST_COMMAND), rel_to_cwd)
    cmd[0] = resolved0
    try:
        proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True, timeout=TIMEOUT_SEC)
    except subprocess.TimeoutExpired:
        raise rs.ScanError(
            f"単一テスト実行が {TIMEOUT_SEC} 秒以内に返らない: {rel}"
            "（ハングは赤の証明にならない——テスト側のタイムアウト整備は §9.1 の思想）")
    except OSError as exc:
        raise rs.ScanError(f"単一テスト実行を起動できない: {cmd[0]} ({exc})")
    return proc.returncode


class ParentWorktree:
    """親コミットの一時 worktree（リポジトリ直下・後片付けまで — 冒頭ヘッダー②）。"""

    def __init__(self, root: Path, parent_sha: str):
        self.root = root
        self.parent = parent_sha
        self.tmp: Path | None = None
        self.path: Path | None = None

    def __enter__(self) -> Path:
        self.tmp = Path(tempfile.mkdtemp(prefix=".red-first-", dir=self.root))
        self.path = self.tmp / "wt"
        _git_ok(self.root, "worktree", "add", "--detach", "--quiet",
                str(self.path), self.parent)
        return self.path

    def __exit__(self, *_exc) -> None:
        if self.path is not None:
            _git(self.root, "worktree", "remove", "--force", str(self.path))
        if self.tmp is not None:
            shutil.rmtree(self.tmp, ignore_errors=True)
        _git(self.root, "worktree", "prune")


def copy_blob(root: Path, sha: str, rel: str, worktree: Path) -> None:
    data = _git_ok(root, "show", f"{sha}:{rel}")  # コミットの内容そのもの（バイト忠実）
    dest = worktree / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)


def append_step_summary(lines: list[str], headline: str) -> None:
    """GitHub Actions のジョブサマリへ赤/緑を表示する（無ければ何もしない — §5 決定点③）。"""
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    try:
        with open(path, "a", encoding="utf-8", newline="\n") as f:
            f.write(f"### red-first 証明（.guardrails/GUARDRAILS.md §5）\n\n{headline}\n\n")
            f.write("```\n" + "\n".join(lines) + "\n```\n")
    except OSError as exc:
        print(f"check_red_first: 警告: ジョブサマリへ書けない（{exc}）——判定には影響しない",
              file=sys.stderr)


def check_commit(root: Path, sha: str, resolved0: str, log: list[str]) -> str:
    """fix コミット1つの判定。返り値 ∈ {"proven","exempt","skipped","violation"}。"""
    short = sha[:7]

    def note(line: str) -> None:
        print(line)
        log.append(line)

    exempt_seen = False
    for line in commit_message(root, sha):
        stripped = line.strip()
        if not stripped.startswith(EXEMPT_PREFIX):
            continue
        exempt_seen = True
        reason = stripped[len(EXEMPT_PREFIX):].strip()
        if reason:
            note(f"[red-first] {short} 免除: {EXEMPT_PREFIX} {reason}（逃げ道の意味論は検査2と同一 — §5）")
            return "exempt"
    if exempt_seen:
        note(f"[red-first] {short} 免除不成立: {EXEMPT_PREFIX} に理由が無い——理由の無い"
             "免除は無効（乱用監視の機械化部分 — §5・v2.9）。通常判定を続行する")

    if _git(root, "rev-parse", "--verify", "-q", f"{sha}^").returncode != 0:
        note(f"[red-first] {short} 対象外: 親コミットが無い（初回コミット — §5）")
        return "skipped"

    tests = added_test_files(root, sha)
    if not tests:
        note(f"[red-first] {short} 対象外: 追加テストなし（既存テストへの追記は単離できない。"
             "同梱自体は検査2が担保済み — §5）")
        return "skipped"

    runnable = tests
    if rs.SINGLE_TEST_CWD:
        prefix = rs.SINGLE_TEST_CWD.rstrip("/") + "/"
        runnable = [t for t in tests if t.startswith(prefix)]
        for t in sorted(set(tests) - set(runnable)):
            note(f"[red-first] {short} 配線外: {t}（SINGLE_TEST_CWD={rs.SINGLE_TEST_CWD!r} の外"
                 "——単一スロットの副言語側は対象外 — §5）")
    if not runnable:
        note(f"[red-first] {short} 対象外: 実行可能な追加テストなし（§5）")
        return "skipped"

    with ParentWorktree(root, f"{sha}^") as wt:
        run_dir = wt / rs.SINGLE_TEST_CWD if rs.SINGLE_TEST_CWD else wt
        if not run_dir.is_dir():
            note(f"[red-first] {short} 対象外: 親コミットに実行ディレクトリ "
                 f"{rs.SINGLE_TEST_CWD!r} が無い（§5）")
            return "skipped"
        greens: list[str] = []
        for rel in runnable:
            copy_blob(root, sha, rel, wt)
            rc = run_single_test(wt, rel, resolved0)
            if rc != 0:
                note(f"[red-first] {short} 証明成立: {rel} が親コミットで赤 (exit {rc})")
                return "proven"
            greens.append(rel)
            note(f"[red-first] {short} 親で緑: {rel} (exit 0)")
    return "violation"


def main(argv: list[str]) -> int:
    rs.reconfigure_stdio()
    ap = argparse.ArgumentParser(
        description="red-first 証明: fix の同梱テストが親コミットで赤だったか（.guardrails/GUARDRAILS.md §5）")
    ap.add_argument("--base", default="origin/main",
                    help="比較の起点リビジョン（既定: origin/main。CI は PR の base SHA を渡す）")
    ap.add_argument("--head", default="HEAD", help="対象範囲の終点（既定: HEAD）")
    ap.add_argument("--soft", action="store_true",
                    help="表示のみ: 違反を SOFT: で列挙して exit 0（required からのロールバック用 — §5）")
    args = ap.parse_args(argv)

    started = time.monotonic()
    root = rs.repo_root()

    if not rs.TEST_PATH_PATTERNS or rs.SINGLE_TEST_COMMAND is None:
        print("[red-first] 未配線のため不発: TEST_PATH_PATTERNS / SINGLE_TEST_COMMAND を "
              "bindings/catalog.md の採用列で充填すると有効化される（§12.7・§5）")
        return 0
    if not rs.SINGLE_TEST_COMMAND or rs.SINGLE_TEST_COMMAND[0] == FILE_TOKEN:
        raise rs.ScanError("SINGLE_TEST_COMMAND の先頭がコマンド名でない（列の paste-block を確認 — §5）")
    resolved0 = shutil.which(rs.SINGLE_TEST_COMMAND[0])
    if resolved0 is None:  # §12.1 の流儀: 未導入は導入先を示す明示エラー（静かなスキップ禁止）
        raise rs.ScanError(
            f"単一テスト実行コマンドが見つからない: {rs.SINGLE_TEST_COMMAND[0]!r}"
            "（採用列の前提ツール欄を確認。CI では red-first ジョブの BINDING で"
            "セットアップする — §5）")

    base = resolve_rev(root, args.base, "--base")
    head = resolve_rev(root, args.head, "--head")

    log: list[str] = []
    counts = {"proven": 0, "exempt": 0, "skipped": 0, "violation": 0}
    violations: list[str] = []
    prefix = "SOFT" if args.soft else "HARD"
    total = 0
    for sha in fix_commits(root, base, head):
        subject = next((ln for ln in commit_message(root, sha) if ln.strip()), "")
        if not subject.startswith("fix:"):
            continue
        total += 1
        verdict = check_commit(root, sha, resolved0, log)
        counts[verdict] += 1
        if verdict == "violation":
            line = (f"{prefix}:red-first-green ({sha[:7]}) fix の同梱テストが親コミットでも"
                    "全部緑——バグを再現していない。親で赤になるテストに直すか、CI 上で"
                    f"赤にできない修正なら本文に `{EXEMPT_PREFIX} 理由` を書く"
                    "（.guardrails/GUARDRAILS.md §5）")
            print(line, file=sys.stderr)
            violations.append(line)
            log.append(line)

    elapsed = int((time.monotonic() - started) * 1000)
    summary = (f"[red-first] fix {total}件: 証明 {counts['proven']} / 免除 {counts['exempt']}"
               f" / 対象外 {counts['skipped']} / 違反 {counts['violation']} (+{elapsed}ms)")
    print(summary)
    log.append(summary)

    if counts["violation"]:
        headline = (f"**赤: 親コミットでも緑の fix が {counts['violation']} 件**"
                    + ("（--soft: 表示のみ — 決定点③）" if args.soft else ""))
        append_step_summary(log, headline)
        if args.soft:
            print(f"check-red-first: 違反 {counts['violation']} 件（--soft: 表示のみ・exit 0"
                  "——出荷既定は required。--soft はロールバック用 — §5）",
                  file=sys.stderr)
            return 0
        return 1
    append_step_summary(log, "**緑: 違反なし**")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except rs.ScanError as exc:
        print(f"check_red_first: 内部エラー: {exc}", file=sys.stderr)
        sys.exit(2)
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as exc:  # 想定外も exit 2（exit 1 は違反に予約 — §7.5 と同義）
        print(f"check_red_first: 内部エラー: {exc!r}", file=sys.stderr)
        sys.exit(2)
