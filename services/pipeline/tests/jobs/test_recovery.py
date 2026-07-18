"""test_recovery.py — Phase 12タスク4 DoD: PC再起動後の中断ジョブ検出を固定する。

「起動時点でstatus='running'のジョブは前回プロセスの異常終了の痕跡」という
単一プロセス前提の判定ロジックを、実際のプロセスクラッシュを起こさずに
テストする——`mark_running()`で直接「クラッシュ前の状態」を再現するだけで十分
（fault injectionそのものはPlaywright/実機側の責務ではなく、この判定ロジックが
「runningのまま残っている行を見つけたら確実にblockedへ落とす」ことを保証する
のがこのテストの役目）。
"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine, select

from history_radio.jobs.recovery import ORPHANED_JOB_REASON, recover_orphaned_jobs
from history_radio.store.db import create_sqlite_engine, session_factory
from history_radio.store.episodes import create_episode
from history_radio.store.jobs import (
    create_job,
    get_job,
    mark_running,
    mark_succeeded,
)
from history_radio.store.orm import AuditEventRow, Base


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Engine]:
    eng = create_sqlite_engine(tmp_path / "test.db")
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


def test_running_job_is_blocked_and_others_are_untouched(engine: Engine) -> None:
    session_maker = session_factory(engine)
    with session_maker() as session:
        create_episode(session, episode_id="ep-1", title="中断されたジョブのエピソード")
        create_episode(session, episode_id="ep-2", title="成功済みのエピソード")
        create_episode(session, episode_id="ep-3", title="待機中のエピソード")

        create_job(session, job_id="job-orphaned", episode_id="ep-1", kind="episode_generation")
        mark_running(session, "job-orphaned")

        create_job(session, job_id="job-succeeded", episode_id="ep-2", kind="episode_generation")
        mark_running(session, "job-succeeded")
        mark_succeeded(session, "job-succeeded")

        create_job(session, job_id="job-queued", episode_id="ep-3", kind="episode_generation")

    recovered = recover_orphaned_jobs(session_maker)

    assert [job.job_id for job in recovered] == ["job-orphaned"]

    with session_maker() as session:
        orphaned = get_job(session, "job-orphaned")
        assert orphaned.status == "blocked"
        assert orphaned.error == ORPHANED_JOB_REASON
        assert orphaned.finished_at is not None

        # running状態でなかったジョブは触れない。
        assert get_job(session, "job-succeeded").status == "succeeded"
        assert get_job(session, "job-queued").status == "queued"


def test_recovery_records_an_audit_event_per_orphaned_job(engine: Engine) -> None:
    session_maker = session_factory(engine)
    with session_maker() as session:
        create_episode(session, episode_id="ep-1", title="中断されたジョブのエピソード")
        create_job(session, job_id="job-orphaned", episode_id="ep-1", kind="episode_generation")
        mark_running(session, "job-orphaned")

    recover_orphaned_jobs(session_maker)

    with session_maker() as session:
        events = (
            session.execute(
                select(AuditEventRow).where(
                    AuditEventRow.entity_type == "job",
                    AuditEventRow.entity_id == "job-orphaned",
                    AuditEventRow.action == "orphan_recovered",
                )
            )
            .scalars()
            .all()
        )
        assert len(events) == 1
        assert events[0].actor == "system_startup"


def test_recovery_with_no_orphaned_jobs_is_a_no_op(engine: Engine) -> None:
    session_maker = session_factory(engine)
    with session_maker() as session:
        create_episode(session, episode_id="ep-1", title="正常終了したエピソード")
        create_job(session, job_id="job-1", episode_id="ep-1", kind="episode_generation")
        mark_running(session, "job-1")
        mark_succeeded(session, "job-1")

    recovered = recover_orphaned_jobs(session_maker)

    assert recovered == []


def test_recovery_is_idempotent_across_repeated_startups(engine: Engine) -> None:
    """2回連続で呼んでも(=2回連続で異常終了しても)、既にblocked済みのジョブを
    再度触らない(二重にAuditEventが増えない)ことを固定する。
    """
    session_maker = session_factory(engine)
    with session_maker() as session:
        create_episode(session, episode_id="ep-1", title="中断されたジョブのエピソード")
        create_job(session, job_id="job-orphaned", episode_id="ep-1", kind="episode_generation")
        mark_running(session, "job-orphaned")

    first_run = recover_orphaned_jobs(session_maker)
    second_run = recover_orphaned_jobs(session_maker)

    assert len(first_run) == 1
    assert second_run == []
