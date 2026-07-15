# fill_bindings.py — 採用列の paste-block を管理区画へ機械充填する（契約: .guardrails/GUARDRAILS.md §11 前段・Phase 47）
"""fill_bindings.py — カタログの列を対象ファイルの管理区画へ自動適用する充填器。

導入の Step 0/2 でエージェントが手作業で行っていた「bindings/catalog.md から
paste-block をコピーして貼る」を機械化する（コピペは決定的な作業——LLM の仕事ではない）。

使い方（対象リポジトリのルートで）:
    uv run scripts/fill_bindings.py <列ID@版> [<列ID@版>...] [--dry-run]
例: uv run scripts/fill_bindings.py python-uv@10
    uv run scripts/fill_bindings.py dart-flutter@8 rust@9   # 併用（加算形が前提）

動作:
- bindings/catalog.md の `## 列: <ID>@<版>` 節から `<!-- FILL <対象パス> -->` マーカー
  直後の fenced code block を抽出し、対象ファイルの管理区画（>>> GUARDRAILS BINDING >>>）
  の内側末尾へ挿入する。
- 冪等: 同一ブロックが既に区画内に在れば SKIPPED（再実行しても二重貼りしない）。
- 刻印: 最初に指定された列を BINDING-SOURCE としてプレースホルダ行を置換（§12.7 の
  「プライマリ列を1つ」）。既に実IDで刻印済みなら触らない。
- 版上げの差分適用はしない（初回充填専用——版上げは PROMPT_claude_code_update.md U4 の
  持ち場。既存ブロックと新版ブロックの差分マージは判断を含むため機械化しない）。

出力: 1行1操作 `FILLED/SKIPPED/NO-BLOCK/STAMPED <対象> <列ID@版>`（G4）。
exit: 0 = 成功 / 1 = 列が無い・区画が壊れている等 / 2 = 内部エラー（§7.5 と同義）。
Windows 絶対規則（§7.2）: encoding/newline 明示・shell 非経由。
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import install_kit as ik  # noqa: E402  （管理区画の定義と抽出は installer が正本 — §7.3）
import repo_scan as rs  # noqa: E402

CATALOG = "bindings/catalog.md"
FILL_MARKER = re.compile(r"<!--\s*FILL\s+(\S+)\s*-->\s*\n```[a-z]*\n(.*?)\n```", re.S)
COLUMN_HEAD = re.compile(r"^## 列: ([A-Za-z0-9_.-]+@[0-9]+)\b.*$", re.M)
STAMP_PLACEHOLDER = re.compile(r"^#\s*BINDING-SOURCE:\s*<.*$", re.M)


def column_section(catalog_text: str, column: str) -> str | None:
    """`## 列: <column>` の節本文（次の `## ` まで）を返す。無ければ None。"""
    heads = list(COLUMN_HEAD.finditer(catalog_text))
    for i, m in enumerate(heads):
        if m.group(1) == column:
            end = heads[i + 1].start() if i + 1 < len(heads) else len(catalog_text)
            return catalog_text[m.end(): end]
    return None


def split_target(target: str) -> tuple[str, str | None]:
    return tuple(target.split("#", 1)) if "#" in target else (target, None)


def region_inner(text: str, region: str | None) -> tuple[int, int] | None:
    return ik.named_managed_inner(text, region) if region else ik.managed_inner(text)


def fill_one(root: Path, target_rel: str, block: str, column: str, dry: bool) -> str:
    """1ブロックを対象ファイルの管理区画へ挿入する。戻り値は表示ステータス。"""
    file_rel, region_name = split_target(target_rel)
    path = root / file_rel
    if not path.is_file():
        return "MISSING-TARGET"
    text = path.read_text(encoding="utf-8", errors="replace")
    inner = region_inner(text, region_name)
    if inner is None:
        return "NO-REGION"
    region = text[inner[0]: inner[1]]
    if block in region:
        return "SKIPPED"
    insert = f"# ---- {column} (fill_bindings) ----\n{block}\n"
    new_text = text[: inner[1]] + insert + text[inner[1]:]
    if not dry:
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(new_text)
    return "FILLED"


def validate_target(root: Path, target_rel: str) -> str | None:
    """書き込み前検証。失敗時に部分充填や不正刻印を残さないため全件先に走らせる。"""
    file_rel, region_name = split_target(target_rel)
    path = root / file_rel
    if not path.is_file():
        return "MISSING-TARGET"
    text = path.read_text(encoding="utf-8", errors="replace")
    if region_inner(text, region_name) is None:
        return "NO-REGION"
    return None


def stamp_primary(root: Path, column: str, dry: bool) -> list[str]:
    """BINDING_STAMP_FILES のプレースホルダ刻印をプライマリ列で置換する。"""
    done: list[str] = []
    for rel in rs.BINDING_STAMP_FILES:
        path = root / rel
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if f"BINDING-SOURCE: {column}" in text:
            continue  # 刻印済み（冪等）
        new_text, n = STAMP_PLACEHOLDER.subn(f"# BINDING-SOURCE: {column}", text, count=1)
        if n == 0:
            # プレースホルダが無いファイル（yaml 等はコメント形式が違う）——既存の刻印
            # 検査（binding-unstamped / binding-drift — §12.7）が残りを可視化する。
            continue
        if not dry:
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(new_text)
        done.append(rel)
    return done


def main() -> int:
    rs.reconfigure_stdio()
    ap = argparse.ArgumentParser(description="採用列の paste-block を管理区画へ機械充填する")
    ap.add_argument("columns", nargs="+", metavar="列ID@版",
                    help="適用する列（複数可。最初の列がプライマリ＝刻印に使う — §12.7）")
    ap.add_argument("--dry-run", action="store_true", help="書き込みせず判定のみ表示")
    args = ap.parse_args()

    root = rs.repo_root()
    catalog_path = root / CATALOG
    if not catalog_path.is_file():
        print(f"INTERNAL カタログが無い: {CATALOG}")
        return 2
    catalog = catalog_path.read_text(encoding="utf-8", errors="replace")

    failed = False
    filled_any = False
    selected: list[tuple[str, list[tuple[str, str]]]] = []

    # 先に列・ブロック・全貼り先を検証する。1件でも不正なら一切書かずに終了する。
    # 特に先頭列が不正なのに後続列だけ適用し、その不正IDを刻印する状態を防ぐ（G9）。
    for column in args.columns:
        section = column_section(catalog, column)
        if section is None:
            avail = ", ".join(m.group(1) for m in COLUMN_HEAD.finditer(catalog))
            print(f"NO-COLUMN {column} カタログに該当版の列が無い（存在する列: {avail}。"
                  "版まで一致させる——§12.7）")
            failed = True
            continue
        blocks = FILL_MARKER.findall(section)
        if not blocks:
            print(f"NO-BLOCK {column} FILL マーカー付き paste-block が節内に無い")
            failed = True
            continue
        selected.append((column, blocks))
        for target_rel, block in blocks:
            status = validate_target(root, target_rel)
            if status:
                print(f"{status} {target_rel} {column}")
                failed = True

    if failed:
        print("\nfill_bindings: 事前検証失敗（書き込みなし。上の行を解消して再実行）")
        return 1

    for column, blocks in selected:
        for target_rel, block in blocks:
            status = fill_one(root, target_rel, block, column, args.dry_run)
            print(f"{status} {target_rel} {column}")
            filled_any |= status == "FILLED"

    for rel in stamp_primary(root, args.columns[0], args.dry_run):
        print(f"STAMPED {rel} {args.columns[0]}")
    tail = "（--dry-run: 書き込みなし）" if args.dry_run else ""
    print(f"\nfill_bindings: 完了{tail}。次: `uv run scripts/check_structure.py` で"
          "binding-dead-pattern / binding-drift を確認し、`uv run scripts/dev.py gates` で"
          "有効化された門を見る（充填の検証は既存の門の持ち場 — G9）"
          + ("" if not filled_any else "。pre-commit / CI の列固有ブロックも名前付き管理区画へ"
             "適用済み。列にFILLマーカーが無い任意機能だけはカタログの注記に従う"))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except rs.ScanError as exc:
        print(f"fill_bindings: 内部エラー: {exc}", file=sys.stderr)
        sys.exit(2)
    except Exception as exc:  # 内部エラーは exit 2（検査の失敗と区別 — §7.5）
        print(f"INTERNAL {type(exc).__name__}: {exc}")
        sys.exit(2)
