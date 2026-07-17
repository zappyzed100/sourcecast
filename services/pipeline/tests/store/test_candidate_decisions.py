"""test_candidate_decisions.py — Phase 11タスク1・3 DoD: 審査結果の追記保存・監査ログ記録"""

from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import Engine, select

from history_radio.domain.models import CandidateDecision
from history_radio.store.candidate_decisions import (
    latest_decision_for_candidate,
    list_decisions_for_candidate,
    save_candidate_decision,
)
from history_radio.store.db import create_sqlite_engine, session_factory
from history_radio.store.orm import AuditEventRow, Base


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Engine]:
    eng = create_sqlite_engine(tmp_path / "test.db")
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


def _decision(
    *, decision_id: str, candidate_id: str, decision: str, reason: str, decided_at: datetime
) -> CandidateDecision:
    return CandidateDecision(
        decision_id=decision_id,
        candidate_id=candidate_id,
        decision=decision,  # type: ignore[arg-type]
        reason=reason,
        decided_at=decided_at,
    )


def test_re_reviewing_a_candidate_keeps_the_old_decision(engine: Engine) -> None:
    """append-only: 同じ候補を再審査しても過去の判定が消えない。"""
    session_maker = session_factory(engine)

    with session_maker() as session:
        save_candidate_decision(
            session,
            _decision(
                decision_id="dec-1",
                candidate_id="cand-1",
                decision="excluded",
                reason="出典不足",
                decided_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
            ),
        )

    with session_maker() as session:
        save_candidate_decision(
            session,
            _decision(
                decision_id="dec-2",
                candidate_id="cand-1",
                decision="adopted",
                reason="",
                decided_at=datetime(2026, 7, 19, tzinfo=timezone.utc),
            ),
        )

    with session_maker() as session:
        history = list_decisions_for_candidate(session, "cand-1")

    assert [d.decision_id for d in history] == ["dec-1", "dec-2"]
    assert history[0].decision == "excluded"
    assert history[1].decision == "adopted"


def test_latest_decision_returns_the_most_recent_review(engine: Engine) -> None:
    session_maker = session_factory(engine)

    with session_maker() as session:
        save_candidate_decision(
            session,
            _decision(
                decision_id="dec-1",
                candidate_id="cand-2",
                decision="excluded",
                reason="重複題材",
                decided_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
            ),
        )

    with session_maker() as session:
        latest = latest_decision_for_candidate(session, "cand-2")

    assert latest is not None
    assert latest.decision_id == "dec-1"
    assert latest.reason == "重複題材"


def test_no_decision_returns_none(engine: Engine) -> None:
    session_maker = session_factory(engine)
    with session_maker() as session:
        assert latest_decision_for_candidate(session, "cand-missing") is None


def test_saving_a_decision_also_appends_an_audit_event(engine: Engine) -> None:
    """仕様書§15: 候補審査を追記型監査ログへ記録する。"""
    session_maker = session_factory(engine)

    with session_maker() as session:
        save_candidate_decision(
            session,
            _decision(
                decision_id="dec-audit-1",
                candidate_id="cand-3",
                decision="adopted",
                reason="",
                decided_at=datetime(2026, 7, 19, tzinfo=timezone.utc),
            ),
        )

    with session_maker() as session:
        events = (
            session.execute(select(AuditEventRow).where(AuditEventRow.entity_id == "cand-3"))
            .scalars()
            .all()
        )

    assert len(events) == 1
    assert events[0].entity_type == "candidate_decision"
    assert events[0].action == "candidate_adopted"
