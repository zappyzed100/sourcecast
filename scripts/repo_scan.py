# repo_scan.py — 共通走査モジュール: ファイル列挙・読み込み・シンボル/import抽出（契約: .guardrails/GUARDRAILS.md §7.3）
#
# generate_structure.py と check_structure.py と dev.py がこのモジュールを import する。
# 同じ正規表現を2箇所に書くことは禁止（二重実装は必ずドリフトする — §7.3）。
#
# 【BINDING セクション】言語・構成バインディング（.guardrails/GUARDRAILS.md §11 Step 0 の表A/B/D）は
# 本ファイル後半の「BINDING」セクションに集約してある。v2キットは言語なし（中立既定値）で
# 出荷される——Step 0 で bindings/catalog.md の採用列の paste-block をここへ充填する。
# 走査ロジック（前半）と言語別抽出関数（中盤）は触らない。
#
# BINDING-SOURCE の刻印は下の管理区画内に書く（§12.7。未刻印は SOFT:binding-unstamped）
#
# Windows 絶対規則（§7.2）:
#   - すべての open() に encoding="utf-8" 明示。読み込みは errors="replace"。
#   - ファイル列挙は git ls-files -z（os.walk / glob 禁止）。
#   - stdout/stderr を utf-8 に reconfigure（cp932 コンソールでの検査クラッシュ防止）。
#   - ソートは素の sorted()（Unicode コードポイント順）。

from __future__ import annotations

import json
import posixpath
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


class ScanError(RuntimeError):
    """内部エラー（git 不在・ルート解決失敗など）。呼び出し側は exit 2 に変換する（§7.4）。"""


# ----------------------------------------------------------------------------
# 走査ロジック（言語非依存）
# ----------------------------------------------------------------------------

