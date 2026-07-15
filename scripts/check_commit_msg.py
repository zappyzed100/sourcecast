# check_commit_msg.py — コミットメッセージ検査: 形式 + fix⇔テスト + G引用 + 依存宣言 + feat⇔plan（契約: .guardrails/GUARDRAILS.md §3.4）
#
# 呼び出しは2形態:
#   uv run scripts/check_commit_msg.py <メッセージファイル>
#     commit-msg ステージのフックとして pre-commit から呼ばれる単発形態（§7.6: pass_filenames
#     は既定 true のまま）。ステージ済みの索引（`git diff --cached`）を対象にする。
#   uv run scripts/check_commit_msg.py --base <rev> [--head <rev>]
#     v2.30 新設（G9・下記「commit-msg 系ゲートの CI 実効化」）。base..head の非マージ
#     コミット1つずつを、そのコミットを今まさに作ろうとしている状態（一時 worktree で
#     `git worktree add <sha>` → `git reset --soft <sha>^` により HEAD だけ親へ戻し、
#     index/working tree はそのコミットのスナップショットのまま——「これから commit
#     しようとしている」状態と同一の結果を返す）で再現し、単発形態と全く同じチェック
#     関数を再実行する。コードの二重化はしない。
#   exit 0 = 合格 / exit 1 = 違反 / exit 2 = 内部エラー
#
# 検査1（形式）: 件名が `^(feat|fix|test|docs|refactor|chore): .+` に一致すること。
#   Merge / Revert / fixup! / squash! で始まるものは素通し。
# 検査2（fix ⇔ 回帰テストの対）: `fix:` のとき、ステージ済み変更にテストファイルが
#   1つも無ければ exit 1。テストで再現できない修正は chore / refactor / docs を名乗る。
#   ステージ済み変更が空（メッセージのみの --amend 等）は検査2〜4とも素通し（§3.4）。
#   v2.30（G7・実測で是正）: `TEST_PATH_PATTERNS`（列充填）が空なら不発——検査5/6/7/8の
#   兄弟検査は元から持っていたこのバイパスが検査2だけ抜けていた。列未選択のキット原本
#   自身で「fix: コミットが原理上絶対に通らない」状態を放置していたことが実機で判明した
#   （§3.4 参照）。
#   v2.39（G10・採用先の実測で是正）: テスト同梱の判定を「パス一致（TEST_PATH_PATTERNS）
#   **または** ステージ済み diff の追加行一致（INLINE_TEST_PATTERNS——同一ファイル内
#   `#[cfg(test)]` 形式の言語向け）」の OR へ拡張（検査6も同じ判定を使う）。パス判別のみ
#   だと、インライン形式のファイル単独の fix: が実際にテストを同梱していても誤ブロック
#   される（採用先 Rust リポジトリで実測——テストと生成器をペア修正する限り生成器側の
#   パスが偶然一致して顕在化しなかった）。発火条件も「どちらかのスロットが充填済み」へ拡張。
# 検査4（undeclared-dependency — v2.5・Phase 13）: 依存マニフェスト（正本:
#   repo_scan.DEPENDENCY_MANIFESTS——basename 一致）の依存セクションに HEAD と比べて
#   **追加**された名前があるとき、その名前がメッセージに現れなければ exit 1。
#   依存は増えてよいが、黙って増えてはならない（fix⇔test と同じ「意味論で塞ぐ」設計）。
#   対象外の境界（§3.4）: lockfile（DEPENDENCY_MANIFESTS に載せない）／版更新・削除
#   （名前集合の差分に出ない）／HEAD の無い初回コミット／HEAD に無い新規マニフェスト
#   （ファイル全体が diff で見える＝「黙って」ではない）／解釈不能な構文（警告1行で
#   素通し——行指向の近似は仕様 — §7.4）。名前照合は大文字小文字と -/_ を畳んだ集合差、
#   メッセージ照合は大小無視の部分一致。
# 検査5（feat-without-plan — v2.6 soft 導入・**v2.8 hard 昇格＝G14「意図の保存」**）:
#   `feat:` がレイヤー直下（正本: repo_scan.PLAN_LAYER_ROOTS——列充填・空なら不発）に
#   HEAD に無い新規ディレクトリを作るのに、設計根拠文書（repo_scan.PLAN_DOC_PATTERNS——
#   plan.md / docs/plans/。置き場の規約は AGENTS.md §4）の差分が無ければ exit 1
#   （1ディレクトリ1行）。fix⇔テスト（検査2・G10＝回帰の複利）と対をなす「意図の複利」。
#   逃げ道の意味論は検査2と同一: 根拠を書けない構造変更は feat を名乗らない
#   （refactor / chore）。決定点①は v2.8 で案Aに確定（§10 Phase 19）。

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import repo_scan as rs  # noqa: E402

