"""test_media_gate.py — §8.4 DoD: unresolved語1件でもジョブがblockedへ遷移することを固定する"""

from history_radio.readings.media_gate import decide_media_job_status, unresolved_surfaces
from history_radio.readings.resolver import ResolvedReading, UnresolvedReading


def _resolved(surface: str) -> ResolvedReading:
    return ResolvedReading(
        surface=surface, reading="ヨミ", layer="manual", source_id="manual-dictionary"
    )


def _unresolved(surface: str) -> UnresolvedReading:
    return UnresolvedReading(surface=surface, reason="どの層でも解決できない")


def test_all_resolved_yields_queued() -> None:
    assert decide_media_job_status([_resolved("西郷隆盛"), _resolved("東京")]) == "queued"


def test_single_unresolved_yields_blocked() -> None:
    """Phase 7 DoD: unresolved語1件でもジョブがblockedへ遷移する。"""
    assert decide_media_job_status([_resolved("西郷隆盛"), _unresolved("謎の語")]) == "blocked"


def test_empty_resolutions_yields_queued() -> None:
    assert decide_media_job_status([]) == "queued"


def test_unresolved_surfaces_lists_only_unresolved() -> None:
    resolutions = [_resolved("西郷隆盛"), _unresolved("謎の語1"), _unresolved("謎の語2")]
    assert unresolved_surfaces(resolutions) == ["謎の語1", "謎の語2"]
