# dev.py — ランタイム共通動詞のルーター: 全プロジェクト同名の動詞で環境を操作する（契約: .guardrails/GUARDRAILS.md §12.1）
#
# 呼び出し（§7.1: 必ず uv 経由）:
#   uv run scripts/dev.py verbs                 … 動詞一覧と配線状態を表示
#   uv run scripts/dev.py <動詞> [引数...]      … 例: up / reset / seed / time 2026-02-28T23:59 /
#                                                  test / e2e / fmt / check / probe "git push -f" /
#                                                  db "select 1"
#   exit = 実行したコマンドの終了コードをそのまま返す / 未配線の動詞 = exit 1 /
#   不明な動詞・引数不正 = exit 2（内部エラー扱い）
#
# 契約（§12.1）:
#   - 動詞の意味論は全プロジェクトで共通。配線（実コマンド）だけが列ごとに違う。
#   - 各動詞は冪等であること（冪等性は配線先コマンドの責務。up を2回叩いても壊れない）。
#   - 出力は `[dev] 動詞: コマンド` → 実行 → `[dev] 動詞: exit N (+Xms)`（ログ形式 — AGENTS.md §7）。
#   - COMMANDS が None の動詞は「未配線」を明示して落ちる（静かに何もしない fail-open の禁止）。
#
# ===== BINDING: 動詞 → コマンド列（bindings/catalog.md の採用列から充填する）=====
# 値は「argv のリスト」のリスト（shell=False で順に実行・非0で中断 — §7.2）。
# 引数を受ける動詞は "{args}" トークンの位置に呼び出し引数が展開される。
# トークンが無いのに引数が来た場合は末尾に連結される。
# 充填は下の管理区画（>>> GUARDRAILS BINDING >>>）内で COMMANDS.update({...}) で行う。

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import repo_scan as rs  # noqa: E402

ARGS_TOKEN = "{args}"

COMMANDS: dict[str, list[list[str]] | None] = {
    "up": None,  # ローカル環境の起動（例: supabase start / docker compose up -d）
    "reset": None,  # 既知状態への復帰（DB reset + seed まで含めて1コマンド — §12.2）
    "seed": None,  # シードデータ投入のみ（reset に含まれるなら同じ配線でよい）
    "time": None,  # 時刻の凍結/解除（例: dev.py time 2026-02-28T23:59 / dev.py time clear）
    "test": None,  # 単体テスト一式
    "e2e": None,  # E2E（実UI貫通）テスト一式
    "fmt": None,  # 整形（冪等）
    "check": [
        ["uv", "run", "scripts/check_structure.py"],
        ["uv", "run", "scripts/check_codex_hooks.py"],
    ],  # 構造・Codexフック検査
    "probe": [["uv", "run", "scripts/check_guard_corpus.py", "--probe", "{args}"]],
    # ↑ 迂回防止の事前照会（言語なしで即動く — §2。「試して exit 2」の1周を削る）
    #   `probe --live` は実ホスト経路の発火確認（§2・Phase 44——main で分岐）
    "db": None,  # ローカルDBへの読み取りクエリ（例: dev.py db "select count(*) from x"）
    "selftest": [
        ["uv", "run", "scripts/check_guard_corpus.py"],
        ["uv", "run", "scripts/check_ownership_guard.py"],
        ["uv", "run", "scripts/check_codex_hooks.py"],
        ["uv", "run", "scripts/check_fill_bindings.py"],
        ["uv", "run", "scripts/check_rule_dod.py"],
    ],
    # ↑ 門の違反注入コーパス一括（門のテスト — §2。言語なしで即動く・Phase 44）
    "dod": [["uv", "run", "scripts/check_rule_dod.py", "{args}"]],
    # ↑ 列の違反注入コーパス再生（規則DoDの機械化 — §11 Step 2・Phase 47。
    #   採用列のコーパス未同梱は未完了としてexit 1）
    "build": None,  # 全パッケージの型検査＋ビルド（plan.md Phase 0。CIのartifact生成と同じ経路）
}