SUBJECT_FORMAT = re.compile(r"^(feat|fix|test|docs|refactor|chore): .+")
PASS_THROUGH_PREFIXES = ("Merge", "Revert", "fixup!", "squash!")
HISTORY_TIMEOUT_SEC = 60  # 1コミットあたりの保険（ハングした再検査を静かに待たない — G11）

# 検査6（feat-without-test — v2.13・Phase 25・**soft**＝警告のみで通す）:
#   `feat:` でコードファイルに触れるのにテストファイルの変更が無ければ警告1行。
#   出典: 著名ワークフローの収斂（Superpowers の test-driven-development 等——実装前に
#   テスト）。fix⇔テスト（検査2・hard）の feat 版だが、テスト不要な feat（配線のみ・
#   雛形生成）が正当に存在するため soft で観測から始める（昇格トリガーは §10 Phase 25）。
#   TEST_PATH_PATTERNS が空なら不発（列充填で有効化——全 feat が偽陽性になるのを防ぐ）。
# 検査7（commit-too-large — v2.13・Phase 26・**soft**）:
#   純変更行数（追加+削除。生成物・lockfile 除外——数え方の正本は
#   rs.COMMIT_SIZE_SOFT_LIMIT / rs.LOCKFILE_NAMES）が上限超過なら警告1行。
#   大きな塊は検証の追跡可能性を壊す（実行規律2の一般開発版）。
# 検査8（test-shrink — v2.18・Phase 30・**soft**・列充填で有効化）:
#   fix:/feat: でテストファイルの純減（削除行>追加行）なら警告1行。既存テストの弱体化は
#   門を欺く最短路（調査④ Clean Room QA の脅威モデル——red-first が守るのは「新テストが
#   親で赤」まで）。正当な整理も普通に存在するため soft。TEST_PATH_PATTERNS 空なら不発。
# 検査3（governance-without-goal — §3.4・.guardrails/GOALS.md 運用ルールの機械化）:
# 正本3文書をステージしたコミットは、メッセージ本文に「どのGに効くか」の引用が必須。
GOVERNANCE_PATHS = frozenset({".guardrails/GOALS.md", ".guardrails/GUARDRAILS.md", "bindings/catalog.md"})
GOAL_CITATION = re.compile(r"\bG(1[0-4]|[1-9])\b")  # G14 新設と同時改修（v2.8・§10 Phase 19）
_SCISSORS = ">8"  # `git commit -v` の切り取り線以降（diff本体）は本文ではない

# 違反ログ（§3.6 — v2.34）: 単発形態の違反を集めて main() が最後に1回で追記する。
# 履歴再検査（main_history）は記録しない——各コミットの再実行は一時 worktree 内で走り、
# その中の repo_root() は worktree を指すため、ledger ごと worktree と一緒に破棄される
# （過去コミットの再生を「新しい違反事象」として二重計上しない境界が構造的に成立する）。
_VIOLATIONS: list[tuple[str, str, str, str]] = []


def _emit(severity: str, rule_id: str, location: str, message: str) -> None:
    """1違反1行の表示（§3.3 形式）と違反ログ用バッファへの追加を1箇所にする。"""
    print(f"{severity}:{rule_id} ({location}) {message}", file=sys.stderr)
    _VIOLATIONS.append((severity, rule_id, location, message))


