"""test_crawl_control.py — Phase 4 DoD: 429/5xx/タイムアウト/切断の注入と安全停止を固定する"""

import pytest

from history_radio.ingest.crawl_control import USER_AGENT, FetchBlockedError
from tests.ingest.mock_http import Disconnect, Reply, Timeout, scripted_fetcher


def test_success_returns_response_and_sends_user_agent() -> None:
    fetcher, _clock, requests = scripted_fetcher([Reply(status=200, text="ok")])
    response = fetcher.get("https://example.org/page")
    assert response.status_code == 200
    assert requests[0].headers["user-agent"] == USER_AGENT


def test_conditional_get_sends_etag_and_last_modified() -> None:
    fetcher, _clock, requests = scripted_fetcher([Reply(status=304)])
    response = fetcher.get(
        "https://example.org/page",
        etag='W/"abc"',
        last_modified="Wed, 15 Jul 2026 00:00:00 GMT",
    )
    assert response.status_code == 304
    assert requests[0].headers["if-none-match"] == 'W/"abc"'
    assert requests[0].headers["if-modified-since"] == "Wed, 15 Jul 2026 00:00:00 GMT"


def test_same_domain_requests_wait_at_least_min_interval() -> None:
    fetcher, clock, _requests = scripted_fetcher([Reply()], min_wait_seconds=2.0)
    fetcher.get("https://example.org/a")
    fetcher.get("https://example.org/b")
    assert clock.sleeps, "同一ドメイン連続アクセスで待機が発生していない"
    assert clock.sleeps[0] == pytest.approx(2.0)


def test_429_respects_retry_after_then_succeeds() -> None:
    fetcher, clock, _requests = scripted_fetcher(
        [Reply(status=429, headers={"Retry-After": "7"}), Reply(status=200, text="ok")]
    )
    response = fetcher.get("https://example.org/limited")
    assert response.status_code == 200
    assert 7.0 in clock.sleeps


def test_429_over_retry_limit_stops_safely() -> None:
    fetcher, _clock, _requests = scripted_fetcher(
        [Reply(status=429, headers={"Retry-After": "1"})], max_retries=2
    )
    with pytest.raises(FetchBlockedError, match="429"):
        fetcher.get("https://example.org/limited")


def test_5xx_over_retry_limit_stops_safely() -> None:
    fetcher, _clock, _requests = scripted_fetcher([Reply(status=502)], max_retries=2)
    with pytest.raises(FetchBlockedError, match="502"):
        fetcher.get("https://example.org/flaky")


def test_timeout_over_retry_limit_stops_safely() -> None:
    fetcher, _clock, _requests = scripted_fetcher([Timeout()], max_retries=2)
    with pytest.raises(FetchBlockedError, match="通信失敗"):
        fetcher.get("https://example.org/slow")


def test_mid_transfer_disconnect_over_retry_limit_stops_safely() -> None:
    fetcher, _clock, _requests = scripted_fetcher([Disconnect()], max_retries=2)
    with pytest.raises(FetchBlockedError, match="通信失敗"):
        fetcher.get("https://example.org/drop")


def test_transient_5xx_then_success_retries_with_backoff() -> None:
    fetcher, clock, _requests = scripted_fetcher(
        [Reply(status=503), Reply(status=503), Reply(status=200, text="recovered")],
        max_retries=3,
    )
    response = fetcher.get("https://example.org/recovering")
    assert response.status_code == 200
    assert len(clock.sleeps) >= 2
    # 指数バックオフ: 2回目の待機は1回目より長い（ジッタ込みでも 2^1 < 2^2 の差は保たれる）
    assert clock.sleeps[1] > clock.sleeps[0]


def test_oversized_content_length_is_rejected_without_reading_body() -> None:
    fetcher, _clock, _requests = scripted_fetcher(
        [Reply(content_length_override="999999999")], max_response_bytes=1024
    )
    with pytest.raises(FetchBlockedError, match="Content-Length"):
        fetcher.get("https://example.org/bomb")


def test_oversized_actual_body_is_rejected() -> None:
    """Content-Lengthを過少に偽装した過大レスポンス（§7.3）も実サイズ検査で拒否する。"""
    fetcher, _clock, _requests = scripted_fetcher(
        [Reply(text="x" * 2048, content_length_override="10")], max_response_bytes=1024
    )
    with pytest.raises(FetchBlockedError, match="実サイズ"):
        fetcher.get("https://example.org/big")
