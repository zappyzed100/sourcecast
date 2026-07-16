"""test_openrouter.py — Phase 6: 実callerの応答解釈・エラー時のキー非漏洩を固定する"""

import json

import pytest

from history_radio.llm.openrouter import OpenRouterCaller, OpenRouterError
from tests.ingest.mock_http import Reply, scripted_client

_OK_RESPONSE = json.dumps(
    {
        "choices": [{"message": {"content": '{"summary_ja": "要約"}'}}],
        "usage": {"prompt_tokens": 120, "completion_tokens": 45},
    }
)


def test_success_parses_content_and_usage() -> None:
    client, requests = scripted_client([Reply(text=_OK_RESPONSE)])
    caller = OpenRouterCaller(client=client, api_key="sk-test-XYZ")
    result = caller(model_id="vendor/model:free", prompt="要約して")
    assert result.output_text == '{"summary_ja": "要約"}'
    assert result.prompt_tokens == 120
    assert result.completion_tokens == 45
    assert requests[0].headers["authorization"] == "Bearer sk-test-XYZ"


def test_http_error_raises_without_leaking_key() -> None:
    client, _requests = scripted_client([Reply(status=429, text="rate limited")])
    caller = OpenRouterCaller(client=client, api_key="sk-secret-KEY")
    with pytest.raises(OpenRouterError) as exc_info:
        caller(model_id="vendor/model:free", prompt="x")
    assert "sk-secret-KEY" not in str(exc_info.value)
    assert "429" in str(exc_info.value)


def test_malformed_response_raises() -> None:
    client, _requests = scripted_client([Reply(text='{"unexpected": true}')])
    caller = OpenRouterCaller(client=client, api_key="sk-test")
    with pytest.raises(OpenRouterError, match="想定の形でない"):
        caller(model_id="vendor/model:free", prompt="x")


def test_from_env_requires_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    client, _requests = scripted_client([Reply()])
    with pytest.raises(OpenRouterError, match="OPENROUTER_API_KEY"):
        OpenRouterCaller.from_env(client)


def test_from_env_reads_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-from-env")
    client, _requests = scripted_client([Reply(text=_OK_RESPONSE)])
    caller = OpenRouterCaller.from_env(client)
    assert caller.api_key == "sk-from-env"


def test_request_disables_training_providers() -> None:
    """§8.1: 学習利用を許可するプロバイダーへのルーティングを無効化するボディを送る。"""
    captured: list[str] = []
    client, _requests = scripted_client([Reply(text=_OK_RESPONSE)])
    original_post = client.post

    def spying_post(*args: object, **kwargs: object) -> object:
        captured.append(json.dumps(kwargs.get("json"), ensure_ascii=False))
        return original_post(*args, **kwargs)  # type: ignore[arg-type]

    client.post = spying_post  # type: ignore[method-assign]
    OpenRouterCaller(client=client, api_key="sk-t")(model_id="vendor/m:free", prompt="x")
    body = json.loads(captured[0])
    assert body["provider"] == {"data_collection": "deny"}
    assert body["response_format"] == {"type": "json_object"}