def read_message(msg_path: str) -> list[str]:
    """コメント行を除いた本文行。切り取り線（-v の diff）以降は読まない。"""
    out: list[str] = []
    with open(msg_path, "r", encoding="utf-8", errors="replace") as f:
        for line in f.read().splitlines():
            if line.startswith("#"):
                if _SCISSORS in line:
                    break
                continue  # コミットテンプレートのコメント行
            out.append(line)
    return out


def read_subject(msg_path: str) -> str:
    for line in read_message(msg_path):
        if line.strip():
            return line.strip()
    return ""


def staged_files() -> list[str]:
    proc = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "-z"], capture_output=True, check=False
    )
    if proc.returncode != 0:
        raise rs.ScanError("git diff --cached が失敗")
    return [p for p in proc.stdout.decode("utf-8", "replace").split("\0") if p]


def _staged_has_inline_test(staged: list[str]) -> bool:
    """インライン形式（同一ファイル内 `#[cfg(test)]` 等——rs.INLINE_TEST_PATTERNS）の
    テスト同梱を、ステージ済み diff の**追加行**から検出する（v2.39・§3.4 検査2/6）。
    パス判別（rs.is_test_file）と OR で使う。diff の quoted path 等は近似で扱う（§7.4）。"""
    targets = [p for p in staged
               if rs.ext_of(p) in rs.INLINE_TEST_PATTERNS and not rs.is_generated(p)]
    if not targets:
        return False
    proc = subprocess.run(["git", "diff", "--cached", "--unified=0", "--", *targets],
                          capture_output=True, check=False)
    if proc.returncode != 0:
        return False
    current: list[re.Pattern] = []
    for line in proc.stdout.decode("utf-8", "replace").splitlines():
        if line.startswith("+++ "):
            rel = line[4:].strip()
            rel = rel[2:] if rel.startswith("b/") else rel  # "+++ /dev/null"（削除）は拡張子なし
            current = rs.INLINE_TEST_PATTERNS.get(rs.ext_of(rel), [])
        elif line.startswith("+") and current:
            body = line[1:]
            if any(p.search(body) for p in current):
                return True
    return False


def staged_has_test(staged: list[str]) -> bool:
    """検査2/6 の「テスト同梱」判定の正本: テストファイルのパス一致（TEST_PATH_PATTERNS）
    または追加行のインラインテスト一致（INLINE_TEST_PATTERNS）のいずれか。"""
    return any(rs.is_test_file(p) for p in staged) or _staged_has_inline_test(staged)


# --- 検査4（undeclared-dependency）の抽出器 — データの正本は rs.DEPENDENCY_MANIFESTS ---
# いずれも行指向の近似（複数行の凝った書き方は取りこぼし得る——近似は仕様 §7.4）。
_TOML_SECTION_RE = re.compile(r"^\s*\[([^\]]+)\]")
_TOML_KEY_RE = re.compile(r"^\s*([A-Za-z0-9_.-]+)\s*=")
_TOML_ARRAY_OPEN_RE = re.compile(r"^\s*([A-Za-z0-9_-]+)\s*=\s*\[")
_REQ_NAME_RE = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")  # PEP 508 の名前部の近似
_QUOTED_RE = re.compile(r'"([^"]*)"|\'([^\']*)\'')
_YAML_TOP_RE = re.compile(r"^([A-Za-z0-9_]+):")
_YAML_DEP_RE = re.compile(r"^  ([A-Za-z0-9_]+):")


