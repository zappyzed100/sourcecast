"""crawl_control.py — クロール制御（仕様書§7.3）: ドメイン別直列化・待機・リトライ・条件付きGET。

アダプターはHTTPを直接呼ばず、この `PoliteFetcher` を経由する——§7.3の規則
（ドメイン同時接続1・標準待機2秒以上・Retry-After遵守・UA明示・ハッシュによる
再取得抑制）をアダプターごとに再実装させない。

時刻と待機は `Clock` Protocolで注入する（テストでsleepしない — AGENTS.md §8
「テスト内のsleep禁止」。本番は `SystemClock`、テストは即時進行のフェイク）。
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from typing import Protocol

import httpx

USER_AGENT = "history-radio-bot (+https://github.com/zappyzed100/sourcecast)"
DEFAULT_MIN_WAIT_SECONDS = 2.0
DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_MAX_RETRIES = 3
# §7.3: 過大レスポンス拒否の上限（圧縮爆弾・巨大画像対策の一次防衛。個別ソースで
# 大きな資料が正当に必要になったら、そのアダプター単位で明示的に緩める）。
DEFAULT_MAX_RESPONSE_BYTES = 50 * 1024 * 1024


class Clock(Protocol):
    """現在時刻と待機の抽象。テストではsleepせず時間を進めるフェイクを注入する。"""

    def monotonic(self) -> float: ...

    def sleep(self, seconds: float) -> None: ...


class SystemClock:
    def monotonic(self) -> float:
        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


class FetchBlockedError(RuntimeError):
    """リトライ上限・過大レスポンス等で取得を安全に停止した（fail closed）。"""


@dataclass
class PoliteFetcher:
    """§7.3のクロール規則を一手に引き受けるHTTP取得口。

    - ドメインごとに直前アクセス時刻を記録し、`min_wait_seconds` 未満なら待つ
      （同期実装のためドメイン同時接続数は構造的に1）。
    - 429/503は `Retry-After` を遵守し、無ければ指数バックオフ（上限付き）。
    - 5xx・タイムアウト・途中切断も指数バックオフで再試行し、`max_retries` 回
      失敗したら `FetchBlockedError` で停止する（無限リトライしない）。
    - ETag/Last-Modifiedがあれば条件付きGET（If-None-Match / If-Modified-Since)を送る。
    - `Content-Length` が上限超過なら本文を読まずに拒否する（§7.3 過大レスポンス）。
    """

    client: httpx.Client
    clock: Clock = field(default_factory=SystemClock)
    min_wait_seconds: float = DEFAULT_MIN_WAIT_SECONDS
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    max_retries: int = DEFAULT_MAX_RETRIES
    max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES
    _last_access_by_domain: dict[str, float] = field(default_factory=dict)

    def get(
        self,
        url: str,
        *,
        etag: str | None = None,
        last_modified: str | None = None,
    ) -> httpx.Response:
        """§7.3の規則下でGETする。304 Not Modified はそのまま返す（呼び出し側で解釈）。"""
        headers = {"User-Agent": USER_AGENT}
        if etag is not None:
            headers["If-None-Match"] = etag
        if last_modified is not None:
            headers["If-Modified-Since"] = last_modified

        domain = httpx.URL(url).host
        attempt = 0
        while True:
            self._wait_for_domain(domain)
            try:
                response = self.client.get(url, headers=headers, timeout=self.timeout_seconds)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                attempt += 1
                if attempt > self.max_retries:
                    raise FetchBlockedError(
                        f"{url}: 通信失敗が{self.max_retries}回を超えたため停止: {exc}"
                    ) from exc
                self.clock.sleep(self._backoff_seconds(attempt))
                continue

            self._last_access_by_domain[domain] = self.clock.monotonic()

            if response.status_code in (429, 503):
                attempt += 1
                if attempt > self.max_retries:
                    raise FetchBlockedError(
                        f"{url}: {response.status_code} が{self.max_retries}回を超えたため停止"
                    )
                self.clock.sleep(self._retry_after_or_backoff(response, attempt))
                continue

            if 500 <= response.status_code <= 599:
                attempt += 1
                if attempt > self.max_retries:
                    raise FetchBlockedError(
                        f"{url}: {response.status_code} が{self.max_retries}回を超えたため停止"
                    )
                self.clock.sleep(self._backoff_seconds(attempt))
                continue

            self._reject_oversized(url, response)
            return response

    def _wait_for_domain(self, domain: str | None) -> None:
        if domain is None:
            return
        last = self._last_access_by_domain.get(domain)
        if last is None:
            return
        elapsed = self.clock.monotonic() - last
        remaining = self.min_wait_seconds - elapsed
        if remaining > 0:
            self.clock.sleep(remaining)

    def _backoff_seconds(self, attempt: int) -> float:
        # 2^attempt 秒＋ジッタ（同時リトライの雪崩防止）。上限60秒。
        base = min(2.0**attempt, 60.0)
        return base + random.uniform(0, 0.5)  # noqa: S311 — 暗号用途ではない

    def _retry_after_or_backoff(self, response: httpx.Response, attempt: int) -> float:
        retry_after = response.headers.get("Retry-After")
        if retry_after is not None:
            try:
                return max(float(retry_after), 0.0)
            except ValueError:
                pass  # HTTP-date形式等は指数バックオフへフォールバック
        return self._backoff_seconds(attempt)

    def _reject_oversized(self, url: str, response: httpx.Response) -> None:
        declared = response.headers.get("Content-Length")
        if declared is not None and declared.isdigit() and int(declared) > self.max_response_bytes:
            raise FetchBlockedError(
                f"{url}: Content-Length {declared} が上限 {self.max_response_bytes} を超過"
                "（§7.3 過大レスポンス拒否）"
            )
        if len(response.content) > self.max_response_bytes:
            raise FetchBlockedError(
                f"{url}: 実サイズ {len(response.content)} が上限 {self.max_response_bytes} を超過"
                "（§7.3 過大レスポンス拒否）"
            )
