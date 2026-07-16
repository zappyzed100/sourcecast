"""test_resolver.py — §8.4 DoD: 各層単独の解決と上位層優先・曖昧時fail-closedを固定する"""

from history_radio.readings.entry import ReadingEntry
from history_radio.readings.resolver import ResolvedReading, UnresolvedReading, resolve_reading


def _entry(source_id: str, **overrides: object) -> ReadingEntry:
    base: dict[str, object] = {
        "surface": "西郷隆盛",
        "reading": "サイゴウタカモリ",
        "kind": "person",
        "context": None,
        "confidence": 0.8,
        "source_id": source_id,
        "source_url": "https://example.org",
        "license": "CC0 1.0",
        "fetched_at": "2026-07-17",
    }
    base.update(overrides)
    return ReadingEntry.model_validate(base)


def _resolve(surface: str, **layers: list[ReadingEntry]) -> ResolvedReading | UnresolvedReading:
    defaults: dict[str, list[ReadingEntry]] = {
        "manual_entries": [],
        "era_entries": [],
        "wikidata_or_ndl_entries": [],
        "address_entries": [],
        "jmnedict_entries": [],
        "sudachi_entries": [],
    }
    defaults.update(layers)
    return resolve_reading(surface, episode_tags=frozenset(), **defaults)  # type: ignore[arg-type]


def test_manual_layer_resolves_alone() -> None:
    result = _resolve("西郷隆盛", manual_entries=[_entry("manual-dictionary")])
    assert isinstance(result, ResolvedReading)
    assert result.layer == "manual"


def test_era_layer_resolves_alone() -> None:
    result = _resolve(
        "明治", era_entries=[_entry("era-dictionary", surface="明治", reading="メイジ")]
    )
    assert isinstance(result, ResolvedReading)
    assert result.layer == "era"


def test_wikidata_or_ndl_layer_resolves_alone() -> None:
    result = _resolve("西郷隆盛", wikidata_or_ndl_entries=[_entry("wikidata-kana")])
    assert isinstance(result, ResolvedReading)
    assert result.layer == "wikidata_or_ndl"


def test_address_layer_resolves_alone() -> None:
    result = _resolve(
        "難波",
        address_entries=[_entry("digital-agency-abr", surface="難波", reading="ナンバ")],
    )
    assert isinstance(result, ResolvedReading)
    assert result.layer == "address"


def test_jmnedict_layer_resolves_alone() -> None:
    result = _resolve("西郷隆盛", jmnedict_entries=[_entry("jmnedict")])
    assert isinstance(result, ResolvedReading)
    assert result.layer == "jmnedict"


def test_sudachi_layer_resolves_alone() -> None:
    result = _resolve("西郷隆盛", sudachi_entries=[_entry("sudachidict")])
    assert isinstance(result, ResolvedReading)
    assert result.layer == "sudachi"


def test_manual_layer_overrides_all_lower_layers() -> None:
    """上位層（手動辞書）が下位層の結果を上書きする優先順位テスト。"""
    result = _resolve(
        "西郷隆盛",
        manual_entries=[_entry("manual-dictionary", reading="サイゴウ")],
        era_entries=[],
        wikidata_or_ndl_entries=[_entry("wikidata-kana", reading="ベツヨミイチ")],
        jmnedict_entries=[_entry("jmnedict", reading="ベツヨミニ")],
        sudachi_entries=[_entry("sudachidict", reading="ベツヨミサン")],
    )
    assert isinstance(result, ResolvedReading)
    assert result.layer == "manual"
    assert result.reading == "サイゴウ"


def test_higher_layer_wins_over_lower_when_both_present() -> None:
    result = _resolve(
        "西郷隆盛",
        wikidata_or_ndl_entries=[_entry("wikidata-kana", reading="ウィキデータヨミ")],
        sudachi_entries=[_entry("sudachidict", reading="スダチヨミ")],
    )
    assert isinstance(result, ResolvedReading)
    assert result.layer == "wikidata_or_ndl"
    assert result.reading == "ウィキデータヨミ"


def test_no_layer_has_candidate_is_unresolved() -> None:
    result = _resolve("誰も知らない語")
    assert isinstance(result, UnresolvedReading)
    assert result.reason == "どの層でも解決できない"


def test_ambiguous_layer_stops_there_and_does_not_fall_through() -> None:
    """層内で読みが割れた場合、下位層で妥協せずunresolvedにする（上位層飛ばし禁止）。"""
    result = _resolve(
        "西郷隆盛",
        jmnedict_entries=[
            _entry("jmnedict", reading="ヨミエー"),
            _entry("jmnedict", reading="ヨミビー"),
        ],
        sudachi_entries=[_entry("sudachidict", reading="スダチヨミ")],
    )
    assert isinstance(result, UnresolvedReading)
    assert "jmnedict" in result.reason


def test_manual_ambiguous_stops_there_and_does_not_fall_through() -> None:
    """手動辞書に候補があるのに文脈で決められない場合、下位層へは進まずunresolved。"""
    result = _resolve(
        "判官",
        manual_entries=[
            _entry("manual-dictionary", surface="判官", reading="ホウガン", context="源平合戦"),
            _entry("manual-dictionary", surface="判官", reading="ハンガン", context="現代"),
        ],
        sudachi_entries=[_entry("sudachidict", surface="判官", reading="ハンカン")],
    )
    assert isinstance(result, UnresolvedReading)
    assert "手動修正辞書" in result.reason