def _dep_names(kind: str, sections: tuple[str, ...], text: str) -> set[str] | None:
    """依存名の集合。解釈不能（構文不正）は None（呼び出し側が警告1行で素通し — §7.4）。"""
    if kind == "json":
        try:
            data = json.loads(text)
        except ValueError:
            return None
        names: set[str] = set()
        if isinstance(data, dict):
            for sec in sections:
                v = data.get(sec)
                if isinstance(v, dict):
                    names |= set(v)
        return names

    if kind == "toml-table":
        # 対象: [dependencies] 直下のキー、および [dependencies.serde] 形式のサブテーブル
        names = set()
        cur = ""
        for raw in text.splitlines():
            line = raw.split("#", 1)[0]
            m = _TOML_SECTION_RE.match(line)
            if m:
                cur = m.group(1).strip()
                for sec in sections:
                    if cur.startswith(sec + "."):
                        names.add(cur[len(sec) + 1:].strip().strip('"'))
                continue
            if cur in sections:
                k = _TOML_KEY_RE.match(line)
                if k:
                    names.add(k.group(1))
        return names

    if kind == "toml-array":
        # 対象: sections = ("project.dependencies",) のような「テーブル.キー = [ 文字列… ]」
        want = {(sec.rpartition(".")[0], sec.rpartition(".")[2]) for sec in sections}
        names = set()
        cur = ""
        in_array = False
        for raw in text.splitlines():
            line = raw.split("#", 1)[0]
            m = _TOML_SECTION_RE.match(line)
            if m:
                cur = m.group(1).strip()
                in_array = False
                continue
            if not in_array:
                a = _TOML_ARRAY_OPEN_RE.match(line)
                if not (a and (cur, a.group(1)) in want):
                    continue
                in_array = True
                line = line.split("[", 1)[1]
            for q in _QUOTED_RE.findall(line):
                spec = q[0] or q[1]
                nm = _REQ_NAME_RE.match(spec)
                if nm:
                    names.add(nm.group(1))
            if "]" in line:
                in_array = False
        return names

    if kind == "yaml-block":
        # 対象: トップレベルの dependencies: / dev_dependencies: ブロック直下（2スペース）の
        # キー。ネスト（sdk: や git: url: 等の詳細指定）はより深いインデントなので拾わない。
        names = set()
        cur = ""
        for line in text.splitlines():
            t = _YAML_TOP_RE.match(line)
            if t:
                cur = t.group(1)
                continue
            if cur in sections:
                d = _YAML_DEP_RE.match(line)
                if d:
                    names.add(d.group(1))
        return names

    raise rs.ScanError(
        f"DEPENDENCY_MANIFESTS の未知の種別: {kind!r}"
        "（scripts/repo_scan.py の値と check_commit_msg.py の実装を同一コミットで揃える — §3.4）")


def _norm_dep(name: str) -> str:
    """名前集合の差分用の正規化（PEP 503 相当の畳み込みの近似）。"""
    return name.lower().replace("_", "-")


def _blob(spec: str) -> str | None:
    """`git show <rev>:<path>` の中身。その版に存在しなければ None。"""
    proc = subprocess.run(["git", "show", spec], capture_output=True, check=False)
    if proc.returncode != 0:
        return None
    return proc.stdout.decode("utf-8", "replace")


def _head_exists() -> bool:
    proc = subprocess.run(
        ["git", "rev-parse", "--verify", "-q", "HEAD"], capture_output=True, check=False
    )
    return proc.returncode == 0


def check_dependencies(staged: list[str], message_lines: list[str]) -> int:
    """検査4: 追加された依存名がメッセージで宣言されているか。違反件数を返す。"""
    if not _head_exists():
        return 0  # 初回コミットは比較対象が無い（境界は §3.4 に明記）
    message_l = "\n".join(message_lines).lower()
    violations = 0
    for rel in staged:
        spec = rs.DEPENDENCY_MANIFESTS.get(rel.rsplit("/", 1)[-1])
        if spec is None:
            continue
        kind, sections = spec
        new_text = _blob(f":{rel}")
        old_text = _blob(f"HEAD:{rel}")
        if new_text is None or old_text is None:
            continue  # 削除、または HEAD に無い新規マニフェスト（全体が diff で見える）
        new_names = _dep_names(kind, sections, new_text)
        old_names = _dep_names(kind, sections, old_text)
        if new_names is None or old_names is None:
            print(f"check_commit_msg: 警告: {rel} を解釈できないため検査4を素通し"
                  "（構文を直せば再び有効 — 近似は仕様 §7.4）", file=sys.stderr)
            continue
        old_norm = {_norm_dep(n) for n in old_names}
        for name in sorted(n for n in new_names if _norm_dep(n) not in old_norm):
            if name.lower() not in message_l:
                violations += 1
                _emit("HARD", "undeclared-dependency", rel,
                      f"依存追加 {name!r} がメッセージで宣言されていない。本文に "
                      f"`依存追加: {name} — 理由1行` を書く（依存は増えてよいが、"
                      "黙って増えてはならない — .guardrails/GUARDRAILS.md §3.4 検査4）")
    return violations


