# check_fill_bindings.py — fill_bindings の失敗時無変更・正常充填を回帰検査する
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import install_kit as ik  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
FILL = ROOT / "scripts" / "fill_bindings.py"


def run(root: Path, *columns: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(FILL), *columns], cwd=root,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    if not {".ruff_cache", ".pytest_cache", ".venv", "node_modules"} <= ik.EXCLUDE_DIRS:
        print("HARD:installer-cache-leak 生成キャッシュの除外が欠落", file=sys.stderr)
        return 1
    if not ik.is_meta(".claude/scheduled_tasks.lock"):
        print("HARD:installer-cache-leak Claudeランタイム状態の除外が欠落", file=sys.stderr)
        return 1
    with tempfile.TemporaryDirectory(prefix="fill-bindings-") as tmp:
        root = Path(tmp)
        (root / "bindings").mkdir()
        (root / "scripts").mkdir()
        target = root / "scripts" / "repo_scan.py"
        yaml_target = root / ".pre-commit-config.yaml"
        original = (
            "# >>> GUARDRAILS BINDING >>>\n"
            "# BINDING-SOURCE: <列ID@版をここに>\n"
            "# <<< GUARDRAILS BINDING <<<\n"
        )
        target.write_text(original, encoding="utf-8", newline="\n")
        yaml_original = (
            "# BINDING-SOURCE: <列ID@版をここに>\n"
            "repos:\n"
            "  # >>> GUARDRAILS BINDING: pre-push >>>\n"
            "  # <<< GUARDRAILS BINDING: pre-push <<<\n"
        )
        yaml_target.write_text(yaml_original, encoding="utf-8", newline="\n")
        (root / "bindings" / "catalog.md").write_text(
            "## 列: valid@1\n\n"
            "<!-- FILL scripts/repo_scan.py -->\n"
            "```python\nX = 1\n```\n"
            "<!-- FILL .pre-commit-config.yaml#pre-push -->\n"
            "```yaml\n  - id: probe\n```\n",
            encoding="utf-8", newline="\n",
        )
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)

        bad = run(root, "missing@1", "valid@1")
        if (bad.returncode != 1 or target.read_text(encoding="utf-8") != original
                or yaml_target.read_text(encoding="utf-8") != yaml_original):
            print("HARD:fill-bindings-partial 事前検証失敗後にファイルが変更された", file=sys.stderr)
            return 1

        good = run(root, "valid@1")
        text = target.read_text(encoding="utf-8")
        yaml_text = yaml_target.read_text(encoding="utf-8")
        if (good.returncode != 0 or "X = 1" not in text or "BINDING-SOURCE: valid@1" not in text
                or "id: probe" not in yaml_text or "BINDING-SOURCE: valid@1" not in yaml_text):
            print("HARD:fill-bindings-regression 正常な列を充填・刻印できない", file=sys.stderr)
            return 1
        new_yaml = yaml_original.replace("<列ID@版をここに>", "<新版>")
        spliced = ik.splice_managed(new_yaml, yaml_text)
        if spliced is None or "id: probe" not in spliced or "BINDING-SOURCE: valid@1" not in spliced:
            print("HARD:fill-bindings-upgrade 名前付き管理区画を更新時に保持できない", file=sys.stderr)
            return 1
    print("[fill-bindings] 失敗時無変更・正常充填 PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