# >>> GUARDRAILS BINDING >>>
# 採用列の充填は**この区画内**で行う（例: COMMANDS.update({"up": [["supabase", "start"]]})
# ——全置換 `COMMANDS = {...}` は既定配線（check/probe/selftest）を消すため禁止・加算形のみ）。
# インストーラの更新（UPGRADED）はこの区画の中身だけを既存から引き継ぐ（Phase 44）。
# BINDING-SOURCE: python-uv@10 + ts-react-web@12（値はモノレポ構成 — plan.md §2.2 —
# に合わせて手で調整済み。カタログの生の paste-block（supabase/psql等）は不採用——
# このプロジェクトはSupabaseを使わない。python-uv列とts-react-web列が同じ動詞キーを
# 定義するため、fill_bindings の機械充填のままだと後勝ちで前者が消える。verbごとに
# 複数コマンドを列挙できる COMMANDS の仕様（§12.1）を使い、両言語を1動詞へ束ねた）
COMMANDS.update(
    {
        "test": [
            ["uv", "run", "pytest", "-q"],
            ["pnpm", "--filter", "apps-admin", "run", "test"],
        ],
        "e2e": [["pnpm", "exec", "playwright", "test"]],
        "fmt": [
            ["uv", "run", "ruff", "format", "."],
            ["pnpm", "exec", "biome", "format", "--write", "."],
        ],
    }
)
# up/reset/seed/time/db: SQLiteはファイルベースで常駐サービスが無い（Phase 1でAlembic
# migrationsを導入した時点で reset を `uv run alembic upgrade head` 等へ配線する）。
# 現時点は「該当なし」のまま——静かな不発ではなく dev.py 側の明示エラーで可視化される。
# <<< GUARDRAILS BINDING <<<

VERB_HELP: dict[str, str] = {
    "up": "ローカル環境を起動する（冪等）",
    "reset": "環境を既知状態へ戻す（seed込み・決定性の供給 — §12.2）",
    "seed": "シードデータを投入する",
    "time": "アプリ内時刻を凍結/解除する（引数: ISO8601 または clear）",
    "test": "単体テストを実行する",
    "e2e": "E2Eテストを実行する（操作レール — §12.4）",
    "fmt": "コード整形を実行する（冪等）",
    "check": "構造検査を実行する（§3.3）",
    "probe": "コマンドが迂回防止（§2）に通るか事前照会する（引数: コマンド文字列1つ。--live で実ホスト経路の発火確認）",
    "db": "ローカルDBへ読み取りクエリを投げる（観察レール — §12.3）",
    "selftest": "門の違反注入コーパスを一括再生する（門のテスト — §2）",
    "dod": "列の違反注入コーパスを再生する（規則DoDの機械化 — Phase 47）",
    "doctor": "環境診断（ツール・シム・フック配線の集約表示 → check を実行）",
    "gates": "門と機能の全一覧を実状態つきで表示する（発見の導線 — §12.1）",
}


def _gates(root: Path) -> int:
    """門の台帳（rs.GATE_REGISTRY）を、このリポジトリでの実状態つきで表示する（Phase 45）。

    状態は実物から計算する（バインディング充填の有無・settings.json の配線）——
    手書きの機能一覧を持たないための機構。台帳と検査器コードの一致は
    check_structure の gates-registry-drift（hard）が別途機械検査する。
    """
    print(
        "[dev] gates: 門と機能の一覧（このリポジトリの実状態。契約の正本は "
        ".guardrails/GUARDRAILS.md の各節）"
    )
    settings_text = ""
    sp = root / ".claude" / "settings.json"
    if sp.is_file():
        settings_text = sp.read_text(encoding="utf-8", errors="replace")
    current = None
    for gid, cat, act, desc in rs.GATE_REGISTRY:
        if cat != current:
            print(f"\n  [{cat}]")
            current = cat
        if act == "always":
            status = "有効"
        elif act.startswith("var:"):
            status = (
                "有効（充填済み）"
                if getattr(rs, act[4:], None)
                else "未充填（列充填で有効化 — Step 0）"
            )
        elif act.startswith("vars:"):
            status = (
                "有効（充填済み）"
                if any(getattr(rs, n, None) for n in act[5:].split("|"))
                else "未充填（列充填で有効化 — Step 0）"
            )
        elif act.startswith("hook:"):
            status = "配線済み" if act[5:] in settings_text else "未配線（settings.json）"
        else:  # static:
            status = act.split(":", 1)[1]
        print(f"    {gid:<28} {status:<24} {desc}")
    print(
        "\n[dev] gates: 逃げ道・DoD・限界の詳細は各節。導入後のカスタム項目は "
        ".guardrails/CUSTOMIZE.md、保留（トリガー待ち）は §10 保留節"
    )
    return 0


