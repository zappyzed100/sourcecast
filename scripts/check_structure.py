# check_structure.py — 構造検査: hard違反=exit 1・softは警告のみ exit 0（契約: .guardrails/GUARDRAILS.md §7.5・§3.3）
#
# 呼び出し（§7.1: 必ず uv 経由）: uv run scripts/check_structure.py
#   exit 0 = 違反なし or soft のみ / exit 1 = hard 違反あり / exit 2 = 内部エラー
#
# 出力形式（§3.3: LLM が機械的に .guardrails/GUARDRAILS.md と突き合わせて直せる形式）:
#   1違反1行・先頭に規則ID —  例: `HARD:layer-violation app/lib/x.dart:12 説明…`
#
# 検査項目の一覧（何を検査するか）は .guardrails/GUARDRAILS.md §3.3 が契約。検出パターンの実体は
# scripts/repo_scan.py の BINDING セクションが正本（同じ正規表現の二重実装禁止 — §7.3）。
# 性能予算: フルスキャン2秒以内（§7.7）。全ファイル1回読み・O(N²) 禁止（§7.3）。

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import repo_scan as rs  # noqa: E402

Finding = tuple[str, str, str, str]  # (severity, rule_id, location, message)


def _iter_code_lines(ext: str, text: str):
    """コメント行を除いた (行番号, 行) を返す。"""
    for i, line in enumerate(text.splitlines(), 1):
        if rs.is_comment_line(ext, line):
            continue
        yield i, line


def _line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


KIT_SELF_EXEMPT_REQUIRED = {"AGENTS.md", "CLAUDE.md"}


def check_required(files: list[str], tracked: set[str], out: list[Finding]) -> None:
    kit_source = rs.is_kit_source_repo(tracked)
    for req in rs.REQUIRED_PATHS:
        prefix = req.rstrip("/") + "/"
        if req not in tracked and not any(f.startswith(prefix) for f in files):
            if kit_source and req in KIT_SELF_EXEMPT_REQUIRED:
                out.append(("SOFT", "missing-required", req,
                            "キット原本自身は対象外（実体化は導入先プロジェクトの Step 1 — "
                            f"{rs.KIT_SOURCE_MARKER} — .guardrails/GUARDRAILS.md §3.3）"))
                continue
            out.append(("HARD", "missing-required", req, "必須のファイル/ディレクトリが存在しない"))


def check_layers(texts: dict[str, str], out: list[Finding]) -> None:
    for rel, text in texts.items():
        ext = rs.ext_of(rel)
        if ext not in rs.CODE_EXTS:
            continue
        for prefix, pattern, desc in rs.LAYER_FORBIDDEN_IMPORTS:
            if not rel.startswith(prefix):
                continue
            for i, line in _iter_code_lines(ext, text):
                if pattern.search(line):
                    out.append(("HARD", "layer-violation", f"{rel}:{i}", desc))


def check_required_content(
    root: Path, files: list[str], texts: dict[str, str], out: list[Finding]
) -> None:
    # 対象は全追跡ファイル（texts は CODE/HEADER 拡張子しか持たないため、.toml 等の
    # 設定ファイルを狙う規則が「対象ファイル自体が無い」と誤検知していた）。
    # 未読ファイルはローカルキャッシュへ遅延読込（1回だけ読む原則は維持 — §7.3）。
    extra: dict[str, str] = {}

    def _text(rel: str) -> str:
        if rel in texts:
            return texts[rel]
        if rel not in extra:
            extra[rel] = rs.read_text(root, rel)
        return extra[rel]

    kit_source = rs.is_kit_source_repo(set(files))
    for rule_id, path_re, content_re, desc in rs.REQUIRED_CONTENT_RULES:
        candidates = [rel for rel in files if path_re.search(rel) and not rs.is_generated(rel)]
        if not candidates:
            if kit_source and rule_id == "agents-import-missing":
                out.append(("SOFT", rule_id, path_re.pattern,
                            f"{desc}（キット原本自身は対象外——対象ファイル自体が無い。"
                            f"{rs.KIT_SOURCE_MARKER} — .guardrails/GUARDRAILS.md §3.3）"))
                continue
            out.append(("HARD", rule_id, path_re.pattern, f"{desc}（対象ファイル自体が無い）"))
            continue
        if not any(content_re.search(_text(rel)) for rel in candidates):
            out.append(("HARD", rule_id, candidates[0], desc))


