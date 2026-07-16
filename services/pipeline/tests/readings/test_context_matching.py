"""test_context_matching.py — §8.4 DoD: context不一致・曖昧のfail-closedを固定する"""

from history_radio.readings.context_matching import select_manual_reading
from history_radio.readings.entry import ReadingEntry


def _entry(**overrides: object) -> ReadingEntry:
    base: dict[str, object] = {
        "surface": "判官",
        "reading": "ホウガン",
        "kind": "office",
        "context": "源平合戦",
        "confidence": 1.0,
        "source_id": "manual-dictionary",
        "source_url": "config/readings/manual.yaml",
        "license": "本プロジェクトの資産",
        "fetched_at": "2026-07-17",
    }
    base.update(overrides)
    return ReadingEntry.model_validate(base)


def test_matching_context_is_selected() -> None:
    entries = [
        _entry(context="源平合戦", reading="ホウガン"),
        _entry(context="現代", reading="ハンガン"),
    ]
    selected = select_manual_reading("判官", entries, frozenset({"源平合戦"}))
    assert selected is not None
    assert selected.reading == "ホウガン"


def test_non_matching_context_falls_to_none_not_default() -> None:
    """§8.4 DoD: context不一致時はどちらの読みも採用せずunresolvedへ倒す。"""
    entries = [
        _entry(context="源平合戦", reading="ホウガン"),
        _entry(context="現代", reading="ハンガン"),
    ]
    selected = select_manual_reading("判官", entries, frozenset({"江戸時代"}))
    assert selected is None


def test_multiple_matching_contexts_is_ambiguous() -> None:
    entries = [
        _entry(context="源平合戦", reading="ホウガン"),
        _entry(context="鎌倉時代", reading="ホウガン"),
    ]
    selected = select_manual_reading("判官", entries, frozenset({"源平合戦", "鎌倉時代"}))
    assert selected is None


def test_single_default_reading_is_used_when_no_context_entries() -> None:
    entries = [_entry(context=None, reading="ダイジョウダイジン", surface="太政大臣")]
    selected = select_manual_reading("太政大臣", entries, frozenset({"江戸時代"}))
    assert selected is not None
    assert selected.reading == "ダイジョウダイジン"


def test_surface_not_present_returns_none() -> None:
    entries = [_entry()]
    assert select_manual_reading("存在しない語", entries, frozenset()) is None


def test_explicit_default_entry_is_used_when_context_does_not_match() -> None:
    """既定読み(context=None)は「文脈不一致時のフォールバック」として明示的に機能する
    ——これは推測ではなく、人間がその表記に対して既定を明示登録した結果。"""
    entries = [
        _entry(context="源平合戦", reading="ホウガン"),
        _entry(context=None, reading="ナニカベツノヨミ"),
    ]
    selected = select_manual_reading("判官", entries, frozenset({"江戸時代"}))
    assert selected is not None
    assert selected.reading == "ナニカベツノヨミ"
