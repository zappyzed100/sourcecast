"""candidate_review.py — 候補の審査判定（仕様書§12.3・§12.4・Phase 11タスク1・3）。

採用／除外の判定を行う純粋関数。**除外には理由の入力を必須にする**——仕様書§12.4
「破壊的操作は確認、理由入力、監査ログを必須にする」の方針を審査アクションにも適用する
（Phase 11タスク3のDoD「理由なしの却下…をAPIが拒否する」の「却下」に相当）。採用は
新しいものを作る操作であり破壊的ではないため理由を必須にしない。
"""

from __future__ import annotations

from datetime import datetime

from history_radio.domain.models import CandidateDecision, CandidateDecisionValue


class CandidateReviewError(ValueError):
    """審査操作の拒否（除外に理由が無い等）。"""


def review_candidate(
    *,
    decision_id: str,
    candidate_id: str,
    decision: CandidateDecisionValue,
    reason: str | None,
    decided_at: datetime,
) -> CandidateDecision:
    """候補1件の審査結果を確定する。除外時に理由が空ならfail closedで拒否する。"""
    if decision == "excluded" and not (reason and reason.strip()):
        raise CandidateReviewError(
            f"candidate_id={candidate_id!r}: 除外には理由の入力が必須"
            "（仕様書§12.4・development-plan.md Phase 11タスク3）"
        )
    return CandidateDecision(
        decision_id=decision_id,
        candidate_id=candidate_id,
        decision=decision,
        reason=(reason or "").strip(),
        decided_at=decided_at,
    )