def check_tests(texts: dict[str, str], out: list[Finding]) -> None:
    """test-sleep / test-nondeterminism / test-network / test-calls-solver-direct。

    先頭3つは非決定性の再現がテストの本質という正当なケースがある（§9.5・v2.25・
    Phase 35）。境界行の前後 NONDETERMINISM_EXEMPT_WINDOW 行以内に
    `NONDETERMINISM-EXEMPT: 理由` コメントがあれば免除する——missing-log-coverage の
    NO-LOG と同じ「存在検査のみ」の境界。test-calls-solver-direct は別機構
    （SOLVER_TEST_WRAPPER_NAME の同一行検査）で既に免除経路を持つため対象外。
    """
    for rel, text in texts.items():
        if not rs.is_test_file(rel):
            continue
        ext = rs.ext_of(rel)
        lines = text.splitlines()
        for i, line in _iter_code_lines(ext, text):
            lo = max(0, i - 1 - rs.NONDETERMINISM_EXEMPT_WINDOW)
            hi = i - 1 + rs.NONDETERMINISM_EXEMPT_WINDOW + 1
            exempt = any(rs.NONDETERMINISM_EXEMPT_PATTERN.search(w) for w in lines[lo:hi])
            for pat, label in rs.SLEEP_PATTERNS.get(ext, []):
                if pat.search(line) and not exempt:
                    out.append(("HARD", "test-sleep", f"{rel}:{i}",
                                f"テスト内の {label}（flakyの温床 — §3.3）"))
            for pat, label in rs.NONDETERMINISM_PATTERNS.get(ext, []):
                if pat.search(line) and not exempt:
                    out.append(("HARD", "test-nondeterminism", f"{rel}:{i}",
                                f"テスト内の非決定入力: {label}（§9.2）"))
            for pat, label in rs.TEST_NETWORK_PATTERNS.get(ext, []):
                if pat.search(line) and not exempt:
                    out.append(("HARD", "test-network", f"{rel}:{i}",
                                f"テスト内の外部I/O直呼び: {label}"
                                "（記録済みフィクスチャ/フェイクを注入する — §9.5）"))
            if rs.SOLVER_DIRECT_CALL_PATTERNS and rs.SOLVER_TEST_WRAPPER_NAME not in line:
                for pat, label in rs.SOLVER_DIRECT_CALL_PATTERNS:
                    if pat.search(line):
                        out.append(("HARD", "test-calls-solver-direct", f"{rel}:{i}",
                                    f"{label}。テストは {rs.SOLVER_TEST_WRAPPER_NAME} 経由のみ（§9.1）"))


_GATE_EMIT_PATTERNS = [
    re.compile(r'\("(?:HARD|SOFT)",\s*"([a-z0-9-]+)"'),   # check_structure の out.append 形
    re.compile(r'_emit\("(?:HARD|SOFT)",\s*"([a-z0-9-]+)"'),  # check_commit_msg の _emit 形
    re.compile(r'"(?:HARD|SOFT):([a-z0-9-]+)'),           # 文字列直書き形（履歴再実行等）
]
_GATE_SOURCE_FILES = ["scripts/check_structure.py", "scripts/check_commit_msg.py",
                      "scripts/repo_scan.py"]


def check_gates_registry(root: Path, out: list[Finding]) -> None:
    """門の台帳（GATE_REGISTRY — §12.1 `dev.py gates`）と検査器コードの一致検査
    （gates-registry-drift・hard — Phase 45・v2.43）。

    台帳は「何ができるか」の発見導線であり、検査器と食い違えば一覧が嘘をつく（G9）。
    照合は2方向: ① 検査器が emit する規則ID（リテラル）が台帳に無い→未登録
    ② 台帳の強制対象区分（GATE_REGISTRY_ENFORCED）のIDがどのソースにも現れない→台帳が古い。
    """
    sources: dict[str, str] = {}
    for rel in _GATE_SOURCE_FILES:
        try:
            sources[rel] = rs.read_text(root, rel)
        except OSError:
            return  # ソース欠落は missing-required の持ち場（二重報告しない — G4）
    emitted: set[str] = set()
    for rel in ("scripts/check_structure.py", "scripts/check_commit_msg.py"):
        for pat in _GATE_EMIT_PATTERNS:
            emitted |= set(pat.findall(sources[rel]))
    registry_ids = {gid for gid, _, _, _ in rs.GATE_REGISTRY}
    for gid in sorted(emitted - registry_ids):
        out.append(("HARD", "gates-registry-drift", gid,
                    "検査器が emit する規則IDが GATE_REGISTRY に未登録"
                    "（scripts/repo_scan.py の台帳へ1行足す — §12.1 gates）"))
    # 逆方向: 台帳の行そのものも union（repo_scan.py）に含まれるため、存在1回では
    # 「台帳にだけ書いた幽霊規則」と区別できない——**2回以上**（台帳の行＋実装側の実体）を
    # 要求する（自己循環の除去。Phase 45 の違反注入で実測した穴）。
    union = "\n".join(sources.values())
    for gid, cat, _act, _desc in rs.GATE_REGISTRY:
        if cat.split(" ", 1)[0] not in rs.GATE_REGISTRY_ENFORCED:
            continue
        if gid not in emitted and union.count(gid) < 2:
            out.append(("HARD", "gates-registry-drift", gid,
                        "GATE_REGISTRY にあるが検査器コードのどこにも現れない"
                        "（規則を消したなら台帳からも消す — §12.1 gates）"))


