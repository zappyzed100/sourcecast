# check_bootstrap.py — ブートストラップ監査: .guardrails/BOOTSTRAP.md の ✅ を再実行検証し、虚偽✅・順序違反を機械検出（契約: .guardrails/GUARDRAILS.md §3.5）
#
# 呼び出し（§7.1: 必ず uv 経由）: uv run scripts/check_bootstrap.py
#   exit 0 = 台帳と実体が整合 / exit 1 = 違反あり / exit 2 = 内部エラー
#   発火: pre-commit の files: ^\.guardrails/BOOTSTRAP\.md$（台帳に触れたコミット＝✅ 化の瞬間）
#         ＋ CI の --all-files（常時再監査——guard-corpus と同じ二重の網）。
#
# 何を機械化するか（§10 実行規律1〜4の門化 — v2.12・Phase 24）:
#   規律1（順序固定）    → ✅ の集合は先頭からの連続でなければならない（— は飛ばせる）
#   規律2（1Step=1コミット）→ 🚧→✅ のフリップは1コミットに1つだけ（HEAD との diff で判定）
#   規律3（完了=実行結果）→ ✅ の Step ごとに検証可能なアサーションを**その場で再実行**する
#   規律4（虚偽✅の禁止） → アサーションに落ちた ✅ は `bootstrap-false-done`＝🚧 に戻して再実装。
#                          ✅→🚧 の差し戻しは正規経路として許可・✅→— は禁止（証跡の消去）
#
# アサーションは「事後に再実行して検証できる形」に限る（§7.4 近似は仕様——例: Step 4 は
# コーパス全再生そのもの、Step 5 は形式違反メッセージの注入を毎回やり直す）。台帳が
# 全行 🚧 の出荷状態では何も検証せず沈黙で通る（進捗を強要する門ではない——進捗側の
# 規律はプロンプトと Stop ゲートが担う）。
# 出力: 1違反1行・規則ID付き（§3.3 と同形式）。性能: 台帳に触れたコミットのみ発火のため
# 重いアサーション（--check・コーパス再生）を許容（guard-corpus と同じ予算の整理 — §7.7）。

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import repo_scan as rs  # noqa: E402

LEDGER = ".guardrails/BOOTSTRAP.md"
STEP_ORDER = ["0", "1", "2", "3", "4", "5", "6", "7", "8", "8b", "9", "10"]
ROW_RE = re.compile(r"^\|\s*(0|1|2|3|4|5|6|7|8|8b|9|10)\s*\|[^|]*\|\s*(✅|🚧|—)\s*\|([^|]*)\|")
DONE, WIP, NA = "✅", "🚧", "—"
_TODO_WORD = "TO" + "DO"  # 自己検出を避ける連結（Step 10 の grep 対象語）


def _run(root: Path, args: list[str], timeout: int = 60) -> tuple[int, str]:
    proc = subprocess.run(args, cwd=root, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout)
    return proc.returncode, (proc.stdout + proc.stderr)


def parse_ledger(text: str) -> tuple[dict[str, tuple[str, str]], list[str] | None]:
    """台帳を (Step→(状態, 備考), 固有名詞リストC) に解析する。C 未確定（★）は None。"""
    rows: dict[str, tuple[str, str]] = {}
    for line in text.splitlines():
        m = ROW_RE.match(line.strip())
        if m:
            rows[m.group(1)] = (m.group(2), m.group(3).strip())
    nouns: list[str] | None = None
    m = re.search(r"固有名詞リストC.*?```\n(.*?)```", text, re.S)
    if m:
        entries = [ln.strip() for ln in m.group(1).splitlines() if ln.strip()]
        if entries and "★" not in entries:
            nouns = [] if entries == ["該当なし"] else entries
    return rows, nouns


def head_ledger(root: Path) -> str | None:
    try:
        proc = subprocess.run(["git", "show", f"HEAD:{LEDGER}"], cwd=root,
                              capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=30)
        return proc.stdout if proc.returncode == 0 else None
    except OSError:
        return None


