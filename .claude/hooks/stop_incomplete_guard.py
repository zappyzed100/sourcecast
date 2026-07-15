# stop_incomplete_guard.py — ターン終了ゲート: 未完了（未コミット作業/構造検査が赤）の終了を exit 2 で差し戻す（正本: .guardrails/GUARDRAILS.md §2b）
#
# Stop フックの仕様: 応答終了時に発火し、exit 2 で終了を差し戻せる（stderr が Claude に渡る）。
# 入力 JSON: session_id / transcript_path（HARNESS-VERIFIED: code.claude.com/docs/en/hooks.md
# 2026-07-08 — §2d。exit 2 の効果・session_id・transcript_path はここで確認済み）。
# stop_hook_active はこの確認時点の公式ドキュメントに**記載が無い**（未文書化フィールドの
# 可能性——実機のペイロードには存在し、本フックの無限ループ防止（無読）はそれに依存して
# 動いている。ドキュメントと実機が食い違う具体例——次にこのフックへ手を入れる時に
# 実機で再確認すること。stop_hook_active=true は「既に差し戻しで継続中」を意味する
# という理解は Phase 11（v2.4）導入時の実機確認に基づく、ドキュメント未確認の前提のまま）。
#
# 差し戻し条件（いずれかの理由が成立 ∧ 免除なし の時のみ exit 2）:
#   条件A（v2.4）: `git status --porcelain` が非空（未コミットの作業がある）
#   条件B（v2.9・決定点②の強化案を確定）: ツリーはクリーンだが `check_structure.py` が
#     exit 1 かつ出力に `HARD:`（ゲートを通らない状態で終わろうとしている）。
#     条件Bはクリーンな時だけ走る（ダーティなら条件Aが先に成立——毎ターンのコストは
#     §7.7 の予算＋python 起動数十ms。ハングは本体側フックタイムアウトが殺す＝
#     kill は exit 2 以外 → 差し戻されない側に倒れる）。
#     fail-open の枝: check_structure.py 不在（表示1行で素通し）・exit 2（内部
#     エラー）・`HARD:` 行の無い非0——いずれも差し戻さない。
#   免除: transcript 終端 N 行に `"BLOCKED:`（値の先頭が BLOCKED: で始まる報告）がある
#       ※ 素の `BLOCKED:` を探すと、本フック自身の差し戻し文面（`BLOCKED:` の指示）が
#         transcript に載った時点で恒久すり抜けになる。先頭一致の近似は仕様（§7.4 の流儀）。
#       免除・ループ保護・fail-open は条件A/Bで共有。
#
# ループ保護（二重 — §2b）:
#   ① .claude/session/<session_id>.stopcount のカウンタで差し戻しは最大 3 回。
#     stop_hook_active=false（新しい停止連鎖）でカウンタは 0 から数え直す。
#   ② Claude Code 本体側の連続ブロック上限（v2.1.143+・CLAUDE_CODE_STOP_HOOK_BLOCK_CAP）。
#
# 【契約——§2 と逆向き】本フックの想定外エラーは exit 0（fail-open・差し戻さない）。
# PreToolUse（§2）は fail-closed が正だが、Stop で fail-closed にすると壊れたフックが
# セッションを終了不能にする。非対称の正本は §2b。
#
# v2.23（G11・言語移行）: 旧 bash 実装は典型ケースで約698ms/回（grep/sed/jq が14回前後）。
# JSON解析・正規表現・カウンタファイル操作を標準ライブラリで完結させ、条件B判定も
# `uv run scripts/dev.py check`（dev.py 経由で2段の `uv run` を挟む）ではなく
# `check_structure.py` を `sys.executable` で直接1段だけ起動する形に変更した
# （`dev.py` の `check` 動詞は列上書き不可・常に `check_structure.py` 固定なので、
# 迂回しても意味は変わらない — scripts/dev.py 参照）。

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

MAX_REDIRECTS = 3
TAIL_LINES = 50
SESSION_ID_ALLOWED = re.compile(r"[^A-Za-z0-9._-]")
HARD_LINE = re.compile(r"^HARD:", re.MULTILINE)
CHECK_SCRIPTS = ("check_structure.py", "check_codex_hooks.py")


def resolve_root() -> str | None:
    root = os.environ.get("CLAUDE_PROJECT_DIR")
    if root:
        return root
    try:
        proc = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                               capture_output=True, timeout=30)
    except OSError:
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.decode("utf-8", "replace").strip()


