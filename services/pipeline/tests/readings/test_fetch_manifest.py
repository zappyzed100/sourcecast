"""test_fetch_manifest.py — §8.4 DoD: 同一入力での再取得が同一ハッシュになる決定性を固定する"""

from history_radio.readings.entry import ReadingEntry
from history_radio.readings.fetch_manifest import build_fetch_manifest


def _entry(surface: str, reading: str) -> ReadingEntry:
    return ReadingEntry.model_validate(
        {
            "surface": surface,
            "reading": reading,
            "kind": "person",
            "confidence": 0.8,
            "source_id": "jmnedict",
            "source_url": "https://example.org",
            "license": "CC BY-SA 4.0",
            "fetched_at": "2026-07-17",
        }
    )


def test_same_entries_produce_same_hash_regardless_of_order() -> None:
    """Phase 7 DoD: 同一入力での再取得が同一ハッシュになる（順序が変わっても同一）。"""
    a = [_entry("西郷", "サイゴウ"), _entry("東京", "トウキョウ")]
    b = [_entry("東京", "トウキョウ"), _entry("西郷", "サイゴウ")]
    manifest_a = build_fetch_manifest("jmnedict", a, fetched_at="2026-07-17")
    manifest_b = build_fetch_manifest("jmnedict", b, fetched_at="2026-07-18")  # 日付が違っても
    assert manifest_a.content_hash == manifest_b.content_hash


def test_different_entries_produce_different_hash() -> None:
    a = [_entry("西郷", "サイゴウ")]
    b = [_entry("西郷", "サイゴウチガウ")]
    manifest_a = build_fetch_manifest("jmnedict", a, fetched_at="2026-07-17")
    manifest_b = build_fetch_manifest("jmnedict", b, fetched_at="2026-07-17")
    assert manifest_a.content_hash != manifest_b.content_hash


def test_manifest_records_source_and_count() -> None:
    entries = [_entry("西郷", "サイゴウ"), _entry("東京", "トウキョウ")]
    manifest = build_fetch_manifest("jmnedict", entries, fetched_at="2026-07-17")
    assert manifest.source_id == "jmnedict"
    assert manifest.entry_count == 2
    assert manifest.fetched_at == "2026-07-17"
    assert manifest.content_hash.startswith("sha256:")


def test_empty_entries_still_produce_a_hash() -> None:
    manifest = build_fetch_manifest("jmnedict", [], fetched_at="2026-07-17")
    assert manifest.entry_count == 0
    assert manifest.content_hash.startswith("sha256:")
