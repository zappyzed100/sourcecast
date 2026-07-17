"""test_distribution_records.py — Phase 11タスク1 DoD(限定公開): DB永続化されたledgerが
プロセスをまたいでも二重投稿を防ぐことを固定する
"""

import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine, select

from history_radio.publish.distribution_ledger import (
    DistributionError,
    DistributionRecord,
    dispatch,
)
from history_radio.store.db import create_sqlite_engine, session_factory
from history_radio.store.distribution_records import (
    DbDistributionLedger,
    get_distribution_record,
    save_distribution_record,
)
from history_radio.store.orm import AuditEventRow, Base


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Engine]:
    eng = create_sqlite_engine(tmp_path / "test.db")
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


def test_saved_record_can_be_retrieved(engine: Engine) -> None:
    session_maker = session_factory(engine)
    with session_maker() as session:
        save_distribution_record(
            session,
            DistributionRecord(
                episode_id="ep-1",
                target="podcast_rss",
                status="success",
                external_id="guid-abc",
                attempted_at="2026-07-19T00:00:00Z",
            ),
        )

    with session_maker() as session:
        record = get_distribution_record(session, "ep-1", "podcast_rss")

    assert record is not None
    assert record.status == "success"
    assert record.external_id == "guid-abc"


def test_missing_record_returns_none(engine: Engine) -> None:
    session_maker = session_factory(engine)
    with session_maker() as session:
        assert get_distribution_record(session, "ep-missing", "podcast_rss") is None


def test_saving_again_overwrites_the_previous_record(engine: Engine) -> None:
    """DistributionLedgerと同じ意味論: 直近の状態だけを保持する。"""
    session_maker = session_factory(engine)
    with session_maker() as session:
        save_distribution_record(
            session,
            DistributionRecord(
                episode_id="ep-2",
                target="youtube",
                status="failed",
                attempted_at="2026-07-19T00:00:00Z",
                error_message="一時的な障害",
            ),
        )
    with session_maker() as session:
        save_distribution_record(
            session,
            DistributionRecord(
                episode_id="ep-2",
                target="youtube",
                status="success",
                external_id="yt-123",
                attempted_at="2026-07-19T00:05:00Z",
            ),
        )

    with session_maker() as session:
        record = get_distribution_record(session, "ep-2", "youtube")

    assert record is not None
    assert record.status == "success"
    assert record.external_id == "yt-123"


def test_saving_a_record_appends_an_audit_event(engine: Engine) -> None:
    """仕様書§15: 配信結果を追記型監査ログへ記録する。"""
    session_maker = session_factory(engine)
    with session_maker() as session:
        save_distribution_record(
            session,
            DistributionRecord(
                episode_id="ep-3",
                target="amazon_music",
                status="success",
                external_id="az-1",
                attempted_at="2026-07-19T00:00:00Z",
            ),
        )

    with session_maker() as session:
        events = (
            session.execute(select(AuditEventRow).where(AuditEventRow.entity_id == "ep-3"))
            .scalars()
            .all()
        )

    assert len(events) == 1
    assert events[0].entity_type == "distribution_record"
    assert events[0].action == "distribution_success"


def test_db_backed_ledger_survives_a_fresh_instance() -> None:
    """DbDistributionLedgerを新規作成しても(=プロセス再起動を模す)、DB上の記録から
    二重投稿を防げる。"""
    with tempfile.TemporaryDirectory() as tmp:
        engine = create_sqlite_engine(Path(tmp) / "test.db")
        Base.metadata.create_all(engine)
        session_maker = session_factory(engine)
        calls = {"count": 0}

        def publish_fn() -> str:
            calls["count"] += 1
            return "ext-1"

        with session_maker() as session:
            first_ledger = DbDistributionLedger(session)
            dispatch(
                first_ledger,
                episode_id="ep-4",
                episode_state="approved",
                target="podcast_rss",
                attempted_at="2026-07-19T00:00:00Z",
                publish_fn=publish_fn,
            )

        # 新しいledgerインスタンス(=新しいプロセスを模す)でも既存の成功記録を見る
        with session_maker() as session:
            second_ledger = DbDistributionLedger(session)
            result = dispatch(
                second_ledger,
                episode_id="ep-4",
                episode_state="approved",
                target="podcast_rss",
                attempted_at="2026-07-19T00:05:00Z",
                publish_fn=publish_fn,
            )

        assert calls["count"] == 1  # publish_fnは1回しか呼ばれていない
        assert result.external_id == "ext-1"
        engine.dispose()


def test_db_backed_ledger_rejects_states_before_approved(engine: Engine) -> None:
    session_maker = session_factory(engine)
    with session_maker() as session:
        ledger = DbDistributionLedger(session)
        with pytest.raises(DistributionError, match="approved 以降でのみ可能"):
            dispatch(
                ledger,
                episode_id="ep-5",
                episode_state="collected",
                target="podcast_rss",
                attempted_at="2026-07-19T00:00:00Z",
                publish_fn=lambda: "ext-1",
            )
