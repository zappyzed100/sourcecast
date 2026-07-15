# post_edit_lint.py — Edit/Write/MultiEdit 直後の編集ファイルへ単一ファイル lint を当てる第2段（正本: .guardrails/GUARDRAILS.md §1）
#
# 整形（post_edit_format.py・自動修正系）と責務を分けた**判定系**の第2段（v2.5・Phase 12）。
# lint の初出地点が push 段（§4）から編集直後へ2段前倒しになり、「push で落ちて再試行」の
# ループ1周が消える。違反は exit 2 —— stderr が Claude に渡り、コンテキストを保持した
# まま即修正ループに入れる。
#
# 実行順の保証: Claude Code の公式仕様では同一 matcher の複数フックは**並列・順序不定**
# （HARNESS-VERIFIED: code.claude.com/docs/en/hooks.md 2026-07-08 — §2d）。
# そのため本フックは settings.json 側で post_edit_format.py と**1コマンドの直列**として
# 配線される（整形→lint の順を実行環境の仕様に依存させない —— §1）。
#
# 性能予算（§7.7・v2.5 新設）: 整形と合わせて**編集1回あたり3秒以内**。全体 typecheck・
# 全体テストはここに入れない（push 段 §4 に残す。予算に収まる単一ファイル lint のみ）。
# ツール不在: 「lint 未導入」を stderr 1行で表示して素通し（exit 0 —— 表示で静かな不発を
# 防ぎ、編集フローは止めない。表示＋素通しの型は §2b/§2c 系の fail-open 側の整理）。
# --fix 系（自動修正）はここに置かない —— それは整形フック（第1段）の責務。
#
# BINDING-SOURCE の刻印は下の管理区画内に書く（§12.7。未刻印は SOFT:binding-unstamped）
#
# ===== BINDING: 対象拡張子 × lint コマンド（bindings/catalog.md 表A「編集直後 lint」）=====
# v2キットは言語なしで出荷される（下の DISPATCH は空）。Step 0 で採用列の paste-block を
# DISPATCH へ挿入する。単一ファイル・3秒予算に収まる判定系コマンドのみ。
# 予算に収まらない言語は「該当なし（push 段で回収）」——カタログにその判断を記録する。
# **コマンドは直接バイナリを指すこと（npx/uvx 経由は避ける）**——理由は post_edit_format.py
# 冒頭コメントと同じ実測（v2.24）。
#
# 契約: exit 1（違反あり）だけを exit 2 として本フックからブロックする。exit 2 以上
# （usage error・ツール未導入等）はブロックせず警告1行で素通しする（rc==1 のみが
# 「違反」の契約を持つツール——ruff/eslint 等——を前提にした近似。契約が異なる
# ツールを足す列はここを調整する）。

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

# >>> GUARDRAILS BINDING >>>
# 拡張子 → lint コマンド（argv のリストのリスト・順に実行）。空 = キット出荷時の既定。
# 例（python-uv 列・直接バイナリ呼び出し）: ".py": [["ruff", "check", "{file}"]]
# 採用列の paste-block はこの区画内へ。更新はこの区画の中身だけ引き継がれる（Phase 44）。
DISPATCH: dict[str, list[list[str]]] = {}
# BINDING-SOURCE: <列ID@版をここに>   ← Step 0 で刻印（§12.7・区画内=更新で消えない）
# <<< GUARDRAILS BINDING <<<


def main() -> int:
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    raw = sys.stdin.read()
    if not raw:
        return 0
    try:
        payload = json.loads(raw)
    except ValueError:
        return 0

    file_path = (payload.get("tool_input") or {}).get("file_path") or ""
    if not file_path or not Path(file_path).is_file():
        return 0

    ext = Path(file_path).suffix
    cmds = DISPATCH.get(ext)
    if not cmds:
        return 0  # 未配線の拡張子は素通し（この層はゲートではない — §1。門は §3〜§5 が担う）

    for cmd in cmds:
        argv = [file_path if tok == "{file}" else tok for tok in cmd]
        try:
            proc = subprocess.run(argv, capture_output=True, timeout=30)
        except OSError:
            print(f"[post-edit-lint] {argv[0]} を実行できない——ツール未導入の可能性。"
                  "素通し: push 段の CI で回収される", file=sys.stderr)
            return 0
        if proc.returncode == 1:  # 1 = 違反あり（stderr が Claude へ渡り即修正 — §1）
            err = proc.stderr.decode("utf-8", "replace") or proc.stdout.decode("utf-8", "replace")
            sys.stderr.write(err)
            return 2
        if proc.returncode >= 2:  # 2以上 = 実行不能（usage error 等）。ブロックしない
            print(f"[post-edit-lint] {argv[0]} を実行できない（rc={proc.returncode}）ため"
                  "素通し: push 段で回収される", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