def reconfigure_stdio() -> None:
    """cp932 コンソールへの日本語 print で検査自体が落ちる誤爆を防ぐ（§7.2）。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def repo_root() -> Path:
    """カレントディレクトリ非依存でリポジトリルートを解決する（§7.4）。"""
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"], capture_output=True, check=False
        )
    except OSError as exc:
        raise ScanError(f"git を起動できない: {exc}")
    if proc.returncode != 0:
        raise ScanError("git rev-parse --show-toplevel が失敗（git リポジトリ外か）")
    return Path(proc.stdout.decode("utf-8", "replace").strip())


def list_tracked_files(root: Path) -> list[str]:
    """git 追跡下のファイルを '/' 区切り・安定順で返す（§7.2）。

    追跡済みでもディスクに無いファイル（削除コミットの直前 = pre-commit が走る状態）は
    除外する——含めると後段の read_text が FileNotFoundError で検査器ごと落ち、
    本来の `missing-required` 等の違反報告（Fail Loudly）が内部エラーに化ける（v2.4 修正）。
    """
    proc = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z"], capture_output=True, check=False
    )
    if proc.returncode != 0:
        raise ScanError("git ls-files が失敗")
    tracked = sorted(p for p in proc.stdout.decode("utf-8", "replace").split("\0") if p)
    return [p for p in tracked if (root / p).is_file()]


def read_text(root: Path, rel: str) -> str:
    """ファイル読み込みの唯一の入口。非UTF-8断片が混ざってもクラッシュしない（§7.2）。"""
    with open(root / rel, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


VIOLATION_LEDGER_REL = ".guardrails/violations.jsonl"


def append_violations(root: Path, stage: str, findings) -> None:
    """違反ログ（violation ledger — §3.6・v2.34）への追記。findings は
    (severity, rule_id, location, …) の列。1違反1行の JSONL・gitignore 済みの
    ローカル telemetry で、記録するのは第1層（事実）のみ——意味づけ・要約は書かない。

    記録は門の**付帯機能**——書き込み失敗で門の判定（exit code）を変えない。
    ただし黙って握りつぶさない（G9）: 失敗は stderr に1行出して素通しする。
    """
    rows = list(findings)
    if not rows:
        return
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    try:
        with open(root / VIOLATION_LEDGER_REL, "a", encoding="utf-8", newline="\n") as f:
            for sev, rule, loc, *_ in rows:
                f.write(json.dumps(
                    {"ts": ts, "stage": stage, "severity": sev, "rule_id": rule,
                     "location": loc}, ensure_ascii=False) + "\n")
    except OSError as exc:
        print(f"[violation-ledger] 記録失敗（門の判定には影響しない — "
              f".guardrails/GUARDRAILS.md §3.6）: {exc}", file=sys.stderr)


def git_config_get(root: Path, key: str) -> str | None:
    """`git config --get <key>` の値。未設定なら None（hooks-path-overridden 検査用 — §3.3）。"""
    proc = subprocess.run(
        ["git", "-C", str(root), "config", "--get", key], capture_output=True, check=False
    )
    if proc.returncode != 0:
        return None
    value = proc.stdout.decode("utf-8", "replace").strip()
    return value or None


def git_hooks_dir(root: Path) -> Path:
    """git が実際に参照するフックディレクトリ（worktree・core.hooksPath 込みで解決 — §3.3）。"""
    proc = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--git-path", "hooks"],
        capture_output=True, check=False,
    )
    if proc.returncode != 0:
        raise ScanError("git rev-parse --git-path hooks が失敗")
    p = Path(proc.stdout.decode("utf-8", "replace").strip())
    return p if p.is_absolute() else root / p


def ext_of(rel: str) -> str:
    base = rel.rsplit("/", 1)[-1]
    i = base.rfind(".")
    return base[i:] if i > 0 else ""


def is_comment_line(ext: str, line: str) -> bool:
    stripped = line.lstrip()
    return any(stripped.startswith(p) for p in LINE_COMMENT_PREFIXES.get(ext, ()))


def is_generated(rel: str) -> bool:
    return any(p.search(rel) for p in GENERATED_PATTERNS)


def is_test_file(rel: str) -> bool:
    return any(p.search(rel) for p in TEST_PATH_PATTERNS)


def is_ambient_declaration(rel: str) -> bool:
    """TS の環境宣言ファイル（`declare global` 等）。import されずに tsconfig の
    include 経由で自動的に効くため、import グラフ検査（孤立ファイル検出）の対象外。"""
    return rel.endswith(".d.ts")


def _first_meaningful_line(text: str) -> str | None:
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith("#!"):  # shebang は読み飛ばす
            continue
        return s
    return None


def role_header(rel: str, text: str) -> str | None:
    """先頭コメント1行から役割記述を取り出す。無ければ None（黙って落とさない — §7.4）。"""
    prefixes = LINE_COMMENT_PREFIXES.get(ext_of(rel))
    if not prefixes:
        return None
    line = _first_meaningful_line(text)
    if line is None:
        return None
    for p in prefixes:
        if line.startswith(p):
            body = line[len(p):].lstrip("/!").strip()
            return body or None
    return None


def role_header_problem(rel: str, text: str) -> str | None:
    """役割一行ヘッダー規約（`<ファイル名> — 役割` 形式のコメント1行）への違反理由。無問題なら None。"""
    header = role_header(rel, text)
    if header is None:
        return "先頭に役割一行コメントが無い"
    if ROLE_HEADER_SEPARATOR not in header:
        return f"役割ヘッダーに区切り『{ROLE_HEADER_SEPARATOR}』が無い"
    if rel.rsplit("/", 1)[-1] not in header:
        return "役割ヘッダーにファイル名が含まれていない"
    return None


def public_symbols(rel: str, text: str) -> list[str]:
    """公開シンボル抽出（行指向の正規表現による近似であり、それは仕様 — §7.4）。"""
    fn = SYMBOL_EXTRACTORS.get(ext_of(rel))
    return fn(text) if fn else []


def import_targets(rel: str, text: str, dart_pkg_roots: dict[str, str]) -> set[str]:
    """このファイルが参照する他ファイルのリポジトリ相対パス集合（孤立ファイル検出用・近似）。

    抽出器のディスパッチは BINDING の IMPORT_TARGET_EXTRACTORS が正本（列充填で有効化）。
    """
    fn = IMPORT_TARGET_EXTRACTORS.get(ext_of(rel))
    if fn is None:
        return set()
    return fn(rel, text, dart_pkg_roots)


# ----------------------------------------------------------------------------
# 言語別の抽出関数（利用可能な実装。有効化はBINDINGのディスパッチ表が正本）
# ----------------------------------------------------------------------------

# --- Dart ---

_DART_TYPE_DECL = re.compile(
    r"^(?:abstract\s+|base\s+|final\s+|sealed\s+|interface\s+|mixin\s+)*"
    r"(class|mixin|enum|extension\s+type|extension|typedef)\s+([A-Za-z_$][\w$]*)"
)
_DART_TOPLEVEL_FN = re.compile(
    r"^(?:external\s+)?(?:[A-Za-z_$][\w$<>,?\s\[\]]*?\s+)?([a-z][\w$]*)\s*(?:<[^;=]*?>)?\s*\("
)
_DART_FN_EXCLUDE = frozenset(
    {"if", "for", "while", "switch", "catch", "assert", "return", "await", "throw"}
)
_DART_IMPORT = re.compile(r"""^\s*(?:import|export|part)\s+['"]([^'"]+)['"]""")
_PUBSPEC_NAME = re.compile(r"^name:\s*([A-Za-z0-9_]+)")


def _dart_public_symbols(text: str) -> list[str]:
    out: list[str] = []
    for line in text.splitlines():
        if not line or line[0] in " \t})":  # インデント0の宣言だけを見る（§7.4）
            continue
        m = _DART_TYPE_DECL.match(line)
        if m:
            kind, name = " ".join(m.group(1).split()), m.group(2)
            if not name.startswith("_"):
                out.append(f"{kind} {name}")
            continue
        m = _DART_TOPLEVEL_FN.match(line)
        if m:
            name = m.group(1)
            if not name.startswith("_") and name not in _DART_FN_EXCLUDE:
                out.append(f"fn {name}()")
    return out


def dart_package_roots(root: Path, files: list[str]) -> dict[str, str]:
    """pubspec.yaml の name → その lib/ ディレクトリ（package: import の解決用）。"""
    out: dict[str, str] = {}
    for rel in files:
        if rel == "pubspec.yaml" or rel.endswith("/pubspec.yaml"):
            for line in read_text(root, rel).splitlines():
                m = _PUBSPEC_NAME.match(line)
                if m:
                    base = rel[: -len("pubspec.yaml")]
                    out[m.group(1)] = base + "lib"
                    break
    return out


def _dart_import_targets(rel: str, text: str, pkg_roots: dict[str, str]) -> set[str]:
    out: set[str] = set()
    base_dir = posixpath.dirname(rel)
    for line in text.splitlines():
        m = _DART_IMPORT.match(line)
        if not m:
            continue
        target = m.group(1)
        if target.startswith("dart:"):
            continue
        if target.startswith("package:"):
            pkg, _, sub = target[len("package:"):].partition("/")
            lib_root = pkg_roots.get(pkg)
            if lib_root:
                out.add(posixpath.normpath(posixpath.join(lib_root, sub)))
            continue
        out.add(posixpath.normpath(posixpath.join(base_dir, target)))
    return out


# --- Rust ---

_RUST_PUB_DECL = re.compile(
    r"^pub(?:\s*\([^)]*\))?\s+"
    r"(?:async\s+|unsafe\s+|extern\s+\"[^\"]*\"\s+)*"
    r"(const\s+fn|fn|struct|enum|union|trait|mod|const|static|type)\s+"
    r"([A-Za-z_]\w*)"
)
_RUST_MOD_DECL = re.compile(r"^\s*(?:pub(?:\s*\([^)]*\))?\s+)?mod\s+([A-Za-z_]\w*)\s*;")
_RUST_PATH_ATTR = re.compile(r'#\[\s*path\s*=\s*"([^"]+)"\s*\]')


def _rust_public_symbols(text: str) -> list[str]:
    out: list[str] = []
    for line in text.splitlines():
        m = _RUST_PUB_DECL.match(line)
        if m:
            out.append(f'{" ".join(m.group(1).split())} {m.group(2)}')
    return out


def _rust_mod_targets(rel: str, text: str, _pkg_roots: dict[str, str]) -> set[str]:
    """`mod x;` / `#[path = "..."]` を実ファイルパスへ解決（近似）。"""
    out: set[str] = set()
    d = posixpath.dirname(rel)
    base_name = rel.rsplit("/", 1)[-1]
    base = d if base_name in ("lib.rs", "main.rs", "mod.rs") else posixpath.join(d, base_name[:-3])
    pending_path: str | None = None
    for line in text.splitlines():
        pm = _RUST_PATH_ATTR.search(line)
        if pm:
            pending_path = pm.group(1)
            continue
        m = _RUST_MOD_DECL.match(line)
        if m:
            if pending_path is not None:
                out.add(posixpath.normpath(posixpath.join(d, pending_path)))
                pending_path = None
            else:
                name = m.group(1)
                out.add(posixpath.join(base, name + ".rs"))
                out.add(posixpath.join(base, name, "mod.rs"))
        else:
            pending_path = None
    return out


# --- TypeScript / JavaScript ---

_TS_EXPORT_DECL = re.compile(
    r"^export\s+(?:default\s+)?(?:async\s+)?"
    r"(function|class|const|let|var|type|interface|enum)\s+([A-Za-z_$][\w$]*)"
)
_TS_IMPORT = re.compile(r"""^\s*(?:import|export)[^'"]*['"]([^'"]+)['"]""")
# 動的 import() は式なので行頭とは限らない（例: `lazy(() => import("./X"))`）。
# 行頭アンカーの _TS_IMPORT だと、変数名が短くPrettierが改行しない場合に取りこぼす。
_TS_DYNAMIC_IMPORT = re.compile(r"""\bimport\s*\(\s*['"]([^'"]+)['"]""")
_TS_RESOLVE_EXTS = (".ts", ".tsx", ".js", ".jsx", "/index.ts", "/index.tsx")


def _ts_public_symbols(text: str) -> list[str]:
    out: list[str] = []
    for line in text.splitlines():
        m = _TS_EXPORT_DECL.match(line)
        if m:
            out.append(f"{m.group(1)} {m.group(2)}")
    return out


def _ts_import_targets(rel: str, text: str, _pkg_roots: dict[str, str]) -> set[str]:
    """相対 import のみ解決（パッケージ import は対象外・近似 — §7.4 の流儀）。"""
    out: set[str] = set()
    base_dir = posixpath.dirname(rel)
    for line in text.splitlines():
        m = _TS_IMPORT.match(line) or _TS_DYNAMIC_IMPORT.search(line)
        if not m:
            continue
        target = m.group(1)
        if not target.startswith("."):
            continue
        resolved = posixpath.normpath(posixpath.join(base_dir, target))
        if ext_of(resolved):
            out.add(resolved)
        else:
            for suffix in _TS_RESOLVE_EXTS:
                out.add(resolved + suffix)
    return out


# --- Python ---

_PY_TOPLEVEL_DECL = re.compile(r"^(?:async\s+)?(def|class)\s+([A-Za-z_]\w*)")


def _py_public_symbols(text: str) -> list[str]:
    out: list[str] = []
    for line in text.splitlines():
        m = _PY_TOPLEVEL_DECL.match(line)
        if m and not m.group(2).startswith("_"):
            out.append(f"{m.group(1)} {m.group(2)}")
    return out


# ============================================================================
# BINDING — 言語・構成バインディング（.guardrails/GUARDRAILS.md §11 Step 0 の表A/B/Dの正本）
#
# v2キットの出荷状態は「言語なし」——全スロットが中立既定値で、言語・構成に依存する
# 検査は不発。Step 0 で bindings/catalog.md の採用列の paste-block をこのセクションへ
# 充填し、冒頭ヘッダーの BINDING-SOURCE に列ID@版を刻印する（§12.7）。
# 「該当なし」は空リスト/空集合で表現してよいが、判断せずに空けるのは禁止（Step 0）。
# ============================================================================

# --- 行コメントの接頭辞（コメント行は検査対象から除外する。言語横断の一般表で中立）---
LINE_COMMENT_PREFIXES: dict[str, tuple[str, ...]] = {
    ".dart": ("//",),
    ".rs": ("//",),
    ".ts": ("//",),
    ".tsx": ("//",),
    ".js": ("//",),
    ".jsx": ("//",),
    ".mjs": ("//",),
    ".go": ("//",),
    ".kt": ("//",),
    ".swift": ("//",),
    ".py": ("#",),
    ".sh": ("#",),
}

# --- ファイル分類（列充填: CODE_EXTS / HEADER_REQUIRED_EXTS に列の拡張子を足す）---
CODE_EXTS: set[str] = set()                       # 500行検査・レイヤー検査などの対象
HEADER_REQUIRED_EXTS: set[str] = {".py", ".sh"}   # 役割一行ヘッダーの必須対象（キット自身の分は常時）
ROLE_HEADER_SEPARATOR = "—"                       # ヘッダー書式: `<ファイル名> — 役割`

# --- 生成物（手編集禁止・索引/検査から除外 — §2・§7.4。一般則のみ・列が追記する）---
GENERATED_PATTERNS = [re.compile(p) for p in (
    r"(^|/)build/",
    r"(^|/)dist/",
    r"(^|/)target/",
    r"(^|/)node_modules/",
    r"(^|/)\.dart_tool/",
    r"(^|/)__pycache__/",
    r"\.pyc$",
    r"^STRUCTURE\.md$",
)]

# --- テストファイルの判別（§3.4 検査2・§9 の検査対象の定義。列充填）---
TEST_PATH_PATTERNS: list[re.Pattern] = []

# --- インラインテストの判別（§3.4 検査2・検査6 — v2.39。列充填）---
# テストを別ファイルでなく**同一ファイル内**に同居させる言語（例: Rust の
# `#[cfg(test)] mod tests`）は、パス判別（TEST_PATH_PATTERNS）ではテスト同梱を検出
# できない——fix: が実際にテストを足していても fix-without-test で誤ブロックされる。
# check_commit_msg.py がステージ済み diff の**追加行**をこのパターンで走査し、パス一致
# との OR で「テスト同梱」とみなす。キー = 拡張子（充填時は CODE_EXTS へも足す——
# binding-dead-pattern が取りこぼしを検査する §3.3）。パスで判別できる言語は充填不要
# （「該当なし」の判断はカタログの列に記録する）。
INLINE_TEST_PATTERNS: dict[str, list[re.Pattern]] = {}

# --- 単一テストファイル実行（§5 red-first 証明 — v2.7・Phase 18。列充填。None なら不発）---
# check_red_first.py が fix の追加テストを親コミットの worktree 上で1ファイルずつ実行する
# コマンド。"{file}" トークンが SINGLE_TEST_CWD 相対のテストパスに展開される（dev.py の
# "{args}" と同じ流儀）。**単一スロット**＝複数列併用時はプライマリ言語の1列だけが配線する
# （配線外のテストは対象外として1行表示——境界は §5）。単独実行が構造的に不能な言語は
# None のまま「該当なし＋代替」をカタログへ判断ごと記録する（空欄不可・該当なし可）。
SINGLE_TEST_COMMAND: list[str] | None = None
SINGLE_TEST_CWD = ""   # コマンドを実行する worktree 内の相対ディレクトリ（"" = ルート）

# --- 依存マニフェスト（§3.4 検査4 undeclared-dependency — v2.5）---
# キー = マニフェストのファイル名（basename 一致——モノレポのネストも対象）。
# 値 = (種別, 抽出対象セクションのタプル)。種別 ∈ {"json","toml-table","toml-array",
# "yaml-block"}——抽出の実装は check_commit_msg.py（データはここ・実装はスクリプト — §7.3）。
# LINE_COMMENT_PREFIXES と同じ「言語横断の中立既定値」として同梱する——該当マニフェストが
# 無いリポジトリでは何も発火しないため、言語なし出荷と両立する。列は加算で追記してよい
# （例: DEPENDENCY_MANIFESTS["go.mod"] = ...）。lockfile（package-lock.json / uv.lock /
# Cargo.lock / pubspec.lock）は載せない＝推移的更新は対象外（§3.4）。
DEPENDENCY_MANIFESTS: dict[str, tuple[str, tuple[str, ...]]] = {
    "package.json": ("json", ("dependencies", "devDependencies")),
    "pyproject.toml": ("toml-array", ("project.dependencies",)),
    "Cargo.toml": ("toml-table", ("dependencies",)),
    "pubspec.yaml": ("yaml-block", ("dependencies", "dev_dependencies")),
}

# --- 構成（表B）: レイヤーと依存方向（一方向のみ — §3.3 layer-violation。列充填）---
# (対象ファイルの prefix, 禁止パターン, 説明)。コメント行は判定前に除外される。
LAYER_FORBIDDEN_IMPORTS: list[tuple[str, re.Pattern, str]] = []

# --- 必須ディレクトリ・ファイル（表B — §3.3 missing-required。言語なしの最小集合）---
# 正本4文書に加え、防壁の実体ファイル自体も対象——防壁が消えることは静かな fail-open の
# 最悪形（G7/G9）。列は表Bの必須（例: "app"）をここへ += する。
REQUIRED_PATHS = [
    "AGENTS.md", ".guardrails/BOOTSTRAP.md", "CLAUDE.md", ".guardrails/GUARDRAILS.md", ".guardrails/GOALS.md", "bindings/catalog.md",
    ".pre-commit-config.yaml", ".gitattributes", ".python-version",
    ".claude/settings.json",
    ".claude/hooks/guard_git_bypass.py", ".claude/hooks/post_edit_format.py",
    ".claude/hooks/post_edit_lint.py", ".claude/hooks/stop_incomplete_guard.py",
    ".claude/hooks/session_baseline.py", ".claude/hooks/guard_human_wip.py",
    ".codex/hooks.json", ".codex/hooks/codex_hook_adapter.py",
    ".github/workflows/guardrails-ci.yml",
    "scripts/repo_scan.py", "scripts/generate_structure.py",
    "scripts/check_structure.py", "scripts/check_commit_msg.py", "scripts/dev.py",
    "scripts/install_kit.py", "scripts/check_guard_corpus.py",
    "scripts/check_red_first.py", "scripts/check_bootstrap.py",
    "scripts/check_codex_hooks.py",
    "scripts/fill_bindings.py", "scripts/check_fill_bindings.py", "scripts/check_rule_dod.py",
    "tests/guard_corpus.tsv", "tests/injections/common.json",
    "tests/injections/ts-react-web.json", "tests/injections/python-uv.json",
    "tests/injections/dart-flutter.json", "tests/injections/rust.json",
]

# --- キット原本自身の判定（§3.3 kit-source-exempt — v2.14・Phase 27）---
# install_kit.py の META_FILES に同居（配布物からは常に除外——バイトコピーされる
# scripts/repo_scan.py 自体にフラグを持たせると導入先にも複製され判定が骨抜きになるため、
# 「配布されないファイルの有無」という構造的シグナルだけを見る — G9）。
KIT_SOURCE_MARKER = ".guardrails-kit-source"


def is_kit_source_repo(tracked: set[str]) -> bool:
    """このチェックアウトがキット原本自身か（導入先での Step 1 未着手と区別するための
    明示マーカー——構造だけでは両者が同型になるため推測に頼らない — §3.3）。"""
    return KIT_SOURCE_MARKER in tracked


# --- 常時読込文書の行数 soft 上限（§3.3 context-doc-too-large — v2.17・Phase 28）---
# エージェントが常時/自動で読む規約文書の肥大＝注意力の希釈（G3）を警告する。
# 出典: 調査③（2026-07-07。CLAUDE.md は最大200行程度の業界指針）。中立既定値・列上書き可。
# この警告は Skills 化保留（§10——「常駐が問題化した実測」）のセンサーを兼ねる。
CONTEXT_DOC_LIMITS: list[tuple[re.Pattern, int]] = [
    (re.compile(r"(^|/)CLAUDE\.md$"), 200),   # ルート薄層＋フォルダ知見
    (re.compile(r"^AGENTS\.md$"), 500),       # 全章の正本（列充填で育つ分の余白込み）
]

# --- .env 系の追跡禁止（§3.3 env-file-tracked — v2.18・Phase 29）---
# 追跡してよい .env 系は「値の入らない雛形」だけ（basename 完全一致。列が += で追記可）。
# gitleaks は内容パターン検査＝低エントロピーの実値は素通りし得るため、存在自体を hard で塞ぐ。
ENV_FILE_ALLOWED: set[str] = {".env.example", ".env.sample", ".env.template"}
ENV_FILE_PATTERN = re.compile(r"(^|/)\.env(\.[A-Za-z0-9_.-]+)?$")

# --- コミット規模の soft 上限（§3.4 検査7 commit-too-large — v2.13・Phase 26）---
# 1コミットの純変更行数（追加+削除。生成物・lockfile 除外）がこれを超えたら soft 警告。
# 出典: 著名ワークフローの収斂（Superpowers「2〜5分粒度のタスク」・小さな反復の一般則）
# ——大きな塊は「どのゲートがどの変更を検証したか」を追えなくする（実行規律2の一般開発版）。
# 中立既定値。列が上書きしてよい（例: 生成コードの多い列は緩める）。
COMMIT_SIZE_SOFT_LIMIT: int = 400
# 除外する lockfile（基名一致。生成物は GENERATED_PATTERNS が別途除外）
LOCKFILE_NAMES: set[str] = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "bun.lockb",
    "uv.lock", "poetry.lock", "Cargo.lock", "pubspec.lock", "Gemfile.lock",
}