def check_feat_plan(subject: str, staged: list[str]) -> int:
    """検査5（feat-without-plan — v2.6 soft 導入・v2.8 hard 昇格＝G14）。違反件数を返す。

    条件: `feat:` かつ PLAN_LAYER_ROOTS のいずれか直下に HEAD に無い新規ディレクトリを
    作る変更があり、かつ設計根拠文書（PLAN_DOC_PATTERNS）の差分がステージに無いとき、
    1ディレクトリ1行で違反。HEAD の無い初回コミットは素通し（検査4と同じ境界）。
    """
    if not subject.startswith("feat:") or not rs.PLAN_LAYER_ROOTS or not _head_exists():
        return 0
    if any(p.search(f) for f in staged for p in rs.PLAN_DOC_PATTERNS):
        return 0
    candidates: set[str] = set()
    for f in staged:
        for layer in rs.PLAN_LAYER_ROOTS:
            prefix = layer.rstrip("/") + "/"
            if f.startswith(prefix):
                rest = f[len(prefix):]
                if "/" in rest:  # レイヤー直下のディレクトリを1階層だけ見る
                    candidates.add(prefix + rest.split("/", 1)[0])
    violations = 0
    for d in sorted(candidates):
        proc = subprocess.run(
            ["git", "rev-parse", "-q", "--verify", f"HEAD:{d}"], capture_output=True, check=False
        )
        if proc.returncode != 0:  # HEAD にそのツリーが無い = 新規ディレクトリ
            violations += 1
            _emit("HARD", "feat-without-plan", f"{d}/",
                  "レイヤー直下に新規ディレクトリを作る "
                  "feat: に設計根拠文書（plan.md / docs/plans/ — AGENTS.md §4）の差分が無い。"
                  "根拠（1行でよい）を書いて同コミットへ含めるか、根拠を書けない構造変更なら "
                  "feat を名乗らない（意図の複利は fix⇔テスト G10 と対 — G14・"
                  ".guardrails/GUARDRAILS.md §3.4 検査5）")
    return violations


def check_feat_test(subject: str, staged: list[str]) -> None:
    """検査6（feat-without-test — soft・v2.13）。警告のみで exit へ影響しない。"""
    if not subject.startswith("feat:") or not (rs.TEST_PATH_PATTERNS or rs.INLINE_TEST_PATTERNS):
        return  # テスト判別が未充填なら不発（列充填で有効化——layer-violation と同じ型）
    code_touched = any(rs.ext_of(p) in rs.CODE_EXTS and not rs.is_test_file(p)
                       and not rs.is_generated(p) for p in staged)
    if code_touched and not staged_has_test(staged):
        _emit("SOFT", "feat-without-test", "ステージ済み変更",
              "feat: がコードに触れるのにテストの変更が無い（新機能もテストを同梱する"
              "——soft 警告・コミットは通る。契約と昇格条件は .guardrails/GUARDRAILS.md §3.4 検査6・"
              "§10 Phase 25。AGENTS.md §8）")


def check_test_shrink(subject: str) -> None:
    """検査8（test-shrink — soft・v2.18）。警告のみで exit へ影響しない。"""
    if not (subject.startswith("fix:") or subject.startswith("feat:")) or not rs.TEST_PATH_PATTERNS:
        return
    proc = subprocess.run(["git", "diff", "--cached", "--numstat"],
                          capture_output=True, check=False)
    if proc.returncode != 0:
        return
    added = removed = 0
    for line in proc.stdout.decode("utf-8", "replace").splitlines():
        parts = line.split("\t")
        if len(parts) != 3 or parts[0] == "-":
            continue
        if rs.is_test_file(parts[2]):
            added += int(parts[0])
            removed += int(parts[1])
    if removed > added:
        _emit("SOFT", "test-shrink", "ステージ済み変更",
              f"テストファイルが純減している"
              f"（追加 {added} 行 < 削除 {removed} 行）。既存テストの弱体化は門を欺く最短路"
              "（assertion の削除で緑にしていないか——正当な整理なら無視してよい・soft — "
              ".guardrails/GUARDRAILS.md §3.4 検査8・調査④）")