def _doctor(root: Path) -> int:
    """環境診断の集約フロント（Phase 44）。既存検査の呼び出しと事実の表示に限定——
    新しい検査は作らない（重複実装の禁止 — §7.3。検査の正本は check の2スクリプト）。"""
    import platform

    print("[dev] doctor: 環境診断（事実の表示 → check 実行）")
    facts: list[tuple[str, str]] = [("python", platform.python_version())]
    for tool in ("uv", "git", "pre-commit"):
        facts.append((tool, shutil.which(tool) or "見つからない"))
    facts.append(
        (
            "core.hooksPath",
            rs.git_config_get(root, "core.hooksPath")
            or "(未設定=正常 — §3.3 hooks-path-overridden)",
        )
    )
    try:
        hooks_dir = rs.git_hooks_dir(root)
        shims = [n for n in ("pre-commit", "commit-msg", "pre-push") if (hooks_dir / n).exists()]
        facts.append(("pre-commit シム", ", ".join(shims) or "無し（Step 3 未実施 — §0）"))
    except rs.ScanError as exc:
        facts.append(("pre-commit シム", f"判定不能: {exc}"))
    settings = root / ".claude" / "settings.json"
    if settings.is_file():
        try:
            with open(settings, encoding="utf-8") as f:
                hooks = json.load(f).get("hooks", {})
            facts.append((".claude/settings.json hooks", ", ".join(sorted(hooks)) or "配線なし"))
        except ValueError, OSError:
            facts.append((".claude/settings.json hooks", "JSON 解釈不能"))
    else:
        facts.append((".claude/settings.json", "無し"))
    ledger = root / rs.VIOLATION_LEDGER_REL
    if ledger.is_file():
        with open(ledger, encoding="utf-8", errors="replace") as f:
            n = sum(1 for _ in f)
        facts.append(("違反ログ（§3.6）", f"{n} 行"))
    else:
        facts.append(("違反ログ（§3.6）", "無し（まだ違反が記録されていない）"))
    for key, value in facts:
        print(f"[dev] doctor: {key}: {value}")
    return main(["check"])


def _probe_live(root: Path) -> int:
    """実ホスト経路の発火確認（Phase 44 — agent-guard 型の sentinel。§2）。

    コーパス再生（同じ stdin 形式でフックを呼ぶ）が証明しないもの——「実セッションで
    ハーネスが本当に PreToolUse を発火させるか」——を、nonce 入り sentinel 違反の
    ブロックが違反ログ（§3.6）に記録されたことで機械確認する。2段階:
    1回目=発行（exit 1）→ エージェントが sentinel 実行（ブロックが正）→ 2回目=判定。
    """
    session_dir = root / ".claude" / "session"
    nonce_file = session_dir / "live_probe_nonce"
    ledger = root / rs.VIOLATION_LEDGER_REL
    if nonce_file.is_file():
        nonce = nonce_file.read_text(encoding="utf-8").strip()
        if ledger.is_file() and nonce in ledger.read_text(encoding="utf-8", errors="replace"):
            nonce_file.unlink()
            print(
                f"[dev] probe --live: PASS — sentinel（{nonce}）のブロックが違反ログに"
                "記録済み＝実ホスト経路でフックが発火している（§2・Step 4/8b DoD）"
            )
            return 0
        print(
            "[dev] probe --live: 未記録。エージェントの**セッション内**で次を実行してから"
            "再実行する（ブロックされるのが正）:",
            file=sys.stderr,
        )
        print(f'  git commit --no-verify --allow-empty -m "{nonce}"', file=sys.stderr)
        print(
            "  ※人間の端末では実行しない（フックが無いため空コミットが実際に作られる）",
            file=sys.stderr,
        )
        return 1
    nonce = f"GUARDRAILS-LIVE-PROBE-{uuid.uuid4().hex[:12]}"
    session_dir.mkdir(parents=True, exist_ok=True)
    with open(nonce_file, "w", encoding="utf-8", newline="\n") as f:
        f.write(nonce + "\n")
    print(
        "[dev] probe --live: sentinel を発行した。エージェントの**セッション内**で次を実行"
        "（PreToolUse がブロックするのが正——実コミットは作られない）:"
    )
    print(f'  git commit --no-verify --allow-empty -m "{nonce}"')
    print(
        "[dev] probe --live: 実行後にもう一度 `uv run scripts/dev.py probe --live` で判定"
        "（PASS が Step 4/8b の DoD — §2）。※人間の端末では実行しない"
    )
    return 1


