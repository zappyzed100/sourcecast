"""test_cli.py — Phase 11タスク4 DoD: Reactを起動せず主要な復旧操作(状態確認・停止・
再開・バックアップ)ができることを固定する。

`history_radio.api.db`の遅延初期化グローバル（`_engine`/`_session_maker`）を
テストごとにリセットし、`HISTORY_RADIO_JOB_STEP_DELAY_SECONDS=0`で再実行を
高速化する（tests/api/test_main.pyのclient fixtureと同じ理由）。
"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from typer.testing import CliRunner

from history_radio.api import db as db_module
from history_radio.api.db import get_session_maker
from history_radio.cli import app
from history_radio.store.episodes import create_episode, get_episode
from history_radio.store.jobs import create_job, get_job, mark_failed, mark_running

runner = CliRunner()


@pytest.fixture
def isolated_db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    """CLIが使う遅延初期化DBをtmp_path配下の新しいファイルへ差し替える
    ——本番既定パス(data/history_radio.sqlite3)へは絶対に触れない。
    """
    monkeypatch.setenv("HISTORY_RADIO_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("HISTORY_RADIO_JOB_STEP_DELAY_SECONDS", "0")
    monkeypatch.setattr(db_module, "_engine", None)
    monkeypatch.setattr(db_module, "_session_maker", None)
    yield


def _seed_episode_and_job(*, job_id: str = "job-001", episode_id: str = "ep-001") -> None:
    session_maker = get_session_maker()
    with session_maker() as session:
        create_episode(session, episode_id=episode_id, title="復旧テスト用エピソード")
        create_job(session, job_id=job_id, episode_id=episode_id, kind="episode_generation")


def test_status_lists_jobs_and_episodes(isolated_db: None) -> None:
    del isolated_db
    _seed_episode_and_job()

    result = runner.invoke(app, ["status"])

    assert result.exit_code == 0
    assert "ジョブ: 1件" in result.output
    assert "job-001" in result.output
    assert "エピソード: 1件" in result.output
    assert "ep-001" in result.output


def test_status_with_no_data_shows_zero_counts(isolated_db: None) -> None:
    del isolated_db
    session_maker = get_session_maker()
    with session_maker():
        pass  # DBファイル・テーブルだけ作る(get_session_makerの遅延初期化で十分)

    result = runner.invoke(app, ["status"])

    assert result.exit_code == 0
    assert "ジョブ: 0件" in result.output
    assert "エピソード: 0件" in result.output


def test_stop_cancels_a_running_job(isolated_db: None) -> None:
    del isolated_db
    _seed_episode_and_job()
    session_maker = get_session_maker()
    with session_maker() as session:
        mark_running(session, "job-001")

    result = runner.invoke(app, ["stop", "job-001"])

    assert result.exit_code == 0
    assert "キャンセルを要求した: job-001" in result.output

    with session_maker() as session:
        assert get_job(session, "job-001").cancel_requested is True


def test_stop_unknown_job_exits_with_error(isolated_db: None) -> None:
    del isolated_db
    session_maker = get_session_maker()
    with session_maker():
        pass

    result = runner.invoke(app, ["stop", "does-not-exist"])

    assert result.exit_code == 1
    assert "エラー" in result.output


def test_resume_reexecutes_a_failed_job_to_completion(isolated_db: None) -> None:
    del isolated_db
    _seed_episode_and_job()
    session_maker = get_session_maker()
    with session_maker() as session:
        mark_failed(session, "job-001", error="VOICEVOXエンジンへの接続タイムアウト")

    result = runner.invoke(app, ["resume", "job-001"])

    assert result.exit_code == 0
    assert "再実行を開始した" in result.output
    assert "status=succeeded" in result.output

    with session_maker() as session:
        assert get_episode(session, "ep-001").state == "publish_ready"


def test_resume_rejects_a_non_terminal_job(isolated_db: None) -> None:
    del isolated_db
    _seed_episode_and_job()
    session_maker = get_session_maker()
    with session_maker() as session:
        mark_running(session, "job-001")

    result = runner.invoke(app, ["resume", "job-001"])

    assert result.exit_code == 1
    assert "終端の失敗状態のジョブのみ再実行できる" in result.output


def test_resume_unknown_job_exits_with_error(isolated_db: None) -> None:
    del isolated_db
    session_maker = get_session_maker()
    with session_maker():
        pass

    result = runner.invoke(app, ["resume", "does-not-exist"])

    assert result.exit_code == 1
    assert "エラー" in result.output


def test_backup_creates_a_snapshot_file(isolated_db: None, tmp_path: Path) -> None:
    del isolated_db
    _seed_episode_and_job()
    out_dir = tmp_path / "backups"

    result = runner.invoke(app, ["backup", "--out-dir", str(out_dir)])

    assert result.exit_code == 0
    snapshots = list(out_dir.glob("test-*.db"))
    assert len(snapshots) == 1
    assert str(snapshots[0]) in result.output


def test_backup_errors_when_db_file_does_not_exist(isolated_db: None, tmp_path: Path) -> None:
    del isolated_db
    # get_session_makerを一度も呼ばない = DBファイルがまだ作られていない状態を再現する。
    out_dir = tmp_path / "backups"

    result = runner.invoke(app, ["backup", "--out-dir", str(out_dir)])

    assert result.exit_code == 1
    assert "エラー" in result.output
