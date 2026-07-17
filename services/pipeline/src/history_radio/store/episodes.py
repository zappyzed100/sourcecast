"""episodes.py — Episodeの永続化と楽観ロック（revision列 — plan.md §2.3）。

更新は必ず「期待するrevision」を伴わせ、`UPDATE ... WHERE revision = :expected` の
影響行数が0なら競合とみなして EpisodeConflictError を送出する。SELECTしてから
比較するのではなく、UPDATE自体の条件に含めることで
read-then-write のあいだの競合ウィンドウを作らない。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import cast

from sqlalchemy import CursorResult, select, update
from sqlalchemy.orm import Session

from history_radio.domain.episode_state import EpisodeState
from history_radio.domain.models import Episode
from history_radio.store.orm import EpisodeRow


class EpisodeConflictError(RuntimeError):
    """楽観ロック競合: 渡した revision がDB上の現在値と一致しなかった。"""

    def __init__(self, episode_id: str, expected_revision: int) -> None:
        super().__init__(
            f"Episode {episode_id!r} の更新が競合した"
            f"（expected_revision={expected_revision} が現在のrevisionと不一致）"
        )
        self.episode_id = episode_id
        self.expected_revision = expected_revision


class EpisodeNotFoundError(RuntimeError):
    def __init__(self, episode_id: str) -> None:
        super().__init__(f"Episode {episode_id!r} が存在しない")
        self.episode_id = episode_id


def _row_to_domain(row: EpisodeRow) -> Episode:
    return Episode(
        episode_id=row.episode_id,
        state=row.state,  # type: ignore[arg-type]
        revision=row.revision,
        title=row.title,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def create_episode(session: Session, *, episode_id: str, title: str) -> Episode:
    now = datetime.now(timezone.utc)
    row = EpisodeRow(
        episode_id=episode_id,
        state="collected",
        revision=1,
        title=title,
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    session.commit()
    return _row_to_domain(row)


def get_episode(session: Session, episode_id: str) -> Episode:
    row = session.get(EpisodeRow, episode_id)
    if row is None:
        raise EpisodeNotFoundError(episode_id)
    return _row_to_domain(row)


def list_episodes(session: Session) -> list[Episode]:
    """全エピソードを作成順（古い順）に返す（Phase 11タスク1: 管理画面の一覧表示用）。"""
    rows = session.execute(select(EpisodeRow).order_by(EpisodeRow.created_at)).scalars().all()
    return [_row_to_domain(row) for row in rows]


def update_episode_state(
    session: Session,
    *,
    episode_id: str,
    expected_revision: int,
    new_state: EpisodeState,
) -> Episode:
    """revision一致を条件にstateを更新し、revisionを1進める。0行更新なら競合。"""
    stmt = (
        update(EpisodeRow)
        .where(EpisodeRow.episode_id == episode_id, EpisodeRow.revision == expected_revision)
        .values(
            state=new_state, revision=expected_revision + 1, updated_at=datetime.now(timezone.utc)
        )
    )
    result = cast(CursorResult[object], session.execute(stmt))
    if result.rowcount == 0:
        session.rollback()
        if session.get(EpisodeRow, episode_id) is None:
            raise EpisodeNotFoundError(episode_id)
        raise EpisodeConflictError(episode_id, expected_revision)
    session.commit()
    return get_episode(session, episode_id)
