"""episode_deletion.py — エピソードの削除永続化（仕様書§15・Phase 11タスク3「削除」）。

`episodes`行を実際に削除する（append-onlyではない——公開前のエピソードは
「作り直せば済む」ため、他の判定系テーブルのように履歴を残す価値が薄い）。
削除対象のjob/gate_results等の関連行はそのまま残す（実行履歴・監査証跡として
独立に意味を持つため、カスケード削除しない）。監査ログ（`AuditEventRow`）への
記録は行の削除と同一トランザクションで行う——削除後もaudit_events側に
「いつ・誰が・なぜ削除したか」の記録だけは残る（仕様書§15）。
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import delete
from sqlalchemy.orm import Session

from history_radio.store.episodes import EpisodeNotFoundError, get_episode
from history_radio.store.orm import AuditEventRow, EpisodeRow


def delete_episode(
    session: Session, *, episode_id: str, reason: str, actor: str = "admin_review"
) -> None:
    """`episode_id`の行を削除し、同一トランザクションで監査ログへ記録する。

    存在確認は呼び出し側（publish/episode_deletion.py）が状態検査のために
    先に`get_episode`を呼んでいる想定だが、ここでも独立に存在確認する
    （store層だけを直接使う将来の呼び出し元に対しても安全なようにする）。
    """
    get_episode(session, episode_id)  # 無ければ EpisodeNotFoundError

    session.add(
        AuditEventRow(
            event_id=f"audit-episode-delete-{episode_id}-{uuid4().hex[:8]}",
            entity_type="episode",
            entity_id=episode_id,
            action="deleted",
            actor=actor,
            occurred_at=datetime.now(timezone.utc),
            detail=f"reason={reason!r}",
        )
    )
    session.execute(delete(EpisodeRow).where(EpisodeRow.episode_id == episode_id))
    session.commit()


__all__ = ["EpisodeNotFoundError", "delete_episode"]
