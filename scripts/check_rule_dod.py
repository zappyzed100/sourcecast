# check_rule_dod.py — 列の違反注入コーパスを再生し、各規則が実際に発火することを機械証明する（契約: .guardrails/GUARDRAILS.md §11 Step 2・Phase 47）
"""check_rule_dod.py — 規則DoD（違反注入→発火→除去→沈黙）の自動再生器。

導入 Step の DoD「わざと違反して落ちるのを見届ける」（§0）を、エージェントの手作業から
コーパス再生へ移す。guard コーパス（§2——門番の回帰）の構造検査・commit-msg 検査版。

使い方: uv run scripts/check_rule_dod.py [列ID]
  読み込むコーパス（両方あれば両方）:
    tests/injections/common.json   … 言語なしで発火する規則（常に読み込む）
    tests/injections/<列ID>.json   … 列固有（列ID 省略時は BINDING-SOURCE 刻印から解決）
  ケースの書式:
    {"rule","severity","stage"("check"|"commit"・既定 check),
     "path"+"content" または "files":{path:content},
     "msg"(commit 段の件名・本文), "requires":[バインディング変数名]（いずれか充填で実行）}

再生手順:
  check 段  … 基準線 → 全ケース一括で書き込み・git add → check_structure 1回 →
              各 `<severity>:<rule>` の存在を検証 → 除去 → 基準線へ戻ることを確認
  commit 段 … 1ケースずつ隔離（stage → check_commit_msg.py 直接呼び出し → unstage）。
              既にステージ済みの変更があれば commit 段は SKIP（混線防止・表示つき）

安全側の既定: 注入先パスが既に存在するケースは SKIP(exists)（既存ファイルを上書きしない）。
requires 未充填のケースは SKIP(unfilled)（不発の規則を PASS と偽らない — G9）。

出力: 1行1ケース `DOD:PASS/FAIL/SKIP <rule>`（G4）。
exit: 0 = FAIL なし（コーパス無しは表示つき素通し——DoD 道具であり門ではない） /
      1 = FAIL あり・採用列コーパス欠落 / 2 = 内部エラー。
Windows 絶対規則（§7.2）: encoding/newline 明示・shell 非経由。
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import repo_scan as rs  # noqa: E402

COMMON_CORPUS = "tests/injections/common.json"


def run_check(root: Path) -> str:
    proc = subprocess.run(
        ["uv", "run", "scripts/check_structure.py"], cwd=str(root),
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    return (proc.stdout or "") + (proc.stderr or "")


def run_commit_msg(root: Path, msg: str) -> tuple[int, str]:
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n",
                                     suffix=".txt", delete=False) as f:
        f.write(msg + "\n")
        msg_path = f.name
    try:
        proc = subprocess.run(
            ["uv", "run", "scripts/check_commit_msg.py", msg_path], cwd=str(root),
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        return proc.returncode, (proc.stdout or "") + (proc.stderr or "")
    finally:
        try:
            Path(msg_path).unlink()
        except OSError:
            pass


def git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(root), *args],
                          capture_output=True, text=True, encoding="utf-8", errors="replace")


def resolve_column(root: Path) -> str | None:
    text = rs.read_text(root, "scripts/repo_scan.py")
    m = rs.BINDING_SOURCE_PATTERN.search(text)
    return m.group(1).split("@", 1)[0] if m else None


def case_files(case: dict) -> dict[str, str]:
    if "files" in case:
        return dict(case["files"])
    return {case["path"]: case["content"]}


def requires_met(case: dict) -> bool:
    names = case.get("requires")
    if not names:
        return True
    return any(getattr(rs, n, None) for n in names)


def write_files(root: Path, files: dict[str, str]) -> None:
    for rel, content in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)


def remove_files(root: Path, files: dict[str, str], out_fail: list[str]) -> None:
    rels = list(files)
    git(root, "rm", "-q", "--cached", "-f", "--ignore-unmatch", "--", *rels)
    for rel in rels:
        p = root / rel
        try:
            p.unlink()
        except OSError as exc:
            out_fail.append(f"後片付け失敗 {rel}: {exc}")
        # 注入で作ったディレクトリの残骸は空なら畳む（git は空ディレクトリを追跡しない）
        parent = p.parent
        while parent != root:
            try:
                parent.rmdir()
            except OSError:
                break
            parent = parent.parent


def token_of(case: dict) -> str:
    return f"{case['severity']}:{case['rule']}"


def main(argv: list[str]) -> int:
    rs.reconfigure_stdio()
    root = rs.repo_root()
    corpora: list[dict] = []
    common = root / COMMON_CORPUS
    if common.is_file():
        corpora.append(json.loads(common.read_text(encoding="utf-8")))
    column = argv[0] if argv else resolve_column(root)
    if column:
        col_path = root / f"tests/injections/{column}.json"
        if col_path.is_file():
            corpora.append(json.loads(col_path.read_text(encoding="utf-8")))
        else:
            print(f"[rule-dod] 列コーパス未同梱: tests/injections/{column}.json"
                  "（新規列はコーパス追加まで未完了——G9/G13）")
            return 1
    else:
        print("[rule-dod] 列は未解決（BINDING-SOURCE 未刻印・引数なし）——共通コーパスのみ再生")
    if not corpora:
        print("[rule-dod] コーパスが1つも無い——表示つき素通し（門ではない）")
        return 0

    cases = [c for corpus in corpora for c in corpus.get("cases", [])]
    if not cases:
        print("INTERNAL コーパスが空")
        return 2

    runnable: list[dict] = []
    for c in cases:
        if not requires_met(c):
            print(f"DOD:SKIP {c['rule']} (requires 未充填: {'/'.join(c['requires'])} — "
                  "充填後に再実行で有効化)")
            continue
        exists = [rel for rel in case_files(c) if (root / rel).exists()]
        if exists:
            print(f"DOD:SKIP {c['rule']} (注入先が既に存在: {exists[0]} — 上書きしない)")
            continue
        runnable.append(c)

    failed = False
    cleanup_errors: list[str] = []

    # --- check 段（一括・2回の実行に束ねる — §7.7）---
    check_cases = [c for c in runnable if c.get("stage", "check") == "check"]
    if check_cases:
        baseline = run_check(root)
        attributable = []
        for c in check_cases:
            if token_of(c) in baseline:
                print(f"DOD:SKIP {c['rule']} (基準線で既に発火——帰属不能。既存違反を先に解消)")
            else:
                attributable.append(c)
        all_files: dict[str, str] = {}
        for c in attributable:
            all_files.update(case_files(c))
        if attributable:
            try:
                write_files(root, all_files)
                add = git(root, "add", "-f", "--", *all_files)
                if add.returncode != 0:
                    print(f"INTERNAL git add 失敗: {add.stderr.strip()}")
                    return 2
                injected = run_check(root)
                for c in attributable:
                    ok = token_of(c) in injected
                    print(f"DOD:{'PASS' if ok else 'FAIL'} {c['rule']} "
                          f"({token_of(c)} が{'発火' if ok else '不発——充填/区画を確認'})")
                    failed |= not ok
            finally:
                remove_files(root, all_files, cleanup_errors)
            after = run_check(root)
            leftover = sorted(t for t in {token_of(c) for c in attributable} if t in after)
            if leftover:
                print(f"DOD:FAIL 除去後も発火が残る: {', '.join(leftover)}")
                failed = True

    # --- commit 段（1ケースずつ隔離）---
    commit_cases = [c for c in runnable if c.get("stage") == "commit"]
    if commit_cases:
        staged = git(root, "diff", "--cached", "--quiet")
        if staged.returncode != 0:
            for c in commit_cases:
                print(f"DOD:SKIP {c['rule']} (既にステージ済みの変更がある——commit 段は"
                      "クリーンな index でのみ再生。commit/stash 後に再実行)")
        else:
            for c in commit_cases:
                files = case_files(c)
                try:
                    write_files(root, files)
                    add = git(root, "add", "-f", "--", *files)
                    if add.returncode != 0:
                        print(f"INTERNAL git add 失敗: {add.stderr.strip()}")
                        return 2
                    rc, out = run_commit_msg(root, c["msg"])
                    ok = token_of(c) in out
                    if c["severity"] == "HARD":
                        ok = ok and rc != 0
                    print(f"DOD:{'PASS' if ok else 'FAIL'} {c['rule']} "
                          f"({token_of(c)} が{'発火' if ok else '不発——充填/前提を確認'}"
                          f"・rc={rc})")
                    failed |= not ok
                finally:
                    remove_files(root, files, cleanup_errors)

    for e in cleanup_errors:
        print(f"[rule-dod] {e}（手で削除する）", file=sys.stderr)
    failed |= bool(cleanup_errors)

    n = len(cases)
    if failed:
        print(f"\nrule-dod: FAIL あり（{n} ケース中）——不発の規則は充填値と管理区画を確認")
        return 1
    print(f"\nrule-dod: FAIL 0（{n} ケース——注入→発火→除去→沈黙を実測。完了=実行結果 §0）")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except rs.ScanError as exc:
        print(f"rule-dod: 内部エラー: {exc}", file=sys.stderr)
        sys.exit(2)
    except Exception as exc:  # 内部エラーは exit 2（§7.5）
        print(f"INTERNAL {type(exc).__name__}: {exc}")
        sys.exit(2)
