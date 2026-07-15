# codex_hook_adapter.py — Codex フックの入力を既存 guardrails フック契約へ正規化するアダプタ
"""Codex の Bash/apply_patch ペイロードを guardrails の Python フックへ橋渡しする。

Codex は編集を `apply_patch` として渡し、対象パスは `tool_input.command` の unified
patch に含める。一方で既存フックは Claude Code の `tool_input.file_path` 契約で書かれて
いる。このアダプタが全対象パスを抽出して1件ずつ実行するため、両ランタイムでフック本体の
安全ルールを共有できる。Codex の cwd から git root を解決して `CLAUDE_PROJECT_DIR` を
設定するのは、フック本体の後方互換用（名称は互換変数だが値は Codex のプロジェクト）。
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

PATCH_PATH = re.compile(r"^\*\*\* (Update|Add|Delete) File: (.+)$", re.MULTILINE)


def project_root(payload: dict) -> str | None:
    cwd = str(payload.get("cwd") or os.getcwd())
    try:
        proc = subprocess.run(["git", "-C", cwd, "rev-parse", "--show-toplevel"],
                              capture_output=True, timeout=30)
    except OSError:
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.decode("utf-8", "replace").strip() or None


def edited_paths(payload: dict, root: str, include_deleted: bool = False) -> list[str]:
    tool_input = payload.get("tool_input") or {}
    direct = tool_input.get("file_path")
    if isinstance(direct, str) and direct:
        return [direct]
    command = tool_input.get("command")
    if not isinstance(command, str):
        return []
    paths: list[str] = []
    for kind, raw in PATCH_PATH.findall(command):
        if kind == "Delete" and not include_deleted:
            continue
        candidate = raw.strip()
        if candidate and not Path(candidate).is_absolute():
            candidate = str(Path(root) / candidate)
        if candidate and candidate not in paths:
            paths.append(candidate)
    return paths


def main(argv: list[str]) -> int:
    if len(argv) != 3 or argv[1] not in {"direct", "files", "guarded-files"}:
        print("codex_hook_adapter: usage: <direct|files|guarded-files> <hook-script>", file=sys.stderr)
        return 2
    fail_closed = argv[1] == "direct" and argv[2] == "guard_git_bypass.py"
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except ValueError as exc:
        print(f"[codex-hook-adapter] 入力JSONを解釈できない: {exc}", file=sys.stderr)
        return 2 if fail_closed else 0
    root = project_root(payload)
    if not root:
        print("[codex-hook-adapter] git root を解決できないためフックをスキップ", file=sys.stderr)
        return 2 if fail_closed else 0
    # 防壁本体は .claude/hooks にだけ置く。Codexはイベント形式だけを変換し、規則実装を複製しない。
    script = Path(root) / ".claude" / "hooks" / argv[2]
    if not script.is_file():
        print(f"codex_hook_adapter: hook が無い: {script.name}", file=sys.stderr)
        return 2
    env = os.environ.copy()
    env["CLAUDE_PROJECT_DIR"] = root
    env["GUARDRAILS_SESSION_DIR"] = ".codex"
    payload["stop_hook_active"] = bool(payload.get("stop_hook_active", False)) or (
        payload.get("hook_event_name") == "Stop"
    )
    file_mode = argv[1] in {"files", "guarded-files"}
    paths = (edited_paths(payload, root, include_deleted=argv[1] == "guarded-files")
             if file_mode else [None])
    if file_mode and not paths:
        return 0
    for file_path in paths:
        current = dict(payload)
        if file_path is not None:
            current["tool_input"] = dict(payload.get("tool_input") or {}, file_path=file_path)
        proc = subprocess.run([sys.executable, str(script)], input=json.dumps(current, ensure_ascii=False),
                              text=True, encoding="utf-8", errors="replace", cwd=root, env=env)
        if proc.returncode != 0:
            return proc.returncode
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv))
    except Exception as exc:
        print(f"codex_hook_adapter: 内部エラー: {exc!r}", file=sys.stderr)
        sys.exit(2)
