# guard_human_wip.py — 人間の未コミット変更（セッション開始時点で dirty だったファイル）への AI の Edit/Write を exit 2 でブロックする（正本: .guardrails/GUARDRAILS.md §2c）
#
# PreToolUse(Edit|Write|MultiEdit)（HARNESS-VERIFIED: code.claude.com/docs/en/hooks.md
# 2026-07-08 — §2d）。ブロック条件は**両方**が成立する時のみ:
#   (A) 対象 file_path が session_baseline.py の保存した baseline に含まれる
#       （＝セッション開始時点で既に未コミット変更があった＝人間のWIP）
#   (B) そのファイルが**現在も**未コミット（`git status --porcelain -- <path>` が非空）
# 人間が commit / stash すれば (B) が外れて自動解除——解除用の特別経路を作らない（§2c）。
#
# 【契約——§2 と逆向き・§2b の仲間】baseline 不在・git 不在などの想定外は
# **警告1行＋exit 0（fail-open）**。書き込み保護は利便とのトレードであり、壊れた
# フックが全編集を止めてはならない（迂回防止 §2 の fail-closed とは非対称——正本は §2c）。
#
# 既知の限界（§2c に明記）: baseline はセッション**開始時点**のスナップショット。
# 同一セッション内で人間が並行して編集を始めたファイルは守れない。
# パスの正規化（絶対→リポジトリ相対・区切り差）は git 自身に任せる——
# `git status --porcelain -- <絶対パス>` の出力がリポジトリ相対で返ることを利用する。
#
# v2.23（G11・言語移行）: 旧 bash 実装は1回の呼び出しで jq×2・tr・git・grep が最大5回
# 起動し、Windows実機で約526ms/回かかっていた。JSON解析・文字列サニタイズ・baseline
# 照合はすべて Python 標準ライブラリで完結するため子プロセスは `git status` 1回だけに
# 減る（git はローカルの実状態を読む必要があり、これは言語を変えても避けられない）。
#
# v2.27（アルゴリズム是正・言語非依存）: `git status` の呼び出し自体を条件(A)の後回しに
# していたため、baseline に載っていない大多数の Edit/Write でも毎回 git を fork していた
# （移行では解消しない無駄——同じ順序の弱点は bash 版にもあった）。baseline はローカルの
# 静的ファイルなので、先にそちらを見て「該当の疑いがある時だけ」git を呼ぶ順序に変更。
# baseline が空（セッション開始時クリーン）なら git を一切呼ばず即 exit 0 になる。
#
# v2.29（G7・session_baseline.py と対）: baseline ファイル先頭に `# source=<値> ts=<UTC>`
# の1行メタデータが付くようになった（compact 誤爆事故の調査コスト削減——事故当時は
# 生の transcript jsonl を読むしかなかった）。`#` 始まりの行はパス比較から除外する。

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

SESSION_ID_ALLOWED = re.compile(r"[^A-Za-z0-9._-]")


def warn_and_pass(reason: str) -> int:
    print(f"[human-wip-guard] {reason}（判定不能のため素通し——所有権ガード §2c は fail-open 側）",
          file=sys.stderr)
    return 0


def local_rel_candidate(root: str, file_path: str) -> str | None:
    """git を呼ばずに求める、baseline 照合用の暫定相対パス（POSIX区切り）。

    解決できない・root の外 等は None を返し、呼び出し側は git ベースの本来経路へ
    フォールバックする（見逃しの方向にしか倒れない——§2c は fail-open）。
    """
    try:
        rel = Path(file_path).resolve().relative_to(Path(root).resolve())
    except (OSError, ValueError):
        return None
    return rel.as_posix()


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

    file_path = (payload.get("tool_input") or {}).get("file_path") or ""
    session_id_raw = payload.get("session_id") or ""
    if not file_path:
        return 0
    session_id = SESSION_ID_ALLOWED.sub("", session_id_raw) or "unknown"

    root = resolve_root()
    if not root or not os.path.isdir(root):
        return warn_and_pass("リポジトリルートを解決できない")

    baseline_file = session_dir(root) / f"{session_id}.baseline"
    if not baseline_file.is_file() or not os.access(baseline_file, os.R_OK):
        return warn_and_pass(
            f"baseline が無い（SessionStart フック未発火か保存失敗: {session_id}.baseline）")

    try:
        raw_lines = baseline_file.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return warn_and_pass(f"baseline を読めない: {session_id}.baseline")
    # `#` 始まりは v2.29 で追加されたメタデータ行（source/ts の診断用ヘッダー。
    # session_baseline.py と対で改修 — §7.4）。パス比較の対象からは除外する。
    baseline_lines = [ln for ln in raw_lines if ln and not ln.startswith("#")]
    if not baseline_lines:
        return 0  # セッション開始時点でクリーン＝守る対象が無い（git を呼ぶ必要が無い）

    # ---- 条件(A) を先に見る（git 不要）: 明らかに baseline 非該当なら即抜ける ----
    # candidate が None（root 外・解決不能）の時だけ、確認のため下の git 経路へ進む。
    candidate = local_rel_candidate(root, file_path)
    if candidate is not None and candidate not in baseline_lines:
        return 0

    # ---- ここから先は「baseline 該当の疑いがある」少数派のみ: 条件(B) を git で確認 ----
    try:
        proc = subprocess.run(["git", "-C", root, "status", "--porcelain", "--", file_path],
                               capture_output=True, timeout=30)
    except OSError:
        return 0
    if proc.returncode != 0:
        return 0
    lines = proc.stdout.decode("utf-8", "replace").splitlines()
    if not lines:
        return 0  # いまクリーン（or 未作成）＝人間のWIPは残っていない
    status_line = lines[0]

    rel = status_line[3:] if len(status_line) > 3 else ""
    if " -> " in rel:
        rel = rel.split(" -> ", 1)[1]  # リネーム行は現行側のパス（近似 — §7.4 の流儀）
    if not rel:
        return 0

    if rel in baseline_lines:
        print(f"ブロック: このファイルにはセッション開始時点から人間の未コミット変更がある: "
              f"{rel}（.guardrails/GUARDRAILS.md §2c 所有権ガード）。人間と AI の変更が混ざった diff は"
              "原因追跡不能の温床。人間が commit / stash すれば自動的に解除される——AI 側から"
              "退避コマンドで消すのは §2 作業消失ガードが別途ブロックする。", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException as exc:  # §2c は fail-open——想定外エラーも exit 0（迂回防止とは非対称）
        print(f"[human-wip-guard] 内部エラーのため素通し: {exc!r}"
              "（判定不能のため素通し——所有権ガード §2c は fail-open 側）", file=sys.stderr)
        sys.exit(0)
