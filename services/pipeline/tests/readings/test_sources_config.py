"""test_sources_config.py — §8.4基盤 DoD: ソース登録の検証と未登録source_idの拒否を固定する"""

from pathlib import Path

import pytest

from history_radio.readings.entry import ReadingEntry
from history_radio.readings.sources_config import (
    ReadingSourcesError,
    load_reading_sources,
    validate_entries_against_sources,
)

REPO_ROOT = Path(__file__).resolve().parents[4]
SOURCES_YAML = REPO_ROOT / "config" / "readings" / "sources.yaml"


def test_real_sources_yaml_loads_with_all_expected_ids() -> None:
    sources = load_reading_sources(SOURCES_YAML)
    ids = {s.source_id for s in sources}
    assert {
        "sudachidict",
        "jmnedict",
        "wikidata-kana",
        "ndl-web-authorities",
        "digital-agency-abr",
        "era-dictionary",
        "manual-dictionary",
    } <= ids


def test_every_source_has_attribution_text() -> None:
    """ライセンス表記の欠けたソースが登録できない（§8.4 検証）——実ファイル全件で確認。"""
    sources = load_reading_sources(SOURCES_YAML)
    assert all(s.attribution_text.strip() for s in sources)


def test_missing_attribution_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "sources.yaml"
    path.write_text(
        """
sources:
  - source_id: bad-source
    name: "表記なしソース"
    license: "CC0"
    url: "https://example.org"
    attribution_text: ""
    redistribution_allowed: true
    first_party: false
""",
        encoding="utf-8",
    )
    with pytest.raises(ReadingSourcesError):
        load_reading_sources(path)


def test_duplicate_source_id_is_rejected(tmp_path: Path) -> None:
    entry = """
  - source_id: dup
    name: "重複"
    license: "CC0"
    url: "https://example.org"
    attribution_text: "dup"
    redistribution_allowed: true
    first_party: false
"""
    path = tmp_path / "sources.yaml"
    path.write_text(f"sources:{entry}{entry}", encoding="utf-8")
    with pytest.raises(ReadingSourcesError, match="重複"):
        load_reading_sources(path)


def test_entry_with_unregistered_source_id_is_rejected() -> None:
    """未登録の source_id を持つ ReadingEntry を拒否する（§8.4 検証）。"""
    sources = load_reading_sources(SOURCES_YAML)
    rogue = ReadingEntry.model_validate(
        {
            "surface": "東京",
            "reading": "トウキョウ",
            "kind": "place",
            "confidence": 1.0,
            "source_id": "unregistered-dictionary",
            "source_url": "https://example.org",
            "license": "unknown",
            "fetched_at": "2026-07-17",
        }
    )
    with pytest.raises(ReadingSourcesError, match="未登録"):
        validate_entries_against_sources([rogue], sources)


def test_registered_entries_pass_validation() -> None:
    sources = load_reading_sources(SOURCES_YAML)
    entry = ReadingEntry.model_validate(
        {
            "surface": "明治",
            "reading": "メイジ",
            "kind": "era",
            "confidence": 1.0,
            "source_id": "era-dictionary",
            "source_url": "config/readings/eras.yaml",
            "license": "本プロジェクトの資産",
            "fetched_at": "2026-07-17",
        }
    )
    validate_entries_against_sources([entry], sources)  # 例外なし
