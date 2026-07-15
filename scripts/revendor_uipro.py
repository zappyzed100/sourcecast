# revendor_uipro.py — ui-ux-pro-max を GitHub main から .claude/skills/ へ再ベンダーする
"""revendor_uipro.py — nextlevelbuilder/ui-ux-pro-max-skill の再ベンダー(README ケース3の ui-ux-pro-max 行)。

npm パッケージ(ui-ux-pro-max-cli)は GitHub main より遅れるため、公式インストーラは使わず
その処理(cli/src/utils/template.ts の renderSkillFile + copyDataAndScripts + copySubSkills)を
GitHub main のクローンに対して再現する。上流のコードは実行しない(ファイル操作のみ)。

使い方(リポジトリのルートで):
    uv run --no-project scripts/revendor_uipro.py [--dry-run]

動作:
  1. 上流を --depth 1 で一時ディレクトリへ clone(HEAD の SHA を記録)
  2. SKILL.md をテンプレートから描画(claude 列: frontmatter + 5プレースホルダ置換)
  3. .claude/skills/ の ui-ux-pro-max とサブスキル群を丸ごと入れ替え
  4. .upstream/sources.yaml の vendored-from-sha を更新
冪等: 上流が同一 SHA なら結果はバイト同一(git status で確認できる)。
exit: 0=成功 / 1=前提不成立 / 2=内部エラー。encoding/newline 明示(kit §7.2 と同じ)。
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

UPSTREAM_URL = "https://github.com/nextlevelbuilder/ui-ux-pro-max-skill.git"
SOURCES_YAML = Path(".upstream/sources.yaml")
SKILLS_DIR = Path(".claude/skills")


def _rm_readonly(func, path, _exc):  # Windows: .git 配下の読み取り専用ファイル対策
    Path(path).chmod(stat.S_IWRITE)
    func(path)


def read_raw(p: Path) -> str:
    """改行変換なしで読む(read_text の newline= は 3.13+ のため open を使う)。"""
    with p.open(encoding="utf-8", newline="") as f:
        return f.read()


def render_skill_md(clone: Path) -> str:
    """cli/src/utils/template.ts renderSkillFile(isGlobal=false) の再現。"""
    assets = clone / "cli" / "assets"
    cfg = json.loads((assets / "templates" / "platforms" / "claude.json").read_text(encoding="utf-8"))
    content = read_raw(assets / "templates" / "base" / "skill-content.md")
    quick = read_raw(assets / "templates" / "base" / "quick-reference.md")

    lines = ["---"]
    for key, value in cfg["frontmatter"].items():  # renderFrontmatter と同じ引用規則
        if ":" in value or '"' in value or "\n" in value:
            lines.append(f'{key}: "{value.replace(chr(34), chr(92) + chr(34))}"')
        else:
            lines.append(f"{key}: {value}")
    lines += ["---", ""]
    fm = "\n".join(lines)

    content = (content
               .replace("{{TITLE}}", cfg["title"])
               .replace("{{DESCRIPTION}}", cfg["description"])
               .replace("{{SCRIPT_PATH}}", cfg["scriptPath"])
               .replace("{{SKILL_OR_WORKFLOW}}", cfg["skillOrWorkflow"])
               .replace("{{QUICK_REFERENCE}}", "\n" + quick))
    return fm + content


def main() -> int:
    ap = argparse.ArgumentParser(description="re-vendor ui-ux-pro-max from GitHub main")
    ap.add_argument("--dry-run", action="store_true", help="書き込みをせず適用内容のみ表示")
    args = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):  # Windows コンソールでの文字化け防止(kit §7.2)
        sys.stdout.reconfigure(encoding="utf-8")

    if not SOURCES_YAML.exists() or not SKILLS_DIR.exists():
        print("CONFLICT リポジトリのルートで実行する(.upstream/sources.yaml と .claude/skills/ が必要)")
        return 1

    tmp = Path(tempfile.mkdtemp(prefix="uipro-"))
    try:
        clone = tmp / "upstream"
        r = subprocess.run(["git", "clone", "--depth", "1", UPSTREAM_URL, str(clone)],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        if r.returncode != 0:
            print(f"CONFLICT clone 失敗: {r.stderr.strip().splitlines()[-1] if r.stderr else '?'}")
            return 1
        sha = subprocess.run(["git", "-C", str(clone), "rev-parse", "HEAD"], capture_output=True,
                             text=True, encoding="utf-8").stdout.strip()
        version = json.loads((clone / "skill.json").read_text(encoding="utf-8"))["version"]
        assets = clone / "cli" / "assets"

        sub_skills = sorted(p.name for p in (assets / "skills").iterdir() if p.is_dir())
        plan = ["ui-ux-pro-max"] + sub_skills
        print(f"上流 HEAD: {sha} (v{version})")
        print(f"入れ替え対象: {', '.join(plan)}")
        if args.dry_run:
            print("\nrevendor_uipro: dry-run——書き込みなし")
            return 0

        # オーケストレータ: SKILL.md 描画 + data/scripts コピー
        orch = SKILLS_DIR / "ui-ux-pro-max"
        if orch.exists():
            shutil.rmtree(orch)
        orch.mkdir(parents=True)
        (orch / "SKILL.md").write_text(render_skill_md(clone), encoding="utf-8", newline="")
        shutil.copytree(assets / "data", orch / "data")
        shutil.copytree(assets / "scripts", orch / "scripts")

        # サブスキル群(既知の名前のみ入れ替え——対象リポジトリ独自のスキルには触れない)
        for name in sub_skills:
            dst = SKILLS_DIR / name
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(assets / "skills" / name, dst)

        # sources.yaml の vendored-from-sha を更新
        text = read_raw(SOURCES_YAML)
        new_text, n = re.subn(r"(vendored-from-sha:\s*)[0-9a-f]{40}[^\r\n]*",
                              rf"\g<1>{sha} # GitHub main, v{version}", text)
        if n != 1:
            print("CONFLICT sources.yaml の vendored-from-sha 行が見つからない(手で確認)")
            return 1
        SOURCES_YAML.write_text(new_text, encoding="utf-8", newline="")

        print(f"\nrevendor_uipro: 完了。vendored-from-sha を {sha[:8]} (v{version}) に更新。"
              "差分は git status / git diff で確認する")
        return 0
    finally:
        shutil.rmtree(tmp, onerror=_rm_readonly)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # 内部エラーは exit 2
        print(f"ERROR {type(e).__name__}: {e}")
        sys.exit(2)