def check_phase_table(root: Path, out: list[Finding]) -> None:
    """§10 の Phase 台帳と実見出しを双方向照合する（Phase 52）。"""
    rel = ".guardrails/GUARDRAILS.md"
    text = rs.read_text(root, rel)
    section = text[text.find("## 10."):]
    first_heading = section.find("### Phase ")
    if first_heading < 0:
        out.append(("HARD", "phase-table-drift", rel, "Phase 見出しが1件も無い"))
        return
    table_ids = {int(n) for n in re.findall(r"(?m)^\|\s*(\d+)\s*\|", section[:first_heading])}
    heading_ids: set[int] = set()
    for start, end in re.findall(r"(?m)^### Phase (\d+)(?:〜(\d+))?\b", section):
        lo, hi = int(start), int(end or start)
        heading_ids.update(range(lo, hi + 1))
    if table_ids != heading_ids:
        missing = sorted(heading_ids - table_ids)
        stale = sorted(table_ids - heading_ids)
        out.append(("HARD", "phase-table-drift", rel,
                    f"Phase台帳と見出しが不一致（台帳欠落={missing}・見出し欠落={stale}）"))


def check_property_tests(texts: dict[str, str], out: list[Finding]) -> None:
    """性質形テストの存在検査（§9.6 missing-property-test — soft・Phase 43・v2.41）。

    発火条件: SOLVER_DIRECT_CALL_PATTERNS が充填済み（=表Bで確率的コンポーネント有）
    かつ、全テストファイルのどこにも PROPERTY_TEST_MARKERS が1つも現れない。
    リポジトリ単位の存在検査（ファイル単位ではない）。マーカー未充填のまま solver
    だけ充填された状態も警告になる——静かな不発にしない（G9。マーカー充填で解消）。
    """
    if not rs.SOLVER_DIRECT_CALL_PATTERNS:
        return
    for rel, text in texts.items():
        if not rs.is_test_file(rel):
            continue
        for pat, _label in rs.PROPERTY_TEST_MARKERS:
            if pat.search(text):
                return
    out.append(("SOFT", "missing-property-test", "(repo)",
                "確率的コンポーネントがあるのに性質形テストの痕跡が無い"
                "（実例オラクルだけの検証は実装と欠陥を共有し得る — §9.6。"
                "PBT ライブラリの import 等を PROPERTY_TEST_MARKERS へ充填し、"
                "性質形テストを1つ以上書く）"))


def check_deprecated(texts: dict[str, str], out: list[Finding]) -> None:
    """世代交代 API 検査（§3.3 deprecated-api — Phase 15・v2.6）。

    テスト内限定でなく**全コード走査**（テストも含む——旧作法はどこに書かれても旧作法）。
    パターンの正本は repo_scan.DEPRECATED_PATTERNS（列充填。出典規律はカタログ注記）。
    唯一の除外は正本ファイル自身（scripts/repo_scan.py）——パターン定義・ラベル文字列は
    禁止対象の**引用**であって使用ではない（Phase 15 の違反注入で実測した自己偽陽性。
    LOG_EXIT_PREFIXES が scripts/ を除外するのと同じ境界の引き方 — §3.3）。
    """
    for rel, text in texts.items():
        if rel == "scripts/repo_scan.py":
            continue
        ext = rs.ext_of(rel)
        pats = rs.DEPRECATED_PATTERNS.get(ext)
        if not pats:
            continue
        for i, line in _iter_code_lines(ext, text):
            for pat, label in pats:
                if pat.search(line):
                    out.append(("HARD", "deprecated-api", f"{rel}:{i}",
                                f"世代交代した旧 API: {label}"
                                "（§3.3。旧作法へ戻さない——パターンの根拠と代替はカタログの列）"))


def check_log_calls(texts: dict[str, str], out: list[Finding]) -> None:
    for rel, text in texts.items():
        ext = rs.ext_of(rel)
        if ext not in rs.PRINT_CALL_PATTERNS or rel in rs.LOG_EXIT_FILES:
            continue
        if rel.startswith(rs.LOG_EXIT_PREFIXES):  # scripts/ 等はキット自身の出力契約（§7・§12.1）
            continue
        for i, line in _iter_code_lines(ext, text):
            for pat, label in rs.PRINT_CALL_PATTERNS[ext]:
                if pat.search(line):
                    out.append(("HARD", "log-direct-call", f"{rel}:{i}",
                                f"{label} の直呼び（ログは単一出口経由にする — §8.2）"))


def check_ffi_boundary(texts: dict[str, str], out: list[Finding]) -> None:
    for rel, text in texts.items():
        if any(p.search(rel) for p in rs.FFI_BOUNDARY_FILE_PATTERNS):
            ext = rs.ext_of(rel)
            # コメント行は除外して探す（コメントで言及しただけで検査を満たす fail-open を防ぐ）
            found = any(
                rs.CATCH_UNWIND_PATTERN.search(line) for _, line in _iter_code_lines(ext, text)
            )
            if not found:
                out.append(("HARD", "missing-catch-unwind", f"{rel}:1",
                            "FFI境界ファイルに catch_unwind が1つも無い（§8.2）"))


