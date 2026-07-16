"""test_era_dictionary.py — §8.4 DoD: 元号辞書の一意性・年代整合・連続性検証を固定する"""

from pathlib import Path

import pytest

from history_radio.readings.era_dictionary import (
    EraDictionaryError,
    load_era_dictionary,
    to_reading_entries,
)
from history_radio.readings.sources_config import (
    load_reading_sources,
    validate_entries_against_sources,
)

REPO_ROOT = Path(__file__).resolve().parents[4]
ERAS_YAML = REPO_ROOT / "config" / "readings" / "eras.yaml"


def _yaml(entries: str) -> str:
    return "eras:\n" + entries


def test_real_eras_yaml_loads_about_250_eras() -> None:
    eras = load_era_dictionary(ERAS_YAML)
    assert len(eras) >= 240  # §8.1「約250件」
    by_name = {e.name: e for e in eras}
    assert by_name["大化"].reading == "タイカ"
    assert by_name["大化"].start_year == 645
    assert by_name["令和"].end_year is None  # 現元号のみ無期限
    assert by_name["明治"].start_year == 1868


def test_real_eras_all_convert_to_valid_reading_entries() -> None:
    """全248件がReadingEntryの検証（カタカナ統一等）と未登録ソース拒否を通過する。"""
    eras = load_era_dictionary(ERAS_YAML)
    entries = to_reading_entries(eras, fetched_at="2026-07-17")
    assert len(entries) == len(eras)
    sources = load_reading_sources(REPO_ROOT / "config" / "readings" / "sources.yaml")
    validate_entries_against_sources(entries, sources)  # 例外なし
    assert all(e.kind == "era" for e in entries)


def test_unverified_era_has_lower_confidence() -> None:
    """§8.4「人手で一度検証」——未検証0.9・検証済み1.0を機械的に区別する。"""
    eras = load_era_dictionary(ERAS_YAML)
    entries = to_reading_entries(eras, fetched_at="2026-07-17")
    unverified = [e for e in entries if e.confidence == 0.9]
    assert unverified  # 初期状態は未検証
    assert all(e.confidence in (0.9, 1.0) for e in entries)


def test_duplicate_era_name_is_rejected(tmp_path: Path) -> None:
    dup = """  - name: 大化
    reading: タイカ
    start_year: 645
    end_year: 650
    wikidata_qid: Q1
    verified: false
  - name: 大化
    reading: タイカ
    start_year: 651
    end_year: null
    wikidata_qid: Q2
    verified: false
"""
    path = tmp_path / "eras.yaml"
    path.write_text(_yaml(dup), encoding="utf-8")
    with pytest.raises(EraDictionaryError, match="重複"):
        load_era_dictionary(path)


def test_end_before_start_is_rejected(tmp_path: Path) -> None:
    bad = """  - name: 大化
    reading: タイカ
    start_year: 650
    end_year: 645
    wikidata_qid: Q1
    verified: false
  - name: 令和
    reading: レイワ
    start_year: 2019
    end_year: null
    wikidata_qid: Q2
    verified: false
"""
    path = tmp_path / "eras.yaml"
    path.write_text(_yaml(bad), encoding="utf-8")
    with pytest.raises(EraDictionaryError, match="end_year"):
        load_era_dictionary(path)


def test_gap_after_701_is_rejected(tmp_path: Path) -> None:
    """§8.4 検証: 年代の欠落がない——大宝以降に2年超の空白があれば拒否。"""
    gapped = """  - name: 大宝
    reading: タイホウ
    start_year: 701
    end_year: 704
    wikidata_qid: Q1
    verified: false
  - name: 和銅
    reading: ワドウ
    start_year: 800
    end_year: null
    wikidata_qid: Q2
    verified: false
"""
    path = tmp_path / "eras.yaml"
    path.write_text(_yaml(gapped), encoding="utf-8")
    with pytest.raises(EraDictionaryError, match="空白"):
        load_era_dictionary(path)


def test_multiple_open_ended_eras_are_rejected(tmp_path: Path) -> None:
    two_open = """  - name: 平成
    reading: ヘイセイ
    start_year: 1989
    end_year: null
    wikidata_qid: Q1
    verified: false
  - name: 令和
    reading: レイワ
    start_year: 2019
    end_year: null
    wikidata_qid: Q2
    verified: false
"""
    path = tmp_path / "eras.yaml"
    path.write_text(_yaml(two_open), encoding="utf-8")
    with pytest.raises(EraDictionaryError, match="現元号1件のみ"):
        load_era_dictionary(path)
