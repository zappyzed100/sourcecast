"""test_main.py — 管理APIのfixtureエンドポイントとDB接続の候補審査エンドポイントを固定する"""

from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from history_radio.api.db import get_session
from history_radio.api.main import app
from history_radio.domain.models import Candidate
from history_radio.publish.publish_gate import GateCheckResult, PublishGateResult
from history_radio.store.candidates import save_candidate
from history_radio.store.db import create_sqlite_engine, session_factory
from history_radio.store.episodes import create_episode, update_episode_state
from history_radio.store.gate_results import save_gate_result
from history_radio.store.orm import Base


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Engine]:
    """テストは常にtmp_path配下のDBを使う——既定パス(data/history_radio.sqlite3)へは
    絶対に触れない(get_sessionをdependency_overridesで差し替える)。
    """
    eng = create_sqlite_engine(tmp_path / "test.db")
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def client(engine: Engine) -> Iterator[TestClient]:
    session_maker = session_factory(engine)

    def _override_get_session() -> Iterator[Any]:
        session = session_maker()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_session] = _override_get_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _get_json(client: TestClient, path: str) -> tuple[int, Any]:
    """TestClient.get()はhttpxの複雑なオーバーロードでstrict型検査と相性が悪いため、
    テスト側の型境界をこの関数1つに閉じ込める(basedpyright strictでの再検査コスト削減)。
    """
    response: Any = client.get(path)  # pyright: ignore[reportUnknownVariableType,reportUnknownMemberType]
    return cast(int, response.status_code), cast(
        Any,
        response.json(),  # pyright: ignore[reportUnknownMemberType]
    )


def _post_json(client: TestClient, path: str, json: dict[str, Any]) -> tuple[int, Any]:
    response: Any = client.post(path, json=json)  # pyright: ignore[reportUnknownVariableType,reportUnknownMemberType]
    return cast(int, response.status_code), cast(
        Any,
        response.json(),  # pyright: ignore[reportUnknownMemberType]
    )


def _seed_candidate(engine: Engine, candidate_id: str = "cand-001") -> None:
    session_maker = session_factory(engine)
    with session_maker() as session:
        save_candidate(
            session,
            Candidate(
                candidate_id=candidate_id,
                topic_title="缶切りより缶詰の方が50年も先に生まれていた",
                score=78.5,
                score_breakdown={"date_match": 0.2, "source_richness": 0.9},
                independent_source_families=2,
            ),
            created_at=datetime(2026, 7, 19, tzinfo=timezone.utc),
        )


def _seed_episode_ready_for_approval(
    engine: Engine, episode_id: str = "ep-001", *, gate_passed: bool = True
) -> None:
    session_maker = session_factory(engine)
    with session_maker() as session:
        create_episode(session, episode_id=episode_id, title="缶切りより缶詰")
        update_episode_state(
            session, episode_id=episode_id, expected_revision=1, new_state="publish_ready"
        )
        save_gate_result(
            session,
            PublishGateResult(
                episode_id=episode_id,
                revision=1,
                rule_version="2026-07-19.1",
                publish_ready=gate_passed,
                checks=(GateCheckResult(name="rights_and_episode_schema", passed=gate_passed),),
                artifact_hash="hash-x",
            ),
            result_id=f"gate-{episode_id}",
            evaluated_at=datetime(2026, 7, 19, tzinfo=timezone.utc),
        )


def _seed_approved_episode(engine: Engine, episode_id: str = "ep-001") -> None:
    _seed_episode_ready_for_approval(engine, episode_id, gate_passed=True)
    session_maker = session_factory(engine)
    with session_maker() as session:
        update_episode_state(
            session, episode_id=episode_id, expected_revision=2, new_state="approved"
        )


def test_dashboard_returns_summary(client: TestClient) -> None:
    status_code, body = _get_json(client, "/api/v1/dashboard")
    assert status_code == 200
    assert body["schema_version"] == 1
    assert body["jobs_running"] >= 0


def test_candidates_returns_empty_list_when_db_is_empty(client: TestClient) -> None:
    status_code, body = _get_json(client, "/api/v1/candidates")
    assert status_code == 200
    assert body == []


def test_candidates_returns_seeded_data(engine: Engine, client: TestClient) -> None:
    _seed_candidate(engine)
    status_code, body = _get_json(client, "/api/v1/candidates")
    assert status_code == 200
    assert len(cast(list[Any], body)) == 1
    assert body[0]["candidate_id"] == "cand-001"


def test_jobs_returns_list_with_failed_job_error_detail(client: TestClient) -> None:
    status_code, body = _get_json(client, "/api/v1/jobs")
    assert status_code == 200
    failed = [j for j in body if j["status"] == "failed"]
    assert len(failed) == 1
    assert failed[0]["error"]


def test_review_candidate_adopted_succeeds_without_reason(
    engine: Engine, client: TestClient
) -> None:
    _seed_candidate(engine)
    status_code, body = _post_json(
        client, "/api/v1/candidates/cand-001/review", {"decision": "adopted"}
    )
    assert status_code == 200
    assert body["decision"] == "adopted"
    assert body["candidate_id"] == "cand-001"