# --- MCP 採用許可リスト（§3.3 mcp-not-allowed — v2.11・Phase 23）---
# プロジェクト正本（追跡された .mcp.json——basename 一致）に置いてよい MCP サーバー名。
# 中立既定値は playwright のみ＝ **2026-07-07 の MCP・エコシステム調査の判定**（採用は
# 操作レール §12.4 の Playwright MCP 1本。Serena / GitHub MCP / Supabase 系ほかは
# 不採用（README v2.11 の不採用記録）、Chrome DevTools MCP / Context7 / Serena（大規模
# 既存限定）/ Skills 化は保留（§10）として判定ごと記録済み）。
# 追加は catalog の「MCP・エコシステム採用規律」のゲート3条を通し、判定を記録してから
# += する（列が足してよい——加算形）。空集合にすると「MCP 全面禁止」の意味になる。
# タスク単位のローカル追加（claude mcp add——保留運用形）は追跡外＝本検査の対象外。
MCP_ALLOWED_SERVERS: set[str] = {"playwright"}

# --- 必須コンテンツ（存在検査）: (規則ID, 対象パス正規表現, 内容正規表現, 説明) ---
# 既定1件（v2.10・Phase 22）: CLAUDE.md 冒頭の `@AGENTS.md` インポート。規約の正本は
# AGENTS.md（全エージェント共通）で、Claude Code はこの import 経由でのみ到達する（§6）。
# 同期スクリプトではなく「分割＋存在検査」でドリフトを構造的に封じる（G5）。列は += で追記可。
REQUIRED_CONTENT_RULES: list[tuple[str, re.Pattern, re.Pattern, str]] = [
    ("agents-import-missing", re.compile(r"^CLAUDE\.md$"), re.compile(r"^@AGENTS\.md\s*$", re.M),
     "CLAUDE.md に `@AGENTS.md` インポート行が無い（Claude Code が規約の正本 AGENTS.md に"
     "到達できない——本文の複製で代替しない — .guardrails/GUARDRAILS.md §6）"),
]

