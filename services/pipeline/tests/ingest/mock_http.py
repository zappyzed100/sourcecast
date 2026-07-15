"""mock_http.py — ingestテスト用のHTTPフェイク組み立て（実ネットワークなし）。

test-network検査（§9.5）が要求する「フェイクの注入」の実装本体。httpx.MockTransport
への参照をこのヘルパーに集約し、各テストファイルは応答台本（Reply/Timeout/Disconnect
の列）だけを書く——アダプターのfixtureテストでも同じ組み立てを再利用する。
"""

from __future__ import annotations

from dataclasses import dataclass, field

import httpx

from history_radio.ingest.crawl_control import PoliteFetcher


@dataclass(frozen=True, slots=True)
class Reply:
    """1回分のHTTP応答の台本。"""

    status: int = 200
    text: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    # Content-Length申告を実サイズと食い違わせたい場合に指定（過大レスポンス偽装の再現用）
    content_length_override: str | None = None


class Timeout:
    """接続タイムアウトを注入する台本要素。"""


class Disconnect:
    """転送途中の切断（connection reset）を注入する台本要素。"""


ScriptItem = Reply | Timeout | Disconnect


@dataclass(frozen=True, slots=True)
class RecordedRequest:
    """フェイクが受け取ったリクエストの記録（テストの検証用）。"""

    url: str
    headers: dict[str, str]


class FakeClock:
    """sleepせず時間だけを進めるClock（AGENTS.md §8: テスト内sleep禁止）。"""

    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def scripted_fetcher(
    script: list[ScriptItem],
    **fetcher_overrides: float | int,
) -> tuple[PoliteFetcher, FakeClock, list[RecordedRequest]]:
    """応答台本どおりに振る舞うPoliteFetcherを組み立てる。

    台本を使い切ったら最後の要素を繰り返す（無限429等の「上限まで失敗し続ける」
    シナリオを台本の長さと切り離すため)。
    """
    requests: list[RecordedRequest] = []
    position = {"index": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(
            RecordedRequest(url=str(request.url), headers=dict(request.headers.items()))
        )
        item = script[min(position["index"], len(script) - 1)]
        position["index"] += 1
        if isinstance(item, Timeout):
            raise httpx.ConnectTimeout("timed out")
        if isinstance(item, Disconnect):
            raise httpx.ReadError("connection reset")
        response = httpx.Response(item.status, text=item.text, headers=item.headers)
        if item.content_length_override is not None:
            response.headers["Content-Length"] = item.content_length_override
        return response

    clock = FakeClock()
    client = httpx.Client(transport=httpx.MockTransport(handler))
    fetcher = PoliteFetcher(client=client, clock=clock, **fetcher_overrides)  # type: ignore[arg-type]
    return fetcher, clock, requests