# ---- Step 別アサーション: 失敗の説明文リストを返す（空=検証PASS） -------------------

def assert_step_0(root: Path, ctx: dict) -> list[str]:
    fails = []
    text = rs.read_text(root, "scripts/repo_scan.py") if "scripts/repo_scan.py" in ctx["tracked"] else ""
    if not rs.BINDING_SOURCE_PATTERN.search(text):
        fails.append("scripts/repo_scan.py に BINDING-SOURCE の刻印が無い（§12.7）")
    if ctx["nouns"] is None:
        fails.append("固有名詞リストCが未確定（★のまま/空欄。無いなら「該当なし」と書く）")
    return fails


def assert_step_1(root: Path, ctx: dict) -> list[str]:
    fails = []
    for name in ("AGENTS.md", "CLAUDE.md"):
        if name not in ctx["tracked"]:
            fails.append(f"{name} が未追跡")
            return fails
    agents = rs.read_text(root, "AGENTS.md")
    claude = rs.read_text(root, "CLAUDE.md")
    for i in list(range(14)):
        if not re.search(rf"^## §{i}(\s|$)", agents, re.M):
            fails.append(f"AGENTS.md に章見出し ## §{i} が無い（章の削除・統合は禁止 — §6）")
    if not re.search(r"^@AGENTS\.md\s*$", claude, re.M):
        fails.append("CLAUDE.md 冒頭の @AGENTS.md インポートが無い（§6）")
    for name, text in (("AGENTS.md", agents), ("CLAUDE.md", claude)):
        if "★" in text:
            fails.append(f"{name} に ★（未充填の雛形記号）が残っている")
        if re.search(rf"\b{_TODO_WORD}\b", text):
            fails.append(f"{name} に {_TODO_WORD} が残っている")
        for term in (ctx["nouns"] or []):
            if term in text:
                fails.append(f"{name} に移植元の固有名詞 {term!r} が残置（リストCの grep）")
    return fails


def assert_step_2(root: Path, ctx: dict) -> list[str]:
    missing = [p for p in ("scripts/generate_structure.py", "scripts/check_structure.py",
                           "scripts/dev.py") if p not in ctx["tracked"]]
    if missing:
        return [f"スクリプト未追跡: {' '.join(missing)}"]
    rc, out = _run(root, ["uv", "run", "scripts/generate_structure.py", "--check"])
    if rc != 0:
        first = next((ln for ln in out.splitlines() if ln.strip()), "")
        return [f"generate_structure --check が exit {rc}（索引の鮮度/決定性 — §3.2）: {first[:120]}"]
    return []


def assert_step_3(root: Path, ctx: dict) -> list[str]:
    cfg = rs.read_text(root, ".pre-commit-config.yaml") if ".pre-commit-config.yaml" in ctx["tracked"] else ""
    m = re.search(r"default_install_hook_types:\s*\[([^\]]*)\]", cfg)
    types = [t.strip() for t in (m.group(1).split(",") if m else []) if t.strip()]
    if not types:
        return ["default_install_hook_types が設定に無い（§7.6）"]
    try:
        proc = subprocess.run(["git", "rev-parse", "--git-path", "hooks"], cwd=root,
                              capture_output=True, text=True, timeout=30)
        hooks_dir = (root / proc.stdout.strip()).resolve()
    except OSError as exc:
        raise rs.ScanError(f"git rev-parse --git-path hooks が失敗: {exc}") from exc
    return [f"pre-commit のシム {t} が未インストール（`pre-commit install` — §11 Step 3）"
            for t in types if not (hooks_dir / t).is_file()]


def assert_step_4(root: Path, ctx: dict) -> list[str]:
    rc, out = _run(root, ["uv", "run", "scripts/check_guard_corpus.py"])
    if rc != 0:
        first = next((ln for ln in out.splitlines() if ln.strip()), "")
        return [f"guard コーパス再生が exit {rc}（門番の回帰が回らない状態で Step 4 は ✅ にできない — §2）: {first[:120]}"]
    return []


