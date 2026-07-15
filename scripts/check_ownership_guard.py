# check_ownership_guard.py — 所有権ガード(§2c)の回帰シナリオ再生（契約: .guardrails/GUARDRAILS.md §2c）
#
# 呼び出し（§7.1: 必ず uv 経由）: uv run scripts/check_ownership_guard.py
#   exit 0 = 全シナリオ一致 / exit 1 = 不一致あり（1違反1行）/ exit 2 = 内部エラー
#
# §2 の guard_git_bypass.py 用コーパス（tests/guard_corpus.tsv・1行=1コマンド）とは違い、
# 所有権ガードは「SessionStart → (作業ツリーの変化) → SessionStart → PreToolUse」という
# 複数手順そのものが検査対象で、TSV1行では表現できない。シナリオはこのファイルへ直接
# Python関数として書く（GUARDRAILS.md §2c「コーパス化は §10 の保留」の解消 — G10）。
#
# 各シナリオは一時 git リポジトリ上で session_baseline.py（SessionStart）と
# guard_human_wip.py（PreToolUse）を本番と同じ stdin JSON 経由で呼ぶ。
#
# v2.29（G10・実機事故の再発防止）: source を見ずに compact でも baseline を無条件に
# 書き直し、AI 自身の未コミット作業を人間 WIP と誤認してブロックし続ける事故が実機で
# 起きたが、§2c には自動テストが無く検出できなかった。scenario_compact_skips_rebaseline
# がその直接の回帰テスト。

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import repo_scan as rs  # noqa: E402

SESSION_BASELINE_REL = ".claude/hooks/session_baseline.py"
GUARD_HUMAN_WIP_REL = ".claude/hooks/guard_human_wip.py"
TIMEOUT_SEC = 30


class Repo:
    """シナリオ用の使い捨て git リポジトリ（フィクスチャ）。"""

    def __init__(self, root: Path, kit_root: Path):
        self.root = root
        self.kit_root = kit_root
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        self.env["CLAUDE_PROJECT_DIR"] = str(root)

    def _git(self, *args: str) -> None:
        proc = subprocess.run(["git", "-C", str(self.root), *args],
                              capture_output=True, env=self.env)
        if proc.returncode != 0:
            raise rs.ScanError(f"フィクスチャ git 失敗: git {' '.join(args)}: "
                               f"{proc.stderr.decode('utf-8', 'replace').strip()}")

    def write(self, rel: str, content: str) -> Path:
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8", newline="\n")
        return p

    def commit_all(self, msg: str) -> None:
        self._git("add", "-A")
        self._git("commit", "-q", "-m", msg)

    def session_start(self, session_id: str, source: str) -> None:
        script = self.kit_root / SESSION_BASELINE_REL
        payload = json.dumps({"session_id": session_id, "source": source}, ensure_ascii=False)
        try:
            proc = subprocess.run([sys.executable, str(script)], input=payload.encode("utf-8"),
                                  capture_output=True, cwd=str(self.root), env=self.env,
                                  timeout=TIMEOUT_SEC)
        except subprocess.TimeoutExpired:
            raise rs.ScanError(f"session_baseline.py が {TIMEOUT_SEC} 秒以内に返らない")
        if proc.returncode != 0:
            raise rs.ScanError(f"session_baseline.py が契約外の終了コード {proc.returncode}: "
                               f"{proc.stderr.decode('utf-8', 'replace').strip()}")

    def edit(self, session_id: str, file_path: Path) -> str:
        script = self.kit_root / GUARD_HUMAN_WIP_REL
        payload = json.dumps({"session_id": session_id,
                              "tool_input": {"file_path": str(file_path)}}, ensure_ascii=False)
        try:
            proc = subprocess.run([sys.executable, str(script)], input=payload.encode("utf-8"),
                                  capture_output=True, cwd=str(self.root), env=self.env,
                                  timeout=TIMEOUT_SEC)
        except subprocess.TimeoutExpired:
            raise rs.ScanError(f"guard_human_wip.py が {TIMEOUT_SEC} 秒以内に返らない")
        if proc.returncode == 2:
            return "DENY"
        if proc.returncode == 0:
            return "ALLOW"
        raise rs.ScanError(f"guard_human_wip.py が契約外の終了コード {proc.returncode}")


def _init_repo(base: Path, kit_root: Path, name: str) -> Repo:
    d = base / name
    d.mkdir()
    r = Repo(d, kit_root)
    r._git("init", "-q")
    r._git("config", "user.email", "corpus@example.invalid")
    r._git("config", "user.name", "ownership-guard-corpus")
    r._git("config", "commit.gpgsign", "false")
    r.write("README.md", "seed\n")
    r.commit_all("init")
    return r


def scenario_clean_start_allows_new_file(repo: Repo) -> str | None:
    repo.session_start("s-clean", "startup")
    target = repo.write("new.txt", "hi\n")
    actual = repo.edit("s-clean", target)
    if actual != "ALLOW":
        return f"期待ALLOW 実際{actual}"
    return None


def scenario_human_wip_blocks_edit(repo: Repo) -> str | None:
    target = repo.write("human.txt", "human edit\n")  # startup前からdirty＝人間のWIP
    repo.session_start("s-humanwip", "startup")
    actual = repo.edit("s-humanwip", target)
    if actual != "DENY":
        return f"期待DENY 実際{actual}"
    return None