def check_commit_size(staged: list[str]) -> None:
    """検査7（commit-too-large — soft・v2.13）。警告のみで exit へ影響しない。"""
    proc = subprocess.run(["git", "diff", "--cached", "--numstat"],
                          capture_output=True, check=False)
    if proc.returncode != 0:
        print("check_commit_msg: 警告: numstat が取れないため検査7を素通し", file=sys.stderr)
        return
    total = 0
    for line in proc.stdout.decode("utf-8", "replace").splitlines():
        parts = line.split("\t")
        if len(parts) != 3 or parts[0] == "-":  # バイナリは "-"
            continue
        rel = parts[2]
        if rs.is_generated(rel) or rel.rsplit("/", 1)[-1] in rs.LOCKFILE_NAMES:
            continue
        total += int(parts[0]) + int(parts[1])
    if total > rs.COMMIT_SIZE_SOFT_LIMIT:
        _emit("SOFT", "commit-too-large", "ステージ済み変更",
              f"純変更 {total} 行 > "
              f"上限 {rs.COMMIT_SIZE_SOFT_LIMIT} 行（生成物・lockfile 除外済み）。"
              "小さく分ける——大きな塊はどのゲートが何を検証したか追えない"
              "（soft 警告・コミットは通る — .guardrails/GUARDRAILS.md §3.4 検査7）")


def main_single(msgfile: str) -> int:
    subject = read_subject(msgfile)
    if subject.startswith(PASS_THROUGH_PREFIXES):
        return 0
    if not SUBJECT_FORMAT.match(subject):
        _emit("HARD", "commit-msg-format", "件名",
              "`^(feat|fix|test|docs|refactor|chore): .+` に一致しない: "
              f"{subject!r}（規約の正本: ルート AGENTS.md §10）")
        return 1

    staged = staged_files()
    if not staged:
        # メッセージのみの `git commit --amend`（ステージ空）は検査2〜4とも素通し。
        # --no-verify は §2 が技術的に禁止しているため、既存コミットの
        # 文言修正にはこの正規の逃げ道が必要（無いと文言修正が不可能になる）。
        return 0

    if (subject.startswith("fix:")
            and (rs.TEST_PATH_PATTERNS or rs.INLINE_TEST_PATTERNS)
            and not staged_has_test(staged)):
        _emit("HARD", "fix-without-test", "ステージ済み変更",
              "fix: コミットに回帰テストの変更が1つも無い"
              "（テストファイルのパス一致・インラインテストの追加行一致とも無し）。"
              "テストを同梱するか、"
              "テストで再現できない修正なら chore/refactor/docs を名乗る（.guardrails/GUARDRAILS.md §3.4）")
        return 1

    # 検査3: 正本3文書（GOALS / GUARDRAILS / catalog）の変更には G引用が必須（§3.4）
    message_lines = read_message(msgfile)
    touched = sorted(GOVERNANCE_PATHS.intersection(staged))
    if touched and not any(GOAL_CITATION.search(line) for line in message_lines):
        _emit("HARD", "governance-without-goal", "ステージ済み変更",
              f"{', '.join(touched)} を変更するのに、メッセージに効くGの引用が無い"
              "（例: `docs: §3.3 に規則追加（G4）`。どのGにも効かない変更は入れない"
              " — .guardrails/GOALS.md 運用ルール・.guardrails/GUARDRAILS.md §3.4）")
        return 1

    # 検査4: 依存マニフェストへの追加はメッセージで宣言する（undeclared-dependency — §3.4）
    dep_violations = check_dependencies(staged, message_lines)

    # 検査5: feat⇔plan 対（hard — §3.4・G14。検査4と同一実行で両方を列挙してから落とす）
    plan_violations = check_feat_plan(subject, staged)

    # 検査6〜8（soft — v2.13/v2.18。警告のみ・exit へ影響しない）
    check_feat_test(subject, staged)
    check_commit_size(staged)
    check_test_shrink(subject)

    return 1 if (dep_violations or plan_violations) else 0