# --- テスト内 sleep 系（§3.3 test-sleep: flakyの温床。列充填）---
SLEEP_PATTERNS: dict[str, list[tuple[re.Pattern, str]]] = {}

# --- テスト内 非決定入力（§9.2 test-nondeterminism。列充填）---
NONDETERMINISM_PATTERNS: dict[str, list[tuple[re.Pattern, str]]] = {}

# --- テスト内 外部I/O（§9.5 test-network: 外部I/Oの検疫。列充填）---
TEST_NETWORK_PATTERNS: dict[str, list[tuple[re.Pattern, str]]] = {}

# --- 非決定性テストの免除（test-sleep/test-nondeterminism/test-network 共通 —
# §9.5・v2.25・Phase 35）---
# 非決定性の再現そのものがテストの本質という正当なケースがある（例: 実ブラウザが
# ヘッダーとbodyを分割TCP書き込みするタイミングのズレを再現する回帰テストは、
# sleep と生ソケットの両方が意図的に必要）。境界行の前後
# NONDETERMINISM_EXEMPT_WINDOW 行以内に `NONDETERMINISM-EXEMPT: 理由` コメントが
# あれば免除する。理由の妥当性は検証しない——存在検査のみ（NO-LOG / RED-FIRST-EXEMPT
# と同じ境界の引き方 — G9）。
NONDETERMINISM_EXEMPT_PATTERN = re.compile(r"NONDETERMINISM-EXEMPT:\s*\S")
NONDETERMINISM_EXEMPT_WINDOW = 3  # 中立既定値・列上書き可