def check_log_boundary_coverage(texts: dict[str, str], out: list[Finding]) -> None:
    """missing-log-coverage（§8.4 — v2.19・Phase 31・soft・列充填で有効化）。

    「この関数は重要だからログすべき」という意味判断は機械化できない（.guardrails/GUARDRAILS.md §8.4）。
    代わりに客観的に検出できる境界（I/O・外部呼び出し・エラーハンドラ——LOG_BOUNDARY_PATTERNS・
    列充填）に対象を絞り、境界行の前後 LOG_BOUNDARY_WINDOW 行以内に単一出口のログ呼び出し
    （LOG_CALL_PATTERN）か `NO-LOG: 理由` コメント（NO_LOG_COMMENT_PATTERN）のどちらかが
    無ければ警告する。理由の妥当性そのものは検証しない——存在検査のみ（RED-FIRST-EXEMPT や
    `#[allow(reason=...)]` と同じ「見えるようにするだけ」の境界 — G9）。
    LOG_BOUNDARY_PATTERNS が空なら不発（列充填で有効化）。
    """
    for rel, text in texts.items():
        ext = rs.ext_of(rel)
        if ext not in rs.LOG_BOUNDARY_PATTERNS or rs.is_generated(rel):
            continue
        if rel.startswith(rs.LOG_EXIT_PREFIXES) or rel in rs.LOG_EXIT_FILES:
            continue
        lines = text.splitlines()
        call_pat = rs.LOG_CALL_PATTERN.get(ext)
        for i, line in _iter_code_lines(ext, text):
            for pat, label in rs.LOG_BOUNDARY_PATTERNS[ext]:
                if not pat.search(line):
                    continue
                lo = max(0, i - 1 - rs.LOG_BOUNDARY_WINDOW)
                hi = i - 1 + rs.LOG_BOUNDARY_WINDOW + 1
                window = lines[lo:hi]
                covered = any(rs.NO_LOG_COMMENT_PATTERN.search(w) for w in window) or (
                    call_pat is not None and any(call_pat.search(w) for w in window)
                )
                if not covered:
                    out.append(("SOFT", "missing-log-coverage", f"{rel}:{i}",
                                f"{label} の境界に前後{rs.LOG_BOUNDARY_WINDOW}行以内のログ被覆が無い"
                                "（単一出口のログ呼び出しか `NO-LOG: 理由` コメントのどちらかを — "
                                ".guardrails/GUARDRAILS.md §8.4）"))


def check_ui_testid(texts: dict[str, str], out: list[Finding]) -> None:
    """UI操作要素のテストID検査（§12.4）。開始タグ単位・全文正規表現の近似（近似は仕様 — §7.4）。"""
    for file_re, element_re, testid_re, desc in rs.UI_TESTID_RULES:
        for rel, text in texts.items():
            if not file_re.search(rel) or rs.is_test_file(rel):
                continue
            for m in element_re.finditer(text):
                if not testid_re.search(m.group(0)):
                    out.append(("HARD", "ui-missing-testid", f"{rel}:{_line_of(text, m.start())}",
                                f"{desc}（操作要素にテストIDが無い — §12.4）"))


_HOOK_TYPES_RE = re.compile(r"^default_install_hook_types:\s*\[([^\]]*)\]", re.MULTILINE)


def check_mcp_allowlist(root: Path, files: list[str], out: list[Finding]) -> None:
    """mcp-not-allowed（§3.3 — v2.11・Phase 23）: プロジェクト正本の MCP を許可リスト制にする。

    2026-07-07 の MCP・エコシステム調査の判定（採用は playwright のみ）を門に固定する。
    対象は追跡された .mcp.json（basename 一致）のみ——タスク単位のローカル追加
    （claude mcp add）は対象外。解釈不能な JSON は警告1行で素通し（検査4と同じ整理 §7.4）。
    """
    for rel in files:
        if rel.rsplit("/", 1)[-1] != ".mcp.json" or rs.is_generated(rel):
            continue
        try:
            data = json.loads(rs.read_text(root, rel))
            servers = sorted(data.get("mcpServers", {}))
        except (ValueError, AttributeError):
            out.append(("SOFT", "mcp-unparseable", rel,
                        "JSON を解釈できないため mcp-not-allowed を素通し"
                        "（構文を直せば再び有効 — 近似は仕様 §7.4）"))
            continue
        for name in servers:
            if name not in rs.MCP_ALLOWED_SERVERS:
                out.append(("HARD", "mcp-not-allowed", rel,
                            f"MCP サーバー {name!r} は採用許可リスト外"
                            "（2026-07-07 調査の判定: プロジェクト正本の採用は "
                            f"{sorted(rs.MCP_ALLOWED_SERVERS)} のみ。追加はカタログの"
                            "「MCP・エコシステム採用規律」ゲート3条を通し、判定を記録して"
                            " repo_scan.MCP_ALLOWED_SERVERS へ — .guardrails/GUARDRAILS.md §3.3・§12.4）"))


