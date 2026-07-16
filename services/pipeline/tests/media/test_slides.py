"""test_slides.py — Phase 7 DoD: 画像0件でも安全にスライドデッキが生成できることを固定する"""

from history_radio.media.media_manifest import MediaAsset
from history_radio.media.slides import (
    MAX_CHARS_PER_LINE,
    MAX_SLIDE_SECONDS,
    MIN_SLIDE_SECONDS,
    build_slide_deck,
)
from history_radio.script.schema import SECTION_KINDS, Script, ScriptSection, ScriptSentence


def _script(*, development_text: str = "出来事の展開なのだ。") -> Script:
    sections: list[ScriptSection] = []
    for kind in SECTION_KINDS:
        text = development_text if kind == "development" else f"{kind}のだ。"
        sentences = [ScriptSentence(text=text, kind="presentation")]
        if kind == "sources":
            sentences = [
                ScriptSentence(text="claim-001の話なのだ。", kind="claim", claim_id="claim-001")
            ]
        sections.append(ScriptSection(kind=kind, sentences=sentences))
    return Script(episode_id="ep-1", sections=sections)


def _asset(**overrides: object) -> MediaAsset:
    base: dict[str, object] = {
        "asset_id": "img-001",
        "origin": "licensed",
        "credit_text": "写真: NDL",
        "source_url": "https://dl.ndl.go.jp/pid/1",
        "normalized_license_id": "ndl-internet-pd",
        "used_in": ["development"],
    }
    base.update(overrides)
    return MediaAsset.model_validate(base)


def test_deck_has_one_slide_per_section() -> None:
    deck = build_slide_deck(_script(), [])
    assert [s.section_kind for s in deck] == list(SECTION_KINDS)


def test_no_assets_yields_self_drawn_fallback_for_every_slide() -> None:
    """Phase 7 DoD: 画像0件でも権利上安全な動画を生成できる——全スライドが自作図形へ倒れる。"""
    deck = build_slide_deck(_script(), [])
    assert all(s.uses_self_drawn_fallback for s in deck)
    assert all(s.asset_ids == () for s in deck)


def test_section_with_matching_asset_does_not_use_fallback() -> None:
    deck = build_slide_deck(_script(), [_asset()])
    by_kind = {s.section_kind: s for s in deck}
    assert by_kind["development"].uses_self_drawn_fallback is False
    assert by_kind["development"].asset_ids == ("img-001",)
    assert by_kind["hook"].uses_self_drawn_fallback is True


def test_duration_is_clamped_within_spec_range() -> None:
    deck = build_slide_deck(_script(development_text="短い" * 1), [])
    for slide in deck:
        assert MIN_SLIDE_SECONDS <= slide.duration_seconds <= MAX_SLIDE_SECONDS


def test_long_text_clamps_to_max_duration() -> None:
    deck = build_slide_deck(_script(development_text="長い出来事の説明なのだ。" * 20), [])
    development = next(s for s in deck if s.section_kind == "development")
    assert development.duration_seconds == MAX_SLIDE_SECONDS


def test_short_text_clamps_to_min_duration() -> None:
    deck = build_slide_deck(_script(development_text="短い"), [])
    development = next(s for s in deck if s.section_kind == "development")
    assert development.duration_seconds == MIN_SLIDE_SECONDS


def test_body_lines_do_not_exceed_max_chars() -> None:
    deck = build_slide_deck(_script(development_text="あ" * 200), [])
    development = next(s for s in deck if s.section_kind == "development")
    assert all(len(line) <= MAX_CHARS_PER_LINE for line in development.body_lines)
    assert "".join(development.body_lines) == "あ" * 200


def test_source_numbers_are_derived_from_claim_ids() -> None:
    deck = build_slide_deck(_script(), [], claim_source_numbers={"claim-001": 3})
    sources_slide = next(s for s in deck if s.section_kind == "sources")
    assert sources_slide.source_numbers == (3,)


def test_section_without_claims_has_no_source_numbers() -> None:
    deck = build_slide_deck(_script(), [], claim_source_numbers={"claim-001": 3})
    hook_slide = next(s for s in deck if s.section_kind == "hook")
    assert hook_slide.source_numbers == ()


def test_slide_ids_are_unique_and_stable() -> None:
    deck = build_slide_deck(_script(), [])
    ids = [s.slide_id for s in deck]
    assert len(ids) == len(set(ids))
    assert all(sid.startswith("ep-1-") for sid in ids)
