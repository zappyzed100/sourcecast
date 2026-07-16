"""test_jmnedict.py — §8.4 DoD: サンプルXMLのパースとソース別テーブルの不混入を固定する"""

from pathlib import Path

import pytest

from history_radio.readings.entry import ReadingEntry
from history_radio.readings.jmnedict import (
    JmnedictParseError,
    hiragana_to_katakana,
    parse_jmnedict,
)
from history_radio.readings.store_jsonl import (
    SourceMixingError,
    load_entries,
    save_entries,
)

# JMnedict形式の記録済みサンプル（実体参照・複数表記・複数読み・非対象name_typeを含む）
_SAMPLE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<JMnedict>
<entry>
<ent_seq>5000001</ent_seq>
<k_ele><keb>西郷</keb></k_ele>
<r_ele><reb>さいごう</reb></r_ele>
<trans><name_type>&surname;</name_type><trans_det>Saigou</trans_det></trans>
</entry>
<entry>
<ent_seq>5000002</ent_seq>
<k_ele><keb>薩摩</keb></k_ele>
<r_ele><reb>さつま</reb></r_ele>
<trans><name_type>&place;</name_type><trans_det>Satsuma</trans_det></trans>
</entry>
<entry>
<ent_seq>5000003</ent_seq>
<k_ele><keb>某商事</keb></k_ele>
<r_ele><reb>ぼうしょうじ</reb></r_ele>
<trans><name_type>&company;</name_type><trans_det>Bou Shouji</trans_det></trans>
</entry>
<entry>
<ent_seq>5000004</ent_seq>
<r_ele><reb>ひらがなのみ</reb></r_ele>
<trans><name_type>&fem;</name_type><trans_det>kana only</trans_det></trans>
</entry>
</JMnedict>"""


def test_sample_xml_parses_to_person_and_place_entries() -> None:
    entries = parse_jmnedict(_SAMPLE_XML, fetched_at="2026-07-17")
    by_surface = {e.surface: e for e in entries}
    assert by_surface["西郷"].reading == "サイゴウ"
    assert by_surface["西郷"].kind == "person"
    assert by_surface["薩摩"].reading == "サツマ"
    assert by_surface["薩摩"].kind == "place"
    assert all(e.source_id == "jmnedict" for e in entries)
    assert all(e.license == "CC BY-SA 4.0" for e in entries)


def test_non_target_name_types_and_kana_only_entries_are_dropped() -> None:
    entries = parse_jmnedict(_SAMPLE_XML, fetched_at="2026-07-17")
    surfaces = {e.surface for e in entries}
    assert "某商事" not in surfaces  # 企業名は読み辞書の対象外
    assert "ひらがなのみ" not in surfaces  # 表記なし（かな見出しのみ）は対象外


def test_broken_xml_raises() -> None:
    with pytest.raises(JmnedictParseError, match="解析できない"):
        parse_jmnedict("<JMnedict><entry>", fetched_at="2026-07-17")


def test_hiragana_to_katakana_covers_small_kana_and_long_vowel() -> None:
    assert hiragana_to_katakana("さいごう") == "サイゴウ"
    assert hiragana_to_katakana("じゃっきー") == "ジャッキー"


def test_jmnedict_entries_cannot_be_written_into_another_sources_table(
    tmp_path: Path,
) -> None:
    """§8.3 DoD: 他ソース由来テーブルにJMnedict由来行が紛れ込まない——書き込み側で拒否。"""
    entries = parse_jmnedict(_SAMPLE_XML, fetched_at="2026-07-17")
    with pytest.raises(SourceMixingError, match="別ソース"):
        save_entries(tmp_path, "wikidata-kana", entries)
    # 正しいテーブルへは書ける
    path = save_entries(tmp_path, "jmnedict", entries)
    assert path.name == "jmnedict.jsonl"


def test_loading_detects_contaminated_table(tmp_path: Path) -> None:
    entries = parse_jmnedict(_SAMPLE_XML, fetched_at="2026-07-17")
    save_entries(tmp_path, "jmnedict", entries)
    # 別ソースの行を手で混入させる（攻撃・事故の再現）
    rogue = ReadingEntry(
        surface="東京",
        reading="トウキョウ",
        kind="place",
        confidence=1.0,
        source_id="wikidata-kana",
        source_url="https://www.wikidata.org/",
        license="CC0 1.0",
        fetched_at="2026-07-17",
    )
    with (tmp_path / "jmnedict.jsonl").open("a", encoding="utf-8") as f:
        f.write(rogue.model_dump_json() + "\n")
    with pytest.raises(SourceMixingError, match="混入"):
        load_entries(tmp_path, "jmnedict")


def test_round_trip_preserves_entries(tmp_path: Path) -> None:
    entries = parse_jmnedict(_SAMPLE_XML, fetched_at="2026-07-17")
    save_entries(tmp_path, "jmnedict", entries)
    loaded = load_entries(tmp_path, "jmnedict")
    assert loaded == entries
