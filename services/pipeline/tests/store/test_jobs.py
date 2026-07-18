"""test_jobs.py — Phase 11タスク2: ジョブの永続化・進捗・キャンセル要求・ログ追記を固定する"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine

from history_radio.store.db import create_sqlite_engine, session_factory
from history_radio.store.jobs import (
    JobAlreadyTerminalError,
    JobNotFoundError,
    append_job_log,
    create_job,
    get_job,
    is_cancel_requested,
    list_job_logs,
    list_jobs,
    mark_blocked,
    mark_cancelled,
    mark_failed,
    mark_running,
    mark_succeeded,
    request_cancel,
    update_progress,
)
from history_radio.store.orm import Base


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Engine]:
    eng = create_sqlite_engine(tmp_path / "test.db")
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


def test_create_job_starts_queued_with_zero_progress(engine: Engine) -> None:
    session_maker = session_factory(engine)
    with session_maker() as session:
        job = create_job(session, job_id="job-1", episode_id="ep-1", kind="episode_generation")
    assert job.status == "queued"
    assert job.progress == 0.0
    assert job.cancel_requested is False
    assert job.retry_of is None
    assert job.started_at is None


def test_get_unknown_job_raises(engine: Engine) -> None:
    session_maker = session_factory(engine)
    with session_maker() as session, pytest.raises(JobNotFoundError):
        get_job(session, "does-not-exist")


def test_mark_running_then_succeeded_updates_status_and_progress(engine: Engine) -> None:
    session_maker = session_factory(engine)
    with session_maker() as session:
        create_job(session, job_id="job-1", episode_id="ep-1", kind="episode_generation")
        running = mark_running(session, "job-1")
        assert running.status == "running"
        assert running.started_at is not None

        update_progress(session, "job-1", progress=0.5)
        succeeded = mark_succeeded(session, "job-1")
        assert succeeded.status == "succeeded"
        assert succeeded.progress == 1.0
        assert succeeded.finished_at is not None


def test_mark_failed_records_error(engine: Engine) -> None:
    session_maker = session_factory(engine)
    with session_maker() as session:
        create_job(session, job_id="job-1", episode_id="ep-1", kind="episode_generation")
        failed = mark_failed(session, "job-1", error="想定外の失敗")
    assert failed.status == "failed"
    assert failed.error == "想定外の失敗"
    assert failed.finished_at is not None


def test_request_cancel_sets_flag_on_running_job(engine: Engine) -> None:
    session_maker = session_factory(engine)
    with session_maker() as session:
        create_job(session, job_id="job-1", episode_id="ep-1", kind="episode_generation")
        mark_running(session, "job-1")
        cancelled_flagged = request_cancel(session, "job-1")
        assert cancelled_flagged.cancel_requested is True
        assert is_cancel_requested(session, "job-1") is True


def test_request_cancel_on_terminal_job_is_rejected(engine: Engine) -> None:
    session_maker = session_factory(engine)
    with session_maker() as session:
        create_job(session, job_id="job-1", episode_id="ep-1", kind="episode_generation")
        mark_succeeded(session, "job-1")
        with pytest.raises(JobAlreadyTerminalError):
            request_cancel(session, "job-1")


def test_mark_cancelled_sets_terminal_status(engine: Engine) -> None:
    session_maker = session_factory(engine)
    with session_maker() as session:
        create_job(session, job_id="job-1", episode_id="ep-1", kind="episode_generation")
        mark_running(session, "job-1")
        cancelled = mark_cancelled(session, "job-1")
    assert cancelled.status == "cancelled"
    assert cancelled.finished_at is not None


def test_list_jobs_returns_newest_first(engine: Engine) -> None:
    session_maker = session_factory(engine)
    with session_maker() as session:
        create_job(session, job_id="job-old", episode_id="ep-1", kind="episode_generation")
        create_job(session, job_id="job-new", episode_id="ep-2", kind="episode_generation")
        jobs = list_jobs(session)
    assert [job.job_id for job in jobs] == ["job-new", "job-old"]


def test_create_job_with_retry_of_links_to_original(engine: Engine) -> None:
    session_maker = session_factory(engine)
    with session_maker() as session:
        create_job(session, job_id="job-1", episode_id="ep-1", kind="episode_generation")
        retry = create_job(
            session, job_id="job-2", episode_id="ep-1", kind="episode_generation", retry_of="job-1"
        )
    assert retry.retry_of == "job-1"


def test_append_job_log_assigns_incrementing_seq(engine: Engine) -> None:
    session_maker = session_factory(engine)
    with session_maker() as session:
        create_job(session, job_id="job-1", episode_id="ep-1", kind="episode_generation")
        first = append_job_log(session, "job-1", level="info", message="開始")
        second = append_job_log(session, "job-1", level="error", message="失敗した")
    assert first.seq == 1
    assert second.seq == 2
    assert second.level == "error"


def test_list_job_logs_filters_by_since_seq(engine: Engine) -> None:
    session_maker = session_factory(engine)
    with session_maker() as session:
        create_job(session, job_id="job-1", episode_id="ep-1", kind="episode_generation")
        append_job_log(session, "job-1", level="info", message="1")
        append_job_log(session, "job-1", level="info", message="2")
        append_job_log(session, "job-1", level="info", message="3")

        all_logs = list_job_logs(session, "job-1")
        since_1 = list_job_logs(session, "job-1", since_seq=1)

    assert [log.message for log in all_logs] == ["1", "2", "3"]
    assert [log.message for log in since_1] == ["2", "3"]


def test_mark_blocked_sets_terminal_status_and_error(engine: Engine) -> None:
    session_maker = session_factory(engine)
    with session_maker() as session:
        create_job(session, job_id="job-1", episode_id="ep-1", kind="episode_generation")
        mark_running(session, "job-1")
        blocked = mark_blocked(session, "job-1", error="外部要因により中断された")
    assert blocked.status == "blocked"
    assert blocked.error == "外部要因により中断された"
    assert blocked.finished_at is not None