def check_env_files(files: list[str], out: list[Finding]) -> None:
    """env-file-tracked（§3.3 — v2.18・Phase 29・hard）: .env 系の追跡を拒否する。

    gitleaks（§3.1）は内容のパターン検査であり、低エントロピーの実値が入った .env は
    素通りし得る——存在自体を塞ぐ（調査④の must ティア項目）。雛形（ENV_FILE_ALLOWED）
    は除外。解消は `git rm --cached <file>` ＋ .gitignore 追記＋値のローテーション。
    """
    for rel in files:
        base = rel.rsplit("/", 1)[-1]
        if rs.ENV_FILE_PATTERN.search(rel) and base not in rs.ENV_FILE_ALLOWED:
            out.append(("HARD", "env-file-tracked", rel,
                        "実値の入り得る .env 系ファイルが追跡されている（gitleaks の内容検査を"
                        "素通りし得る経路 — 調査④）。`git rm --cached` で追跡を外し .gitignore へ、"
                        "値は漏えい扱いでローテーションする（.guardrails/GUARDRAILS.md §3.3）"))


def check_context_doc_size(root: Path, files: list[str], out: list[Finding]) -> None:
    """context-doc-too-large（§3.3 — v2.17・Phase 28・soft）: 常時読込文書の肥大警告。

    規約文書はセッションごとに自動で読まれる＝行数がそのまま常駐コンテキスト（G3）。
    上限は CONTEXT_DOC_LIMITS（中立既定値・列上書き可）。soft の理由: 正当に育つ文書で
    あり、分割（フォルダ CLAUDE.md / Skills 化——§10 保留のセンサーを兼ねる）の判断は人間。
    """
    for rel in files:
        if rs.is_generated(rel):
            continue
        for pat, limit in rs.CONTEXT_DOC_LIMITS:
            if pat.search(rel):
                n = rs.read_text(root, rel).count("\n") + 1
                if n > limit:
                    out.append(("SOFT", "context-doc-too-large", rel,
                                f"{n} 行 > 上限 {limit} 行（常時読込の規約文書の肥大＝"
                                "注意力の希釈 G3。章をフォルダ CLAUDE.md や docs/ へ分割する。"
                                "この警告は Skills 化保留のトリガー実測でもある — "
                                ".guardrails/GUARDRAILS.md §3.3・§10 保留）"))
                break


def check_hooks_installed(root: Path, tracked: set[str], out: list[Finding]) -> None:
    """「install（再）実行忘れ＝静かに無効」の機械検査（§0 の注意の機械化 — §3.3・G7/G9）。

    - core.hooksPath が設定済み → HARD:hooks-path-overridden（フック差し替え＝全防壁が無効。
      guard（§2）は「変更する操作」しか見ないため、既に設定済みの環境はここで検出する）。
    - シムが一部の型にだけ無い → HARD:hook-type-missing（default_install_hook_types に型を
      足して `pre-commit install` を忘れた、§0 が警告するまさにその状態）。
    - シムが1つも無い → SOFT:hooks-not-installed（出荷直後〜Step 3 前の正常状態。
      binding-unstamped と同じ「見える猶予」——Step 3 で解消）。
    - CI ではスキップ（チェックアウトにシムが無いのが正常。GitHub Actions は CI=true を設定する）。
    """
    if os.environ.get("CI"):
        return
    if ".pre-commit-config.yaml" not in tracked:
        return  # 存在自体は missing-required が別途 HARD で報告する
    m = _HOOK_TYPES_RE.search(rs.read_text(root, ".pre-commit-config.yaml"))
    types = ([t.strip() for t in m.group(1).split(",") if t.strip()] if m else ["pre-commit"])

    if rs.git_config_get(root, "core.hooksPath"):
        out.append(("HARD", "hooks-path-overridden", "(git config core.hooksPath)",
                    "core.hooksPath が設定されており .git/hooks のシムが無効（全防壁の静かな迂回）。"
                    "ユーザーの端末で `git config --unset core.hooksPath` を実行して解除する"
                    "（Claude Code からの解除操作は §2 がブロックする）"))
        return

    hooks_dir = rs.git_hooks_dir(root)

    def _is_shim(t: str) -> bool:
        p = hooks_dir / t
        if not p.is_file():
            return False
        with open(p, "r", encoding="utf-8", errors="replace") as f:
            return "pre-commit" in f.read()

    installed = {t for t in types if _is_shim(t)}
    missing = [t for t in types if t not in installed]
    if installed and missing:
        out.append(("HARD", "hook-type-missing", f"{hooks_dir}",
                    f"pre-commit のシムが無いフック種: {', '.join(missing)}"
                    "（`pre-commit install` を再実行する——忘れると当該フックは静かに無効 — §0）"))
    elif not installed:
        out.append(("SOFT", "hooks-not-installed", f"{hooks_dir}",
                    "pre-commit のシムが未インストール（Step 3 の "
                    "`uv tool install pre-commit` → `pre-commit install` で解消 — §11）"))