# --- 世代交代・非推奨 API（§3.3 deprecated-api — v2.6・Phase 15。列充填）---
# LLM が訓練カットオフの都合で書きがちな旧作法を、プロンプト規則（心得）でなく
# 列パターン（門）として封鎖する。テスト内限定でなく**全コード走査**（テスト含む）。
# 列値の出典規律はカタログ注記が正本（①ベンダー公式 AI プロンプト ②公式非推奨告知のみ
# 初期値。正規表現で近似できない構文世代は載せない——偽陽性>価値 — §7.4）。
DEPRECATED_PATTERNS: dict[str, list[tuple[re.Pattern, str]]] = {}

# --- feat⇔plan 対（§3.4 検査5 feat-without-plan — v2.6 soft 導入・v2.8 hard 昇格＝G14）---
# PLAN_DOC_PATTERNS = 設計根拠文書の置き場（AGENTS.md §4。中立既定値——列が += してよい）。
# PLAN_LAYER_ROOTS = 新規ディレクトリを監視するレイヤーのルート（列充填。空なら不発——
# layer-violation と同じ「列充填で有効化」。例: ["src"] / ["app/lib"] / ["engine/src"]）。
PLAN_DOC_PATTERNS = [re.compile(p) for p in (r"(^|/)plan\.md$", r"^docs/plans/")]
PLAN_LAYER_ROOTS: list[str] = []

# --- 確率的コンポーネント（表B）: 有る場合のみ設定（§9.1 test-calls-solver-direct）---
SOLVER_DIRECT_CALL_PATTERNS: list[tuple[re.Pattern, str]] = []
SOLVER_TEST_WRAPPER_NAME = "solve_for_test"   # この名前を含む行は許可（ラッパー経由）

# --- 性質形テストの存在検査（§9.6 missing-property-test — v2.41・Phase 43・soft。列充填）---
# 確率的コンポーネント有（SOLVER_DIRECT_CALL_PATTERNS 充填）のリポジトリでは、実例
# オラクル（期待値のハードコード）だけの検証はテストが実装と欠陥を共有し得る
# （self-deception — surveys/SURVEY_LLM_TESTGEN.md）。テストファイルのどこにも性質形
# テストの痕跡（PBT ライブラリの import 等——列充填）が無ければ soft 警告する。
# 性質の中身・質は検査しない——存在検査のみ（NO-LOG と同じ境界の引き方 — G9）。
PROPERTY_TEST_MARKERS: list[tuple[re.Pattern, str]] = []

# --- print 系直呼び（§8.2 log-direct-call: 出口の単一化。列充填）---
PRINT_CALL_PATTERNS: dict[str, list[tuple[re.Pattern, str]]] = {}
# print 系を呼んでよい唯一の出口（§8.2。列充填）
LOG_EXIT_FILES: set[str] = set()
# 出口検査の除外プレフィックス。scripts/ はキット自身の出力契約（§3.3 の1違反1行・
# §12.1 の `[dev] 動詞:` 形式）が stdout/stderr 直書きを規定するため既定で除外——
# これが無いと python 系の列を採用した瞬間、キット自身が log-direct-call で落ちる（G13）。
# .claude/hooks/ と .codex/hooks/ も同じ理由で除外（v2.45・Phase 47 の fill 実測で発見:
# フックの print/stderr は「exit 2 の stderr が Claude に渡る」というハーネス契約そのもの
# （§1・§2）であり、アプリの単一出口 logOp の管轄外。python-uv 列が【要実測】のまま
# 実充填されたことが無く、初の機械充填 DoD で 23 件の自己偽陽性として顕在化した）。
LOG_EXIT_PREFIXES: tuple[str, ...] = ("scripts/", ".claude/hooks/", ".codex/hooks/")

# --- 境界検査（§8.2 missing-catch-unwind 相当: 該当言語がある列のみ）---
FFI_BOUNDARY_FILE_PATTERNS: list[re.Pattern] = []
CATCH_UNWIND_PATTERN = re.compile(r"catch_unwind")

# --- ログ被覆検査（§8.4 missing-log-coverage — v2.19・Phase 31・soft。列充填）---
# 「重要度」は機械が判定できないため対象にしない。代わりに客観的に検出できる境界
# （I/O・外部呼び出し・エラーハンドラ——列充填）に絞り、境界行の前後 LOG_BOUNDARY_WINDOW
# 行以内に単一出口のログ呼び出し（LOG_CALL_PATTERN）か `NO-LOG: 理由` コメントの
# どちらかが無ければ soft 警告する。理由の妥当性は検証しない（存在検査のみ——
# RED-FIRST-EXEMPT と同じ境界の引き方 — G9「沈黙の禁止」）。
LOG_BOUNDARY_PATTERNS: dict[str, list[tuple[re.Pattern, str]]] = {}
LOG_CALL_PATTERN: dict[str, re.Pattern] = {}
NO_LOG_COMMENT_PATTERN = re.compile(r"NO-LOG:\s*\S")
LOG_BOUNDARY_WINDOW = 5  # 境界行の前後何行を「被覆済み」とみなすか（中立既定値・列上書き可）

# --- UI操作要素のテストID検査（§12.4 ui-missing-testid。列充填）---
# (対象ファイル正規表現, 操作要素の開始タグ正規表現, テストID属性の正規表現, 説明)
# 開始タグ正規表現は全文に対して適用される（[^>] は改行も跨ぐ＝複数行タグも近似で拾う）。
UI_TESTID_RULES: list[tuple[re.Pattern, re.Pattern, re.Pattern, str]] = []

# --- 孤立ファイル検出の対象範囲とエントリポイント（§3.3 soft: orphan-file。列充填）---
# (対象prefixのリスト, 拡張子, エントリポイント正規表現のリスト)
ORPHAN_UNIVERSES: list[tuple[list[str], str, list[re.Pattern]]] = []

