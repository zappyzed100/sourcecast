"""test_main.py — 管理APIのfixtureエンドポイントが仕様どおりの形で返ることを固定する"""

from typing import Any, cast

from fastapi.testclient import TestClient

from history_radio.api.main import app

client = TestClient(app)


def _get_json(path: str) -> tuple[int, Any]:
    """TestClient.get()はhttpxの複雑なオーバーロードでstrict型検査と相性が悪いため、
    テスト側の型境界をこの関数1つに閉じ込める(basedpyright strictでの再検査コスト削減)。
    """
    response: Any = client.get(path)  # pyright: ignore[reportUnknownVariableType,reportUnknownMemberType]
    return cast(int, response.status_code), cast(
        Any,
        response.json(),  # pyright: ignore[reportUnknownMemberType]
    )


def test_dashboard_returns_summary() -> None:
    status_code, body = _get_json("/api/v1/dashboard")
    assert status_code == 200
    assert body["schema_version"] == 1
    assert body["jobs_running"] >= 0


def test_candidates_returns_list() -> None:
    status_code, body = _get_json("/api/v1/candidates")
    assert status_code == 200
    assert isinstance(body, list)
    assert len(cast(list[Any], body)) >= 1
    assert "candidate_id" in body[0]


def test_jobs_returns_list_with_failed_job_error_detail() -> None:
    status_code, body = _get_json("/api/v1/jobs")
    assert status_code == 200
    failed = [j for j in body if j["status"] == "failed"]
    assert len(failed) == 1
    assert failed[0]["error"]
