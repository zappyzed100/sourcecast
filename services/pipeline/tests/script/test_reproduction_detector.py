"""test_reproduction_detector.py — Phase 10タスク2 DoD: 出典原文の25文字コピーを拒否する"""

from history_radio.script.reproduction_detector import detect_reproduction
from history_radio.script.schema import Script, ScriptSection, ScriptSentence

_LONG_JA_25 = "東京タワーの外観は白と橙色で塗り分けられており航空法上の規定に従っている"
_SHORT_JA_24 = _LONG_JA_25[:24]
assert len(_LONG_JA_25) >= 25
assert len(_SHORT_JA_24) == 24


def _script(*sentences: ScriptSentence) -> Script:
    return Script(
        episode_id="ep-1", sections=[ScriptSection(kind="hook", sentences=list(sentences))]
    )


def test_no_match_when_source_texts_are_unrelated() -> None:
    script = _script(ScriptSentence(text="今日は缶詰の話をします。", kind="presentation"))
    spans = detect_reproduction(script, {0: "全く関係のない別の話題についての出典本文です。"})
    assert spans == []


def test_25_char_or_more_japanese_verbatim_copy_is_detected() -> None:
    """Phase 10タスク2 DoD: 出典原文の25文字コピーを拒否する。"""
    script = _script(ScriptSentence(text=_LONG_JA_25, kind="claim", claim_id="c1"))
    spans = detect_reproduction(script, {0: f"出典冒頭。{_LONG_JA_25}。出典末尾。"})
    assert len(spans) == 1
    assert spans[0].match_kind == "japanese_chars"
    assert spans[0].match_length >= 25
    assert spans[0].source_index == 0


def test_under_25_char_japanese_match_is_not_flagged() -> None:
    script = _script(ScriptSentence(text=_SHORT_JA_24, kind="claim", claim_id="c1"))
    spans = detect_reproduction(script, {0: f"出典冒頭。{_SHORT_JA_24}。出典末尾。"})
    assert spans == []


def test_8_word_or_more_western_verbatim_copy_is_detected() -> None:
    long_en = "the quick brown fox jumps over the lazy dog today"  # 10 words
    script = _script(ScriptSentence(text=long_en, kind="claim", claim_id="c1"))
    spans = detect_reproduction(script, {0: f"Source text begins. {long_en} Source text ends."})
    assert len(spans) == 1
    assert spans[0].match_kind == "western_words"
    assert spans[0].match_length >= 8


def test_under_8_word_western_match_is_not_flagged() -> None:
    short_en = "the quick brown fox jumps over"  # 6 words
    script = _script(ScriptSentence(text=short_en, kind="claim", claim_id="c1"))
    spans = detect_reproduction(script, {0: f"Source text begins. {short_en} Source text ends."})
    assert spans == []


def test_quoted_sentence_is_excluded_from_reproduction_check() -> None:
    """仕様書§11: 引用として明示・出所表示した箇所は転載検知の対象外。"""
    script = _script(ScriptSentence(text=_LONG_JA_25, kind="claim", claim_id="c1", is_quoted=True))
    spans = detect_reproduction(script, {0: f"出典冒頭。{_LONG_JA_25}。出典末尾。"})
    assert spans == []


def test_matches_across_multiple_sources_are_all_reported() -> None:
    script = _script(ScriptSentence(text=_LONG_JA_25, kind="claim", claim_id="c1"))
    spans = detect_reproduction(
        script,
        {
            0: f"出典A。{_LONG_JA_25}。",
            1: f"出典B。{_LONG_JA_25}。",
        },
    )
    assert {s.source_index for s in spans} == {0, 1}


def test_custom_thresholds_are_respected() -> None:
    script = _script(ScriptSentence(text=_SHORT_JA_24, kind="claim", claim_id="c1"))
    spans = detect_reproduction(
        script,
        {0: f"出典冒頭。{_SHORT_JA_24}。出典末尾。"},
        min_japanese_chars=10,
    )
    assert len(spans) == 1
