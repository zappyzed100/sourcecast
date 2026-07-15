# guard_git_bypass.py — git の --no-verify/-n・SKIP=・--force/-f push・core.hooksPath 迂回・.git/hooks/ シムの改変除去、および非可逆な作業消失（rm -rf .git／dirty での reset --hard 等）を exit 2 でブロック（正本: .guardrails/GUARDRAILS.md §2）
#
# 呼び出し（PreToolUse: Bash。settings.json 側で `uv run python` 経由——§7.1）。
# PreToolUse(Bash) の仕様: ブロックできるのは exit 2 **だけ**（exit 1 含む他の非0は素通し）。
# したがって本フック内の想定外エラーもすべて exit 2 に倒す（fail-closed）——これが契約
# （HARNESS-VERIFIED: code.claude.com/docs/en/hooks.md 2026-07-08 — §2d）。
# 引用符の中身（コミットメッセージ等）は判定前に取り除くため、メッセージ文面に
# --no-verify という文字列が入っていても誤検知しない。
#
# v2.23（G11・言語移行）: 旧 bash 実装は1回の呼び出しで jq/grep/sed/tr が最大18回
# 起動し、Windows実機で約1000ms/回かかっていた（v2.22 で bash 組み込み構文へ書き換えて
# 約243ms/回まで縮めたが、jq・sed の2プロセスは残っていた）。JSON解析・正規表現・
# 引用符除去はすべて Python 標準ライブラリで完結するため子プロセスがゼロになり、
# 実測で約80〜120ms/回（コーパス全74行の並列再生で1.3〜2秒——旧bashの5〜8秒から
# 3〜5倍）。bash版にあった「jq 不在時の保守的経路」も不要になった（json は標準
# ライブラリで常に使えるため、精密経路が唯一の経路になる——分岐が1本減り誤りの余地も減る）。
# tests/guard_corpus.tsv 全74行で bash 版との完全一致を確認済み。
#
# 作業消失ガード（v2.5・Phase 14）は同一フック内の関数として実装する（プロセス数を
# 増やさない — G11）。対象は**非可逆な作業消失だけ**——汎用の危険コマンド一覧
# （誤検知の密集地帯）は採らない。ローカルDBの破壊は `reset` 1発で戻る設計（§12.2）
# なので対象外。dirty 条件付き規則の回帰再生はコーパスの前提列（tests/guard_corpus.tsv）。

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone


def _word(w: str) -> re.Pattern[str]:
    """単語境界の判定。bash の `\\b`（GNU grep 拡張）と違い、Python の re は
    POSIX/PCRE 系どちらでも `\\b` を素直にサポートするため、そのまま使ってよい
    （v2.22 で bash 側は MSYS2/Windows の `[[ =~ ]]` が `\\b` 非対応と判明し、
    POSIX標準クラスの自前実装が必要だった——Python では発生しない差）。"""
    return re.compile(rf"\b(?:{w})\b")


WORD_GIT = _word("git")
WORD_PRECOMMIT = _word("pre-commit")
WORD_UNINSTALL = _word("uninstall")
WORD_COMMIT_PUSH = _word("commit|push")
WORD_COMMIT = _word("commit")
WORD_PUSH = _word("push")
WORD_RESET = _word("reset")
WORD_CLEAN = _word("clean")
WORD_CHECKOUT = _word("checkout")
WORD_RESTORE = _word("restore")