def scenario_human_wip_commit_lifts_block(repo: Repo) -> str | None:
    target = repo.write("human2.txt", "human edit\n")
    repo.session_start("s-humanwip-commit", "startup")
    repo.commit_all("human commits their own file")  # (B)が外れる
    actual = repo.edit("s-humanwip-commit", target)
    if actual != "ALLOW":
        return f"期待ALLOW 実際{actual}"
    return None


def scenario_compact_skips_rebaseline(repo: Repo) -> str | None:
    """v2.29の実機事故そのものの回帰テスト: compactがAI自身のWIPを人間WIPと誤認しないこと。"""
    repo.session_start("s-compact", "startup")  # cleanなのでbaselineは空
    target = repo.write("ai_work.tsx", "ai wip\n")  # AI自身が書きかけ・未コミット
    repo.session_start("s-compact", "compact")  # ここで誤ってbaselineへ焼き付いたら退行
    actual = repo.edit("s-compact", target)
    if actual != "ALLOW":
        return f"期待ALLOW 実際{actual}（compactがAI自身のWIPを人間WIPと誤認＝v2.29の退行）"
    return None


def scenario_compact_preserves_existing_human_baseline(repo: Repo) -> str | None:
    human_file = repo.write("human3.txt", "human pre-existing wip\n")  # startup前からdirty
    repo.session_start("s-compact-preserve", "startup")  # baselineがhuman3.txtを捕捉
    ai_file = repo.write("ai_work2.tsx", "ai wip\n")  # startup後にAIが作った新規dirty
    repo.session_start("s-compact-preserve", "compact")  # 書き直さない＝両方の性質が保たれるはず
    actual_human = repo.edit("s-compact-preserve", human_file)
    if actual_human != "DENY":
        return f"人間WIP(human3.txt)の保護が消えた: 期待DENY 実際{actual_human}"
    actual_ai = repo.edit("s-compact-preserve", ai_file)
    if actual_ai != "ALLOW":
        return f"AI自身のWIP(ai_work2.tsx)が誤って保護対象になった: 期待ALLOW 実際{actual_ai}"
    return None


def scenario_unknown_source_falls_back_to_rebaseline(repo: Repo) -> str | None:
    """source不明/想定外は安全側（従来通りbaseline再取得）に倒れることの確認。"""
    repo.session_start("s-unknown-source", "startup")
    target = repo.write("ai_work3.tsx", "wip\n")
    repo.session_start("s-unknown-source", "some-future-source")  # 未知値→従来通り再baseline
    actual = repo.edit("s-unknown-source", target)
    if actual != "DENY":
        return f"期待DENY 実際{actual}（source不明時のfail-safeフォールバックが崩れている）"
    return None


SCENARIOS: list[tuple[str, Callable[[Repo], str | None]]] = [
    ("clean_start_allows_new_file", scenario_clean_start_allows_new_file),
    ("human_wip_blocks_edit", scenario_human_wip_blocks_edit),
    ("human_wip_commit_lifts_block", scenario_human_wip_commit_lifts_block),
    ("compact_skips_rebaseline", scenario_compact_skips_rebaseline),
    ("compact_preserves_existing_human_baseline", scenario_compact_preserves_existing_human_baseline),
    ("unknown_source_falls_back_to_rebaseline", scenario_unknown_source_falls_back_to_rebaseline),
]


def main() -> int:
    rs.reconfigure_stdio()
    kit_root = rs.repo_root()
    baseline_script = kit_root / SESSION_BASELINE_REL
    guard_script = kit_root / GUARD_HUMAN_WIP_REL
    if not baseline_script.is_file() or not guard_script.is_file():
        raise rs.ScanError("所有権ガード本体が無い（§2c。missing-required でも検出される）")

    mismatches = 0
    with tempfile.TemporaryDirectory(prefix="ownership-guard-") as tmp:
        base = Path(tmp)
        for name, fn in SCENARIOS:
            repo = _init_repo(base, kit_root, name)
            problem = fn(repo)
            if problem is not None:
                mismatches += 1
                print(f"HARD:ownership-guard-corpus-mismatch {name}: {problem}", file=sys.stderr)

    if mismatches:
        print(f"\ncheck-ownership-guard: 不一致 {mismatches} 件/{len(SCENARIOS)} シナリオ。"
              "所有権ガードの改修が過去に塞いだ誤検知・見逃しを開け直していないか、"
              "session_baseline.py・guard_human_wip.py（.guardrails/GUARDRAILS.md §2c）"
              "を同一コミットで揃える。", file=sys.stderr)
        return 1
    print(f"[ownership-guard] 全{len(SCENARIOS)}シナリオ PASS")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except rs.ScanError as exc:
        print(f"check_ownership_guard: 内部エラー: {exc}", file=sys.stderr)
        sys.exit(2)
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as exc:  # 想定外も exit 2（§7.5 と同義。exit 1 は不一致に予約）
        print(f"check_ownership_guard: 内部エラー: {exc!r}", file=sys.stderr)
        sys.exit(2)