def check_binding_dead_patterns(out: list[Finding]) -> None:
    """列充填の取りこぼし検査: パターン辞書のキー拡張子が走査対象（CODE_EXTS ∪
    HEADER_REQUIRED_EXTS）に無ければ、その検査は永久に不発＝静かな fail-open（G9・§3.3）。"""
    scanned = rs.CODE_EXTS | rs.HEADER_REQUIRED_EXTS
    for name, table in (("SLEEP_PATTERNS", rs.SLEEP_PATTERNS),
                        ("NONDETERMINISM_PATTERNS", rs.NONDETERMINISM_PATTERNS),
                        ("TEST_NETWORK_PATTERNS", rs.TEST_NETWORK_PATTERNS),
                        ("DEPRECATED_PATTERNS", rs.DEPRECATED_PATTERNS),
                        ("PRINT_CALL_PATTERNS", rs.PRINT_CALL_PATTERNS),
                        ("INLINE_TEST_PATTERNS", rs.INLINE_TEST_PATTERNS)):
        for ext in sorted(set(table) - scanned):
            out.append(("HARD", "binding-dead-pattern", f"scripts/repo_scan.py ({name}[{ext!r}])",
                        f"拡張子 {ext} が CODE_EXTS / HEADER_REQUIRED_EXTS に無く検査が不発"
                        "（充填時に CODE_EXTS へ拡張子を足す — §3.3）"))


def check_binding_dead_paths(files: list[str], tracked: set[str], out: list[Finding]) -> None:
    """充填後のドリフト検査: パス/prefix 型バインディングが追跡ファイルに1件も一致しなければ
    対応する検査は静かに不発＝fail-open（G9・§3.3）。binding-dead-pattern（hard）が充填時の
    拡張子取りこぼしを見るのに対し、こちらは充填後のファイル移動・改名に値が追随していない
    状態を見る。soft の理由: ブートストラップ途中（対象コードが未作成）の正当な一時状態と
    区別できない——binding-unstamped と同じ「見える猶予」の整理。
    """
    dead: dict[str, None] = {}  # 挿入順を保つ重複排除（ORPHAN_UNIVERSES は prefix が重複し得る）
    for rel in sorted(rs.LOG_EXIT_FILES):
        if rel not in tracked:
            dead[f"LOG_EXIT_FILES: {rel}"] = None
    for pat in rs.FFI_BOUNDARY_FILE_PATTERNS:
        if not any(pat.search(f) for f in files):
            dead[f"FFI_BOUNDARY_FILE_PATTERNS: {pat.pattern}"] = None
    for prefix, _pat, _desc in rs.LAYER_FORBIDDEN_IMPORTS:
        if not any(f.startswith(prefix) for f in files):
            dead[f"LAYER_FORBIDDEN_IMPORTS: {prefix}"] = None
    for layer_root in rs.PLAN_LAYER_ROOTS:
        prefix = layer_root.rstrip("/") + "/"
        if not any(f.startswith(prefix) for f in files):
            dead[f"PLAN_LAYER_ROOTS: {layer_root}"] = None
    for prefixes, _ext, _entries in rs.ORPHAN_UNIVERSES:
        for prefix in prefixes:
            if not any(f.startswith(prefix) for f in files):
                dead[f"ORPHAN_UNIVERSES: {prefix}"] = None
    for item in dead:
        out.append(("SOFT", "binding-dead-path", f"scripts/repo_scan.py ({item})",
                    "パス/prefix が追跡ファイルに1件も一致せず、対応する検査が静かに不発"
                    "（ファイル移動・改名に充填値が追随していない疑い。実パスへ更新し、"
                    "同じパスを持つ他の設定（lint 設定・カタログの列）も同時に点検する — "
                    ".guardrails/GUARDRAILS.md §3.3・G9）"))


_LOCAL_REPO_BLOCK_RE = re.compile(r"^  - repo: local\n((?:.*\n)*?)(?=^  - repo: |\Z)", re.M)
_HOOK_ID_RE = re.compile(r"^      - id: ([\w-]+)", re.M)