# --- import/参照抽出のディスパッチ（表A。列充填。利用可能な実装は中盤に定義済み）---
# 例: {".dart": _dart_import_targets, ".rs": _rust_mod_targets,
#      ".ts": _ts_import_targets, ".tsx": _ts_import_targets}
IMPORT_TARGET_EXTRACTORS: dict[str, object] = {}

# --- soft 上限（§3.3 soft。言語なしで有効）---
MAX_FILE_LINES = 500
MAX_DIR_FILES = 7
DIR_COUNT_EXEMPT = ("", "scripts", "bindings")   # "" = ルート直下（設定ファイル群が集まるため例外）
REQUIRED_SOFT_PATHS: list[str] = []

# --- シンボル抽出の言語ディスパッチ（表A: 公開シンボル抽出。列充填。実装は中盤）---
# 例: {".dart": _dart_public_symbols, ".rs": _rust_public_symbols,
#      ".ts": _ts_public_symbols, ".tsx": _ts_public_symbols, ".py": _py_public_symbols}
SYMBOL_EXTRACTORS: dict[str, object] = {
    ".py": _py_public_symbols,   # キット自身のスクリプト索引のため常時有効
}

# --- バインディング刻印（§12.7 binding-drift / binding-unstamped）---
# 刻印の書式: 各ファイル内のコメント行 `BINDING-SOURCE: <列ID@版>`（例: ts-react-web@5）。
# 検査対象ファイルは下のリスト（追跡されているものだけ読む）。
BINDING_SOURCE_PATTERN = re.compile(r"BINDING-SOURCE:\s*([A-Za-z0-9][A-Za-z0-9_.-]*@[0-9]+)")
BINDING_STAMP_FILES = [
    "scripts/repo_scan.py",
    "scripts/dev.py",
    ".pre-commit-config.yaml",
    ".github/workflows/guardrails-ci.yml",
    ".claude/hooks/post_edit_format.py",
    ".claude/hooks/post_edit_lint.py",
]