def session_dir(root: str) -> Path:
    """ランタイム別の状態を置く。既定はClaude、Codexアダプタは .codex を明示する。"""
    name = os.environ.get("GUARDRAILS_SESSION_DIR", ".claude")
    return Path(root) / name / "session"


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

    root = resolve_root()
    if not root or not os.path.isdir(root):
        return 0

    try:
        porcelain_proc = subprocess.run(["git", "-C", root, "status", "--porcelain"],
                                        capture_output=True, timeout=30)
    except OSError:
        return 0
    if porcelain_proc.returncode != 0:
        return 0
    porcelain = porcelain_proc.stdout.decode("utf-8", "replace")

    session_id_raw = payload.get("session_id") or ""
    transcript_path = payload.get("transcript_path") or ""
    active = bool(payload.get("stop_hook_active", False))
    session_id = SESSION_ID_ALLOWED.sub("", session_id_raw) or "unknown"
    counter_dir = session_dir(root)
    counter_file = counter_dir / f"{session_id}.stopcount"

    # ---- 差し戻し理由の確定（出口1を含む） ----
    reason = ""
    check_head = ""
    if porcelain.strip():
        reason = "dirty"
    else:
        check_scripts = [Path(root) / "scripts" / name for name in CHECK_SCRIPTS]
        if all(path.is_file() for path in check_scripts):
            try:
                for check_script in check_scripts:
                    check_proc = subprocess.run([sys.executable, str(check_script)],
                                                capture_output=True, cwd=root, timeout=60)
                    check_out = (check_proc.stdout + check_proc.stderr).decode("utf-8", "replace")
                    if check_proc.returncode == 1 and HARD_LINE.search(check_out):
                        reason = "check"
                        hard_lines = [ln for ln in check_out.splitlines() if ln.startswith("HARD:")]
                        check_head = "\n".join(hard_lines[:5])
                        break
                # exit 0=緑 / exit 2=内部エラー / HARD 無しの非0 → いずれも差し戻さない
            except (OSError, subprocess.TimeoutExpired):
                pass  # fail-open
        else:
            print("[stop-gate] 条件B スキップ（必須のキット検査スクリプトが無い）——"
                  "静かな不発の禁止は本表示で満たす（.guardrails/GUARDRAILS.md §2b）", file=sys.stderr)
        if not reason:
            try:
                counter_file.unlink(missing_ok=True)
            except OSError:
                pass
            return 0

    # ---- 出口2: 明示ブロッカー報告（応答の先頭が BLOCKED: で始まる） ----
    transcript_path = os.path.expanduser(transcript_path) if transcript_path else ""
    if not transcript_path or not os.access(transcript_path, os.R_OK):
        return 0
    try:
        with open(transcript_path, "r", encoding="utf-8", errors="replace") as f:
            tail = f.readlines()[-TAIL_LINES:]
    except OSError:
        return 0
    if any('"BLOCKED:' in ln for ln in tail):
        try:
            counter_file.unlink(missing_ok=True)
        except OSError:
            pass
        return 0

    # ---- 差し戻し（ループ保護①のカウンタ内でのみ） ----
    count = 0
    if active:
        try:
            raw_count = counter_file.read_text(encoding="utf-8", errors="replace")
            digits = "".join(c for c in raw_count if c.isdigit())
            count = int(digits) if digits else 0
        except OSError:
            count = 0
        if count >= MAX_REDIRECTS:
            print(f"[stop-gate] 差し戻し上限（{MAX_REDIRECTS}回）到達のため終了を許可"
                  "（.guardrails/GUARDRAILS.md §2b）", file=sys.stderr)
            return 0
    try:
        counter_dir.mkdir(parents=True, exist_ok=True)
        counter_file.write_text(str(count + 1), encoding="utf-8")
    except OSError:
        return 0  # 記録できないなら差し戻さない（fail-open）

    if reason == "check":
        print("作業ツリーはクリーンだが、構造検査（dev.py check）が赤のままターンを終えようと"
              "している（§2b 条件B — v2.9）。終えてよい出口は2つだけ: (a) 規則IDで "
              ".guardrails/GUARDRAILS.md §3.3 を引いて違反を解消し、規約どおりコミットする。 (b) 物理的に"
              "解消不能なら、応答の先頭を `BLOCKED:` で始めて具体的に報告する。検出された違反"
              f"（先頭5行）:\n{check_head}", file=sys.stderr)
    else:
        changed = sum(1 for ln in porcelain.splitlines() if ln.strip())
        print(f"未コミットの作業ツリー（変更 {changed} 件）のままターンを終えようとしている。"
              "終えてよい出口は2つだけ: (a) DoD を満たし規約どおりコミットして作業ツリーを"
              "クリーンにする（§3・§10 実行規律7）。 (b) 本当に手が止まる物理的ブロッカー"
              "なら、応答の先頭を `BLOCKED:` で始めて具体的に報告する。「続けますか?」で"
              "止まるのはサボりの一形態（.guardrails/GUARDRAILS.md §2b）。", file=sys.stderr)
    return 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException as exc:  # §2b は fail-open——想定外エラーも exit 0（迂回防止とは非対称）
        print(f"[stop-gate] 内部エラーのため素通し（差し戻さない）: {exc!r}", file=sys.stderr)
        sys.exit(0)
