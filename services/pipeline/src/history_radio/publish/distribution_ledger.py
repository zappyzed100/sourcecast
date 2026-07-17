"""distribution_ledger.py — 外部配信の成功・失敗・外部IDの記録と二重投稿防止
（仕様書§10D・development-plan.md Phase 9タスク3・4）。

タスク3「公開ボタンはapproved以降だけ有効化する」: `dispatch()`が`episode_state`を
検査し、`approved`/`published`以外はfail closedで拒否する
（`domain/episode_state.py`の状態機械が既に「publish_readyの次にapprovedを経ないと
publishedへ進めない」を保証しているため、ここでは配信操作自体をapproved以降へ
ゲートするだけでよい——状態機械を再実装しない）。

タスク4「同じ配信先への二重投稿を防ぐ」: `DistributionLedger`が
`(episode_id, target)`単位で直近の記録を保持し、既に`success`が記録されている
組み合わせへは実際の配信呼び出し（`publish_fn`）を行わない。これが防ぐのは
「呼び出し側がタイムアウト等で再実行した場合に、こちらの記録に基づいて再送しない」
という範囲であり、「配信先サーバー側では実際に届いていたが呼び出し側だけタイムアウトした」
という真のat-least-once問題（配信先APIのidempotency key機能が必要）までは解決しない
——それは各配信先の実アップロードクライアント実装時（実クレデンシャル取得後）に
配信先固有の冪等キー機構と組み合わせて対処する。失敗（failed）は再試行可能のまま
残す（成功のみを再送禁止の対象にする）。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal

from history_radio.domain.base import SchemaModel
from history_radio.domain.episode_state import EpisodeState

DistributionTarget = Literal["youtube", "podcast_rss", "amazon_music"]

_PUBLISHABLE_STATES: frozenset[EpisodeState] = frozenset({"approved", "published"})


class DistributionError(RuntimeError):
    """配信操作の拒否・失敗。"""


class DistributionRecord(SchemaModel):
    episode_id: str
    target: DistributionTarget
    status: Literal["success", "failed"]
    external_id: str | None = None
    attempted_at: str
    error_message: str | None = None


class DistributionLedger:
    """`(episode_id, target)`単位で直近の配信結果を保持する（インメモリ）。

    永続化は呼び出し側の責務（store/層のD1/SQLite等）——ここでは記録の意味論
    （成功後は再送しない・失敗は再試行可能）だけを定義する。
    """

    def __init__(self) -> None:
        self._records: dict[tuple[str, DistributionTarget], DistributionRecord] = {}

    def get(self, episode_id: str, target: DistributionTarget) -> DistributionRecord | None:
        return self._records.get((episode_id, target))

    def has_succeeded(self, episode_id: str, target: DistributionTarget) -> bool:
        record = self.get(episode_id, target)
        return record is not None and record.status == "success"

    def record_success(
        self, episode_id: str, target: DistributionTarget, external_id: str, attempted_at: str
    ) -> DistributionRecord:
        record = DistributionRecord(
            episode_id=episode_id,
            target=target,
            status="success",
            external_id=external_id,
            attempted_at=attempted_at,
        )
        self._records[(episode_id, target)] = record
        return record

    def record_failure(
        self, episode_id: str, target: DistributionTarget, error_message: str, attempted_at: str
    ) -> DistributionRecord:
        record = DistributionRecord(
            episode_id=episode_id,
            target=target,
            status="failed",
            attempted_at=attempted_at,
            error_message=error_message,
        )
        self._records[(episode_id, target)] = record
        return record


def dispatch(
    ledger: DistributionLedger,
    *,
    episode_id: str,
    episode_state: EpisodeState,
    target: DistributionTarget,
    attempted_at: str,
    publish_fn: Callable[[], str],
) -> DistributionRecord:
    """1配信先への配信を1回試みる。

    - `episode_state`が`approved`/`published`以外ならfail closedで拒否する（タスク3）。
    - 既に`success`が記録済みなら`publish_fn`を呼ばずその記録をそのまま返す（タスク4・冪等）。
    - `publish_fn`が例外を送出したら`failed`として記録し`DistributionError`を送出する
      （失敗は記録に残るが再送を禁止しない——次回の`dispatch`呼び出しで再試行できる）。
    """
    if episode_state not in _PUBLISHABLE_STATES:
        raise DistributionError(
            f"公開操作は approved 以降でのみ可能（episode_id={episode_id!r}, "
            f"target={target!r}, 現在の状態={episode_state!r}）"
        )

    existing = ledger.get(episode_id, target)
    if existing is not None and existing.status == "success":
        return existing

    try:
        external_id = publish_fn()
    except Exception as exc:
        ledger.record_failure(episode_id, target, str(exc), attempted_at)
        raise DistributionError(
            f"{target}への配信に失敗（episode_id={episode_id!r}）: {exc}"
        ) from exc

    return ledger.record_success(episode_id, target, external_id, attempted_at)