RE_HOOKSPATH = re.compile("hookspath", re.IGNORECASE)
RE_GIT_CONFIG_GET = re.compile(r"--get(-all|-regexp)?\b")
# フックシムの改変/除去（v2.46 — §2）: `.git/hooks/` 配下のシムを rm/mv/chmod/ln/tee で
# 消す・無効化する、または `>`（切り詰め）で潰す操作。`pre-commit uninstall` と同じ全ゲート
# 迂回だが「uninstall」の語を使わない経路（`rm .git/hooks/pre-commit` 等）が素通しだった。
# 参照だけ（cat / ls）は素通し——変異動詞か切り詰めリダイレクトを伴う時のみブロック。
RE_HOOKS_SHIM = re.compile(
    r"(?:^|[\s=\"'])(?:\./)?\.git/hooks(?:/|(?=[\s\"']|$))", re.IGNORECASE
)
RE_HOOK_MUTATE = re.compile(
    r"\b(?:rm|mv|cp|chmod|ln|tee|truncate|install|del|erase|copy|move|"
    r"remove-item|move-item|copy-item|rename-item|set-content|clear-content|out-file|new-item)\b",
    re.IGNORECASE,
)
RE_SHELL_LAUNCH = re.compile(r"\b(?:powershell|pwsh|cmd)\b", re.IGNORECASE)
RE_HOOK_REDIRECT = re.compile(r">+\s*(?:\./)?\.git/hooks(?:/|(?=\s|$))", re.IGNORECASE)
CMD_SPLIT = re.compile(r"&&|\|\||;|\|")
RE_SKIP = re.compile(r"(^|[;&|\s])SKIP=")
RE_NFLAG = re.compile(r"(^|\s)-[a-mo-zA-Z]*n[a-zA-Z]*(\s|$)")
RE_FFLAG = re.compile(r"(^|\s)-[a-eg-zA-Z]*f[a-zA-Z]*(\s|$)")
RE_RM_RF = re.compile(r"(^|[;&|\s])rm\s([^;&|]*\s)?-[a-zA-Z]*([rR][a-zA-Z]*f|f[a-zA-Z]*[rR])")
RE_GITDIR = re.compile(r"(^|[\s=/])\.git(/|\s|$)")
RE_GITDIR_QUOTED = re.compile("[\"']\\.git(/|[\"'])")
RE_CHECKOUT_TAIL = re.compile(r"\bcheckout\b[^;&|]*\s\.(\s|$)")
RE_RESTORE_TAIL = re.compile(r"\brestore\b[^;&|]*\s\.(\s|$)")
RE_STAGED = re.compile(r"--staged|(^|\s)-[a-zA-Z]*S")
RE_WORKTREE = re.compile(r"--worktree|(^|\s)-[a-zA-Z]*W")
QUOTE_STRIP = re.compile(r"'[^']*'|\"[^\"]*\"")


class Block(Exception):
    def __init__(self, reason: str, loss: bool = False):
        self.reason = reason
        self.loss = loss


def block(reason: str) -> None:
    raise Block(reason, loss=False)


def block_loss(reason: str) -> None:
    raise Block(reason, loss=True)


def worktree_dirty_or_unknown(project_dir: str) -> bool:
    """未コミットの作業があるか。判定不能（git 不在・リポジトリ外）はブロック側に倒す
    （fail-closed — §2）。クリーンなら False——dirty 条件付き規則は素通しになる。"""
    try:
        proc = subprocess.run(
            ["git", "-C", project_dir, "status", "--porcelain"],
            capture_output=True, timeout=30,
        )
    except OSError:
        return True
    if proc.returncode != 0:
        return True
    return bool(proc.stdout.strip())


