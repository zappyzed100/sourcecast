"""test_rights.py — Phase 3 DoD: rights_recordsの追記のみ・監査ログ同時記録を固定する"""

from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import Engine, select

from history_radio.domain.models import RightsDecision
from history_radio.store.db import create_sqlite_engine, session_factory
from history_radio.store.orm import AuditEventRow, Base
from history_radio.store.rights import (
    latest_rights_decision_for_document,
    list_rights_decisions_for_document,
    save_rights_decision,
)


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Engine]:
    eng = create_sqlite_engine(tmp_path / "test.db")
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


def _decision(
    *, decision_id: str, document_id: str, decision: str, rule_version: str, computed_at: datetime
) -> RightsDecision:
    return RightsDecision(
        decision_id=decision_id,
        document_id=document_id,
        decision=decision,  # type: ignore[arg-type]
        rule_version=rule_version,
        reasons=["テスト用の理由"],
        computed_at=computed_at,
    )


def test_re_judging_the_same_document_keeps_the_old_decision(engine: Engine) -> None:
    """Phase 3タスクd: 同じ資料を新ルールで再判定しても旧判定が消えない。"""
    session_maker = session_factory(engine)

    with session_maker() as session:
        save_rights_decision(
            session,
            _decision(
                decision_id="dec-1",
                document_id="doc-1",
                decision="manual_review",
                rule_version="5a-v1",
                computed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            ),
        )

    with session_maker() as session:
        save_rights_decision(
            session,
            _decision(
                decision_id="dec-2",
                document_id="doc-1",
                decision="allow_public_use",
                rule_version="5a-v2",
                computed_at=datetime(2026, 7, 16, tzinfo=timezone.utc),
            ),
        )

    with session_maker() as session:
        history = list_rights_decisions_for_document(session, "doc-1")

    assert [d.decision_id for d in history] == ["dec-1", "dec-2"]
    assert history[0].decision == "manual_review"
    assert history[1].decision == "allow_public_use"


def test_latest_decision_returns_the_most_recent_computation(engine: Engine) -> None:
    session_maker = session_factory(engine)

    with session_maker() as session:
        save_rights_decision(
            session,
            _decision(
                decision_id="dec-1",
                document_id="doc-2",
                decision="deny",
                rule_version="5a-v1",
                computed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            ),
        )
        save_rights_decision(
            session,
            _decision(
                decision_id="dec-2",
                document_id="doc-2",
                decision="allow_public_use",
                rule_version="5a-v1",
                computed_at=datetime(2026, 7, 16, tzinfo=timezone.utc),
            ),
        )

    with session_maker() as session:
        latest = latest_rights_decision_for_document(session, "doc-2")

    assert latest is not None
    assert latest.decision_id == "dec-2"


def test_no_decision_returns_none(engine: Engine) -> None:
    session_maker = session_factory(engine)
    with session_maker() as session:
        assert latest_rights_decision_for_document(session, "doc-missing") is None


def test_saving_a_decision_also_appends_an_audit_event(engine: Engine) -> None:
    """仕様書§15: 権利判定変更を追記型監査ログへ記録する。"""
    session_maker = session_factory(engine)

    with session_maker() as session:
        save_rights_decision(
            session,
            _decision(
                decision_id="dec-audit-1",
                document_id="doc-3",
                decision="allow_public_use",
                rule_version="5a-v1",
                computed_at=datetime(2026, 7, 16, tzinfo=timezone.utc),
            ),
        )

    with session_maker() as session:
        events = (
            session.execute(select(AuditEventRow).where(AuditEventRow.entity_id == "doc-3"))
            .scalars()
            .all()
        )

    assert len(events) == 1
    assert events[0].entity_type == "rights_decision"
    assert events[0].action == "rights_decision_computed"