# --- 門の台帳（GATE REGISTRY — §12.1 `dev.py gates`・v2.43・Phase 45）---
# 「このキットが何をできるか」を機械可読で1箇所に持つ（発見の導線 — G4/G9。
# CUSTOMIZE.md 導線と同型）。手書き文書との二重正本にしないため、検査器が実際に emit
# する規則IDとの一致を check_structure の `gates-registry-drift`（hard）が機械検査する
# ——台帳に無い規則を emit したら赤、emit されない規則が台帳に残っても赤。
# 行 = (識別子, 区分（正本節）, 有効化, 一行説明)。有効化の書式:
#   "always"        = 言語なしで常時有効
#   "var:NAME"      = repo_scan の同名バインディングが充填されて初めて発火（空なら不発）
#   "vars:A|B"      = いずれかの充填で発火
#   "hook:名前"     = .claude/settings.json にそのフックが配線されていれば有効
#   "static:ラベル" = 状態を計算せずラベルをそのまま表示（CI・キット原本限定 等）
GATE_REGISTRY: list[tuple[str, str, str, str]] = [
    # --- §1 編集直後（フック層）---
    ("post-edit-format", "§1 編集直後", "hook:post_edit_format.py",
     "編集直後の自動整形（第1段。対象拡張子は列充填の DISPATCH）"),
    ("post-edit-lint", "§1 編集直後", "hook:post_edit_lint.py",
     "編集直後の単一ファイル lint（第2段・exit 2 で自己修正を要求）"),
    # --- §2 操作直前（フック層）---
    ("guard-git-bypass", "§2 操作直前", "hook:guard_git_bypass.py",
     "--no-verify / force push / hooksPath 付け替え / pre-commit uninstall の技術的ブロック"),
    ("work-loss-guard", "§2 操作直前", "hook:guard_git_bypass.py",
     "非可逆な作業消失（rm -rf .git・dirty での reset --hard 等）のブロック"),
    ("ownership-guard", "§2c 編集直前", "hook:guard_human_wip.py",
     "人間の未コミット変更への AI の Edit/Write をブロック（commit/stash で自動解除）"),
    ("stop-gate", "§2b ターン終了", "hook:stop_incomplete_guard.py",
     "未コミット作業・検査赤のままの「完了しました」を差し戻し"),
    # --- §3.3 構造検査（pre-commit・hard）---
    ("missing-required", "§3.3 コミット時", "always", "必須ファイル・防壁の実体の欠落検出"),
    ("agents-import-missing", "§3.3 コミット時", "always", "CLAUDE.md の @AGENTS.md インポート欠落"),
    ("mcp-not-allowed", "§3.3 コミット時", "always", "MCP 許可リスト外の常駐サーバー検出"),
    ("mcp-unparseable", "§3.3 コミット時", "always", ".mcp.json が解釈不能（soft）"),
    ("env-file-tracked", "§3.3 コミット時", "always", "実値の入り得る .env 系の追跡拒否"),
    ("layer-violation", "§3.3 コミット時", "var:LAYER_FORBIDDEN_IMPORTS", "レイヤー逆流 import の検出"),
    ("test-sleep", "§3.3 コミット時", "var:SLEEP_PATTERNS", "テスト内 sleep（flaky の温床）の検出"),
    ("test-nondeterminism", "§3.3 コミット時", "var:NONDETERMINISM_PATTERNS", "テスト内の時刻・seed なし乱数の検出"),
    ("test-network", "§3.3 コミット時", "var:TEST_NETWORK_PATTERNS", "テスト内の外部 I/O 直呼びの検出"),
    ("test-calls-solver-direct", "§3.3 コミット時", "var:SOLVER_DIRECT_CALL_PATTERNS",
     "ソルバー直呼びテストの拒否（solve_for_test 経由のみ — §9.1）"),
    ("missing-property-test", "§9.6 コミット時", "var:SOLVER_DIRECT_CALL_PATTERNS",
     "確率的コンポーネント有なのに性質形テストが無い（soft・オラクル契約）"),
    ("log-direct-call", "§8.2 コミット時", "var:PRINT_CALL_PATTERNS", "単一出口以外での print 系直呼びの検出"),
    ("missing-log-coverage", "§8.4 コミット時", "var:LOG_BOUNDARY_PATTERNS",
     "I/O・エラー境界のログ被覆（soft・NO-LOG: で免除可視化）"),
    ("missing-catch-unwind", "§8.2 コミット時", "var:FFI_BOUNDARY_FILE_PATTERNS", "FFI 境界の catch_unwind 欠落検出"),
    ("deprecated-api", "§3.3 コミット時", "var:DEPRECATED_PATTERNS", "世代交代した旧 API の使用検出（全コード走査）"),
    ("ui-missing-testid", "§12.4 コミット時", "var:UI_TESTID_RULES", "UI 操作要素のテスト ID 欠落検出"),
    ("binding-drift", "§12.7 コミット時", "always", "バインディング刻印の不一致検出"),
    ("binding-unstamped", "§12.7 コミット時", "always", "刻印未設定の注意喚起（soft）"),
    ("binding-dead-pattern", "§3.3 コミット時", "always", "充填パターンの拡張子取りこぼし（充填時の不発）検出"),
    ("binding-dead-path", "§3.3 コミット時", "always", "充填パスのファイル移動ドリフト（充填後の不発）検出（soft）"),
    ("hook-type-missing", "§3.3 コミット時", "always", "pre-commit シムの部分欠落（install 忘れ）検出"),
    ("hooks-path-overridden", "§3.3 コミット時", "always", "core.hooksPath による全フック迂回の静的検出"),
    ("hooks-not-installed", "§3.3 コミット時", "always", "シム未導入の注意喚起（soft・Step 3 前の正常状態）"),
    ("installer-token-drift", "§3.3 コミット時", "static:キット原本限定",
     "インストーラ検証条項のフック追随漏れ検出"),
    ("context-doc-too-large", "§3.3 コミット時", "always", "常時読込文書の肥大警告（soft・Skills 化のセンサー）"),
    ("file-too-long", "§3.3 コミット時", "always", "1ファイル500行超の警告（soft）"),
    ("dir-too-crowded", "§3.3 コミット時", "always", "1フォルダ7ファイル超の警告（soft）"),
    ("missing-role-header", "§3.3 コミット時", "var:HEADER_REQUIRED_EXTS", "役割一行ヘッダーの欠落警告（soft）"),
    ("missing-folder-claude-md", "§3.3 コミット時", "var:REQUIRED_SOFT_PATHS", "レイヤーCLAUDE.md の欠落警告（soft）"),
    ("orphan-file", "§3.3 コミット時", "var:ORPHAN_UNIVERSES", "どこからも import されない孤立ファイル警告（soft）"),
    ("gates-registry-drift", "§3.3 コミット時", "always", "この台帳自体と検査器コードの不一致検出（台帳の門）"),
    # --- §3.4 commit-msg 検査 ---
    ("commit-msg-format", "§3.4 コミット時", "always", "コミットメッセージ形式（feat|fix|test|docs|refactor|chore:）"),
    ("fix-without-test", "§3.4 コミット時", "vars:TEST_PATH_PATTERNS|INLINE_TEST_PATTERNS",
     "fix: への回帰テスト同梱の機械強制（G10）"),
    ("governance-without-goal", "§3.4 コミット時", "always", "正本3文書の変更に G 引用が無ければ拒否"),
    ("undeclared-dependency", "§3.4 コミット時", "always", "依存の黙認追加の拒否（本文に宣言1行を要求）"),
    ("feat-without-plan", "§3.4 コミット時", "var:PLAN_LAYER_ROOTS", "新規構造への設計根拠同梱の機械強制（G14）"),
    ("feat-without-test", "§3.4 コミット時", "vars:TEST_PATH_PATTERNS|INLINE_TEST_PATTERNS",
     "feat: のテスト欠落警告（soft）"),
    ("commit-too-large", "§3.4 コミット時", "always", "コミット規模の警告（soft）"),
    ("test-shrink", "§3.4 コミット時", "var:TEST_PATH_PATTERNS", "既存テストの純減警告（soft・弱体化の可視化）"),
    # --- §5 CI（最終防衛線）---
    ("red-first", "§5 CI", "static:CI（required・列充填で単一テスト実行）",
     "fix 同梱テストが親コミットで赤だった（バグを再現した）ことの機械証明"),
    ("commit-msg-history-mismatch", "§5 CI", "static:CI",
     "PR 範囲の全コミットへ commit-msg 検査を履歴再実行（ローカルフック未導入でも門が掛かる）"),
    ("ci-rerun-all", "§5 CI", "static:CI", "編集直後〜push の全検査の再実行（迂回の最終防衛線）"),
    # --- §3.5 / §2 門の門（検査の検証）---
    ("guard-corpus", "§2 門の門", "always", "迂回ブロッカー自身のコーパス回帰再生（門番の回帰テスト）"),
    ("ownership-guard-scenarios", "§2c 門の門", "always", "所有権ガードの複数手順シナリオ再生"),
    ("codex-hooks-check", "§2 門の門", "always", "Codex フック設定とアダプタの回帰検査"),
    ("check-bootstrap", "§3.5 導入時", "always", "進捗台帳の ✅ を再実行検証（虚偽✅・順序スキップの門）"),
    ("violation-ledger", "§3.6 常時", "always", "門が止めた事象の機械記録（soft→hard 昇格を計数で判断する土台）"),
    # --- §11 前段 / §12 導入・ランタイム ---
    ("install-detect", "§11 導入", "static:install_kit.py --detect", "採用列の候補をマニフェストから提示"),
    ("install-diff-check", "§11 導入", "static:install_kit.py --diff/--check",
     "適用前プレビューと CI 用ドリフト検出"),
    ("fill-bindings", "§11 導入", "static:fill_bindings.py <列ID@版>",
     "採用列の paste-block を管理区画へ機械充填＋刻印（Step 0/2 のコピペ作業の機械化）"),
    ("rule-dod", "§11 導入", "always",
     "列の違反注入コーパス再生（注入→発火→除去→沈黙の機械証明——dev.py dod）"),
    ("managed-splice", "§11 更新", "static:UPGRADED 時に自動", "管理区画の充填を保持したままキットを更新"),
    ("dev-verbs", "§12.1 実行時", "always", "全プロジェクト共通の開発動詞ルーター（未配線は明示エラー）"),
    ("probe", "§12.1 実行時", "always", "迂回防止への事前照会（実行前に ALLOW/DENY）"),
    ("probe-live", "§12.1 実行時", "always", "実ホスト経路のフック発火を sentinel で実測"),
    ("selftest", "§12.1 実行時", "always", "門の違反注入コーパス一括再生"),
    ("doctor", "§12.1 実行時", "always", "環境診断の集約表示 → check 実行"),
]
# gates-registry-drift の照合対象（検査器コードとの一致を強制する区分）
GATE_REGISTRY_ENFORCED = {"§3.3", "§3.4", "§8.2", "§8.4", "§9.6", "§12.4", "§12.7"}

# >>> GUARDRAILS BINDING >>>
# 採用列の paste-block は**この区画内**へ貼る（bindings/catalog.md — §12.7）。
# インストーラの更新（UPGRADED）はこの区画の中身だけを既存から引き継ぐ（§11 前段・Phase 44）。
# 刻印（BINDING-SOURCE の行 — §12.7）もこの区画内に書く。
# BINDING-SOURCE: python-uv@10 + ts-react-web@12（パスはモノレポ構成 — plan.md §2.2 —
# に合わせて手で調整済み。カタログの生の paste-block は `src/` 直下の単一パッケージ
# を前提にしており、このリポジトリの実配置（services/pipeline/src・apps/*/src・
# packages/*/src）とは異なるため、パス依存の行だけ書き換えている）
# ---- python-uv@10 (fill_bindings, パス調整済み) ----
CODE_EXTS |= {".py"}
TEST_PATH_PATTERNS += [re.compile(p) for p in (r"_test\.py$", r"(^|/)test_[^/]+\.py$")]
SLEEP_PATTERNS[".py"] = [(re.compile(r"\btime\.sleep\s*\("), "time.sleep")]
NONDETERMINISM_PATTERNS[".py"] = [
    (re.compile(r"\bdatetime\.now\s*\(|\btime\.time\s*\("), "現在時刻（Clock/引数で注入する）"),
    (re.compile(r"\brandom\.(random|randint|choice)\s*\("), "seedなし乱数（Random(seed)を注入する）")]
