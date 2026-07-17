"""test_candidate_review.py — Phase 11タスク1・3 DoD: 理由なしの除外をAPIが拒否する"""

from datetime import datetime, timezone

import pytest

from history_radio.select.candidate_review import CandidateReviewError, review_candidate

_NOW = datetime(2026, 7, 19, tzinfo=timezone.utc)


def test_adopting_a_candidate_does_not_require_a_reason() -> None:
    decision = review_candidate(
        decision_id="dec-1", candidate_id="cand-1", decision="adopted", reason=None, decided_at=_NOW
    )
    assert decision.decision == "adopted"
    assert decision.reason == ""


def test_excluding_without_reason_is_rejected() -> None:
    """Phase 11タスク3 DoD: 理由なしの却下をAPIが拒否する。"""
    with pytest.raises(CandidateReviewError, match="理由の入力が必須"):
        review_candidate(
            decision_id="dec-1",
            candidate_id="cand-1",
            decision="excluded",
            reason=None,
            decided_at=_NOW,
        )


def test_excluding_with_blank_reason_is_rejected() -> None:
    with pytest.raises(CandidateReviewError, match="理由の入力が必須"):
        review_candidate(
            decision_id="dec-1",
            candidate_id="cand-1",
            decision="excluded",
            reason="   ",
            decided_at=_NOW,
        )


def test_excluding_with_reason_succeeds() -> None:
    decision = review_candidate(
        decision_id="dec-1",
        candidate_id="cand-1",
        decision="excluded",
        reason="出典が信頼できない",
        decided_at=_NOW,
    )
    assert decision.decision == "excluded"
    assert decision.reason == "出典が信頼できない"


def test_reason_is_stripped() -> None:
    decision = review_candidate(
        decision_id="dec-1",
        candidate_id="cand-1",
        decision="excluded",
        reason="  出典が信頼できない  ",
        decided_at=_NOW,
    )
    assert decision.reason == "出典が信頼できない"
