"""test_episode_publishing.py — Phase 11タスク1 DoD: 限定公開はapproved状態を要求し
同じ配信先への二重投稿を防ぐ
"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from history_radio.publish.episode_publishing import EpisodePublishError, publish_episode_limited
from history_radio.store.db import create_sqlite_engine, session_factory
from history_radio.store.distribution_records import get_distribution_record
from history_radio.store.episodes import create_episode, get_episode, update_episode_state
from history_radio.store.orm import Base


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Engine]:
    eng = create_sqlite_engine(tmp_path / "test.db")
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


def _approve(session_maker: sessionmaker[Session], episode_id: str) -> None:
    with session_maker() as session:
        create_episode(session, episode_id=episode_id, title="テストエピソード")
        update_episode_state(
            session, episode_id=episode_id, expected_revision=1, new_state="publish_ready"
        )
        update_episode_state(
            session, episode_id=episode_id, expected_revision=2, new_state="approved"
        )


def test_publish_succeeds_when_approved(engine: Engine) -> None:
    session_maker = session_factory(engine)
    _approve(session_maker, "ep-1")

    with session_maker() as session:
        published = publish_episode_limited(session, episode_id="ep-1")

    assert published.state == "published"

    with session_maker() as session:
        assert get_episode(session, "ep-1").state == "published"
        record = get_distribution_record(session, "ep-1", "youtube")
        assert record is not None
        assert record.status == "success"
        assert record.external_id == "placeholder-youtube-ep-1"


def test_publish_rejects_episode_not_approved(engine: Engine) -> None:
    session_maker = session_factory(engine)
    with session_maker() as session:
        create_episode(session, episode_id="ep-2", title="まだ承認前")

    with session_maker() as session:
        with pytest.raises(EpisodePublishError, match="限定公開できない"):
            publish_episode_limited(session, episode_id="ep-2")

    with session_maker() as session:
        assert get_episode(session, "ep-2").state == "collected"


def test_publish_again_after_already_published_is_rejected_by_the_state_machine(
    engine: Engine,
) -> None:
    """一度限定公開したエピソードへの再実行は、状態機械の終端状態チェックで拒否される
    （`published`はTERMINAL_STATES——段階飛ばし・逆行防止と同じ仕組み）。
    配信台帳自体の二重投稿防止（`publish_fn`が2回目は呼ばれないこと）は
    `tests/store/test_distribution_records.py`の
    `test_db_backed_ledger_survives_a_fresh_instance`で直接検証している。
    """
    session_maker = session_factory(engine)
    _approve(session_maker, "ep-3")

    with session_maker() as session:
        first = publish_episode_limited(session, episode_id="ep-3")
    assert first.state == "published"

    with session_maker() as session:
        with pytest.raises(EpisodePublishError, match="限定公開できない"):
            publish_episode_limited(session, episode_id="ep-3")

    with session_maker() as session:
        record = get_distribution_record(session, "ep-3", "youtube")
        assert record is not None
        assert record.external_id == "placeholder-youtube-ep-3"
