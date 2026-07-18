"""jobs.py — ジョブの永続化（仕様書§13・§14・Phase 11タスク2）。

`job_id`単位で1行を持つ（append-onlyではない——status/progress/errorは実行の進行に
つれて同じ行を更新する。再実行は新しいjob_idで別行を作る想定なので、履歴が消えるのは
「実行中の1件についての更新」だけで、過去の実行そのものは`retry_of`で辿れる）。
ログ（`JobLogRow`）だけは追記のみ——他のappend-onlyテーブルと同じ方針。
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from history_radio.domain.models import Job, JobLogEntry, JobLogLevel, JobStatus
from history_radio.store.orm import JobLogRow, JobRow

TERMINAL_JOB_STATUSES: frozenset[JobStatus] = frozenset(
    {"succeeded", "failed", "blocked", "cancelled"}
)


class JobNotFoundError(RuntimeError):
    def __init__(self, job_id: str) -> None:
        super().__init__(f"Job {job_id!r} が存在しない")
        self.job_id = job_id


class JobAlreadyTerminalError(RuntimeError):
    """終了済み（succeeded/failed/blocked/cancelled）のジョブへキャンセルを要求した。"""

    def __init__(self, job_id: str, status: JobStatus) -> None:
        super().__init__(f"Job {job_id!r} は既に終了している（status={status!r}）")
        self.job_id = job_id
        self.status = status


def _row_to_domain(row: JobRow) -> Job:
    return Job(
        job_id=row.job_id,
        episode_id=row.episode_id,
        kind=row.kind,
        status=row.status,  # type: ignore[arg-type]
        progress=row.progress,
        cancel_requested=row.cancel_requested,
        retry_of=row.retry_of,
        error=row.error,
        created_at=row.created_at,
        started_at=row.started_at,
        finished_at=row.finished_at,
    )


def _get_row(session: Session, job_id: str) -> JobRow:
    row = session.get(JobRow, job_id)
    if row is None:
        raise JobNotFoundError(job_id)
    return row


def create_job(
    session: Session, *, job_id: str, episode_id: str | None, kind: str, retry_of: str | None = None
) -> Job:
    row = JobRow(
        job_id=job_id,
        episode_id=episode_id,
        kind=kind,
        status="queued",
        progress=0.0,
        cancel_requested=False,
        retry_of=retry_of,
        error=None,
        created_at=datetime.now(timezone.utc),
        started_at=None,
        finished_at=None,
    )
    session.add(row)
    session.commit()
    return _row_to_domain(row)


def get_job(session: Session, job_id: str) -> Job:
    return _row_to_domain(_get_row(session, job_id))


def list_jobs(session: Session) -> list[Job]:
    """新しい順（作成日時降順）——管理画面の一覧は直近のジョブが先頭に来るのが自然なため。"""
    rows = session.execute(select(JobRow).order_by(JobRow.created_at.desc())).scalars().all()
    return [_row_to_domain(row) for row in rows]


def mark_running(session: Session, job_id: str) -> Job:
    row = _get_row(session, job_id)
    row.status = "running"
    row.started_at = datetime.now(timezone.utc)
    session.commit()
    return _row_to_domain(row)


def mark_succeeded(session: Session, job_id: str) -> Job:
    row = _get_row(session, job_id)
    row.status = "succeeded"
    row.progress = 1.0
    row.finished_at = datetime.now(timezone.utc)
    session.commit()
    return _row_to_domain(row)


def mark_failed(session: Session, job_id: str, *, error: str) -> Job:
    row = _get_row(session, job_id)
    row.status = "failed"
    row.error = error
    row.finished_at = datetime.now(timezone.utc)
    session.commit()
    return _row_to_domain(row)


def mark_cancelled(session: Session, job_id: str) -> Job:
    row = _get_row(session, job_id)
    row.status = "cancelled"
    row.finished_at = datetime.now(timezone.utc)
    session.commit()
    return _row_to_domain(row)


def update_progress(session: Session, job_id: str, *, progress: float) -> Job:
    row = _get_row(session, job_id)
    row.progress = progress
    session.commit()
    return _row_to_domain(row)


def request_cancel(session: Session, job_id: str) -> Job:
    """実行中/開始前のジョブへキャンセルを要求する。実際に停止させるのは実行側
    （jobs/runner.py）の役目——ここではフラグを立てて即座に返す（cancelは非同期）。
    """
    row = _get_row(session, job_id)
    if row.status in TERMINAL_JOB_STATUSES:
        raise JobAlreadyTerminalError(job_id, row.status)  # type: ignore[arg-type]
    row.cancel_requested = True
    session.commit()
    return _row_to_domain(row)


def is_cancel_requested(session: Session, job_id: str) -> bool:
    return _get_row(session, job_id).cancel_requested


def append_job_log(
    session: Session, job_id: str, *, level: JobLogLevel, message: str
) -> JobLogEntry:
    next_seq = (
        session.execute(select(func.max(JobLogRow.seq)).where(JobLogRow.job_id == job_id)).scalar()
        or 0
    ) + 1
    now = datetime.now(timezone.utc)
    row = JobLogRow(job_id=job_id, seq=next_seq, level=level, message=message, occurred_at=now)
    session.add(row)
    session.commit()
    return JobLogEntry(job_id=job_id, seq=next_seq, level=level, message=message, occurred_at=now)


def list_job_logs(session: Session, job_id: str, *, since_seq: int = 0) -> list[JobLogEntry]:
    rows = (
        session.execute(
            select(JobLogRow)
            .where(JobLogRow.job_id == job_id, JobLogRow.seq > since_seq)
            .order_by(JobLogRow.seq)
        )
        .scalars()
        .all()
    )
    return [
        JobLogEntry(
            job_id=row.job_id,
            seq=row.seq,
            level=row.level,  # type: ignore[arg-type]
            message=row.message,
            occurred_at=row.occurred_at,
        )
        for row in rows
    ]


__all__ = [
    "TERMINAL_JOB_STATUSES",
    "JobAlreadyTerminalError",
    "JobNotFoundError",
    "append_job_log",
    "create_job",
    "get_job",
    "is_cancel_requested",
    "list_job_logs",
    "list_jobs",
    "mark_cancelled",
    "mark_failed",
    "mark_running",
    "mark_succeeded",
    "request_cancel",
    "update_progress",
]
