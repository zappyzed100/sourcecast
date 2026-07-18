"""episode_revocations.py — エピソードの公開取消の永続化（仕様書§10B「法的削除要請や
重大な権利問題では本文・メディアを非公開化できるが、可能な範囲でURLに理由と履歴を残す」・
Phase 11タスク3「公開取消」）。

`episodes`行・配信記録（`distribution_records`）はどちらも書き換えない——公開取消は
「取り下げた」という事実と理由を`audit_events`へ追記するだけ（append-only）。
episode_stateを書き換えないのは、仕様書§10Bが「公開済みページのURL変更を原則禁止」
としているため——エピソードの状態機械上は`published`のまま、取消の事実だけを
監査ログで別途表現する（episode_deletion.pyが行そのものを消すのとは対照的な設計）。
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from history_radio.domain.models import AuditEvent
from history_radio.store.orm import AuditEventRow

REVOCATION_ACTION = "publish_revoked"


def _row_to_domain(row: AuditEventRow) -> AuditEvent:
    return AuditEvent(
        event_id=row.event_id,
        entity_type=row.entity_type,
        entity_id=row.entity_id,
        action=row.action,
        actor=row.actor,
        occurred_at=row.occurred_at,
        detail=row.detail,
    )


def is_publish_revoked(session: Session, episode_id: str) -> bool:
    return (
        session.execute(
            select(AuditEventRow).where(
                AuditEventRow.entity_type == "episode",
                AuditEventRow.entity_id == episode_id,
                AuditEventRow.action == REVOCATION_ACTION,
            )
        ).first()
        is not None
    )


def revoke_episode_publication(
    session: Session, *, episode_id: str, reason: str, actor: str = "admin_review"
) -> AuditEvent:
    row = AuditEventRow(
        event_id=f"audit-episode-revoke-{episode_id}-{uuid4().hex[:8]}",
        entity_type="episode",
        entity_id=episode_id,
        action=REVOCATION_ACTION,
        actor=actor,
        occurred_at=datetime.now(timezone.utc),
        detail=f"reason={reason!r}",
    )
    session.add(row)
    session.commit()
    return _row_to_domain(row)


__all__ = ["REVOCATION_ACTION", "is_publish_revoked", "revoke_episode_publication"]
