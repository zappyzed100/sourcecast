"""test_episode_deletion.py — Phase 11タスク3 DoD: 理由なしの削除・公開済みの削除をAPIが拒否する"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine, select

from history_radio.publish.episode_deletion import EpisodeDeletionError, delete_episode_with_reason
from history_radio.store.db import create_sqlite_engine, session_factory
from history_radio.store.episodes import (
    EpisodeNotFoundError,
    create_episode,
    get_episode,
    update_episode_state,
)
from history_radio.store.orm import AuditEventRow, Base


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Engine]:
    eng = create_sqlite_engine(tmp_path / "test.db")
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


def test_delete_without_reason_is_rejected(engine: Engine) -> None:
    session_maker = session_factory(engine)
    with session_maker() as session:
        create_episode(session, episode_id="ep-1", title="削除対象")

    with session_maker() as session:
        with pytest.raises(EpisodeDeletionError, match="理由の入力が必須"):
            delete_episode_with_reason(session, episode_id="ep-1", reason=None)
        with pytest.raises(EpisodeDeletionError, match="理由の入力が必須"):
            delete_episode_with_reason(session, episode_id="ep-1", reason="   ")

    with session_maker() as session:
        assert get_episode(session, "ep-1").episode_id == "ep-1"


def test_delete_published_episode_is_rejected(engine: Engine) -> None:
    session_maker = session_factory(engine)
    with session_maker() as session:
        create_episode(session, episode_id="ep-1", title="公開済み")
        for state in (
            "rights_passed",
            "topic_selected",
            "facts_verified",
            "script_generated",
            "script_verified",
            "media_generated",
            "publish_ready",
            "approved",
            "published",
        ):
            episode = get_episode(session, "ep-1")
            update_episode_state(
                session, episode_id="ep-1", expected_revision=episode.revision, new_state=state
            )

    with session_maker() as session:
        with pytest.raises(EpisodeDeletionError, match="公開済み"):
            delete_episode_with_reason(session, episode_id="ep-1", reason="事情変更")

    with session_maker() as session:
        assert get_episode(session, "ep-1").state == "published"


def test_delete_unknown_episode_raises_not_found(engine: Engine) -> None:
    session_maker = session_factory(engine)
    with session_maker() as session:
        with pytest.raises(EpisodeNotFoundError):
            delete_episode_with_reason(session, episode_id="does-not-exist", reason="理由あり")


def test_delete_removes_the_row_and_records_an_audit_event(engine: Engine) -> None:
    session_maker = session_factory(engine)
    with session_maker() as session:
        create_episode(session, episode_id="ep-1", title="削除対象")

    with session_maker() as session:
        delete_episode_with_reason(session, episode_id="ep-1", reason="重複作成のため")

    with session_maker() as session:
        with pytest.raises(EpisodeNotFoundError):
            get_episode(session, "ep-1")

        events = (
            session.execute(
                select(AuditEventRow).where(
                    AuditEventRow.entity_type == "episode",
                    AuditEventRow.entity_id == "ep-1",
                    AuditEventRow.action == "deleted",
                )
            )
            .scalars()
            .all()
        )
        assert len(events) == 1
        assert "重複作成のため" in events[0].detail