def test_review_candidate_excluded_without_reason_is_rejected(
    engine: Engine, client: TestClient
) -> None:
    """Phase 11タスク3 DoD: 理由なしの却下をAPIが拒否する。"""
    _seed_candidate(engine)
    status_code, body = _post_json(
        client, "/api/v1/candidates/cand-001/review", {"decision": "excluded"}
    )
    assert status_code == 400
    assert "理由" in body["detail"]


def test_review_candidate_excluded_with_reason_succeeds(engine: Engine, client: TestClient) -> None:
    _seed_candidate(engine)
    status_code, body = _post_json(
        client,
        "/api/v1/candidates/cand-001/review",
        {"decision": "excluded", "reason": "出典が信頼できない"},
    )
    assert status_code == 200
    assert body["decision"] == "excluded"
    assert body["reason"] == "出典が信頼できない"


def test_review_unknown_candidate_returns_404(client: TestClient) -> None:
    status_code, _body = _post_json(
        client, "/api/v1/candidates/does-not-exist/review", {"decision": "adopted"}
    )
    assert status_code == 404


def test_get_decisions_for_unknown_candidate_returns_404(client: TestClient) -> None:
    status_code, _body = _get_json(client, "/api/v1/candidates/does-not-exist/decisions")
    assert status_code == 404


def test_get_decisions_returns_review_history(engine: Engine, client: TestClient) -> None:
    _seed_candidate(engine)
    _post_json(client, "/api/v1/candidates/cand-001/review", {"decision": "adopted"})
    status_code, body = _get_json(client, "/api/v1/candidates/cand-001/decisions")
    assert status_code == 200
    assert len(body) == 1
    assert body[0]["decision"] == "adopted"


def test_episodes_returns_empty_list_when_db_is_empty(client: TestClient) -> None:
    status_code, body = _get_json(client, "/api/v1/episodes")
    assert status_code == 200
    assert body == []


def test_episodes_returns_seeded_data(engine: Engine, client: TestClient) -> None:
    _seed_episode_ready_for_approval(engine)
    status_code, body = _get_json(client, "/api/v1/episodes")
    assert status_code == 200
    assert len(body) == 1
    assert body[0]["episode_id"] == "ep-001"
    assert body[0]["state"] == "publish_ready"


def test_approve_episode_succeeds_when_gate_passed(engine: Engine, client: TestClient) -> None:
    _seed_episode_ready_for_approval(engine, gate_passed=True)
    status_code, body = _post_json(client, "/api/v1/episodes/ep-001/approve", {})
    assert status_code == 200
    assert body["state"] == "approved"


def test_approve_episode_rejected_when_gate_failed(engine: Engine, client: TestClient) -> None:
    _seed_episode_ready_for_approval(engine, gate_passed=False)
    status_code, body = _post_json(client, "/api/v1/episodes/ep-001/approve", {})
    assert status_code == 400
    assert "不合格" in body["detail"]


def test_approve_episode_rejected_when_not_publish_ready(
    engine: Engine, client: TestClient
) -> None:
    session_maker = session_factory(engine)
    with session_maker() as session:
        create_episode(session, episode_id="ep-002", title="準備中")
    status_code, body = _post_json(client, "/api/v1/episodes/ep-002/approve", {})
    assert status_code == 400
    assert "承認できない" in body["detail"]


def test_approve_unknown_episode_returns_404(client: TestClient) -> None:
    status_code, _body = _post_json(client, "/api/v1/episodes/does-not-exist/approve", {})
    assert status_code == 404


def test_publish_episode_succeeds_when_approved(engine: Engine, client: TestClient) -> None:
    _seed_approved_episode(engine)
    status_code, body = _post_json(client, "/api/v1/episodes/ep-001/publish", {})
    assert status_code == 200
    assert body["state"] == "published"


def test_publish_episode_rejected_when_not_approved(engine: Engine, client: TestClient) -> None:
    _seed_episode_ready_for_approval(engine, gate_passed=True)  # publish_readyのまま
    status_code, body = _post_json(client, "/api/v1/episodes/ep-001/publish", {})
    assert status_code == 400
    assert "限定公開できない" in body["detail"]


def test_publish_unknown_episode_returns_404(client: TestClient) -> None:
    status_code, _body = _post_json(client, "/api/v1/episodes/does-not-exist/publish", {})
    assert status_code == 404


def test_publish_episode_is_rejected_on_second_call(engine: Engine, client: TestClient) -> None:
    """development-plan.md Phase 9タスク4 DoD: 同じ配信先への二重投稿を防ぐ
    (publishedは終端状態のため再実行自体が拒否される)。"""
    _seed_approved_episode(engine)
    first_status, _first_body = _post_json(client, "/api/v1/episodes/ep-001/publish", {})
    assert first_status == 200

    second_status, second_body = _post_json(client, "/api/v1/episodes/ep-001/publish", {})
    assert second_status == 400
    assert "限定公開できない" in second_body["detail"]
