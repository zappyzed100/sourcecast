"""test_episodes.py — Phase 1 DoD: WAL下の同時読取+書込、および楽観ロック競合の拒否を固定する"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine

from history_radio.store.db import create_sqlite_engine, session_factory
from history_radio.store.episodes import (
    EpisodeConflictError,
    create_episode,
    get_episode,
    update_episode_state,
)
from history_radio.store.orm import Base


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Engine]:
    eng = create_sqlite_engine(tmp_path / "test.db")
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


def test_writer_commits_while_two_readers_hold_open_transactions(engine: Engine) -> None:
    """WAL: 読み取り中でも書き込みがブロックされない（§12.2の前提）。"""
    session_maker = session_factory(engine)

    with session_maker() as setup_session:
        create_episode(setup_session, episode_id="ep-wal", title="WAL確認用")

    reader1 = session_maker()
    reader2 = session_maker()
    try:
        # 2つの読取トランザクションを開いたままにする(コミットしない)
        assert get_episode(reader1, "ep-wal").title == "WAL確認用"
        assert get_episode(reader2, "ep-wal").title == "WAL確認用"

        # 読取が開いたままでも writer は更新・コミットできる
        with session_maker() as writer_session:
            updated = update_episode_state(
                writer_session,
                episode_id="ep-wal",
                expected_revision=1,
                new_state="rights_passed",
            )
            assert updated.state == "rights_passed"
            assert updated.revision == 2
    finally:
        reader1.close()
        reader2.close()


def test_concurrent_update_with_stale_revision_is_rejected(engine: Engine) -> None:
    """楽観ロック: 2つのセッションが同じrevisionを読んだ後、後勝ちの更新が拒否される。"""
    session_maker = session_factory(engine)

    with session_maker() as setup_session:
        create_episode(setup_session, episode_id="ep-conflict", title="競合確認用")

    with session_maker() as session_a, session_maker() as session_b:
        episode_seen_by_a = get_episode(session_a, "ep-conflict")
        episode_seen_by_b = get_episode(session_b, "ep-conflict")
        assert episode_seen_by_a.revision == episode_seen_by_b.revision == 1

        # 先に更新した側は成功する
        first_update = update_episode_state(
            session_a,
            episode_id="ep-conflict",
            expected_revision=episode_seen_by_a.revision,
            new_state="rights_passed",
        )
        assert first_update.revision == 2

        # 後から古いrevisionのまま更新しようとした側は競合として拒否される
        with pytest.raises(EpisodeConflictError):
            update_episode_state(
                session_b,
                episode_id="ep-conflict",
                expected_revision=episode_seen_by_b.revision,
                new_state="rejected",
            )

    with session_maker() as verify_session:
        final = get_episode(verify_session, "ep-conflict")
        assert final.revision == 2
        assert final.state == "rights_passed"