def check(cmd: str) -> None:
    no_newlines = cmd.replace("\n", " ")
    stripped = QUOTE_STRIP.sub("", no_newlines)
    # Windows の `\` と重複 `/` を正規化してからパスを判定する。シェルが異なっても
    # `.git/hooks` は同じ実体であり、表記差を迂回路にしない（§2・G7）。
    normalized = re.sub(r"/+", "/", stripped.replace("\\", "/"))
    raw_normalized = re.sub(r"/+", "/", no_newlines.replace("\\", "/"))
    # v2.28: 全フック迂回とcommit/push系はセグメント（&&/||/;/|区切り）単位で判定する。
    # 全文字列を1本の対象として見ると、無関係なセグメントに散らばった部分文字列同士が
    # 組み合わさって誤検知する（実測2件: `git config --get core.hooksPath` が
    # `--get` を見ずに即ブロックされていた／`find . -newer X` の `-newer` が
    # 「-n(--no-verify)」に誤検知され、同一コマンド内の無関係な "pre-commit" という
    # 文字列が `\bcommit\b` に一致してしまい発火していた）。セグメント単位にしても
    # 実コマンドは1セグメント内で完結する（`git commit -n` を `&&` 等で分割して書く
    # ことに実用上の意味は無い）ため、本来の検知力は落ちない——過剰ブロックの緩和のみ。
    segments = CMD_SPLIT.split(normalized)

    # 全フック迂回: core.hooksPath の付け替え（`git config core.hooksPath …`・
    # `git -c core.hooksPath=…`）。フック本体ごと差し替えれば --no-verify 検査は
    # 無意味になるため、git を含むコマンドでの言及自体をブロックする
    # （キー名は git 仕様どおり大文字小文字非区別で判定・過剰ブロック側に倒す）。
    # `--get`/`--get-all`/`--get-regexp` を伴う読み取り専用の照会は除外する
    # （同一セグメント内に限定——無関係なセグメントの `--get` では免除しない）。
    for seg in segments:
        if WORD_GIT.search(seg) and RE_HOOKSPATH.search(seg) and not RE_GIT_CONFIG_GET.search(seg):
            block("core.hooksPath の変更（フック本体の付け替え）")

    # 全フック迂回: pre-commit uninstall（シムの取り外し）。settings.json の deny は
    # 前方一致のみで `cd x && pre-commit uninstall`・`uvx pre-commit uninstall`・
    # `uv tool uninstall pre-commit` を通してしまう——引数順・経由の迂回を塞ぐのは
    # 主防壁の責務（--force と同じ二重構造）。
    if WORD_PRECOMMIT.search(stripped) and WORD_UNINSTALL.search(stripped):
        block("pre-commit uninstall（フックシムの取り外し）")

    # 全フック迂回: シムの直接改変/除去（v2.46）。`pre-commit uninstall` を使わずに
    # `.git/hooks/` 配下のシムを消す・上書きする・無効化する経路を塞ぐ。参照（cat/ls）は
    # 通し、変異動詞（rm/mv/chmod/ln/tee/truncate）か切り詰めリダイレクト（`> .git/hooks/…`）
    # を伴う時だけブロックする。`pre-commit install`（語に .git/hooks/ を含まない正規の
    # 再導入）は素通し。
    for raw_seg in CMD_SPLIT.split(raw_normalized):
        code_seg = QUOTE_STRIP.sub("", raw_seg)
        if RE_HOOK_REDIRECT.search(code_seg) or (
            RE_HOOKS_SHIM.search(raw_seg) and RE_HOOK_MUTATE.search(code_seg)
        ) or (
            RE_SHELL_LAUNCH.search(code_seg) and RE_HOOKS_SHIM.search(raw_seg)
            and RE_HOOK_MUTATE.search(raw_seg)
        ):
            block(".git/hooks/ 配下のフックシムの改変/除去（pre-commit uninstall と同じ全ゲート迂回）")

    for seg in segments:
        if WORD_GIT.search(seg) and WORD_COMMIT_PUSH.search(seg):
            if "--no-verify" in seg:
                block("--no-verify")
            if RE_SKIP.search(seg):
                block("SKIP=")
            # git commit の -n / 結合短フラグ内の n も --no-verify の別名
            if WORD_COMMIT.search(seg) and RE_NFLAG.search(seg):
                block("-n (--no-verify の別名)")
            # force push（--force / --force-with-lease / -f / 結合短フラグ内の f）。
            # settings.json の deny は前方一致のみで、引数順を変えた `git push origin -f` を
            # 通してしまう——引数順の迂回を塞ぐのは主防壁であるこのフックの責務。
            if WORD_PUSH.search(seg):
                if "--force" in seg:
                    block("--force push（--force-with-lease 含む。履歴を書き換えない）")
                if RE_FFLAG.search(seg):
                    block("-f (--force の別名)")

    # --- 作業消失ガード（§2・Phase 14 — v2.5）: 非可逆な作業消失だけを塞ぐ ---
    # ① `.git` を含む rm -rf は**常時**ブロック（履歴＝全作業の非可逆な破壊。履歴ごと
    #    消えたら guard もコーパスも無力）。フラグ検出は結合形（-rf/-fr/-Rf/-rvf 等）の
    #    近似——分離形 `rm -r -f` は §7.4「近似は仕様」の範囲外（実測されたらコーパスと
    #    同一コミットで還元する）。引用符で包んだ `.git` は stripped から消えるため、
    #    生コマンド側の引用付きトークンも併せて見る（過剰ブロック側に倒す — §2）。
    if RE_RM_RF.search(stripped):
        if RE_GITDIR.search(stripped) or RE_GITDIR_QUOTED.search(cmd):
            block_loss(".git を含む rm -rf（リポジトリ履歴の非可逆な破壊）は常時ブロック")

    # ② dirty 条件付き: 未コミットの作業がある時だけ、それを消すコマンドをブロックする。
    #    クリーンなら同じコマンドは無害なので素通し（dirty 条件が誤検知をほぼ消す）。
    #    広域判定の `.` は checkout/restore の**後**の単独トークンのみ（`git add .` 等の
    #    複合コマンドで誤検知しない）。`git restore --staged .` はインデックス操作のみで
    #    作業ツリーは無傷のため対象外（--worktree / -W を伴えば対象）。
    if WORD_GIT.search(stripped):
        wipe = ""
        if WORD_RESET.search(stripped) and "--hard" in stripped:
            wipe = "git reset --hard"
        elif WORD_CLEAN.search(stripped) and ("--force" in stripped or RE_FFLAG.search(stripped)):
            wipe = "git clean -f"
        elif WORD_CHECKOUT.search(stripped) and RE_CHECKOUT_TAIL.search(stripped):
            wipe = "広域の git checkout -- ."
        elif WORD_RESTORE.search(stripped) and RE_RESTORE_TAIL.search(stripped):
            if RE_STAGED.search(stripped) and not RE_WORKTREE.search(stripped):
                wipe = ""  # --staged のみ＝インデックス操作。作業ツリーの消失ではない
            else:
                wipe = "広域の git restore ."
        if wipe and worktree_dirty_or_unknown(os.environ.get("CLAUDE_PROJECT_DIR", ".")):
            block_loss(f"未コミット作業がある状態での {wipe}（非可逆な作業消失。"
                       "クリーンなツリーなら素通しになる）")


