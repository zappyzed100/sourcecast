"""rights.py — 権利判定結果の永続化（`rights_records`）と監査ログ追記（仕様書§5A・§15）。

追記のみ（append-only）: この module は挿入・参照の関数しか持たない。更新・削除関数を
意図的に置かないことで、「同じ資料を新ルールで再判定しても旧判定が消えない」契約を
構造的に保証する（Phase 3タスクd）。
"""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from history_radio.domain.models import RightsDecision, RightsDecisionValue
from history_radio.store.orm import AuditEventRow, RightsDecisionRow


def _row_to_domain(row: RightsDecisionRow) -> RightsDecision:
    return RightsDecision(
        decision_id=row.decision_id,
        document_id=row.document_id,
        decision=row.decision,  # type: ignore[arg-type]
        rule_version=row.rule_version,
        reasons=json.loads(row.reasons_json),
        computed_at=row.computed_at,
    )


def save_rights_decision(session: Session, decision: RightsDecision) -> RightsDecision:
    """`RightsDecision` を1件追記し、対応する監査ログイベントも同時に記録する。

    仕様書§15「すべての公開・訂正・削除・権利判定変更を追記型監査ログへ記録する」に
    従い、rights_records への挿入と audit_events への挿入を同一トランザクションで行う。
    """
    session.add(
        RightsDecisionRow(
            decision_id=decision.decision_id,
            document_id=decision.document_id,
            decision=decision.decision,
            rule_version=decision.rule_version,
            reasons_json=json.dumps(decision.reasons, ensure_ascii=False),
            computed_at=decision.computed_at,
        )
    )
    session.add(
        AuditEventRow(
            event_id=f"audit-rights-{decision.decision_id}",
            entity_type="rights_decision",
            entity_id=decision.document_id,
            action="rights_decision_computed",
            actor="rights_engine",
            occurred_at=decision.computed_at,
            detail=f"decision={decision.decision} rule_version={decision.rule_version}",
        )
    )
    session.commit()
    return decision


def list_rights_decisions_for_document(session: Session, document_id: str) -> list[RightsDecision]:
    """ある資料の判定履歴を、判定時刻の古い順にすべて返す（新ルールでの再判定を含む）。"""
    rows = (
        session.execute(
            select(RightsDecisionRow)
            .where(RightsDecisionRow.document_id == document_id)
            .order_by(RightsDecisionRow.computed_at)
        )
        .scalars()
        .all()
    )
    return [_row_to_domain(row) for row in rows]


def latest_rights_decision_for_document(
    session: Session, document_id: str
) -> RightsDecision | None:
    """ある資料の最新判定を返す。判定が一度も無ければ `None`。"""
    decisions = list_rights_decisions_for_document(session, document_id)
    return decisions[-1] if decisions else None


__all__ = [
    "RightsDecisionValue",
    "latest_rights_decision_for_document",
    "list_rights_decisions_for_document",
    "save_rights_decision",
]
