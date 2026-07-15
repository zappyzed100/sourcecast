# check_codex_hooks.py — Codex フック設定とアダプタの回帰検査（契約: .guardrails/GUARDRAILS.md §2）
from __future__ import annotations

import json
import importlib.util
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HOOKS = ROOT / ".codex" / "hooks.json"
ADAPTER = ROOT / ".codex" / "hooks" / "codex_hook_adapter.py"
REQUIRED_EVENTS = {"PreToolUse", "PostToolUse", "SessionStart", "Stop"}


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    try:
        config = json.loads(HOOKS.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"HARD:codex-hooks-invalid .codex/hooks.json: {exc}", file=sys.stderr)
        return 1
    events = config.get("hooks", {})
    missing = REQUIRED_EVENTS - set(events)
    if missing:
        print(f"HARD:codex-hooks-invalid .codex/hooks.json: event不足 {sorted(missing)}", file=sys.stderr)
        return 1
    commands = [hook for groups in events.values() for group in groups for hook in group.get("hooks", [])]
    if not all("command" in hook and "commandWindows" in hook for hook in commands):
        print("HARD:codex-hooks-invalid .codex/hooks.json: command/commandWindows の組が不足", file=sys.stderr)
        return 1
    if any("CLAUDE_PROJECT_DIR" in hook["command"] for hook in commands):
        print("HARD:codex-hooks-invalid .codex/hooks.json: Claude 専用環境変数への依存が残っている", file=sys.stderr)
        return 1
    expected_hooks = {"guard_git_bypass.py", "guard_human_wip.py", "post_edit_format.py",
                      "post_edit_lint.py", "session_baseline.py", "stop_incomplete_guard.py"}
    command_text = "\n".join(hook["command"] for hook in commands)
    if any(name not in command_text for name in expected_hooks):
        print("HARD:codex-hooks-invalid .codex/hooks.json: 必須フックの配線が不足", file=sys.stderr)
        return 1
    missing_sources = [name for name in expected_hooks if not (ROOT / ".claude" / "hooks" / name).is_file()]
    if missing_sources:
        print(f"HARD:codex-hooks-invalid .claude/hooks: 共通フック本体が不足 {missing_sources}", file=sys.stderr)
        return 1
    spec = importlib.util.spec_from_file_location("codex_hook_adapter", ADAPTER)
    if spec is None or spec.loader is None:
        print("HARD:codex-hook-adapter adapter を読み込めない", file=sys.stderr)
        return 1
    adapter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(adapter)
    with tempfile.TemporaryDirectory(prefix="codex-hook-") as tmp:
        root = Path(tmp)
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        fixture_hooks = root / ".claude" / "hooks"
        fixture_hooks.mkdir(parents=True)
        for name in ("guard_human_wip.py", "stop_incomplete_guard.py"):
            shutil.copyfile(ROOT / ".claude" / "hooks" / name, fixture_hooks / name)
        payload = {"tool_input": {"command": "*** Begin Patch\n*** Add File: src/a.py\n+x\n*** Update File: src/b.py\n+y\n*** Delete File: src/c.py\n*** End Patch\n"}}
        expected = [str(root / "src" / "a.py"), str(root / "src" / "b.py")]
        actual = adapter.edited_paths(payload, str(root))
        protected_paths = adapter.edited_paths(payload, str(root), include_deleted=True)
        protected = root / "human.txt"
        protected.write_text("human work\n", encoding="utf-8")
        (root / ".codex" / "session").mkdir(parents=True)
        (root / ".codex" / "session" / "codex-test.baseline").write_text(
            "# source=startup\nhuman.txt\n", encoding="utf-8"
        )
        guard_payload = json.dumps({
            "cwd": str(root), "session_id": "codex-test",
            "tool_input": {"command": "*** Begin Patch\n*** Delete File: human.txt\n*** End Patch\n"},
        })
        proc = subprocess.run([sys.executable, str(ADAPTER), "guarded-files", "guard_human_wip.py"],
                              input=guard_payload, text=True, encoding="utf-8", errors="replace",
                              cwd=root, capture_output=True)
        checks_dir = root / "scripts"
        checks_dir.mkdir()
        (checks_dir / "check_structure.py").write_text("raise SystemExit(0)\n", encoding="utf-8")
        (checks_dir / "check_codex_hooks.py").write_text(
            "import sys\nprint('HARD:codex-hooks-invalid fixture')\nraise SystemExit(1)\n",
            encoding="utf-8",
        )
        subprocess.run(["git", "-C", str(root), "config", "user.email", "corpus@example.invalid"], check=True)
        subprocess.run(["git", "-C", str(root), "config", "user.name", "codex-hook-corpus"], check=True)
        subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(root), "commit", "-q", "-m", "fixture"], check=True)
        transcript = Path(tmp).parent / "codex-hook-transcript.jsonl"
        transcript.write_text("{}\n", encoding="utf-8")
        stop_payload = json.dumps({"cwd": str(root), "session_id": "codex-stop",
                                   "hook_event_name": "Stop", "transcript_path": str(transcript)})
        stop_proc = subprocess.run([sys.executable, str(ADAPTER), "direct", "stop_incomplete_guard.py"],
                                   input=stop_payload, text=True, encoding="utf-8", errors="replace",
                                   cwd=root, capture_output=True)
        malformed_proc = subprocess.run(
            [sys.executable, str(ADAPTER), "direct", "guard_git_bypass.py"],
            input="{not-json", text=True, encoding="utf-8", errors="replace",
            cwd=root, capture_output=True,
        )
        missing_root_proc = subprocess.run(
            [sys.executable, str(ADAPTER), "direct", "guard_git_bypass.py"],
            input=json.dumps({"cwd": str(root / "missing"),
                              "tool_input": {"command": "git commit --no-verify"}}),
            text=True, encoding="utf-8", errors="replace", cwd=root, capture_output=True,
        )
    if actual != expected:
        print(f"HARD:codex-hook-adapter apply_patch の対象抽出が不正: {actual!r}", file=sys.stderr)
        return 1
    if protected_paths != [*expected, str(root / "src" / "c.py")]:
        print("HARD:codex-hook-adapter 削除パッチを所有権ガード対象にできない", file=sys.stderr)
        return 1
    if proc.returncode != 2:
        print("HARD:codex-hook-adapter Codex apply_patch で人間WIPをブロックできない", file=sys.stderr)
        return 1
    if stop_proc.returncode != 2 or "HARD:codex-hooks-invalid fixture" not in (stop_proc.stderr or ""):
        print("HARD:codex-stop-gate dev.py check に追加された検査を回収できない", file=sys.stderr)
        return 1
    if malformed_proc.returncode != 2 or missing_root_proc.returncode != 2:
        print("HARD:codex-hook-adapter 操作直前ガードの異常入力がfail-open", file=sys.stderr)
        return 1
    print("[codex-hooks] 設定・Windows経路・apply_patch入力変換 PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