def check_installer_tokens(root: Path, tracked: set[str], out: list[Finding]) -> None:
    """installer-token-drift（キット原本限定・hard — v2.38）: インストーラの検証条項が
    キット自身の実体に追随しているか。

    導入済みリポジトリの更新はインストーラ再実行だが、.pre-commit-config.yaml /
    .claude/settings.json はトークン検証つきの KEPT（既存維持）——検証条項が古いままだと、
    新版で増えたフックが**旧設定を KEPT のまま通して静かに届かない**（fail-open — G9。
    実例: ownership-guard / codex-hooks が PRECOMMIT_REQUIRED から漏れたまま2版経過していた）。
    導入先では列フックが混ざり「キットのフック」を機械判別できないため、原本側で堰き止める
    （kit-source-exempt と対称の「原本限定」ゲート — §3.3）。
    """
    if not rs.is_kit_source_repo(tracked):
        return
    import install_kit  # 原本のみの遅延 import。定数を直接読む（正本の二重実装禁止 — §7.3）
    cfg = rs.read_text(root, ".pre-commit-config.yaml") if ".pre-commit-config.yaml" in tracked else ""
    m = _LOCAL_REPO_BLOCK_RE.search(cfg)
    for hid in (_HOOK_ID_RE.findall(m.group(1)) if m else []):
        if hid not in install_kit.PRECOMMIT_REQUIRED:
            out.append(("HARD", "installer-token-drift",
                        "scripts/install_kit.py (PRECOMMIT_REQUIRED)",
                        f"ローカルフック {hid!r} が検証条項に無い——導入済みリポジトリの更新時、"
                        "旧 .pre-commit-config.yaml が KEPT 判定のまま新フックが静かに届かない"
                        "（同一コミットでトークンを足す — §3.3・G9）"))
    ik_text = rs.read_text(root, "scripts/install_kit.py") if "scripts/install_kit.py" in tracked else ""
    for rel in sorted(tracked):
        if not (rel.startswith((".claude/hooks/", ".codex/hooks/")) and rel.endswith(".py")):
            continue
        base = rel.rsplit("/", 1)[-1]
        if base not in ik_text:
            out.append(("HARD", "installer-token-drift",
                        "scripts/install_kit.py (settings_ok / codex_hooks_ok)",
                        f"フック {base} が settings 系の検証条項に現れない——更新時に旧設定が"
                        "KEPT のまま新フックの配線が静かに届かない（検証条項へ足す — §3.3・G9）"))


def check_binding_source(root: Path, tracked: set[str], out: list[Finding]) -> None:
    """バインディング刻印の整合（§12.7）。刻印は列ID@版・全対象ファイルで一致していること。

    値の不一致だけでなく「一部ファイルのみ刻印」も HARD——刻印し始めたのに一部を忘れた
    状態は、まさに静かに守りが消えるドリフト（全て未刻印の出荷状態だけが SOFT）。
    """
    present = [rel for rel in rs.BINDING_STAMP_FILES if rel in tracked]
    stamps: dict[str, str] = {}
    for rel in present:
        m = rs.BINDING_SOURCE_PATTERN.search(rs.read_text(root, rel))
        if m:
            stamps[rel] = m.group(1)
    distinct = sorted(set(stamps.values()))
    if len(distinct) > 1:
        detail = ", ".join(f"{rel}={sid}" for rel, sid in sorted(stamps.items()))
        out.append(("HARD", "binding-drift", "(BINDING-SOURCE)",
                    f"バインディング刻印が不一致: {detail}"
                    "（同じ列@版で揃える — §12.7）"))
    elif stamps and len(stamps) < len(present):
        missing = ", ".join(rel for rel in present if rel not in stamps)
        out.append(("HARD", "binding-drift", "(BINDING-SOURCE)",
                    f"バインディング刻印が一部ファイルに無い: {missing}"
                    f"（全対象ファイルへ `BINDING-SOURCE: {distinct[0]}` を刻印する — §12.7）"))
    elif not stamps:
        out.append(("SOFT", "binding-unstamped", "(BINDING-SOURCE)",
                    "バインディング刻印が未設定（Step 0 で採用列を選び、"
                    "対象ファイルに `BINDING-SOURCE: 列ID@版` を刻印する — §12.7）"))


def check_soft_limits(files: list[str], texts: dict[str, str], out: list[Finding]) -> None:
    # 1ファイル500行超
    for rel, text in texts.items():
        if rs.ext_of(rel) in rs.CODE_EXTS:
            n = text.count("\n") + (0 if text.endswith("\n") or not text else 1)
            if n > rs.MAX_FILE_LINES:
                out.append(("SOFT", "file-too-long", f"{rel}:{rs.MAX_FILE_LINES + 1}",
                            f"{rs.MAX_FILE_LINES}行超（現在 {n} 行）— 分割を検討"))

    # 1フォルダに CLAUDE.md 以外で7ファイル超（例外フォルダは表B — §3.3）
    counts: dict[str, int] = {}
    for rel in files:
        if rs.is_generated(rel) or rel.rsplit("/", 1)[-1] == "CLAUDE.md":
            continue
        d = rel.rsplit("/", 1)[0] if "/" in rel else ""
        counts[d] = counts.get(d, 0) + 1
    for d in sorted(counts):
        if any(d == e or (e and d.startswith(e + "/")) for e in rs.DIR_COUNT_EXEMPT):
            continue
        if counts[d] > rs.MAX_DIR_FILES:
            out.append(("SOFT", "dir-too-crowded", d or "(root)",
                        f"1フォルダに{rs.MAX_DIR_FILES}ファイル超（現在 {counts[d]}）— サブフォルダ化を検討"
                        "（分割で作る新フォルダには CLAUDE.md の新設も検討する — AGENTS.md §13）"))

    # 役割一行ヘッダー
    for rel, text in texts.items():
        if rs.ext_of(rel) in rs.HEADER_REQUIRED_EXTS:
            problem = rs.role_header_problem(rel, text)
            if problem:
                out.append(("SOFT", "missing-role-header", f"{rel}:1",
                            f"{problem}（書式: `<ファイル名> {rs.ROLE_HEADER_SEPARATOR} 役割` のコメント1行）"))

    # フォルダ CLAUDE.md の欠落（親フォルダが存在する場合のみ）
    tracked = set(files)
    for req in rs.REQUIRED_SOFT_PATHS:
        parent = req.rsplit("/", 1)[0] + "/"
        if req not in tracked and any(f.startswith(parent) for f in files):
            out.append(("SOFT", "missing-folder-claude-md", req, "フォルダ CLAUDE.md が無い"))


