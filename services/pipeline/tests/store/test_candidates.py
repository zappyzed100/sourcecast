"""test_candidates.py — Phase 11タスク1 DoD: 候補一覧が実DBから取得できる"""

from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import Engine

from history_radio.domain.models import Candidate
from history_radio.store.candidates import get_candidate, list_candidates, save_candidate
from history_radio.store.db import create_sqlite_engine, session_factory
from history_radio.store.orm import Base


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Engine]:
    eng = create_sqlite_engine(tmp_path / "test.db")
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


def _candidate(candidate_id: str = "cand-1") -> Candidate:
    return Candidate(
        candidate_id=candidate_id,
        topic_title="缶切りより缶詰の方が50年も先に生まれていた",
        score=78.5,
        score_breakdown={"date_match": 0.2, "source_richness": 0.9},
        independent_source_families=2,
    )


def test_saved_candidate_can_be_retrieved(engine: Engine) -> None:
    session_maker = session_factory(engine)
    with session_maker() as session:
        save_candidate(session, _candidate(), created_at=datetime(2026, 7, 19, tzinfo=timezone.utc))

    with session_maker() as session:
        candidate = get_candidate(session, "cand-1")

    assert candidate is not None
    assert candidate.topic_title == "缶切りより缶詰の方が50年も先に生まれていた"
    assert candidate.score_breakdown == {"date_match": 0.2, "source_richness": 0.9}


def test_missing_candidate_returns_none(engine: Engine) -> None:
    session_maker = session_factory(engine)
    with session_maker() as session:
        assert get_candidate(session, "does-not-exist") is None


def test_list_candidates_returns_oldest_first(engine: Engine) -> None:
    session_maker = session_factory(engine)
    with session_maker() as session:
        save_candidate(
            session, _candidate("cand-new"), created_at=datetime(2026, 7, 19, tzinfo=timezone.utc)
        )
        save_candidate(
            session, _candidate("cand-old"), created_at=datetime(2026, 7, 1, tzinfo=timezone.utc)
        )

    with session_maker() as session:
        candidates = list_candidates(session)

    assert [c.candidate_id for c in candidates] == ["cand-old", "cand-new"]


def test_list_candidates_returns_empty_list_when_nothing_saved(engine: Engine) -> None:
    session_maker = session_factory(engine)
    with session_maker() as session:
        assert list_candidates(session) == []
