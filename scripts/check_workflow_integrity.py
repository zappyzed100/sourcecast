# check_workflow_integrity.py — base branch から PR 側 CI workflow の不変条件を検査する
"""PR が required workflow 自体を骨抜きにする経路を、base 側の信頼済みコードで止める。

``pull_request_target`` はこのスクリプトを既定ブランチから実行し、PR head は checkout も
実行もせず ``git show`` のデータとしてだけ読む。信頼の根 ``guardrails-trusted.yml`` と
本ファイルと CI workflow 全体は base と head のバイト一致を要求する。更新時は人間が PR をレビューした上で
一時的に required context を外し、PR 経由で更新して直ちに戻す（直接 push はしない）。
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import repo_scan as rs

CI = ".github/workflows/guardrails-ci.yml"
TRUSTED = ".github/workflows/guardrails-trusted.yml"
CODEOWNERS = ".github/CODEOWNERS"
SELF = "scripts/check_workflow_integrity.py"
TRUST_ROOTS = (TRUSTED, SELF, CI, CODEOWNERS)


def changed_trust_roots(base: dict[str, str], head: dict[str, str]) -> list[str]:
    """PR自身が変更した信頼の根を列挙する（全体byte固定）。"""
    return [rel for rel in TRUST_ROOTS if base.get(rel) != head.get(rel)]


def _blob(root: Path, rev: str, rel: str) -> str:
    proc = subprocess.run(["git", "-C", str(root), "show", f"{rev}:{rel}"],
                          capture_output=True, check=False)
    if proc.returncode != 0:
        raise rs.ScanError(f"{rev[:20]}:{rel} を読めない（信頼済みworkflowの削除/参照失敗）")
    return proc.stdout.decode("utf-8", "replace")


def _live(block: str) -> list[str]:
    return [line.strip() for line in block.splitlines()
            if line.strip() and not line.lstrip().startswith("#")]


def _values(block: str, marker: str) -> list[str]:
    prefix = f"- {marker}:"
    values: list[str] = []
    for line in _live(block):
        if not line.startswith(prefix):
            continue
        value = line[len(prefix):].strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        values.append(value)
    return values


def _trigger_keys(text: str) -> set[str]:
    keys: set[str] = set()
    for line in rs.yaml_top_block(text, "on"):
        if line.startswith("  ") and not line.startswith("    "):
            key = line.strip().split(":", 1)[0]
            if key:
                keys.add(key)
    return keys


def validate_ci(text: str) -> list[str]:
    fails: list[str] = []
    triggers = _trigger_keys(text)
    for trigger in ("push", "pull_request"):
        if trigger not in triggers:
            fails.append(f"{CI}: on.{trigger} が無い")
    blocks = rs.workflow_job_blocks(text)
    specs = {
        "checks": {
            "uses": ["actions/checkout@v4", "astral-sh/setup-uv@v5", "actions/cache@v4"],
            "runs": ["uvx pre-commit run --all-files --show-diff-on-failure"],
            "ifs": [],
        },
        "red-first": {
            "uses": ["actions/checkout@v4", "astral-sh/setup-uv@v5"],
            "runs": ['uv run scripts/check_red_first.py --base "${{ github.event.pull_request.base.sha }}"'],
            "ifs": ["if: github.event_name == 'pull_request'"],
        },
        "commit-msg-history": {
            "uses": ["actions/checkout@v4", "astral-sh/setup-uv@v5"],
            "runs": ['uv run scripts/check_commit_msg.py --base "${{ github.event.pull_request.base.sha }}"'],
            "ifs": ["if: github.event_name == 'pull_request'"],
        },
    }
    for job, spec in specs.items():
        block = blocks.get(job)
        if block is None:
            fails.append(f"{CI}: 必須 job {job} が無い")
            continue
        live = _live(block)
        if _values(block, "uses") != spec["uses"]:
            fails.append(f"{CI}: {job} の uses が信頼済み構成と不一致")
        if _values(block, "run") != spec["runs"]:
            fails.append(f"{CI}: {job} の run が信頼済み構成と不一致")
        if [line for line in live if line.startswith("if:")] != spec["ifs"]:
            fails.append(f"{CI}: {job} の if が信頼済み構成と不一致")
        if any(line.startswith(("continue-on-error:", "permissions:", "shell:")) for line in live):
            fails.append(f"{CI}: {job} に判定を弱める属性がある")
        if job in {"red-first", "commit-msg-history"} and not any(
            line.startswith("fetch-depth: 0") for line in live
        ):
            fails.append(f"{CI}: {job} に fetch-depth: 0 が無い")
    return fails


def verify_scenarios(root: Path) -> int:
    original = rs.read_text(root, CI)
    cases = [
        ("正常", original, 0),
        ("checks削除", original.replace("  checks:\n", "  checks-removed:\n", 1), 1),
        ("checks素通し", original.replace("      - run: uvx pre-commit run --all-files --show-diff-on-failure",
                                          "      - run: true", 1), 1),
        ("continue-on-error", original.replace("  checks:\n", "  checks:\n    continue-on-error: true\n", 1), 1),
        ("pull_request削除", original.replace("  pull_request:\n", "", 1), 1),
    ]
    bad = 0
    for name, text, minimum in cases:
        got = len(validate_ci(text))
        if got < minimum:
            bad += 1
            print(f"HARD:workflow-integrity-scenario {name}: 期待fail>={minimum}・実際{got}",
                  file=sys.stderr)
    base = {rel: rs.read_text(root, rel) for rel in TRUST_ROOTS}
    for name, rel in (("trusted workflow改変", TRUSTED), ("言語jobを含むCI全体改変", CI),
                      ("CODEOWNERS改変", CODEOWNERS)):
        head = dict(base)
        head[rel] += "\n# malicious weakening\n"
        if rel not in changed_trust_roots(base, head):
            bad += 1
            print(f"HARD:workflow-integrity-scenario {name}: 信頼の根の変更を検出しない",
                  file=sys.stderr)
    if bad:
        return 1
    print(f"[workflow-integrity] verify シナリオ 全{len(cases) + 3}本 PASS")
    return 0


def main(argv: list[str]) -> int:
    rs.reconfigure_stdio()
    ap = argparse.ArgumentParser()
    ap.add_argument("--base")
    ap.add_argument("--head")
    ap.add_argument("--verify-scenarios", action="store_true")
    args = ap.parse_args(argv)
    root = rs.repo_root()
    if args.verify_scenarios:
        return verify_scenarios(root)
    if bool(args.base) != bool(args.head):
        raise rs.ScanError("--base と --head は同時に指定する")
    if args.head:
        base_blobs = {rel: _blob(root, args.base, rel) for rel in TRUST_ROOTS}
        head_blobs = {rel: _blob(root, args.head, rel) for rel in TRUST_ROOTS}
        changed = changed_trust_roots(base_blobs, head_blobs)
        for rel in changed:
                print(f"HARD:workflow-trust-root-changed {rel} workflowの信頼の根はPR自身では変更できない。"
                      "人間レビュー後に required context を一時解除してPRマージし、直ちに戻す",
                      file=sys.stderr)
        if changed:
            return 1
        ci_text = head_blobs[CI]
    else:
        ci_text = rs.read_text(root, CI)
    fails = validate_ci(ci_text)
    for message in fails:
        print(f"HARD:workflow-integrity {message}", file=sys.stderr)
    if fails:
        return 1
    print("[workflow-integrity] PASS")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except rs.ScanError as exc:
        print(f"check_workflow_integrity: 内部エラー: {exc}", file=sys.stderr)
        sys.exit(2)
    except Exception as exc:
        print(f"check_workflow_integrity: 内部エラー: {exc!r}", file=sys.stderr)
        sys.exit(2)
