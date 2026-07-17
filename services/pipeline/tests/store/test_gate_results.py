"""test_gate_results.py — Phase 10タスク3 DoD: 公開済み版から当時の検査結果を再表示できる"""

from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import Engine, select

from history_radio.publish.publish_gate import GateCheckResult, PublishGateResult
from history_radio.store.db import create_sqlite_engine, session_factory
from history_radio.store.gate_results import (
    latest_gate_result_for_revision,
    list_gate_results_for_episode,
    save_gate_result,
)
from history_radio.store.orm import AuditEventRow, Base


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Engine]:
    eng = create_sqlite_engine(tmp_path / "test.db")
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


def _gate_result(
    *, episode_id: str, revision: int, publish_ready: bool, artifact_hash: str = "hash-x"
) -> PublishGateResult:
    return PublishGateResult(
        episode_id=episode_id,
        revision=revision,
        rule_version="2026-07-19.1",
        publish_ready=publish_ready,
        checks=(
            GateCheckResult(
                name="rights_and_episode_schema",
                passed=publish_ready,
                reasons=() if publish_ready else ("失敗理由",),
            ),
        ),
        artifact_hash=artifact_hash,
    )


def test_gate_result_can_be_saved_and_retrieved_by_revision(engine: Engine) -> None:
    """Phase 10タスク3 DoD: 公開済み版から当時の検査結果を再表示できる。"""
    session_maker = session_factory(engine)

    with session_maker() as session:
        save_gate_result(
            session,
            _gate_result(episode_id="ep-1", revision=1, publish_ready=True),
            result_id="gate-1",
            evaluated_at=datetime(2026, 7, 19, tzinfo=timezone.utc),
        )

    with session_maker() as session:
        result = latest_gate_result_for_revision(session, "ep-1", 1)

    assert result is not None
    assert result.publish_ready is True
    assert result.artifact_hash == "hash-x"
    assert result.checks[0].name == "rights_and_episode_schema"


def test_reevaluating_the_same_revision_keeps_the_old_result(engine: Engine) -> None:
    """append-only: 同じepisode_id・revisionを再評価しても過去の結果が消えない。"""
    session_maker = session_factory(engine)

    with session_maker() as session:
        save_gate_result(
            session,
            _gate_result(
                episode_id="ep-2", revision=1, publish_ready=False, artifact_hash="hash-a"
            ),
            result_id="gate-a",
            evaluated_at=datetime(2026, 7, 19, tzinfo=timezone.utc),
        )

    with session_maker() as session:
        save_gate_result(
            session,
            _gate_result(episode_id="ep-2", revision=1, publish_ready=True, artifact_hash="hash-b"),
            result_id="gate-b",
            evaluated_at=datetime(2026, 7, 20, tzinfo=timezone.utc),
        )

    with session_maker() as session:
        history = list_gate_results_for_episode(session, "ep-2")

    assert len(history) == 2
    assert history[0].publish_ready is False
    assert history[1].publish_ready is True


def test_latest_result_for_revision_returns_the_most_recent_evaluation(engine: Engine) -> None:
    session_maker = session_factory(engine)

    with session_maker() as session:
        save_gate_result(
            session,
            _gate_result(
                episode_id="ep-3", revision=1, publish_ready=False, artifact_hash="hash-old"
            ),
            result_id="gate-1",
            evaluated_at=datetime(2026, 7, 19, tzinfo=timezone.utc),
        )
        save_gate_result(
            session,
            _gate_result(
                episode_id="ep-3", revision=1, publish_ready=True, artifact_hash="hash-new"
            ),
            result_id="gate-2",
            evaluated_at=datetime(2026, 7, 20, tzinfo=timezone.utc),
        )

    with session_maker() as session:
        latest = latest_gate_result_for_revision(session, "ep-3", 1)

    assert latest is not None
    assert latest.artifact_hash == "hash-new"


def test_different_revisions_of_the_same_episode_are_independent(engine: Engine) -> None:
    """revision 2公開後もrevision 1の検査結果はそのまま参照できる。"""
    session_maker = session_factory(engine)

    with session_maker() as session:
        save_gate_result(
            session,
            _gate_result(
                episode_id="ep-4", revision=1, publish_ready=True, artifact_hash="hash-r1"
            ),
            result_id="gate-r1",
            evaluated_at=datetime(2026, 7, 19, tzinfo=timezone.utc),
        )
        save_gate_result(
            session,
            _gate_result(
                episode_id="ep-4", revision=2, publish_ready=True, artifact_hash="hash-r2"
            ),
            result_id="gate-r2",
            evaluated_at=datetime(2026, 7, 20, tzinfo=timezone.utc),
        )

    with session_maker() as session:
        r1 = latest_gate_result_for_revision(session, "ep-4", 1)
        r2 = latest_gate_result_for_revision(session, "ep-4", 2)

    assert r1 is not None
    assert r2 is not None
    assert r1.artifact_hash == "hash-r1"
    assert r2.artifact_hash == "hash-r2"


def test_no_result_returns_none(engine: Engine) -> None:
    session_maker = session_factory(engine)
    with session_maker() as session:
        assert latest_gate_result_for_revision(session, "ep-missing", 1) is None


def test_saving_a_gate_result_also_appends_an_audit_event(engine: Engine) -> None:
    """仕様書§15: ゲート評価を追記型監査ログへ記録する。"""
    session_maker = session_factory(engine)

    with session_maker() as session:
        save_gate_result(
            session,
            _gate_result(episode_id="ep-5", revision=1, publish_ready=True),
            result_id="gate-audit-1",
            evaluated_at=datetime(2026, 7, 19, tzinfo=timezone.utc),
        )

    with session_maker() as session:
        events = (
            session.execute(select(AuditEventRow).where(AuditEventRow.entity_id == "ep-5"))
            .scalars()
            .all()
        )

    assert len(events) == 1
    assert events[0].entity_type == "publish_gate_result"
    assert events[0].action == "publish_gate_evaluated"


def test_checks_with_reasons_round_trip_through_json(engine: Engine) -> None:
    session_maker = session_factory(engine)
    result = PublishGateResult(
        episode_id="ep-6",
        revision=1,
        rule_version="2026-07-19.1",
        publish_ready=False,
        checks=(
            GateCheckResult(
                name="media_manifest", passed=False, reasons=("クレジット欠落", "出典URL欠落")
            ),
        ),
        artifact_hash="hash-6",
    )

    with session_maker() as session:
        save_gate_result(
            session,
            result,
            result_id="gate-6",
            evaluated_at=datetime(2026, 7, 19, tzinfo=timezone.utc),
        )

    with session_maker() as session:
        loaded = latest_gate_result_for_revision(session, "ep-6", 1)

    assert loaded is not None
    assert loaded.checks[0].reasons == ("クレジット欠落", "出典URL欠落")