def assert_step_5(root: Path, ctx: dict) -> list[str]:
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False,
                                     encoding="utf-8") as f:
        f.write("サボり: 形式違反の件名\n")
        msg_path = f.name
    try:
        rc, _ = _run(root, ["uv", "run", "scripts/check_commit_msg.py", msg_path])
    finally:
        Path(msg_path).unlink(missing_ok=True)
    if rc != 1:
        return [f"形式違反メッセージの注入が exit {rc}（1 が期待値——検査1が効いていない §3.4）"]
    return []


def assert_step_6(root: Path, ctx: dict) -> list[str]:
    cfg = rs.read_text(root, ".pre-commit-config.yaml") if ".pre-commit-config.yaml" in ctx["tracked"] else ""
    live = [ln.split("#", 1)[0] for ln in cfg.splitlines()]
    if not any("stages:" in ln and "pre-push" in ln for ln in live):
        return ["pre-push 段のフックが1つも無い（テスト・静的解析の paste-block 未充填 — §4）"]
    return []


def assert_step_7(root: Path, ctx: dict) -> list[str]:
    fails = []
    if not rs.PRINT_CALL_PATTERNS:
        fails.append("PRINT_CALL_PATTERNS が未充填（log-direct-call が不発のまま — §8.2）")
    fails += [f"ログ単一出口 {p} が未追跡（LOG_EXIT_FILES と実体の不一致 — §8.2）"
              for p in rs.LOG_EXIT_FILES if p not in ctx["tracked"]]
    return fails


def assert_step_8(root: Path, ctx: dict) -> list[str]:
    if not rs.NONDETERMINISM_PATTERNS:
        return ["NONDETERMINISM_PATTERNS が未充填（test-nondeterminism が不発のまま — §9.2）"]
    return []


def assert_step_8b(root: Path, ctx: dict) -> list[str]:
    import dev  # 動詞表はモジュール定数（import に副作用なし — §12.1）
    if dev.COMMANDS.get("test") is None:
        return ["dev.py の test 動詞が未配線（ランタイム共通動詞の最低線 — §12.1）"]
    return []


_GITHUB_REMOTE_RE = re.compile(r"github\.com[:/]([^/\s]+)/([^/\s]+?)(?:\.git)?/?$")

# Step 9 ④ の強制最低線（v2.37——3コアジョブ）。red-first だけでは、ローカルフックが
# 動かない経路（Web 編集・フック未導入マシン——§5 が CI を最終防衛線とする理由そのもの）で
# checks / commit-msg-history の赤をマージから止められない。列固有のテスト/E2E ジョブは
# 名前が列依存のため最低線に含めない（required 化は推奨・§11 Step 9）。
REQUIRED_CHECK_CONTEXTS = ("checks", "red-first", "commit-msg-history")


