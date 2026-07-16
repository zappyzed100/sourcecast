"""test_sudachi.py — §8.4 DoD: SudachiDict導入と既知語の読みが引けることを固定する"""

from dataclasses import dataclass
from pathlib import Path

from history_radio.readings.sources_config import (
    load_reading_sources,
    validate_entries_against_sources,
)
from history_radio.readings.sudachi import (
    create_tokenizer,
    fetch_sudachi_readings,
    tokens_to_reading_entries,
)

REPO_ROOT = Path(__file__).resolve().parents[4]


@dataclass(frozen=True, slots=True)
class _FakeToken:
    """SudachiPy Morpheme互換のテスト用フェイク（実辞書のロードを避ける）。"""

    _surface: str
    _reading: str
    _pos: tuple[str, ...]

    def surface(self) -> str:
        return self._surface

    def reading_form(self) -> str:
        return self._reading

    def part_of_speech(self) -> tuple[str, ...]:
        return self._pos


def test_person_name_token_maps_to_person_kind() -> None:
    token = _FakeToken(
        "西郷隆盛", "サイゴウタカモリ", ("名詞", "固有名詞", "人名", "一般", "*", "*")
    )
    entries = tokens_to_reading_entries([token], fetched_at="2026-07-17")
    assert len(entries) == 1
    assert entries[0].kind == "person"
    assert entries[0].reading == "サイゴウタカモリ"
    assert entries[0].source_id == "sudachidict"
    assert entries[0].license == "Apache-2.0"


def test_place_name_token_maps_to_place_kind() -> None:
    token = _FakeToken("東京", "トウキョウ", ("名詞", "固有名詞", "地名", "一般", "*", "*"))
    entries = tokens_to_reading_entries([token], fetched_at="2026-07-17")
    assert entries[0].kind == "place"


def test_common_noun_maps_to_common_kind() -> None:
    token = _FakeToken("銅像", "ドウゾウ", ("名詞", "普通名詞", "一般", "*", "*", "*"))
    entries = tokens_to_reading_entries([token], fetched_at="2026-07-17")
    assert entries[0].kind == "common"


def test_particles_and_verbs_are_skipped() -> None:
    """名詞以外（助詞・動詞等）は読み辞書の対象外——TTSが困る固有名詞に絞る。"""
    tokens = [
        _FakeToken("で", "デ", ("助詞", "格助詞", "*", "*", "*", "*")),
        _FakeToken("見", "ミ", ("動詞", "非自立可能", "*", "*", "上一段-マ行", "連用形-一般")),
    ]
    assert tokens_to_reading_entries(tokens, fetched_at="2026-07-17") == []


def test_non_katakana_reading_is_skipped_not_raised() -> None:
    """数字・記号等カタカナ化できない語は候補にしない——1語の失敗で全体を止めない。"""
    tokens = [
        _FakeToken("1990", "1990", ("名詞", "数詞", "*", "*", "*", "*")),
        _FakeToken("東京", "トウキョウ", ("名詞", "固有名詞", "地名", "一般", "*", "*")),
    ]
    entries = tokens_to_reading_entries(tokens, fetched_at="2026-07-17")
    assert len(entries) == 1
    assert entries[0].surface == "東京"


def test_entries_pass_source_registration_check() -> None:
    token = _FakeToken("東京", "トウキョウ", ("名詞", "固有名詞", "地名", "一般", "*", "*"))
    entries = tokens_to_reading_entries([token], fetched_at="2026-07-17")
    sources = load_reading_sources(REPO_ROOT / "config" / "readings" / "sources.yaml")
    validate_entries_against_sources(entries, sources)  # 例外なし


def test_real_sudachidict_resolves_known_word() -> None:
    """Phase 7 DoD: 既知語の読みが引ける固定テスト（実SudachiDict導入の統合確認）。"""
    tokenizer = create_tokenizer()
    entries = fetch_sudachi_readings(
        tokenizer, "西郷隆盛は東京タワーで銅像を見た", fetched_at="2026-07-17"
    )
    by_surface = {e.surface: e for e in entries}
    assert by_surface["西郷隆盛"].reading == "サイゴウタカモリ"
    assert by_surface["西郷隆盛"].kind == "person"
    assert by_surface["東京タワー"].kind in ("place", "common")


def test_apache_license_is_recorded_in_third_party_notices() -> None:
    """Phase 7 DoD: Apache-2.0のライセンス文がTHIRD_PARTY_NOTICES.mdに含まれる。"""
    notices = (REPO_ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    assert "SudachiDict" in notices
    assert "Apache License 2.0" in notices or "Apache-2.0" in notices
