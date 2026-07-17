"""test_episode_approval.py — Phase 11タスク1 DoD: 承認はゲート合格・publish_ready状態を要求する"""

from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import Engine

from history_radio.publish.episode_approval import EpisodeApprovalError, approve_episode
from history_radio.publish.publish_gate import GateCheckResult, PublishGateResult
from history_radio.store.db import create_sqlite_engine, session_factory
from history_radio.store.episodes import create_episode, get_episode, update_episode_state
from history_radio.store.gate_results import save_gate_result
from history_radio.store.orm import Base


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Engine]:
    eng = create_sqlite_engine(tmp_path / "test.db")
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


def _passing_gate_result(episode_id: str, revision: int = 1) -> PublishGateResult:
    return PublishGateResult(
        episode_id=episode_id,
        revision=revision,
        rule_version="2026-07-19.1",
        publish_ready=True,
        checks=(GateCheckResult(name="rights_and_episode_schema", passed=True),),
        artifact_hash="hash-x",
    )


def _failing_gate_result(episode_id: str, revision: int = 1) -> PublishGateResult:
    return PublishGateResult(
        episode_id=episode_id,
        revision=revision,
        rule_version="2026-07-19.1",
        publish_ready=False,
        checks=(
            GateCheckResult(name="rights_and_episode_schema", passed=False, reasons=("失敗理由",)),
        ),
        artifact_hash="hash-x",
    )


def test_approve_succeeds_when_publish_ready_and_gate_passed(engine: Engine) -> None:
    session_maker = session_factory(engine)
    with session_maker() as session:
        create_episode(session, episode_id="ep-1", title="テストエピソード")
        update_episode_state(
            session, episode_id="ep-1", expected_revision=1, new_state="publish_ready"
        )
        save_gate_result(
            session,
            _passing_gate_result("ep-1"),
            result_id="gate-1",
            evaluated_at=datetime(2026, 7, 19, tzinfo=timezone.utc),
        )

    with session_maker() as session:
        approved = approve_episode(session, episode_id="ep-1")

    assert approved.state == "approved"

    with session_maker() as session:
        assert get_episode(session, "ep-1").state == "approved"


def test_approve_rejects_episode_not_in_publish_ready_state(engine: Engine) -> None:
    """development-plan.md Phase 11タスク1: 状態機械の段階飛ばしを承認操作にも適用する。"""
    session_maker = session_factory(engine)
    with session_maker() as session:
        create_episode(session, episode_id="ep-2", title="まだ準備中のエピソード")
        save_gate_result(
            session,
            _passing_gate_result("ep-2"),
            result_id="gate-2",
            evaluated_at=datetime(2026, 7, 19, tzinfo=timezone.utc),
        )

    with session_maker() as session:
        with pytest.raises(EpisodeApprovalError, match="承認できない"):
            approve_episode(session, episode_id="ep-2")

    with session_maker() as session:
        assert get_episode(session, "ep-2").state == "collected"


def test_approve_rejects_when_no_gate_result_exists(engine: Engine) -> None:
    session_maker = session_factory(engine)
    with session_maker() as session:
        create_episode(session, episode_id="ep-3", title="ゲート未評価のエピソード")
        update_episode_state(
            session, episode_id="ep-3", expected_revision=1, new_state="publish_ready"
        )

    with session_maker() as session:
        with pytest.raises(EpisodeApprovalError, match="評価結果が無い"):
            approve_episode(session, episode_id="ep-3")


def test_approve_rejects_when_gate_result_failed(engine: Engine) -> None:
    session_maker = session_factory(engine)
    with session_maker() as session:
        create_episode(session, episode_id="ep-4", title="ゲート不合格のエピソード")
        update_episode_state(
            session, episode_id="ep-4", expected_revision=1, new_state="publish_ready"
        )
        save_gate_result(
            session,
            _failing_gate_result("ep-4"),
            result_id="gate-4",
            evaluated_at=datetime(2026, 7, 19, tzinfo=timezone.utc),
        )

    with session_maker() as session:
        with pytest.raises(EpisodeApprovalError, match="不合格"):
            approve_episode(session, episode_id="ep-4")

    with session_maker() as session:
        assert get_episode(session, "ep-4").state == "publish_ready"


def test_approve_uses_the_latest_gate_result_for_the_current_revision(engine: Engine) -> None:
    """古い失敗結果があっても、最新の合格結果があれば承認できる。"""
    session_maker = session_factory(engine)
    with session_maker() as session:
        create_episode(session, episode_id="ep-5", title="再評価されたエピソード")
        update_episode_state(
            session, episode_id="ep-5", expected_revision=1, new_state="publish_ready"
        )
        save_gate_result(
            session,
            _failing_gate_result("ep-5"),
            result_id="gate-5-fail",
            evaluated_at=datetime(2026, 7, 19, tzinfo=timezone.utc),
        )
        save_gate_result(
            session,
            _passing_gate_result("ep-5"),
            result_id="gate-5-pass",
            evaluated_at=datetime(2026, 7, 20, tzinfo=timezone.utc),
        )

    with session_maker() as session:
        approved = approve_episode(session, episode_id="ep-5")

    assert approved.state == "approved"
