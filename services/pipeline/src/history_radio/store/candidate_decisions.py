"""candidate_decisions.py — 候補審査結果の永続化（仕様書§12.3・§12.4・Phase 11タスク1・3）。

追記のみ（append-only）: この module は挿入・参照の関数しか持たない。更新・削除関数を
意図的に置かないことで、「同じcandidate_idを再審査しても過去の判定が消えない」契約を
構造的に保証する（store/rights.pyと同じ方針）。
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from history_radio.domain.models import CandidateDecision
from history_radio.store.orm import AuditEventRow, CandidateDecisionRow


def _row_to_domain(row: CandidateDecisionRow) -> CandidateDecision:
    return CandidateDecision(
        decision_id=row.decision_id,
        candidate_id=row.candidate_id,
        decision=row.decision,  # type: ignore[arg-type]
        reason=row.reason,
        decided_at=row.decided_at,
    )


def save_candidate_decision(session: Session, decision: CandidateDecision) -> CandidateDecision:
    """`CandidateDecision` を1件追記し、対応する監査ログイベントも同時に記録する。

    仕様書§15「すべての公開・訂正・削除・権利判定変更を追記型監査ログへ記録する」に
    従い、candidate_decisions への挿入と audit_events への挿入を同一トランザクションで行う。
    """
    session.add(
        CandidateDecisionRow(
            decision_id=decision.decision_id,
            candidate_id=decision.candidate_id,
            decision=decision.decision,
            reason=decision.reason,
            decided_at=decision.decided_at,
        )
    )
    session.add(
        AuditEventRow(
            event_id=f"audit-candidate-{decision.decision_id}",
            entity_type="candidate_decision",
            entity_id=decision.candidate_id,
            action=f"candidate_{decision.decision}",
            actor="admin_review",
            occurred_at=decision.decided_at,
            detail=f"decision={decision.decision} reason={decision.reason!r}",
        )
    )
    session.commit()
    return decision


def list_decisions_for_candidate(session: Session, candidate_id: str) -> list[CandidateDecision]:
    """ある候補の審査履歴を、判定時刻の古い順にすべて返す（再審査を含む）。"""
    rows = (
        session.execute(
            select(CandidateDecisionRow)
            .where(CandidateDecisionRow.candidate_id == candidate_id)
            .order_by(CandidateDecisionRow.decided_at)
        )
        .scalars()
        .all()
    )
    return [_row_to_domain(row) for row in rows]


def latest_decision_for_candidate(session: Session, candidate_id: str) -> CandidateDecision | None:
    """ある候補の最新の審査結果を返す。審査が一度も無ければ`None`。"""
    decisions = list_decisions_for_candidate(session, candidate_id)
    return decisions[-1] if decisions else None


__all__ = [
    "latest_decision_for_candidate",
    "list_decisions_for_candidate",
    "save_candidate_decision",
]