def check_orphans(root: Path, files: list[str], texts: dict[str, str], out: list[Finding]) -> None:
    """孤立ファイル検出: 1パスで（対象集合, 参照集合）を作り集合演算で出す（O(N²)禁止 — §7.3）。"""
    if not rs.ORPHAN_UNIVERSES:
        return
    pkg_roots = (
        rs.dart_package_roots(root, files) if ".dart" in rs.IMPORT_TARGET_EXTRACTORS else {}
    )
    referenced: set[str] = set()
    for rel, text in texts.items():
        referenced |= rs.import_targets(rel, text, pkg_roots)

    for prefixes, ext, entry_pats in rs.ORPHAN_UNIVERSES:
        for rel in files:
            if (rs.ext_of(rel) != ext or rs.is_generated(rel) or rs.is_test_file(rel)
                    or rs.is_ambient_declaration(rel)):
                continue  # テストは誰からも import されない正当な起点／環境宣言ファイルは import グラフ対象外（孤立ではない）
            if not any(rel.startswith(p) for p in prefixes):
                continue
            if any(pat.search(rel) for pat in entry_pats):
                continue
            if rel not in referenced:
                out.append(("SOFT", "orphan-file", rel,
                            "どこからも import / mod されていない孤立ファイル"))


def main() -> int:
    rs.reconfigure_stdio()
    root = rs.repo_root()
    files = rs.list_tracked_files(root)
    tracked = set(files)

    # 全ファイルはプロセス内で1回だけ読む（§7.3）
    texts: dict[str, str] = {}
    for rel in files:
        if rs.is_generated(rel):
            continue
        ext = rs.ext_of(rel)
        if ext in rs.CODE_EXTS or ext in rs.HEADER_REQUIRED_EXTS:
            texts[rel] = rs.read_text(root, rel)

    findings: list[Finding] = []
    check_required(files, tracked, findings)
    check_layers(texts, findings)
    check_required_content(root, files, texts, findings)
    check_tests(texts, findings)
    check_property_tests(texts, findings)
    check_gates_registry(root, findings)
    check_phase_table(root, findings)
    check_deprecated(texts, findings)
    check_log_calls(texts, findings)
    check_log_boundary_coverage(texts, findings)
    check_ffi_boundary(texts, findings)
    check_ui_testid(texts, findings)
    check_mcp_allowlist(root, files, findings)
    check_env_files(files, findings)
    check_context_doc_size(root, files, findings)
    check_hooks_installed(root, tracked, findings)
    check_binding_dead_patterns(findings)
    check_binding_dead_paths(files, tracked, findings)
    check_installer_tokens(root, tracked, findings)
    check_binding_source(root, tracked, findings)
    check_soft_limits(files, texts, findings)
    check_orphans(root, files, texts, findings)

    for sev, rule, loc, msg in findings:
        print(f"{sev}:{rule} {loc} {msg}", file=sys.stderr)
    rs.append_violations(root, "check-structure", findings)  # 違反ログ（§3.6）

    hard_count = sum(1 for f in findings if f[0] == "HARD")
    if hard_count:
        print(f"\ncheck-structure: hard違反 {hard_count} 件（コミット停止）。"
              "規則IDで .guardrails/GUARDRAILS.md §3.3 を参照して違反そのものを解消する。", file=sys.stderr)
        return 1
    if findings:
        print(f"\ncheck-structure: soft警告 {len(findings)} 件（コミットは通る）。", file=sys.stderr)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except rs.ScanError as exc:
        print(f"check_structure: 内部エラー: {exc}", file=sys.stderr)
        sys.exit(2)
    except Exception as exc:  # 想定外も契約どおり exit 2 に倒す
        print(f"check_structure: 内部エラー: {exc!r}", file=sys.stderr)
        sys.exit(2)