TEST_NETWORK_PATTERNS[".py"] = [
    (re.compile(r"\brequests\.|\bhttpx\.|\burllib\.request"), "requests/httpx/urllib")]
PRINT_CALL_PATTERNS[".py"] = [(re.compile(r"(?<![\w.])print\s*\("), "print(")]
LOG_BOUNDARY_PATTERNS[".py"] = [
    (re.compile(r"\brequests\.(get|post|put|delete|patch)\s*\(|\bhttpx\.(get|post|put|delete|patch)\s*\("),
     "外部HTTP呼び出し"),
    (re.compile(r"^\s*except\b"), "エラーハンドラ")]
LOG_CALL_PATTERN[".py"] = re.compile(r"\blog_op\s*\(")
DEPRECATED_PATTERNS[".py"] = [
    (re.compile(r"\butcnow\s*\("), "datetime.utcnow()（3.12 で非推奨。datetime.now(timezone.utc) へ）"),
    (re.compile(r"\butcfromtimestamp\s*\("), "datetime.utcfromtimestamp()（3.12 で非推奨。fromtimestamp(ts, timezone.utc) へ）")]
PLAN_LAYER_ROOTS += ["services/pipeline/src"]
SINGLE_TEST_COMMAND = ["uv", "run", "pytest", "{file}"]   # 単一スロット。python/ts両列とも定義するため
# こちらをプライマリに採用（判断ごと記録 — §5）: 生成パイプラインの権利判定・選出・ゲート等の
# ドメインロジックが red-first の主戦場になる見込みで、TS側（vitest）はUI層で構成が薄い。
# vitestの単一ファイル実行はpnpm workspace越しにcwd指定が要り、この1スロットに同居できない
# ——TS側の red-first は「その列のCIジョブが通しで再現する」運用に留める。
LOG_EXIT_FILES |= {"services/pipeline/src/history_radio/log.py"}   # Phase 1で実装予定（§8.2）
# 確率的コンポーネント有（表B）の場合のみ以下2行を充填（無ければ貼らない——§9.6）:
# SOLVER_DIRECT_CALL_PATTERNS += [(re.compile(r"\bsolve\s*\("), "ソルバー本体の直呼び")]
# PROPERTY_TEST_MARKERS += [(re.compile(r"\bfrom hypothesis import|\bimport hypothesis\b"), "hypothesis")]
# ORPHAN_UNIVERSES は既定のまま不発（Pythonのimport解決は近似が粗い。必要なら列を版上げ）
# SYMBOL_EXTRACTORS[".py"] は出荷既定で有効（キット自身の索引のため）——追記不要
# ---- ts-react-web@12 (fill_bindings, パス調整済み) ----
CODE_EXTS |= {".ts", ".tsx"}
HEADER_REQUIRED_EXTS |= {".ts", ".tsx"}
TEST_PATH_PATTERNS += [re.compile(p) for p in (r"\.test\.tsx?$", r"^e2e/.*\.spec\.ts$")]
_TS_SLEEP = [(re.compile(r"\bsetTimeout\s*\(|\bsleep\s*\("), "setTimeout/sleep")]
SLEEP_PATTERNS[".ts"] = _TS_SLEEP; SLEEP_PATTERNS[".tsx"] = _TS_SLEEP
_TS_NONDET = [(re.compile(r"\bDate\.now\s*\("), "Date.now()（Clock抽象で注入する）"),
              (re.compile(r"\bnew Date\s*\(\s*\)"), "引数なし new Date()（固定時刻を渡す）"),
              (re.compile(r"\bMath\.random\s*\("), "Math.random()（seed付き乱数を注入する）")]
NONDETERMINISM_PATTERNS[".ts"] = _TS_NONDET; NONDETERMINISM_PATTERNS[".tsx"] = _TS_NONDET
_TS_NET = [(re.compile(r"\bfetch\s*\(|\baxios\b|\bXMLHttpRequest\b"), "fetch/axios/XHR")]
TEST_NETWORK_PATTERNS[".ts"] = _TS_NET; TEST_NETWORK_PATTERNS[".tsx"] = _TS_NET
_TS_PRINT = [(re.compile(r"\bconsole\.(log|info|debug)\s*\("), "console.*(")]
PRINT_CALL_PATTERNS[".ts"] = _TS_PRINT; PRINT_CALL_PATTERNS[".tsx"] = _TS_PRINT
LOG_EXIT_FILES |= {"apps/admin/src/lib/log.ts"}   # Phase 11で実装予定（§8.2）
_TS_LOG_BOUNDARY = [(re.compile(r"\bfetch\s*\("), "外部HTTP呼び出し（fetch）"),
                    (re.compile(r"\bcatch\s*[({]"), "エラーハンドラ（catch）")]
LOG_BOUNDARY_PATTERNS[".ts"] = _TS_LOG_BOUNDARY; LOG_BOUNDARY_PATTERNS[".tsx"] = _TS_LOG_BOUNDARY
LOG_CALL_PATTERN[".ts"] = re.compile(r"\blogOp\s*\(")
LOG_CALL_PATTERN[".tsx"] = re.compile(r"\blogOp\s*\(")
UI_TESTID_RULES += [(re.compile(r"\.tsx$"),
                     re.compile(r"<(?:button|a|input|select|textarea|[A-Z]\w*)\b[^>]*on(?:Click|Submit|Change)=[^>]*>"),
                     re.compile(r"data-testid\s*="),
                     "React操作要素")]
ORPHAN_UNIVERSES += [(["apps/admin/src/"], ".ts", [re.compile(r"(^|/)main\.tsx?$"), re.compile(r"vite\.config")]),
                     (["apps/admin/src/"], ".tsx", [re.compile(r"(^|/)main\.tsx?$")])]
IMPORT_TARGET_EXTRACTORS[".ts"] = _ts_import_targets
IMPORT_TARGET_EXTRACTORS[".tsx"] = _ts_import_targets
SYMBOL_EXTRACTORS[".ts"] = _ts_public_symbols
SYMBOL_EXTRACTORS[".tsx"] = _ts_public_symbols
# _TS_DEPRECATED（@supabase/auth-helpers-nextjs）は不採用——このプロジェクトはSupabaseを
# 使わない（plan.md §2.1: SQLite+Git+R2）。該当しない非推奨パターンを持ち込まない。
PLAN_LAYER_ROOTS += ["apps/site/src", "apps/admin/src", "packages/contracts/src"]

# ---- プロジェクト固有の特別対応（AGENTS.md §6・2026-07-15 決定。本来は
# scripts/install_workbench.py が適用する契約だが、このリポジトリにはまだ存在しないため
# 手で適用する。内容はAGENTS.md §6の正本コードブロックと同一）----
GENERATED_PATTERNS += [re.compile(r"^\.claude/skills/")]
GENERATED_PATTERNS += [re.compile(r"^design-system/")]
# <<< GUARDRAILS BINDING <<<