def record_block(rule_id: str, command: str) -> None:
    """違反ログ（.guardrails/GUARDRAILS.md §3.6 — v2.34）への追記。

    フックは依存ゼロ（標準ライブラリのみ・repo_scan を import しない）が前提のため、
    repo_scan.append_violations と独立の最小実装を持つ（スキーマは同一——変えるときは
    両方を同一コミットで揃える）。コーパス再生・probe（check_guard_corpus.py）は
    GUARDRAILS_LEDGER_SUPPRESS=1 で抑止する——再生のたびに約40行の DENY 期待行が
    「実際の迂回試行」として偽計上されるのを防ぐ。記録失敗は stderr 1行で素通し
    （ブロック判定そのものには影響させない——fail-closed の契約は exit 2 側が担う）。
    """
    if os.environ.get("GUARDRAILS_LEDGER_SUPPRESS"):
        return
    root = os.environ.get("CLAUDE_PROJECT_DIR") or "."
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    try:
        with open(os.path.join(root, ".guardrails", "violations.jsonl"),
                  "a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(
                {"ts": ts, "stage": "guard", "severity": "DENY", "rule_id": rule_id,
                 "location": command[:200]}, ensure_ascii=False) + "\n")
    except OSError as exc:
        print(f"[violation-ledger] 記録失敗（ブロック判定には影響しない）: {exc}", file=sys.stderr)


def main() -> int:
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    raw = sys.stdin.read()
    if not raw:
        return 0
    payload = json.loads(raw) if raw.strip() else {}
    cmd = (payload.get("tool_input") or {}).get("command") or ""
    if not cmd:
        return 0
    try:
        check(cmd)
    except Block as b:
        record_block("work-loss" if b.loss else "git-bypass", cmd)
        prefix = (
            f"ブロック: {b.reason}（.guardrails/GUARDRAILS.md §2 作業消失ガード）。消してよい変更なら"
            "先に commit / stash で退避するのが正規経路。人間の指示によるものなら、その旨を"
            "人間に確認してから人間側の端末で実行する。"
            if b.loss else
            f"ブロック: {b.reason} によるフック迂回は禁止（.guardrails/GUARDRAILS.md §2）。フックが"
            "落ちるなら迂回せず違反そのものを直すこと。2回連続で同じフックが落ちるなら"
            "原因調査に切り替える（ルート AGENTS.md §10-4）。"
        )
        print(prefix, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException as exc:  # fail-closed（§2の契約——想定外エラーも exit 2）
        print(f"guard_git_bypass: フック内部エラーのため fail-closed でブロック"
              f"（.guardrails/GUARDRAILS.md §2）: {exc!r}", file=sys.stderr)
        sys.exit(2)
