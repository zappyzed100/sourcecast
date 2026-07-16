"""test_cloudflare_pages.py — Phase 8タスク6 DoD: ロールバック手順が直前デプロイへ正しく戻る"""

import json
from typing import Any

import pytest

from history_radio.publish.cloudflare_pages import PagesClient, PagesRollbackError
from tests.ingest.mock_http import Disconnect, RecordedRequest, Reply, ScriptItem, scripted_client


def _deployment(id_: str, created_on: str, environment: str = "production") -> dict[str, Any]:
    return {
        "id": id_,
        "created_on": created_on,
        "environment": environment,
        "url": f"https://{id_}.example.pages.dev",
    }


def _list_reply(deployments: list[dict[str, Any]]) -> Reply:
    return Reply(status=200, text=json.dumps({"success": True, "result": deployments}))


def _pages_client(script: list[ScriptItem]) -> tuple[PagesClient, list[RecordedRequest]]:
    client, requests = scripted_client(script)
    return (
        PagesClient(
            client=client,
            account_id="0123456789abcdef0123456789abcdef",
            project_name="history-radio-site",
            api_token="test-token",
        ),
        requests,
    )


def test_list_deployments_filters_by_environment_and_sorts_newest_first() -> None:
    deployments = [
        _deployment("d1", "2026-07-10T00:00:00Z"),
        _deployment("d2", "2026-07-01T00:00:00Z", environment="preview"),
        _deployment("d3", "2026-07-15T00:00:00Z"),
    ]
    client, _requests = _pages_client([_list_reply(deployments)])
    result = client.list_deployments(environment="production")
    assert [d.id for d in result] == ["d3", "d1"]


def test_rollback_to_previous_calls_rollback_with_second_newest_deployment_id() -> None:
    """Phase 8タスク6 DoD: 直前版へロールバックする(1つ前=2番目に新しいデプロイ)。"""
    deployments = [
        _deployment("current", "2026-07-15T00:00:00Z"),
        _deployment("previous", "2026-07-10T00:00:00Z"),
        _deployment("older", "2026-07-01T00:00:00Z"),
    ]
    client, requests = _pages_client([_list_reply(deployments), Reply(status=200, text="{}")])
    result = client.rollback_to_previous()
    assert result.id == "previous"
    assert len(requests) == 2
    assert requests[1].url.endswith("/deployments/previous/rollback")


def test_rollback_with_no_previous_deployment_is_rejected() -> None:
    """ロールバック先が無い(デプロイ1件以下)場合はfail closedで拒否する。"""
    client, _requests = _pages_client([_list_reply([_deployment("only", "2026-07-15T00:00:00Z")])])
    with pytest.raises(PagesRollbackError, match="ロールバック先が無い"):
        client.rollback_to_previous()


def test_rollback_with_zero_deployments_is_rejected() -> None:
    client, _requests = _pages_client([_list_reply([])])
    with pytest.raises(PagesRollbackError, match="ロールバック先が無い"):
        client.rollback_to_previous()


def test_list_deployments_rejects_unsuccessful_response() -> None:
    client, _requests = _pages_client(
        [Reply(status=200, text=json.dumps({"success": False, "result": None}))]
    )
    with pytest.raises(PagesRollbackError, match="応答が不正"):
        client.list_deployments()


def test_list_deployments_rejects_missing_required_field() -> None:
    broken: list[dict[str, Any]] = [
        {"id": "d1", "created_on": "2026-07-10T00:00:00Z"}
    ]  # environment欠落
    client, _requests = _pages_client(
        [Reply(status=200, text=json.dumps({"success": True, "result": broken}))]
    )
    with pytest.raises(PagesRollbackError, match="必須フィールドが無い"):
        client.list_deployments()


def test_list_deployments_rejects_non_200_status() -> None:
    client, _requests = _pages_client([Reply(status=500)])
    with pytest.raises(PagesRollbackError, match="異常応答"):
        client.list_deployments()


def test_rollback_call_rejects_non_200_status() -> None:
    deployments = [
        _deployment("current", "2026-07-15T00:00:00Z"),
        _deployment("previous", "2026-07-10T00:00:00Z"),
    ]
    client, _requests = _pages_client(
        [_list_reply(deployments), Reply(status=403, text="forbidden")]
    )
    with pytest.raises(PagesRollbackError, match="異常応答"):
        client.rollback_to_previous()


def test_network_error_during_list_is_rejected() -> None:
    client, _requests = _pages_client([Disconnect()])
    with pytest.raises(PagesRollbackError, match="取得に失敗"):
        client.list_deployments()


def test_authorization_header_uses_bearer_token() -> None:
    client, requests = _pages_client([_list_reply([])])
    with pytest.raises(PagesRollbackError):
        client.rollback_to_previous()
    assert requests[0].headers.get("authorization") == "Bearer test-token"
