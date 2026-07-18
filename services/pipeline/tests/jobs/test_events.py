"""test_events.py — Phase 11タスク2: SSE配信が現在の状態を必ず1件配信し、
終端状態で確実に閉じ、途中の更新も取りこぼさないことを固定する。

`on_before_poll`フックで各ポーリングの直前にDBを直接更新することで、
sleepに頼らず「配信中に別スレッドが状態を進めた」状況を決定的に再現する
（§8「テスト内のsleepはflakyの温床」）。
"""

import asyncio
import json
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Engine

from history_radio.jobs.events import stream_job_events
from history_radio.store.db import create_sqlite_engine, session_factory
from history_radio.store.jobs import (
    JobNotFoundError,
    append_job_log,
    create_job,
    mark_running,
    mark_succeeded,
)
from history_radio.store.orm import Base


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Engine]:
    eng = create_sqlite_engine(tmp_path / "test.db")
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


async def _drain(agen: AsyncIterator[str]) -> list[str]:
    return [item async for item in agen]


def _collect_lines(agen: AsyncIterator[str]) -> list[str]:
    """`stream_job_events`は非同期ジェネレータ（events.pyのモジュールdocstring参照:
    SSE接続がスレッドプールを占有し続けないための設計）——テストでは同期的に
    全件排出してから通常のリストとして検査する。
    """
    return asyncio.run(_drain(agen))


def _parse_events(lines: list[str]) -> list[dict[str, Any]]:
    return [json.loads(line[len("data: ") :]) for line in lines if line.startswith("data: ")]


def test_stream_closes_immediately_for_an_already_terminal_job(engine: Engine) -> None:
    session_maker = session_factory(engine)
    with session_maker() as session:
        create_job(session, job_id="job-1", episode_id="ep-1", kind="episode_generation")
        append_job_log(session, "job-1", level="info", message="開始")
        mark_succeeded(session, "job-1")

    lines = _collect_lines(stream_job_events(session_maker, "job-1", poll_interval_seconds=0))
    events = _parse_events(lines)

    assert len(events) == 1
    assert events[0]["job"]["status"] == "succeeded"
    assert [log["message"] for log in events[0]["logs"]] == ["開始"]


def test_stream_delivers_incremental_updates_across_polls(engine: Engine) -> None:
    session_maker = session_factory(engine)
    with session_maker() as session:
        create_job(session, job_id="job-1", episode_id="ep-1", kind="episode_generation")
        mark_running(session, "job-1")

    def on_before_poll(poll_index: int) -> None:
        # 1回目の配信(poll_index=0)の後、2回目のポーリング直前(poll_index=1)に
        # 別スレッド相当の更新を行う——sleepせずに「配信中の進行」を再現する。
        if poll_index == 1:
            with session_maker() as session:
                append_job_log(session, "job-1", level="info", message="状態 rights_passed へ遷移")
                mark_succeeded(session, "job-1")

    lines = _collect_lines(
        stream_job_events(
            session_maker, "job-1", poll_interval_seconds=0, on_before_poll=on_before_poll
        )
    )
    events = _parse_events(lines)

    assert len(events) == 2
    assert events[0]["job"]["status"] == "running"
    assert events[0]["logs"] == []
    assert events[1]["job"]["status"] == "succeeded"
    assert [log["message"] for log in events[1]["logs"]] == ["状態 rights_passed へ遷移"]


def test_stream_returns_404_worthy_error_for_unknown_job(engine: Engine) -> None:
    session_maker = session_factory(engine)
    with pytest.raises(JobNotFoundError):
        _collect_lines(stream_job_events(session_maker, "does-not-exist", poll_interval_seconds=0))