# ---- v2.30（G9）: commit-msg 系ゲートの CI 実効化 ----
# `check-commit-msg` は stages:[commit-msg] のため、CI の `checks` ジョブが実行する
# `pre-commit run --all-files`（--hook-stage 未指定）では走らない。ローカルで
# `pre-commit install` していない限り、本ファイルの全検査が誰にも掛からない静かな穴
# だった（実機で発見——.guardrails/GUARDRAILS.md §3.4 参照）。base..head の各コミットを
# 一時 worktree で「今まさに作ろうとしている状態」に再現し、main_single() をそのまま
# 再実行することで、単発形態と検査ロジックを1つも複製せずに埋める。


def resolve_rev(root: Path, rev: str, role: str) -> str:
    proc = subprocess.run(["git", "-C", str(root), "rev-parse", "--verify", "-q", f"{rev}^{{commit}}"],
                          capture_output=True)
    if proc.returncode != 0:
        raise rs.ScanError(
            f"{role} を解決できない: {rev!r}（例: --base origin/main。"
            "CI では PR の base SHA を渡し、checkout は fetch-depth: 0 で全履歴を取る — §5 と同じ流儀）")
    return proc.stdout.decode("utf-8", "replace").strip()


def commits_in_range(root: Path, base: str, head: str) -> list[str]:
    """base..head の非マージコミット（古い順）。"""
    proc = subprocess.run(["git", "-C", str(root), "rev-list", "--no-merges", "--reverse", f"{base}..{head}"],
                          capture_output=True)
    if proc.returncode != 0:
        raise rs.ScanError(f"git rev-list が失敗: {proc.stderr.decode('utf-8', 'replace').strip()}")
    return [s for s in proc.stdout.decode("utf-8", "replace").split() if s]


def commit_message_text(root: Path, sha: str) -> str:
    proc = subprocess.run(["git", "-C", str(root), "log", "-1", "--format=%B", sha], capture_output=True)
    if proc.returncode != 0:
        raise rs.ScanError(f"{sha[:7]} のメッセージを取得できない")
    return proc.stdout.decode("utf-8", "replace")


class CommitWorktree:
    """コミット1つを「今まさに commit しようとしている状態」として再現する一時 worktree。

    `git worktree add <sha>` で対象コミットへ checkout（HEAD=sha・index/working tree=sha
    のスナップショット）した後 `reset --soft <sha>^` で HEAD だけ親へ戻す——index・working
    tree はそのまま。main_single() 内の `git diff --cached` / `git show :path` /
    `HEAD:path` 呼び出しは cwd 経由でこの worktree の git 状態を読むため、コード変更ゼロで
    履歴上の任意のコミットを「ステージ済みの索引」として再検査できる（親の無い初回
    コミットは `update-ref -d HEAD` で「まだ何もコミットしていない」状態を模す——
    `check_dependencies` 等の `_head_exists()` 判定はこの状態を正しく「初回」と扱う）。
    """

    def __init__(self, root: Path, sha: str):
        self.root = root
        self.sha = sha
        self.tmp: Path | None = None
        self.path: Path | None = None

    def __enter__(self) -> Path:
        self.tmp = Path(tempfile.mkdtemp(prefix=".commit-msg-history-", dir=self.root))
        self.path = self.tmp / "wt"
        proc = subprocess.run(["git", "-C", str(self.root), "worktree", "add", "--detach",
                               "--quiet", str(self.path), self.sha], capture_output=True)
        if proc.returncode != 0:
            raise rs.ScanError(
                f"{self.sha[:7]} の worktree 作成に失敗: {proc.stderr.decode('utf-8', 'replace').strip()}")
        has_parent = subprocess.run(
            ["git", "-C", str(self.path), "rev-parse", "-q", "--verify", f"{self.sha}^"],
            capture_output=True).returncode == 0
        if has_parent:
            subprocess.run(["git", "-C", str(self.path), "reset", "--soft", f"{self.sha}^"],
                          capture_output=True, check=False)
        else:
            subprocess.run(["git", "-C", str(self.path), "update-ref", "-d", "HEAD"],
                          capture_output=True, check=False)
        return self.path

    def __exit__(self, *_exc) -> None:
        if self.path is not None:
            subprocess.run(["git", "-C", str(self.root), "worktree", "remove", "--force", str(self.path)],
                          capture_output=True, check=False)
        if self.tmp is not None:
            shutil.rmtree(self.tmp, ignore_errors=True)
        subprocess.run(["git", "-C", str(self.root), "worktree", "prune"], capture_output=True, check=False)


