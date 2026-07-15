# post_edit_format.py — Edit/Write/MultiEdit 直後に編集ファイルへ整形を当てる（正本: .guardrails/GUARDRAILS.md §1）
#
# 狙い: フォーマット崩れの検出地点を「コミット時」から「編集した瞬間」へ前倒しする。
# PostToolUse の仕様: 編集自体は取り消せない。exit 2 のとき stderr が Claude に渡り
# 自己修正の材料になる（整形が失敗する = 構文エラーの可能性が高いので exit 2 を使う）
# （HARNESS-VERIFIED: code.claude.com/docs/en/hooks.md 2026-07-08 — §2d）。
# フォーマッタ未導入・対象外拡張子は exit 0（この層は利便であってゲートではない。
# ゲートは §3〜§5 が担う）。どの整形も冪等。
#
# BINDING-SOURCE の刻印は下の管理区画内に書く（§12.7。未刻印は SOFT:binding-unstamped）
#
# ===== BINDING: 対象拡張子 × 整形コマンド（bindings/catalog.md の採用列から充填）=====
# v2キットは言語なしで出荷される（下の DISPATCH は空）。Step 0 で採用列の paste-block を
# DISPATCH へ挿入する。冪等な整形コマンドのみ許可（表A「整形」）。
# **コマンドは直接バイナリを指すこと（npx/uvx 経由は避ける）**——実測: `npx prettier`
# はローカル install 済みでも約900ms/回、node_modules/.bin の直接呼び出しなら約240ms/回
# （v2.24。差の大半は npx 自体の解決コストで Node 起動コストではない）。編集の度に
# 発火するホットパスでは、この差が言語移行そのものより効く（G11）。

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

# >>> GUARDRAILS BINDING >>>
# 拡張子 → 整形コマンド（argv のリストのリスト・順に実行）。空 = キット出荷時の既定。
# 例（python-uv 列・直接バイナリ呼び出し）: ".py": [["ruff", "format", "{file}"]]
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
        return 0  # 未配線の拡張子は素通し（この層はゲートではない — §1）

    for cmd in cmds:
        argv = [file_path if tok == "{file}" else tok for tok in cmd]
        try:
            proc = subprocess.run(argv, capture_output=True, timeout=30)
        except OSError:
            print(f"[post-edit-format] {argv[0]} を実行できない——ツール未導入の可能性。"
                  "素通し（この層はゲートではない — §1）", file=sys.stderr)
            return 0
        if proc.returncode != 0:
            err = proc.stderr.decode("utf-8", "replace") or proc.stdout.decode("utf-8", "replace")
            print(f"{argv[0]} が失敗（構文エラーの可能性）。直後に修正すること:\n{err}",
                  file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