def _splice(cmd: list[str], args: list[str]) -> list[str]:
    if ARGS_TOKEN in cmd:
        out: list[str] = []
        for part in cmd:
            if part == ARGS_TOKEN:
                out.extend(args)
            else:
                out.append(part)
        return out
    return cmd + args if args else cmd


def _print_verbs() -> None:
    print(
        "[dev] 動詞一覧（意味論は全プロジェクト共通・配線は bindings/catalog.md の採用列 — §12.1）"
    )
    for verb in COMMANDS:
        wired = "配線済み" if COMMANDS[verb] else "未配線"
        print(f"  {verb:<8} {wired:<4}  {VERB_HELP.get(verb, '')}")
    print(f"  {'doctor':<8} 内蔵    {VERB_HELP['doctor']}")
    print(f"  {'gates':<8} 内蔵    {VERB_HELP['gates']}")


def main(argv: list[str]) -> int:
    rs.reconfigure_stdio()
    if not argv or argv[0] in ("-h", "--help", "verbs"):
        _print_verbs()
        return 0
    verb, args = argv[0], argv[1:]
    if verb == "doctor":
        return _doctor(rs.repo_root())
    if verb == "gates":
        return _gates(rs.repo_root())
    if verb == "probe" and args == ["--live"]:
        return _probe_live(rs.repo_root())
    if verb not in COMMANDS:
        print(
            f"[dev] 不明な動詞: {verb!r}（`uv run scripts/dev.py verbs` で一覧 — §12.1）",
            file=sys.stderr,
        )
        return 2
    cmds = COMMANDS[verb]
    if not cmds:
        print(
            f"[dev] {verb}: 未配線 — bindings/catalog.md の採用列の値を "
            "scripts/dev.py の COMMANDS へ充填する（§12.1。静かな不発は禁止）",
            file=sys.stderr,
        )
        return 1
    root = rs.repo_root()
    for cmd in cmds:
        final = _splice(list(cmd), args)
        print(f"[dev] {verb}: {' '.join(final)}")
        # PATH 上のコマンド名は which で解決してから実行する（§7.2 の Windows 前提:
        # npx / prettier 等の .cmd/.bat ランチャーは shell=False の直呼びでは起動できず、
        # PATHEXT 込みで解決した実パスを渡す必要がある。未導入は明示エラー — fail-open 禁止）。
        if "/" not in final[0] and "\\" not in final[0]:
            resolved = shutil.which(final[0])
            if resolved is None:
                print(
                    f"[dev] {verb}: コマンドが見つからない: {final[0]!r}"
                    "（導入は README / 採用列の「前提ツール」欄。PATH を確認する）",
                    file=sys.stderr,
                )
                return 1
            final = [resolved, *final[1:]]
        started = time.monotonic()
        try:
            proc = subprocess.run(final, cwd=root)
        except OSError as exc:
            print(
                f"[dev] {verb}: 起動失敗 {exc}（コマンドの導入は README/採用列の前提ツール欄）",
                file=sys.stderr,
            )
            return 1
        elapsed = int((time.monotonic() - started) * 1000)
        print(f"[dev] {verb}: exit {proc.returncode} (+{elapsed}ms)")
        if proc.returncode != 0:
            return proc.returncode
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except rs.ScanError as exc:
        print(f"dev: 内部エラー: {exc}", file=sys.stderr)
        sys.exit(2)
    except KeyboardInterrupt:
        sys.exit(130)
    except BrokenPipeError:
        # 出力先が先に閉じた（`dev.py verbs | head` 等）。ツール自体のクラッシュ扱いにしない。
        import os

        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        sys.exit(0)
