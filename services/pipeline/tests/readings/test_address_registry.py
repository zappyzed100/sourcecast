"""test_address_registry.py — §8.4 DoD: PDL1.0の出典・加工表示が欠けないことを固定する"""

from pathlib import Path

from history_radio.readings.address_registry import AddressColumns, convert_address_rows
from history_radio.readings.sources_config import (
    load_reading_sources,
    validate_entries_against_sources,
)

REPO_ROOT = Path(__file__).resolve().parents[4]

# 実CSVのヘッダー名は取得時に確認する（列名パラメータ化の理由 — アダプタのdocstring参照）。
# テストでは列名を明示指定し、変換ロジック自体を固定する。
_COLUMNS = AddressColumns(name_column="町字名", kana_column="町字名_カナ")


def _rows() -> list[dict[str, str]]:
    return [
        {"町字名": "丸の内", "町字名_カナ": "まるのうち", "都道府県名": "東京都"},
        {"町字名": "難波", "町字名_カナ": "なんば", "都道府県名": "大阪府"},
        {"町字名": "難波", "町字名_カナ": "なんば", "都道府県名": "大阪府"},  # 重複
    ]


def test_rows_convert_to_place_entries_with_katakana_readings() -> None:
    entries = convert_address_rows(_rows(), _COLUMNS, fetched_at="2026-07-17")
    by_surface = {e.surface: e for e in entries}
    assert by_surface["丸の内"].reading == "マルノウチ"
    assert by_surface["難波"].reading == "ナンバ"
    assert all(e.kind == "place" for e in entries)


def test_duplicate_rows_are_deduplicated() -> None:
    entries = convert_address_rows(_rows(), _COLUMNS, fetched_at="2026-07-17")
    assert len(entries) == 2  # 丸の内・難波（難波の重複行は1件に統合）


def test_every_entry_carries_attribution_and_processing_notice() -> None:
    """development-plan.md §8.4 検証: 出典表示と加工した旨が各レコードに欠けていない。"""
    entries = convert_address_rows(_rows(), _COLUMNS, fetched_at="2026-07-17")
    for e in entries:
        assert "デジタル庁" in e.license  # 出典表示
        assert "加工して作成" in e.license  # 加工した旨


def test_rows_missing_name_or_kana_are_skipped() -> None:
    rows = [
        {"町字名": "", "町字名_カナ": "からっぽ"},
        {"町字名": "読みなし町", "町字名_カナ": ""},
        {"町字名": "正常町", "町字名_カナ": "せいじょうちょう"},
    ]
    entries = convert_address_rows(rows, _COLUMNS, fetched_at="2026-07-17")
    assert [e.surface for e in entries] == ["正常町"]


def test_already_katakana_kana_column_is_left_as_is() -> None:
    rows = [{"町字名": "梅田", "町字名_カナ": "ウメダ"}]
    entries = convert_address_rows(rows, _COLUMNS, fetched_at="2026-07-17")
    assert entries[0].reading == "ウメダ"


def test_entries_pass_source_registration_check() -> None:
    entries = convert_address_rows(_rows(), _COLUMNS, fetched_at="2026-07-17")
    sources = load_reading_sources(REPO_ROOT / "config" / "readings" / "sources.yaml")
    validate_entries_against_sources(entries, sources)  # 例外なし
