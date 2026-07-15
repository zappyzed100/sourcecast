# install_workbench.py — workbench(UIスキル一式+特別対応の充填)を kit 導入済みリポジトリへ機械適用する
"""install_workbench.py — guardrails-workbench の機械的インストーラ(README「導入方法」ケース1/2/4)。

役割: guardrails-kit 導入済みの対象リポジトリへ、workbench の上乗せ分を差分適用する:
  1. `.claude/skills/`(ui-ux-pro-max ベンダーコピー)・`.upstream/sources.yaml`・
     `scripts/setup-upstreams.ps1`・`.github/workflows/update-ui-skills.yml`・
     `.github/dependabot.yml` のコピー(既存と差異があれば CONFLICT で停止——黙って上書きしない)
  2. CLAUDE.md への UI スキル節の追記(無ければ新規作成・追記済みなら何もしない)
  3. upstream submodule 2つ(guardrails-kit / emilkowalski-skills + sparse-checkout)の追加
  4. 特別対応3点を管理区画(>>> GUARDRAILS BINDING >>>)へ充填
     (GENERATED_PATTERNS 2行 → scripts/repo_scan.py / design 動詞 → scripts/dev.py)

使い方(対象リポジトリのルートで):
    uv run --no-project <workbenchクローン>/scripts/install_workbench.py [--dry-run]
workbench 自身のクローン内で実行してもよい(コピーは全て OK になり、充填だけが行われる)。

前提: 対象に kit が導入済み(scripts/repo_scan.py・scripts/dev.py に管理区画があること)。
無ければ exit 1 で停止する——その場合は README のケース1/2(kit のプロンプト)を先に。
kit の版揃えは不要: 充填は管理区画がある全ての版で成立し、版上げ(ケース3)とは独立。

出力は1行1操作(OK/INSTALLED/MERGED/ADDED/FILLED/SKIPPED/CONFLICT)。
exit: 0=衝突なし / 1=CONFLICT または前提不成立 / 2=内部エラー。
Windows 絶対規則: encoding/newline 明示・シェル非経由(guardrails-kit GUARDRAILS §7.2 と同じ)。
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

WB_ROOT = Path(__file__).resolve().parent.parent

# --- コピー対象(workbench 相対パス。ツリーは配下全ファイル) ---
COPY_TREES = [".claude/skills"]
COPY_FILES = [
    ".upstream/sources.yaml",
    "scripts/setup-upstreams.ps1",
    ".github/workflows/update-ui-skills.yml",
    ".github/dependabot.yml",
]

# --- submodule(scripts/setup-upstreams.ps1・.upstream/sources.yaml と同期を保つ) ---
SUBMODULES = [
    ("upstream/guardrails-kit", "https://github.com/zappyzed100/guardrails-kit.git", "master", None),
    ("upstream/ui-skills/emilkowalski-skills", "https://github.com/emilkowalski/skills.git", "main", [
        "/LICENSE", "/README.md",
        "skills/animation-vocabulary/", "skills/apple-design/", "skills/emil-design-eng/",
        "skills/improve-animations/", "skills/review-animations/",
    ]),
]

# --- CLAUDE.md へ追記する UI スキル節(見出しが冪等判定のマーカー) ---
CLAUDE_SECTION_MARKER = "## UI スキル"

# --- 管理区画への充填(冪等判定は needle の有無) ---
BINDING_OPEN = "# >>> GUARDRAILS BINDING >>>"
BINDING_CLOSE = "# <<< GUARDRAILS BINDING <<<"
FILLS = [
    ("scripts/repo_scan.py", r"^\.claude/skills/",
     '# workbench: ベンダー領域と design-system 生成物の除外(正本: workbench CLAUDE.md)\n'
     'GENERATED_PATTERNS += [re.compile(r"^\\.claude/skills/"), re.compile(r"^design-system/")]'),
    ("scripts/dev.py", '"design"',
     '# workbench: ui-ux-pro-max 検索を uv 経由の動詞にする(正本: workbench CLAUDE.md)\n'
     'COMMANDS.update({\n'
     '    "design": [["uv", "run", "python",\n'
     '                ".claude/skills/ui-ux-pro-max/scripts/search.py", "{args}"]],\n'
     '})'),
]


def read_bytes(p: Path) -> bytes:
    return p.read_bytes()


def read_raw(p: Path) -> str:
    """改行変換なしで読む(read_text の newline= は 3.13+ のため open を使う)。"""
    with p.open(encoding="utf-8", newline="") as f:
        return f.read()


def newline_of(text: str) -> str:
    return "\r\n" if "\r\n" in text else "\n"


def run_git(target: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(target), *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace")


def copy_one(rel: str, target: Path, dry: bool, out: list[str]) -> None:
    src = WB_ROOT / rel
    dst = target / rel
    if not src.exists():
        out.append(f"CONFLICT {rel} workbench 側に存在しない(クローンが不完全)")
        return
    if dst.exists():
        if read_bytes(src) == read_bytes(dst):
            out.append(f"OK {rel}")
        else:
            out.append(f"CONFLICT {rel} 既存と内容が異なる(手動で差分確認——黙って上書きしない)")
        return
    if not dry:
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(read_bytes(src))
    out.append(f"INSTALLED {rel}")


def merge_claude_md(target: Path, dry: bool, out: list[str]) -> None:
    src_text = (WB_ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    i = src_text.find(CLAUDE_SECTION_MARKER)
    if i < 0:
        out.append("CONFLICT CLAUDE.md workbench 側に UI スキル節が見つからない")
        return
    section = src_text[i:]
    dst = target / "CLAUDE.md"
    if not dst.exists():
        if not dry:
            dst.write_text("# CLAUDE.md\n\n" + section, encoding="utf-8", newline="\n")
        out.append("INSTALLED CLAUDE.md(UI スキル節のみで新規作成)")
        return
    cur = read_raw(dst)
    if CLAUDE_SECTION_MARKER in cur:
        out.append("OK CLAUDE.md(UI スキル節は追記済み)")
        return
    nl = newline_of(cur)
    body = (cur.rstrip("\r\n") + nl * 2 + section.replace("\n", nl))
    if not dry:
        dst.write_text(body, encoding="utf-8", newline="")
    out.append("MERGED CLAUDE.md UI スキル節を末尾へ追記")


def ensure_submodules(target: Path, dry: bool, out: list[str]) -> None:
    for rel, url, branch, sparse in SUBMODULES:
        if (target / rel / ".git").exists() or (target / ".gitmodules").exists() and \
                rel in (target / ".gitmodules").read_text(encoding="utf-8", errors="replace"):
            out.append(f"OK submodule {rel}")
            continue
        if dry:
            out.append(f"ADDED(dry) submodule {rel} <- {url}")
            continue
        r = run_git(target, "submodule", "add", "-b", branch, url, rel)
        if r.returncode != 0:
            out.append(f"CONFLICT submodule {rel} 追加に失敗: {r.stderr.strip().splitlines()[-1] if r.stderr else '?'}")
            continue
        if sparse:
            r2 = run_git(target / rel, "sparse-checkout", "set", "--no-cone", *sparse)
            if r2.returncode != 0:
                out.append(f"CONFLICT submodule {rel} sparse-checkout に失敗")
                continue
        out.append(f"ADDED submodule {rel}")


def fill_binding(rel: str, needle: str, block: str, target: Path, dry: bool, out: list[str]) -> None:
    p = target / rel
    text = read_raw(p)
    if needle in text:
        out.append(f"SKIPPED {rel} 充填済み")
        return
    close_idx = text.find(BINDING_CLOSE)
    if BINDING_OPEN not in text or close_idx < 0:
        out.append(f"CONFLICT {rel} 管理区画が見つからない(kit が旧版——先にケース3で更新)")
        return
    nl = newline_of(text)
    insert = block.replace("\n", nl) + nl
    new_text = text[:close_idx] + insert + text[close_idx:]
    if not dry:
        p.write_text(new_text, encoding="utf-8", newline="")
    out.append(f"FILLED {rel} 特別対応を管理区画へ充填")


def main() -> int:
    ap = argparse.ArgumentParser(description="guardrails-workbench installer")
    ap.add_argument("--dry-run", action="store_true", help="書き込み・git 実行をせず判定のみ表示")
    args = ap.parse_args()
    dry = args.dry_run
    target = Path.cwd()
    if hasattr(sys.stdout, "reconfigure"):  # Windows コンソールでの文字化け防止(kit §7.2)
        sys.stdout.reconfigure(encoding="utf-8")

    # 前提: git リポジトリ + kit 導入済み(管理区画の存在)
    if not (target / ".git").exists():
        print("CONFLICT 対象が git リポジトリのルートではない")
        return 1
    for req in ("scripts/repo_scan.py", "scripts/dev.py"):
        if not (target / req).exists():
            print(f"CONFLICT {req} が無い——kit 未導入。README のケース1/2(kit のプロンプト)を先に")
            return 1

    out: list[str] = []
    for rel in COPY_FILES:
        copy_one(rel, target, dry, out)
    for tree in COPY_TREES:
        for src in sorted((WB_ROOT / tree).rglob("*")):
            if src.is_file():
                copy_one(src.relative_to(WB_ROOT).as_posix(), target, dry, out)
    merge_claude_md(target, dry, out)
    ensure_submodules(target, dry, out)
    for rel, needle, block in FILLS:
        fill_binding(rel, needle, block, target, dry, out)

    conflicts = [l for l in out if l.startswith("CONFLICT")]
    for line in out:
        print(line)
    print()
    if conflicts:
        print(f"install_workbench: CONFLICT {len(conflicts)} 件——上の行を解消して再実行(冪等)")
        return 1
    mode = "(dry-run——書き込みなし)" if dry else ""
    print(f"install_workbench: 完了{mode}。次: uv run scripts/dev.py design \"saas dashboard\" で動詞の動作確認")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # 内部エラーは exit 2(§7.5 と同義)
        print(f"ERROR {type(e).__name__}: {e}")
        sys.exit(2)
