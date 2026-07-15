# install_kit.py — キットの機械的配置（詳細は直下の docstring と README_SETUP.md §1）
"""install_kit.py — ガードレール・キットの機械的インストーラ（README_SETUP.md §1 / .guardrails/GUARDRAILS.md §11 前段）

役割: zip または展開フォルダで対象リポジトリのルートに置かれたキットを、既存ファイルを
**決して黙って上書きせずに**ルートへ展開する。判定は決定的（G1）、結果は1行1ファイルの
機械可読形式（G4）、衝突は CONFLICT として fail-closed に停止（G9）、成功時は zip・展開元を
既定で後片付けする（心得ではなく機械 — G7）。

使い方（対象リポジトリのルートで）:
    python3 <キット展開先>/scripts/install_kit.py [--dry-run] [--keep-source] [--skip 相対パス]...
zip のままなら先に:  python3 -m zipfile -e guardrails-kit-*.zip .guardrails-kit-src
（`python3` が無い環境では `py -3` / `uv run --no-project` で同じ引数のまま実行できる）

追加モード（v2.42 — Phase 44。いずれも書き込みをしない）:
    --detect   対象リポジトリのマニフェストから採用列の候補を提示（確定は Step 0 の人間/
               エージェント。残る質問の一覧も表示する — G12）。キット展開なしでも動く
    --diff     適用した場合の判定を全件表示＋差分行数を注記（更新前のプレビュー）
    --check    ドリフト検出: 全ファイルが OK/KEPT/SKIPPED なら exit 0、それ以外は exit 1
               （CI から「導入先が新版に追随しているか」を機械判定できる）

管理区画（v2.42 — Phase 44）: 充填先 Python 4ファイル（MANAGED_FILES）は
`# >>> GUARDRAILS BINDING >>>` 〜 `# <<< GUARDRAILS BINDING <<<` 区画を持ち、UPGRADED は
**区画の中身だけ既存を引き継いで**それ以外を新版にする（列充填の復元作業が消える）。
区画マーカーが無い旧版は CONFLICT で停止する（充填を黙って失わない — G9）。
YAML 系（.pre-commit-config.yaml / guardrails-ci.yml）は対象外——ユーザー統合が区画の
内側に入る構造のため（判断の記録は surveys/SURVEY_HARNESS_TOOLS.md §1）。

ファイルごとの判定（表示ステータス）:
    OK         既存とバイト同一（何もしない・冪等）
    INSTALLED  対象に無かったので新規コピー
    UPGRADED   キット系統（シグネチャ有）かつ git 追跡済み・クリーン → 新版で上書き
               （旧内容は git 履歴が安全網。未コミット変更があれば CONFLICT で停止）
    MERGED     .gitignore のみ: キット区画マーカーが無ければ区画ごと追記
    KEPT       マージ対象4ファイル: 内容が検証条項を満たすので既存を維持
    SKIPPED    --skip で明示された既存維持
    CONFLICT   上書きも自動統合もしない。理由と解消ヒントを添えて exit 1
規約: 依存は stdlib のみ・Windows 絶対規則（§7.2: encoding/newline 明示・シェル非経由）。
exit: 0=衝突なし（検証込み） / 1=CONFLICT または検証不合格 / 2=内部エラー（§7.5 と同義）。
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

# --- 配置対象から除外するメタファイル（インストーラの説明書。リポジトリへは入れない）---
META_FILES = {
    "README_SETUP.md",
    "PROMPT_claude_code.md",
    "PROMPT_claude_code_existing.md",
    ".guardrails-kit-source",  # キット原本判定マーカー（§3.3 kit-source-exempt）。導入先には複製しない
}


def is_meta(rel: str) -> bool:
    """メタ判定。zip 展開系のファイル名エンコーディング差で日本語名が化けても
    取りこぼさないよう、ルート直下の README*/PROMPT_* はプレフィックスでも除外する。
    surveys/ と docs/plans/ はキット自身の判断記録であり移植先には配置しない。
    gitignore 済みのローカルテレメトリ（違反ログ・セッション状態）は、zip 配布には
    元々含まれないが、**作業チェックアウトから直接インストールした場合に混入する**
    （Phase 44 の DoD で実測——rglob はファイルシステム走査のため）ので明示除外する。"""
    return rel in META_FILES or rel.startswith(("surveys/", "docs/plans/")) or (
        "/" not in rel and (rel.startswith("README") or rel.startswith("PROMPT_"))
    ) or rel == ".guardrails/violations.jsonl" or rel.startswith(
        (".claude/session/", ".codex/session/", ".claude/routines/.state/",
         ".claude/worktrees/", ".claude/checkpoints/", ".claude/mailbox/")
    ) or rel in {
        ".claude/scheduled_tasks.lock", ".claude/scheduled_tasks.json",
        ".claude/agent-registry.json", ".claude/agent-memory-local",
        ".claude/first-run", ".claude/assistant-daemon-state.json",
    }
# 作業チェックアウトから直接導入しても、言語ツールの生成キャッシュを配布しない。
# zip配布では通常含まれないため、直インストール経路でだけ混入する差をここで消す。
EXCLUDE_DIRS = {
    ".git", "__pycache__", ".ruff_cache", ".pytest_cache", ".mypy_cache",
    ".coverage", "htmlcov", ".venv", "node_modules", "target", "build", "dist",
}

# --- キット系統の判定シグネチャ（UPGRADED 可否。全キットファイルが最低1つ含む）---
KIT_SIGNATURES = ("GUARDRAILS", "guardrails", "BINDING", "guard_git_bypass")
# シグネチャ判定を使わず常に「既存優先の衝突」にするファイル（中身が短く系統判定不能）
FOREIGN_ALWAYS = {".python-version"}
# 自動追記・内容検証つきでマージするファイル（バイト一致を要求しない）
GITIGNORE = ".gitignore"
GITATTRIBUTES = ".gitattributes"
PRECOMMIT = ".pre-commit-config.yaml"
SETTINGS = ".claude/settings.json"
CODEX_HOOKS = ".codex/hooks.json"
GITIGNORE_BEGIN = "# >>> guardrails-kit >>>"
# 旧版キットの痕跡（新パスへ移行済み。存在すれば NOTE で削除を促す——ブロックはしない）
LEGACY_PATHS = [".github/workflows/ci.yml"]

# --- 管理区画（Phase 44・v2.42）: 充填を保持したまま UPGRADED するファイル ---
MANAGED_BEGIN = "# >>> GUARDRAILS BINDING >>>"
MANAGED_END = "# <<< GUARDRAILS BINDING <<<"
MANAGED_FILES = {
    "scripts/repo_scan.py",
    "scripts/dev.py",
    ".claude/hooks/post_edit_format.py",
    ".claude/hooks/post_edit_lint.py",
    ".pre-commit-config.yaml",
    ".github/workflows/guardrails-ci.yml",
}


def managed_inner(text: str) -> tuple[int, int] | None:
    """区画の中身の [開始, 終了) を返す。マーカーが無い・複数・順序不正なら None。"""
    if text.count(MANAGED_BEGIN) != 1 or text.count(MANAGED_END) != 1:
        return None
    b = text.find(MANAGED_BEGIN)
    e = text.find(MANAGED_END)
    if e < b:
        return None
    nl = text.find("\n", b)
    start = nl + 1 if nl != -1 else len(text)
    return (start, e) if start <= e else None


def named_managed_inner(text: str, name: str) -> tuple[int, int] | None:
    """YAML等の複数貼り先用に、名前付き管理区画の内側を返す。"""
    begin = f"# >>> GUARDRAILS BINDING: {name} >>>"
    end = f"# <<< GUARDRAILS BINDING: {name} <<<"
    if text.count(begin) != 1 or text.count(end) != 1:
        return None
    b, e = text.find(begin), text.find(end)
    if e < b:
        return None
    nl = text.find("\n", b)
    start = nl + 1 if nl != -1 else len(text)
    return (start, e) if start <= e else None


def splice_managed(src_text: str, dst_text: str) -> str | None:
    """新版 src の区画の中身を、既存 dst の区画の中身で置き換えた全文を返す。"""
    names = re.findall(r"# >>> GUARDRAILS BINDING: ([A-Za-z0-9_.-]+) >>>", src_text)
    if names:
        result = src_text
        for name in names:
            s = named_managed_inner(result, name)
            d = named_managed_inner(dst_text, name)
            if s is None or d is None:
                return None
            result = result[:s[0]] + dst_text[d[0]:d[1]] + result[s[1]:]
    else:
        s = managed_inner(src_text)
        d = managed_inner(dst_text)
        if s is None or d is None:
            return None
        result = src_text[:s[0]] + dst_text[d[0]:d[1]] + src_text[s[1]:]
    # YAML の刻印は区画外のヘッダーにある。既存の実IDを新版プレースホルダへ戻さない。
    stamp = re.search(r"BINDING-SOURCE:\s*([A-Za-z0-9][A-Za-z0-9_.-]*@[0-9]+)", dst_text)
    if stamp:
        result = re.sub(r"BINDING-SOURCE:\s*<[^\n]*", f"BINDING-SOURCE: {stamp.group(1)}", result, count=1)
    return result


def diff_stat(old: str, new: str) -> str:
    adds = dels = 0
    for ln in difflib.unified_diff(old.splitlines(), new.splitlines(), lineterm=""):
        if ln.startswith("+") and not ln.startswith("+++"):
            adds += 1
        elif ln.startswith("-") and not ln.startswith("---"):
            dels += 1
    return f"+{adds}/-{dels}行"


# --- 採用列の自動検出（--detect — Phase 44・v2.42）---
# 判定はマニフェストの存在（＋根拠の補足）。**提示のみ**で確定しない——確定・刻印は
# Step 0（bindings/catalog.md の列を人間/エージェントが選ぶ）。ここに列を足したら
# カタログの列と名前を一致させること。
STEP0_REMAINING = [
    "レイヤー一覧と依存方向（表B）",
    "ログ単一出口の置き場所（表A — §8.2）",
    "確率的コンポーネントの有無（表B — §9.1）",
    "独立オラクルの有無（表B — §9.6）",
    "中核不変条件と強制層（表D — §12.6）",
]


def detect(target: Path) -> int:
    found: list[tuple[str, str]] = []  # (列名, 根拠)
    pj = target / "package.json"
    if pj.is_file():
        ev = ["package.json"]
        try:
            deps = json.loads(read_text(pj))
            all_deps = {**deps.get("dependencies", {}), **deps.get("devDependencies", {})}
            if "react" in all_deps:
                ev.append("react 依存")
            if "vite" in all_deps or list(target.glob("vite.config.*")):
                ev.append("vite")
        except (json.JSONDecodeError, OSError):
            ev.append("(parse不能——中身は Step 0 で確認)")
        found.append(("ts-react-web", "・".join(ev)))
    if (target / "pyproject.toml").is_file():
        found.append(("python-uv", "pyproject.toml"))
    if (target / "Cargo.toml").is_file() or list(target.glob("*/Cargo.toml")):
        found.append(("rust", "Cargo.toml"))
    if (target / "pubspec.yaml").is_file() or list(target.glob("*/pubspec.yaml")):
        found.append(("dart-flutter", "pubspec.yaml"))
    for col, ev in found:
        print(f"DETECT {col} 根拠: {ev}")
    if not found:
        print("DETECT:none 既知列のマニフェストに一致なし——bindings/catalog.md で新列を起こす"
              "（.guardrails/GUARDRAILS.md §11 Step 0）")
    print("\n確定は Step 0（候補の採否と版の選択・BINDING-SOURCE 刻印）。"
          "機械で導出できない残りの質問:")
    for q in STEP0_REMAINING:
        print(f"  - {q}")
    return 0

# .pre-commit-config.yaml が満たすべき検証条項（統合後の必須トークン — §3・§7.6）。
# **キットのローカルフックを増やしたら同一コミットでここへ id を足す**——漏れると導入済み
# リポジトリの更新時、旧設定が KEPT 判定のまま新フックが静かに届かない（fail-open — G9）。
# 漏れ自体はキット原本の `installer-token-drift`（check-structure・hard）が機械検出する（§3.3）。
PRECOMMIT_REQUIRED = [
    "gitleaks", "generate-structure", "check-structure", "check-commit-msg",
    "guard-corpus", "rule-dod", "fill-bindings-corpus", "ownership-guard", "codex-hooks", "check-bootstrap",
    "bootstrap-verify-scenarios", "default_stages",
]


def read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")


def kit_lines(p: Path) -> list[str]:
    """コメント・空行を除いた実効行（.gitignore / .gitattributes の検証条項）。"""
    return [
        ln.strip() for ln in read_text(p).splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]


def lines_present(kit_file: Path, target_file: Path) -> bool:
    have = {ln.strip() for ln in read_text(target_file).splitlines()}
    return all(ln in have for ln in kit_lines(kit_file))


def precommit_ok(target_file: Path) -> bool:
    text = read_text(target_file)
    return all(tok in text for tok in PRECOMMIT_REQUIRED)


def settings_ok(kit_file: Path, target_file: Path) -> bool:
    try:
        kit = json.loads(read_text(kit_file))
        tgt = json.loads(read_text(target_file))
    except (json.JSONDecodeError, OSError):
        return False
    kit_deny = kit.get("permissions", {}).get("deny", [])
    tgt_deny = tgt.get("permissions", {}).get("deny", [])
    if not all(d in tgt_deny for d in kit_deny):
        return False
    dump = json.dumps(tgt)
    return ("guard_git_bypass.py" in dump and "post_edit_format.py" in dump
            and "post_edit_lint.py" in dump and "stop_incomplete_guard.py" in dump
            and "session_baseline.py" in dump and "guard_human_wip.py" in dump)


def codex_hooks_ok(kit_file: Path, target_file: Path) -> bool:
    try:
        kit = json.loads(read_text(kit_file))
        tgt = json.loads(read_text(target_file))
    except (json.JSONDecodeError, OSError):
        return False
    required_events = {"PreToolUse", "PostToolUse", "SessionStart", "Stop"}
    hooks = tgt.get("hooks", {})
    if not required_events <= set(hooks):
        return False
    dump = json.dumps(tgt)
    return ("codex_hook_adapter.py" in dump and "commandWindows" in dump
            and "apply_patch" in dump and "CLAUDE_PROJECT_DIR" not in dump
            and kit.get("hooks", {}).keys() <= hooks.keys())


def git(target: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=str(target), capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )


def git_tracked_clean(target: Path, rel: str) -> tuple[bool, bool]:
    """(追跡済みか, 追跡済みかつ作業ツリーがクリーンか)。.git が無ければ (False, False)。"""
    if not (target / ".git").exists():
        return (False, False)
    tracked = git(target, "ls-files", "--error-unmatch", "--", rel).returncode == 0
    if not tracked:
        return (False, False)
    dirty = git(target, "status", "--porcelain", "--", rel).stdout.strip() != ""
    return (True, not dirty)


def copy_file(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)  # バイトコピー（LF を書き換えない — §7.2）
    if dst.suffix == ".sh":
        try:
            dst.chmod(dst.stat().st_mode | 0o755)
        except OSError:
            pass  # Windows では意味を持たない（フックは `bash <path>` 起動なので必須ではない）


def append_gitignore_block(kit_file: Path, target_file: Path) -> None:
    block = kit_file.read_bytes()
    cur = target_file.read_bytes()
    sep = b"" if cur.endswith(b"\n") or not cur else b"\n"
    target_file.write_bytes(cur + sep + b"\n" + block if cur else block)


CONFLICT_HINTS = {
    PRECOMMIT: "既存設定へキットの repos/hooks を統合する（必須トークン: "
               + " / ".join(PRECOMMIT_REQUIRED) + "。統合後の再実行で KEPT になる）",
    SETTINGS: "permissions.deny の全エントリと PreToolUse（Bash・Edit|Write|MultiEdit）/"
              "PostToolUse/Stop/SessionStart のフック配線（スクリプト6本。PostToolUse は"
              "整形→lint の直列1コマンド — §1）を既存 JSON へ"
              "マージする（既存エントリは消さない — 既存導入プロンプトの Step 4）",
    CODEX_HOOKS: "Codex の hooks.json へ PreToolUse/PostToolUse/SessionStart/Stop を統合する"
                 "（Codex は apply_patch を編集として送るため、codex_hook_adapter.py・commandWindows"
                 "・Gitルート基準のコマンドを残す。既存フックは消さない）",
    GITATTRIBUTES: "キットの実効行（LF 固定）を既存へ追記する。gitattributes は後勝ちのため"
                   "既存の binary 指定等より上に `* text=auto eol=lf` を置く",
    GITIGNORE: "キット区画（>>> guardrails-kit >>> 〜 <<<）の中身が実効行ごと存在するよう"
               "統合する",
    ".python-version": "キットは 3.12 を想定（§7.1）。既存の版でスクリプト群が動くなら "
                       "--skip .python-version で既存維持を明示してよい",
}
DEFAULT_HINT_FOREIGN = "キット系統ではない同名ファイル。内容を確認し、手動で統合するか、退避後に再実行する"
DEFAULT_HINT_DIRTY = "未コミットの変更がある。コミット（または退避）してから再実行すると git 履歴を安全網に UPGRADED で置換できる"
DEFAULT_HINT_NOGIT = "git リポジトリではないため履歴の安全網が無い。`git init` と既存分のコミット後に再実行する"


def main() -> int:
    # §7.2: cp932 コンソール/パイプへの日本語出力で UnicodeEncodeError → exit 2 に化ける
    # のを防ぐ（Windows で `install_kit.py | grep` 等に流した瞬間クラッシュする実測）
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description="ガードレール・キットの機械的インストーラ")
    ap.add_argument("--dry-run", action="store_true", help="書き込み・削除をせず判定のみ表示")
    ap.add_argument("--keep-source", action="store_true", help="成功時も zip・展開元を削除しない")
    ap.add_argument("--skip", action="append", default=[], metavar="RELPATH",
                    help="既存維持を明示するパス（繰り返し可。検証条項の対象は検証だけ行う）")
    ap.add_argument("--detect", action="store_true",
                    help="採用列の候補をマニフェストから提示（書き込みなし・キット展開不要）")
    ap.add_argument("--diff", action="store_true",
                    help="適用した場合の判定＋差分行数を表示（書き込みなし）")
    ap.add_argument("--check", action="store_true",
                    help="ドリフト検出: 全て OK/KEPT/SKIPPED なら 0、他は 1（書き込みなし）")
    args = ap.parse_args()

    if sum((args.detect, args.diff, args.check)) > 1:
        print("INTERNAL --detect / --diff / --check は同時指定できない")
        return 2
    if args.detect:
        return detect(Path.cwd().resolve())
    dry = args.dry_run or args.diff or args.check

    kit_root = Path(__file__).resolve().parents[1]
    target = Path.cwd().resolve()
    if not (kit_root / ".guardrails/GUARDRAILS.md").is_file():
        print(f"INTERNAL キットの形をしていない: {kit_root}（.guardrails/GUARDRAILS.md が無い）")
        return 2
    if kit_root == target:
        print("INTERNAL 対象リポジトリのルートで実行する（キット展開先の中ではなく）。"
              "例: cd <リポジトリルート> && python3 .guardrails-kit-src/scripts/install_kit.py")
        return 2

    # --- マニフェスト = キット内の全ファイル − メタ ---
    manifest: list[str] = []
    for p in sorted(kit_root.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(kit_root).as_posix()
        if is_meta(rel) or any(part in EXCLUDE_DIRS for part in p.parts):
            continue
        manifest.append(rel)

    skips = set(args.skip)
    unknown_skips = sorted(skips - set(manifest))
    if unknown_skips:
        for s in unknown_skips:
            print(f"CONFLICT:unknown-skip {s} --skip の対象がキットのマニフェストに無い")
        print(f"\ninstall_kit: --skip の指定誤り {len(unknown_skips)} 件"
              "（何も行っていない。パスはマニフェストの相対パスで指定する）")
        return 1

    results: list[tuple[str, str, str]] = []  # (status, rel, note)
    conflicts = False

    for rel in manifest:
        src = kit_root / rel
        dst = target / rel
        if rel in skips:
            results.append(("SKIPPED", rel, "指定により既存を維持"))
            continue
        if not dst.exists():
            if not dry:
                copy_file(src, dst)
            results.append(("INSTALLED", rel, ""))
            continue
        if dst.is_dir():
            results.append(("CONFLICT:is-dir", rel, "同名ディレクトリが存在する"))
            conflicts = True
            continue
        if src.read_bytes() == dst.read_bytes():
            results.append(("OK", rel, "既存と同一"))
            continue

        # --- 差分あり: 管理区画ファイルは区画スプライスで充填を保持（Phase 44）---
        if rel in MANAGED_FILES:
            src_text, dst_text = read_text(src), read_text(dst)
            spliced = splice_managed(src_text, dst_text)
            if spliced is None:
                results.append(("CONFLICT:unmarked-binding", rel,
                                "管理区画マーカー（" + MANAGED_BEGIN + " 〜 END）が無いか壊れて"
                                "いる。既存の充填部分を区画マーカーで包んでから再実行する"
                                "（旧版からの移行——充填の黙失を防ぐための停止）"))
                conflicts = True
                continue
            if spliced == dst_text:
                results.append(("OK", rel, "区画外は新版と同一（差分は充填のみ）"))
                continue
            note_diff = f"（区画外の更新 {diff_stat(dst_text, spliced)}）" if args.diff else ""
            tracked, clean = git_tracked_clean(target, rel)
            if not (target / ".git").exists():
                results.append(("CONFLICT:no-git", rel, DEFAULT_HINT_NOGIT))
                conflicts = True
            elif tracked and clean:
                if not dry:
                    with open(dst, "w", encoding="utf-8", newline="\n") as f:
                        f.write(spliced)
                results.append(("UPGRADED", rel, "BINDING 区画の充填を保持して更新" + note_diff))
            else:
                results.append(("CONFLICT:uncommitted", rel, DEFAULT_HINT_DIRTY))
                conflicts = True
            continue

        # --- 差分あり: マージ対象4ファイルは検証条項ベース ---
        if rel == GITIGNORE:
            if lines_present(src, dst):
                results.append(("KEPT", rel, "実効行を包含済み"))
            elif GITIGNORE_BEGIN not in read_text(dst):
                if not dry:
                    append_gitignore_block(src, dst)
                results.append(("MERGED", rel, "キット区画を追記"))
            else:
                results.append(("CONFLICT:block-drift", rel, CONFLICT_HINTS[GITIGNORE]))
                conflicts = True
            continue
        if rel == GITATTRIBUTES:
            if lines_present(src, dst):
                results.append(("KEPT", rel, "実効行を包含済み"))
            else:
                results.append(("CONFLICT:merge-needed", rel, CONFLICT_HINTS[GITATTRIBUTES]))
                conflicts = True
            continue
        if rel == PRECOMMIT:
            if precommit_ok(dst):
                results.append(("KEPT", rel, "検証条項を満たす既存設定"))
            else:
                results.append(("CONFLICT:merge-needed", rel, CONFLICT_HINTS[PRECOMMIT]))
                conflicts = True
            continue
        if rel == SETTINGS:
            if settings_ok(src, dst):
                results.append(("KEPT", rel, "deny・フック配線を包含済み"))
            else:
                results.append(("CONFLICT:merge-needed", rel, CONFLICT_HINTS[SETTINGS]))
                conflicts = True
            continue
        if rel == CODEX_HOOKS:
            if codex_hooks_ok(src, dst):
                results.append(("KEPT", rel, "Codex フック配線を包含済み"))
            else:
                results.append(("CONFLICT:merge-needed", rel, CONFLICT_HINTS[CODEX_HOOKS]))
                conflicts = True
            continue

        # --- 差分あり: 正本・スクリプト等（バイト管理）---
        if rel in FOREIGN_ALWAYS or not any(s in read_text(dst) for s in KIT_SIGNATURES):
            hint = CONFLICT_HINTS.get(rel, DEFAULT_HINT_FOREIGN)
            results.append(("CONFLICT:foreign", rel, hint))
            conflicts = True
            continue
        tracked, clean = git_tracked_clean(target, rel)
        if not (target / ".git").exists():
            results.append(("CONFLICT:no-git", rel, DEFAULT_HINT_NOGIT))
            conflicts = True
        elif tracked and clean:
            if not dry:
                copy_file(src, dst)
            note = "旧内容は git 履歴に保存済み"
            if args.diff:
                note += f"（{diff_stat(read_text(dst), read_text(src))}）"
            results.append(("UPGRADED", rel, note))
        else:
            results.append(("CONFLICT:uncommitted", rel, DEFAULT_HINT_DIRTY))
            conflicts = True

    # --- 旧版パスの痕跡（非ブロック）---
    for rel in LEGACY_PATHS:
        p = target / rel
        if p.is_file() and any(s in read_text(p) for s in KIT_SIGNATURES):
            results.append(("NOTE:legacy", rel,
                            "旧キットの配置先。guardrails-ci.yml へ移行済みのため削除を推奨"))

    # --- 検証（配置直後の必達条件。--skip でも免除しない）---
    verify_fail = False
    for rel in manifest:
        if not (target / rel).exists() and not dry:
            results.append(("VERIFY-FAIL:missing", rel, "配置後に存在しない"))
            verify_fail = True
    checks = [
        (GITIGNORE, lambda: lines_present(kit_root / GITIGNORE, target / GITIGNORE)),
        (GITATTRIBUTES, lambda: lines_present(kit_root / GITATTRIBUTES, target / GITATTRIBUTES)),
        (PRECOMMIT, lambda: precommit_ok(target / PRECOMMIT)),
        (SETTINGS, lambda: settings_ok(kit_root / SETTINGS, target / SETTINGS)),
        (CODEX_HOOKS, lambda: codex_hooks_ok(kit_root / CODEX_HOOKS, target / CODEX_HOOKS)),
    ]
    if not dry:
        conflicted = {r for s, r, _ in results if s.startswith("CONFLICT")}
        for rel, fn in checks:
            if rel in conflicted:  # 同一ファイルへの二重報告を避ける（1違反1行 — G4）
                continue
            if (target / rel).exists() and not fn():
                results.append(("VERIFY-FAIL:content", rel, "検証条項を満たしていない"))
                verify_fail = True

    for status, rel, note in results:
        print(f"{status} {rel}" + (f" {note}" if note else ""))

    # --- --check: ドリフト判定だけ返す（書き込みなし・CI 用の exit 契約）---
    if args.check:
        drift = [r for s, r, _ in results
                 if s.split(":")[0] not in ("OK", "KEPT", "SKIPPED") and not s.startswith("NOTE")]
        print(f"\ninstall_kit --check: ドリフト {len(drift)} 件"
              + ("（OK/KEPT/SKIPPED 以外＝新版と食い違う）" if drift else "（新版に追随済み）"))
        return 1 if drift else 0

    failed = conflicts or verify_fail
    n = {"c": sum(r[0].startswith("CONFLICT") for r in results),
         "v": sum(r[0].startswith("VERIFY-FAIL") for r in results)}
    if failed:
        print(f"\ninstall_kit: CONFLICT {n['c']} 件 / VERIFY-FAIL {n['v']} 件（何も削除していない。"
              "各行のヒントに従って解消し、再実行する — 再実行は冪等）")
        return 1
    if args.diff:
        print("\ninstall_kit --diff: 適用可能（衝突 0）。書き込みは行っていない——"
              "適用はフラグなしで再実行する")
        return 0

    # --- 後片付け（既定で有効。心得ではなく機械 — G7）---
    removed: list[str] = []
    if not args.keep_source and not dry:
        for z in sorted(target.glob("guardrails-kit*.zip")):
            z.unlink()
            removed.append(z.name)
        # 後片付け対象は「target 直下で kit_root を含む最初の階層」——GitHub の
        # Download ZIP / Release zip は `<repo>-<ref>/` で1階層ネストされる
        # （.guardrails-kit-src/guardrails-kit-master/ 等）ため、kit_root.parent と
        # target の直接一致だけでは判定できない（不一致で沈黙してしまう＝G9 違反）。
        try:
            top_component = kit_root.relative_to(target).parts[0]
        except ValueError:
            top_component = None
        if top_component and re.match(r"^\.?guardrails-kit", top_component):
            shutil.rmtree(target / top_component)
            removed.append(top_component + "/")
        elif top_component:
            print(f"NOTE:source-kept {top_component}/ 既定外の名前のため削除しない"
                  "（不要なら手動で削除）")
        else:
            print(f"NOTE:source-kept {kit_root} は対象直下の外にあるため削除しない"
                  "（不要なら手動で削除）")
    for name in removed:
        print(f"CLEANUP {name} を削除")

    print("\ninstall_kit: 完了（衝突 0・検証合格）。次: .guardrails/GUARDRAILS.md §11 の Step 0 へ"
          "（.claude/settings.json を今回配置した場合は、先に /hooks でフック有効化の承認を）。"
          " ブートストラップ完了後にカスタムできる項目は .guardrails/CUSTOMIZE.md を参照。")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # 内部エラーは exit 2（検査の失敗と区別 — §7.5）
        print(f"INTERNAL {type(e).__name__}: {e}")
        sys.exit(2)
