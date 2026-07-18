"""test_runner.py — Phase 11タスク2 DoD: エピソード生成ジョブが工程単位で実行され、
キャンセル・失敗時にも必ず終端状態へ到達することを固定する。

キャンセル中断のテストはtime.sleep等の実待機を使わず、`on_before_step`フック +
`threading.Event`でジョブ実行スレッドと決定的に同期する（§8「テスト内のsleepは
flakyの温床」——Event.wait()はタイムアウトを安全弁としてのみ使う信号待ちであり、
実待機に依存した判定はしない）。
"""

import threading
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine

from history_radio.domain.episode_state import EpisodeState
from history_radio.jobs.runner import run_episode_generation_job
from history_radio.store.db import create_sqlite_engine, session_factory
from history_radio.store.episodes import create_episode, get_episode, update_episode_state
from history_radio.store.jobs import create_job, get_job, list_job_logs, request_cancel
from history_radio.store.orm import Base

SYNC_TIMEOUT_SECONDS = 5.0


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Engine]:
    eng = create_sqlite_engine(tmp_path / "test.db")
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


def test_job_advances_episode_to_publish_ready_and_succeeds(engine: Engine) -> None:
    session_maker = session_factory(engine)
    with session_maker() as session:
        create_episode(session, episode_id="ep-1", title="題材")
        create_job(session, job_id="job-1", episode_id="ep-1", kind="episode_generation")

    run_episode_generation_job(
        session_maker, job_id="job-1", episode_id="ep-1", step_delay_seconds=0
    )

    with session_maker() as session:
        job = get_job(session, "job-1")
        episode = get_episode(session, "ep-1")
        logs = list_job_logs(session, "job-1")

    assert job.status == "succeeded"
    assert job.progress == 1.0
    assert episode.state == "publish_ready"
    # collected -> ... -> publish_ready の7遷移 + 開始1件 + 完了1件 = 9件
    assert len(logs) == 9
    assert any("publish_ready" in log.message for log in logs)


def test_job_resumes_from_the_episodes_current_state(engine: Engine) -> None:
    """仕様書§14「工程単位で再実行」: 既に途中まで進んだエピソードなら、そこから続きだけ行う。"""
    session_maker = session_factory(engine)
    with session_maker() as session:
        create_episode(session, episode_id="ep-1", title="題材")
        update_episode_state(
            session, episode_id="ep-1", expected_revision=1, new_state="rights_passed"
        )
        update_episode_state(
            session, episode_id="ep-1", expected_revision=2, new_state="topic_selected"
        )
        create_job(session, job_id="job-1", episode_id="ep-1", kind="episode_generation")

    run_episode_generation_job(
        session_maker, job_id="job-1", episode_id="ep-1", step_delay_seconds=0
    )

    with session_maker() as session:
        episode = get_episode(session, "ep-1")
        logs = list_job_logs(session, "job-1")

    assert episode.state == "publish_ready"
    # topic_selectedの次から: facts_verified〜publish_readyの5遷移 + 開始1件 + 完了1件 = 7件
    assert len(logs) == 7


def test_job_fails_when_episode_is_in_a_terminal_failure_state(engine: Engine) -> None:
    session_maker = session_factory(engine)
    with session_maker() as session:
        create_episode(session, episode_id="ep-1", title="題材")
        update_episode_state(session, episode_id="ep-1", expected_revision=1, new_state="rejected")
        create_job(session, job_id="job-1", episode_id="ep-1", kind="episode_generation")

    run_episode_generation_job(
        session_maker, job_id="job-1", episode_id="ep-1", step_delay_seconds=0
    )

    with session_maker() as session:
        job = get_job(session, "job-1")
    assert job.status == "failed"
    assert job.error is not None and "rejected" in job.error


def test_job_fails_visibly_when_episode_does_not_exist(engine: Engine) -> None:
    session_maker = session_factory(engine)
    with session_maker() as session:
        create_job(session, job_id="job-1", episode_id="does-not-exist", kind="episode_generation")

    run_episode_generation_job(
        session_maker, job_id="job-1", episode_id="does-not-exist", step_delay_seconds=0
    )

    with session_maker() as session:
        job = get_job(session, "job-1")
    assert job.status == "failed"
    assert job.error is not None


def test_cancel_requested_mid_run_stops_the_job_and_preserves_partial_progress(
    engine: Engine,
) -> None:
    """ブラウザから「キャンセル」を押した想定: 2番目の遷移に入る直前で要求を出し、
    ジョブがその時点で停止して`cancelled`になること、既に完了した1歩目は保持されることを固定する。
    """
    session_maker = session_factory(engine)
    with session_maker() as session:
        create_episode(session, episode_id="ep-1", title="題材")
        create_job(session, job_id="job-1", episode_id="ep-1", kind="episode_generation")

    paused_at_step: EpisodeState | None = None
    reached_pause = threading.Event()
    resume = threading.Event()

    def on_before_step(state: EpisodeState) -> None:
        nonlocal paused_at_step
        if state == "topic_selected":
            paused_at_step = state
            reached_pause.set()
            resume.wait(timeout=SYNC_TIMEOUT_SECONDS)

    runner_thread = threading.Thread(
        target=run_episode_generation_job,
        kwargs={
            "session_maker": session_maker,
            "job_id": "job-1",
            "episode_id": "ep-1",
            "step_delay_seconds": 0,
            "on_before_step": on_before_step,
        },
        daemon=True,
    )
    runner_thread.start()

    assert reached_pause.wait(timeout=SYNC_TIMEOUT_SECONDS), "ジョブが一時停止点へ到達しなかった"
    assert paused_at_step == "topic_selected"

    with session_maker() as session:
        request_cancel(session, "job-1")
    resume.set()

    runner_thread.join(timeout=SYNC_TIMEOUT_SECONDS)
    assert not runner_thread.is_alive(), "ジョブスレッドがキャンセル後も終了しなかった"

    with session_maker() as session:
        job = get_job(session, "job-1")
        episode = get_episode(session, "ep-1")

    assert job.status == "cancelled"
    # rights_passedへの1歩目は完了済みのまま保持され、topic_selectedへは進んでいない
    assert episode.state == "rights_passed"