def check_commit(root: Path, checker_script: Path, sha: str) -> tuple[str, int, str]:
    """1コミットを再検査する。戻り値は (件名, exit code, stderr全体)。"""
    with CommitWorktree(root, sha) as wt:
        msg_text = commit_message_text(root, sha)
        msg_file = wt / ".commit-msg-history.txt"
        msg_file.write_text(msg_text, encoding="utf-8", newline="\n")
        try:
            proc = subprocess.run([sys.executable, str(checker_script), str(msg_file)],
                                  cwd=str(wt), capture_output=True, timeout=HISTORY_TIMEOUT_SEC)
        except subprocess.TimeoutExpired:
            raise rs.ScanError(f"{sha[:7]} の再検査が {HISTORY_TIMEOUT_SEC} 秒以内に返らない"
                               "（ハングは赤の証明にならない — G11）")
    subject = msg_text.splitlines()[0].strip() if msg_text.strip() else ""
    return subject, proc.returncode, proc.stderr.decode("utf-8", "replace").strip()


def main_history(base_arg: str, head_arg: str) -> int:
    root = rs.repo_root()
    checker_script = Path(__file__).resolve()
    base = resolve_rev(root, base_arg, "--base")
    head = resolve_rev(root, head_arg, "--head")
    shas = commits_in_range(root, base, head)
    if not shas:
        print("[commit-msg-history] 対象コミット無し（base..head が空 — §3.4）")
        return 0

    violations = 0
    for sha in shas:
        short = sha[:7]
        subject, rc, stderr_text = check_commit(root, checker_script, sha)
        if rc == 0:
            print(f"[commit-msg-history] {short} PASS: {subject!r}")
            continue
        if rc == 2:
            raise rs.ScanError(f"{short} の再検査中に内部エラー: {stderr_text}")
        violations += 1
        first_line = stderr_text.splitlines()[0] if stderr_text else "(詳細不明)"
        print(f"HARD:commit-msg-history-mismatch {short} {subject!r}: {first_line}", file=sys.stderr)

    if violations:
        print(f"\ncheck-commit-msg-history: 不一致 {violations} 件/{len(shas)} コミット。"
              "各コミットの内容とメッセージ検査（.guardrails/GUARDRAILS.md §3.4）を揃える。",
              file=sys.stderr)
        return 1
    print(f"[commit-msg-history] 全{len(shas)}コミット PASS")
    return 0


def main(argv: list[str]) -> int:
    rs.reconfigure_stdio()
    ap = argparse.ArgumentParser(
        description="コミットメッセージ検査（.guardrails/GUARDRAILS.md §3.4）")
    ap.add_argument("msgfile", nargs="?",
                    help="コミットメッセージファイル（commit-msg フックからの単発呼び出し用）")
    ap.add_argument("--base", help="このリビジョンから --head までの全コミットを履歴再検査する（CI用）")
    ap.add_argument("--head", default="HEAD", help="履歴再検査の終点（既定: HEAD）")
    args = ap.parse_args(argv)

    if args.base is not None:
        return main_history(args.base, args.head)

    if args.msgfile is None:
        print("usage: uv run scripts/check_commit_msg.py <コミットメッセージファイル> | --base <rev> [--head <rev>]",
              file=sys.stderr)
        return 2
    rc = main_single(args.msgfile)
    rs.append_violations(rs.repo_root(), "commit-msg", _VIOLATIONS)  # 違反ログ（§3.6）
    return rc


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except rs.ScanError as exc:
        print(f"check_commit_msg: 内部エラー: {exc}", file=sys.stderr)
        sys.exit(2)
    except Exception as exc:
        print(f"check_commit_msg: 内部エラー: {exc!r}", file=sys.stderr)
        sys.exit(2)
