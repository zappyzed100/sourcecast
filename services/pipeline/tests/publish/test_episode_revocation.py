"""test_episode_revocation.py — Phase 11タスク3 DoD: 理由なしの公開取消・未公開の取消を拒否する"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

from history_radio.publish.episode_revocation import (
    EpisodeRevocationError,
    revoke_publication_with_reason,
)
from history_radio.store.db import create_sqlite_engine, session_factory
from history_radio.store.episodes import (
    EpisodeNotFoundError,
    create_episode,
    get_episode,
    update_episode_state,
)
from history_radio.store.orm import AuditEventRow, Base

_FORWARD_STATES = (
    "rights_passed",
    "topic_selected",
    "facts_verified",
    "script_generated",
    "script_verified",
    "media_generated",
    "publish_ready",
    "approved",
    "published",
)


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Engine]:
    eng = create_sqlite_engine(tmp_path / "test.db")
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


def _create_published_episode(
    session_maker: sessionmaker[Session], episode_id: str = "ep-1"
) -> None:
    with session_maker() as session:
        create_episode(session, episode_id=episode_id, title="公開済み")
        for state in _FORWARD_STATES:
            episode = get_episode(session, episode_id)
            update_episode_state(
                session, episode_id=episode_id, expected_revision=episode.revision, new_state=state
            )


def test_revoke_without_reason_is_rejected(engine: Engine) -> None:
    session_maker = session_factory(engine)
    _create_published_episode(session_maker)

    with session_maker() as session:
        with pytest.raises(EpisodeRevocationError, match="理由の入力が必須"):
            revoke_publication_with_reason(session, episode_id="ep-1", reason=None)
        with pytest.raises(EpisodeRevocationError, match="理由の入力が必須"):
            revoke_publication_with_reason(session, episode_id="ep-1", reason="  ")


def test_revoke_unpublished_episode_is_rejected(engine: Engine) -> None:
    session_maker = session_factory(engine)
    with session_maker() as session:
        create_episode(session, episode_id="ep-1", title="未公開")

    with session_maker() as session:
        with pytest.raises(EpisodeRevocationError, match="公開済みでない"):
            revoke_publication_with_reason(session, episode_id="ep-1", reason="理由あり")


def test_revoke_unknown_episode_raises_not_found(engine: Engine) -> None:
    session_maker = session_factory(engine)
    with session_maker() as session:
        with pytest.raises(EpisodeNotFoundError):
            revoke_publication_with_reason(session, episode_id="does-not-exist", reason="理由あり")


def test_revoke_succeeds_and_does_not_change_episode_state(engine: Engine) -> None:
    session_maker = session_factory(engine)
    _create_published_episode(session_maker)

    with session_maker() as session:
        event = revoke_publication_with_reason(
            session, episode_id="ep-1", reason="権利者からの削除要請"
        )

    assert event.action == "publish_revoked"
    assert "権利者からの削除要請" in event.detail

    with session_maker() as session:
        # 仕様書§10B: 公開済みページのURL変更を原則禁止するため、状態は変えない。
        assert get_episode(session, "ep-1").state == "published"

        events = (
            session.execute(
                select(AuditEventRow).where(
                    AuditEventRow.entity_type == "episode",
                    AuditEventRow.entity_id == "ep-1",
                    AuditEventRow.action == "publish_revoked",
                )
            )
            .scalars()
            .all()
        )
        assert len(events) == 1


def test_revoke_twice_is_rejected(engine: Engine) -> None:
    session_maker = session_factory(engine)
    _create_published_episode(session_maker)

    with session_maker() as session:
        revoke_publication_with_reason(session, episode_id="ep-1", reason="1回目の理由")

    with session_maker() as session:
        with pytest.raises(EpisodeRevocationError, match="既に公開取消済み"):
            revoke_publication_with_reason(session, episode_id="ep-1", reason="2回目の理由")