def _gh_api(gh: str, root: Path, endpoint: str, jq: str) -> tuple[str, list[str]]:
    """gh api を1回呼ぶ。戻り値は (判定, 出力行)。判定 ∈ ok / absent(HTTP 404) / unverifiable。
    404 は「対象が無いことの確定回答」（例: 旧来ブランチ保護が未設定）で、照会不能
    （オフライン・未認証・権限不足）とは意味が違う——ここで区別しないと fail の向きを誤る。"""
    try:
        proc = subprocess.run([gh, "api", endpoint, "--jq", jq], cwd=root,
                              capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return "unverifiable", []
    if proc.returncode == 0:
        return "ok", [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]
    if "404" in proc.stderr:
        return "absent", []
    return "unverifiable", []


def verify_required_checks(root: Path) -> list[str]:
    """Step 9 ④ の外部設定（required checks への `red-first` 登録）を実測検証する（v2.35）。

    ローカルの門もリポジトリ内の CI 定義も、この設定だけは代替できない——required checks は
    リポジトリ設定側にしか存在せず（§5・Phase 21「required の完成はリポジトリ設定まで」）、
    従来の assert_step_9 はリポジトリ内のファイルしか見ないため、④ だけが監査の空白だった。

    fail の向きは2段:
    - **検証できて不在** → 失敗（✅ の主張と実体の不一致＝虚偽✅ — fail-closed）。
    - **検証そのものが不能**（GitHub 以外のリモート・gh 不在・オフライン・未認証・権限不足）
      → 表示して素通し（fail-open＋表示 — Stop ゲート §2b と同じ契約。検証不能の日に
      ブートストラップを止めない。CI の再監査は checks ジョブの GH_TOKEN で認証される）。
    照会はルールセット（/rules/branches——読み取り権限で可）と旧来ブランチ保護
    （admin 権限が要る——403 は照会不能・404 は「保護なし」の確定回答）の両系統を見る。
    """
    url = rs.git_config_get(root, "remote.origin.url") or ""
    m = _GITHUB_REMOTE_RE.search(url)
    if not m:
        print("[bootstrap] Step 9 ④: GitHub リモートが無いため required checks は検証対象外"
              "（ホスティング側の同等設定を手動確認 — §3.5）", file=sys.stderr)
        return []
    gh = shutil.which("gh")
    if gh is None:
        print("[bootstrap] Step 9 ④: gh CLI 不在のため required checks を検証できない"
              "（表示して素通し——gh を導入して再実行すれば検証が効く — §3.5）", file=sys.stderr)
        return []
    owner, repo = m.group(1), m.group(2)
    status, lines = _gh_api(gh, root, f"repos/{owner}/{repo}", ".default_branch")
    if status != "ok" or not lines:
        print("[bootstrap] Step 9 ④: GitHub API に到達できず required checks を検証できない"
              "（オフライン/未認証/権限不足——表示して素通し — §3.5）", file=sys.stderr)
        return []
    branch = lines[0]
    contexts: set[str] = set()
    st, ls = _gh_api(
        gh, root, f"repos/{owner}/{repo}/rules/branches/{branch}",
        '.[] | select(.type=="required_status_checks") | .parameters.required_status_checks[].context')
    rules_definitive = st == "ok"
    if rules_definitive:
        contexts |= set(ls)
    st2, ls2 = _gh_api(
        gh, root, f"repos/{owner}/{repo}/branches/{branch}/protection/required_status_checks",
        ".contexts[]")
    # 404 = 旧来保護が「無い」ことの確定回答（403/オフライン=照会不能とは意味が違う）
    classic_definitive = st2 in ("ok", "absent")
    if st2 == "ok":
        contexts |= set(ls2)
    # 最低線は3コアジョブ（v2.37）。「checks / commit-msg-history はローカルでも走るから
    # 重複」はローカルフックが動く経路にしか成立しない——CI を最終防衛線とする主張
    # （§5・README）の対象経路（Web 編集・フック未導入マシン）では、この2ジョブが唯一の
    # 強制点で、required でなければ赤のままマージできる。
    missing = [j for j in REQUIRED_CHECK_CONTEXTS if j not in contexts]
    if not missing:
        return []  # 各ジョブはどちらか一方の系統で確認できれば存在証明として十分
    if rules_definitive and classic_definitive:
        # 不在の断定は両系統の確定回答が揃った時だけ（v2.36 是正——片系統が照会不能のまま
        # 「検証できて不在」と誤断定すると、旧来保護だけに登録した採用先が CI で必ず偽赤になる:
        # CI の GITHUB_TOKEN は旧来保護の照会が常に 403＝admin 必須のため）
        listed = ", ".join(sorted(contexts)) if contexts else "なし"
        return [f"required checks にコアジョブが不足: {', '.join(missing)}"
                f"（{branch} の必須チェック実測: {listed}。リポジトリ設定で登録する——"
                "required の完成はリポジトリ設定まで — §5・§11 Step 9 ④）"]
    unchecked = [name for name, d in (("ルールセット", rules_definitive),
                                      ("旧来ブランチ保護", classic_definitive)) if not d]
    print(f"[bootstrap] Step 9 ④: {'・'.join(unchecked)}を照会できず、コアジョブ"
          f"（{', '.join(missing)}）の不在を断定できない（照会できた範囲には無い——表示して"
          "素通し。CI の GITHUB_TOKEN は旧来ブランチ保護を照会できない（admin 必須）ため、"
          "CI 再監査で確定判定を得るには rulesets 側で登録する — §3.5）", file=sys.stderr)
    return []


def assert_step_9(root: Path, ctx: dict) -> list[str]:
    ci = ".github/workflows/guardrails-ci.yml"
    text = rs.read_text(root, ci) if ci in ctx["tracked"] else ""
    jobs = set(re.findall(r"^  ([A-Za-z][\w-]*):\s*(?:#.*)?$", text, re.M))
    fails = []
    if not jobs - {"checks", "red-first"}:
        fails.append("CI に列のテスト/解析ジョブが無い（checks/red-first 以外ゼロ——近似判定 §7.4）")
    fails += verify_required_checks(root)  # ④ 外部設定の実測（v2.35）
    return fails


def run_verify_scenarios() -> int:
    """`--verify-scenarios`: verify_required_checks の回帰シナリオ再生（v2.36・§3.5）。

    ネットワークに一切出ない（gh api・which・remote 照会を全部モックする）——
    check_ownership_guard.py と同じ「門番自身の回帰」の型。発火は pre-commit の
    `files: ^scripts/check_bootstrap\\.py$`（本体に触れた時だけ）＋ CI の --all-files。
    シナリオ4は v2.36 で是正した偽陽性（rulesets 確定・空＋旧来保護 403 →
    誤って「検証できて不在」）の再発防止が目的。
    """
    RULES = "rules/branches"
    CLASSIC = "protection/required_status_checks"

    def fake_api(responses: dict[str, tuple[str, list[str]]]):
        def _fake(gh: str, root: Path, endpoint: str, jq: str) -> tuple[str, list[str]]:
            for key, resp in responses.items():
                if key in endpoint:
                    return resp
            return responses.get("", ("ok", ["main"]))  # 既定: default_branch 照会は成功
        return _fake

    ALL3 = list(REQUIRED_CHECK_CONTEXTS)
    # (名前, 期待fail件数, remote, gh有無, _gh_api の応答表)
    scenarios = [
        ("rulesetsのみに3コアジョブ登録（旧来保護は照会不能）", 0, "git@github.com:o/r.git", True,
         {RULES: ("ok", ALL3), CLASSIC: ("unverifiable", [])}),
        ("旧来保護のみに3コアジョブ登録（rulesets は照会不能）", 0, "git@github.com:o/r.git", True,
         {RULES: ("unverifiable", []), CLASSIC: ("ok", ALL3)}),
        ("両系統とも確定回答で全部不在 → 失敗", 1, "git@github.com:o/r.git", True,
         {RULES: ("ok", []), CLASSIC: ("absent", [])}),
        ("rulesets確定・空＋旧来保護は照会不能 → 断定せず素通し（v2.36 是正の回帰）", 0,
         "git@github.com:o/r.git", True,
         {RULES: ("ok", []), CLASSIC: ("unverifiable", [])}),
        ("両系統確定・red-first と checks のみ → 最低線3ジョブに不足で失敗（v2.37 の回帰）", 1,
         "git@github.com:o/r.git", True,
         {RULES: ("ok", []), CLASSIC: ("ok", ["red-first", "checks"])}),
        ("2系統に分かれて合計3コアジョブ（存在証明は系統横断の和集合）", 0,
         "git@github.com:o/r.git", True,
         {RULES: ("ok", ["red-first"]), CLASSIC: ("ok", ["checks", "commit-msg-history"])}),
        ("red-first のみ確認・旧来保護は照会不能 → 残り2つの不在を断定せず素通し", 0,
         "git@github.com:o/r.git", True,
         {RULES: ("ok", ["red-first"]), CLASSIC: ("unverifiable", [])}),
        ("gh 不在 → 表示して素通し", 0, "git@github.com:o/r.git", False, {}),
        ("GitHub 以外のリモート → 検証対象外", 0, "https://gitlab.com/o/r.git", True, {}),
        ("API 到達不能（default_branch 照会失敗）→ 表示して素通し", 0,
         "git@github.com:o/r.git", True, {"": ("unverifiable", [])}),
    ]

    this = sys.modules[__name__]
    orig = (this._gh_api, shutil.which, rs.git_config_get)
    mismatches = 0
    t0 = time.monotonic()
    try:
        for name, want, remote, has_gh, responses in scenarios:
            rs.git_config_get = lambda root, key, _u=remote: _u  # noqa: B023
            shutil.which = (lambda n: "gh") if has_gh else (lambda n: None)
            this._gh_api = fake_api(responses)
            got = len(verify_required_checks(Path(".")))
            if got != want:
                mismatches += 1
                print(f"HARD:step9-scenario-mismatch {name}: 期待fail {want} 件・実際 {got} 件"
                      "（§3.5——本体とシナリオ期待値を同一コミットで揃える）", file=sys.stderr)
    finally:
        this._gh_api, shutil.which, rs.git_config_get = orig
    if mismatches:
        print(f"\ncheck-bootstrap --verify-scenarios: 不一致 {mismatches} 件/{len(scenarios)} 本",
              file=sys.stderr)
        return 1
    print(f"[bootstrap] verify シナリオ 全{len(scenarios)}本 PASS "
          f"(+{int((time.monotonic() - t0) * 1000)}ms)")
    return 0


def assert_step_10(root: Path, ctx: dict) -> list[str]:
    fails = []
    todo_re = re.compile(rf"\b{_TODO_WORD}\b")
    for rel in ctx["tracked"]:
        ext = rs.ext_of(rel)
        if rel == "scripts/check_bootstrap.py" or rs.is_generated(rel):
            continue
        if ext in rs.CODE_EXTS or ext in rs.HEADER_REQUIRED_EXTS:
            if todo_re.search(rs.read_text(root, rel)):
                fails.append(f"{rel} に {_TODO_WORD} が残っている（総合監査 — §11 Step 10）")
    for name in ("AGENTS.md", "CLAUDE.md", "README.md"):
        if name in ctx["tracked"]:
            text = rs.read_text(root, name)
            fails += [f"{name} に固有名詞 {term!r} が残置（リストCの grep）"
                      for term in (ctx["nouns"] or []) if term in text]
    return fails


ASSERTS = {"0": assert_step_0, "1": assert_step_1, "2": assert_step_2,
           "3": assert_step_3, "4": assert_step_4, "5": assert_step_5,
           "6": assert_step_6, "7": assert_step_7, "8": assert_step_8,
           "8b": assert_step_8b, "9": assert_step_9, "10": assert_step_10}


def main() -> int:
    rs.reconfigure_stdio()
    t0 = time.monotonic()
    root = rs.repo_root()
    if not (root / LEDGER).is_file():
        print(f"check-bootstrap: {LEDGER} が無い（missing-required 側で検出される — §3.3）",
              file=sys.stderr)
        return 0
    rows, nouns = parse_ledger((root / LEDGER).read_text(encoding="utf-8"))
    violations: list[str] = []

    # ---- 台帳の書式（静的不変条件——毎回） ----
    for step in STEP_ORDER:
        if step not in rows:
            violations.append(f"HARD:bootstrap-ledger (Step {step}) 台帳に行が無い/書式が壊れている（行構造を崩さない — §3.5）")
    for step, (status, note) in rows.items():
        if status == NA and not note:
            violations.append(f"HARD:bootstrap-ledger (Step {step}) — には備考の理由が必須（黙って対象外にしない — §3.5）")

    # ---- 規律1: 順序（✅ は先頭からの連続。— は飛ばせる） ----
    for i, step in enumerate(STEP_ORDER):
        if rows.get(step, (WIP, ""))[0] == DONE:
            for prev in STEP_ORDER[:i]:
                if rows.get(prev, (WIP, ""))[0] == WIP:
                    violations.append(
                        f"HARD:bootstrap-order (Step {step}) が ✅ なのに先行 Step {prev} が 🚧"
                        "（順序は固定・飛ばすなら — に理由付きで — §10 実行規律1・§3.5）")

    # ---- 規律2・4: フリップ検査（HEAD の台帳と比較。HEAD 無し=初回は対象外） ----
    old_text = head_ledger(root)
    if old_text is not None:
        old_rows, _ = parse_ledger(old_text)
        flips = [s for s in STEP_ORDER
                 if rows.get(s, (WIP, ""))[0] == DONE and old_rows.get(s, (WIP, ""))[0] != DONE]
        if len(flips) > 1:
            violations.append(
                f"HARD:bootstrap-multi-flip Step {', '.join(flips)} を同一コミットで ✅ 化しようと"
                "している（1Step=1コミット——まとめての完了報告は監査不能 — §10 実行規律2・§3.5）")
        demoted = [s for s in STEP_ORDER
                   if old_rows.get(s, (WIP, ""))[0] == DONE and rows.get(s, (WIP, ""))[0] == NA]
        for s in demoted:
            violations.append(
                f"HARD:bootstrap-demote (Step {s}) ✅ を — に変更している（証跡の消去。"
                "やり直しは ✅→🚧 が正規経路 — §3.5）")

    # ---- 規律3・4: ✅ の再実行検証（虚偽 ✅ の検出） ----
    ctx = {"tracked": set(rs.list_tracked_files(root)), "nouns": nouns}
    audited = 0
    for step in STEP_ORDER:
        if rows.get(step, (WIP, ""))[0] != DONE:
            continue
        audited += 1
        for fail in ASSERTS[step](root, ctx):
            violations.append(
                f"HARD:bootstrap-false-done (Step {step}) {fail} → 状態を 🚧 に戻して"
                "再実装する（完了=実行結果・虚偽✅の禁止 — §10 実行規律3/4・§3.5）")

    for line in violations:
        print(line, file=sys.stderr)
    if violations:
        print(f"\ncheck-bootstrap: 違反 {len(violations)} 件（コミット停止）。"
              ".guardrails/GUARDRAILS.md §3.5 を参照。", file=sys.stderr)
        return 1
    done = sum(1 for s in rows.values() if s[0] == DONE)
    na = sum(1 for s in rows.values() if s[0] == NA)
    print(f"[bootstrap] 台帳OK: ✅ {done} / — {na} / 🚧 {len(rows) - done - na}"
          f"（✅ {audited} 件の再実行検証 PASS +{int((time.monotonic() - t0) * 1000)}ms）")
    return 0


if __name__ == "__main__":
    try:
        if "--verify-scenarios" in sys.argv[1:]:
            rs.reconfigure_stdio()
            sys.exit(run_verify_scenarios())
        sys.exit(main())
    except subprocess.TimeoutExpired as exc:
        print(f"check-bootstrap: 内部エラー: サブプロセスがタイムアウト: {exc.cmd}", file=sys.stderr)
        sys.exit(2)
    except rs.ScanError as exc:
        print(f"check-bootstrap: 内部エラー: {exc}", file=sys.stderr)
        sys.exit(2)
    except Exception as exc:  # 想定外も契約どおり exit 2 に倒す（§7.5）
        print(f"check-bootstrap: 内部エラー: {exc!r}", file=sys.stderr)
        sys.exit(2)
