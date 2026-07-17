"""test_distribution_ledger.py — Phase 9タスク3・4 DoD: approved未満は拒否・二重投稿を防ぐ"""

import pytest

from history_radio.domain.episode_state import ALL_STATES, EpisodeState
from history_radio.publish.distribution_ledger import (
    DistributionError,
    DistributionLedger,
    dispatch,
)

_NON_PUBLISHABLE_STATES = tuple(s for s in ALL_STATES if s not in {"approved", "published"})


@pytest.mark.parametrize("state", _NON_PUBLISHABLE_STATES)
def test_dispatch_rejects_states_before_approved(state: EpisodeState) -> None:
    """Phase 9タスク3 DoD: approved未満の状態から公開操作できない。"""
    ledger = DistributionLedger()
    calls: list[None] = []

    def publish_fn() -> str:
        calls.append(None)
        return "ext-1"

    with pytest.raises(DistributionError, match="approved 以降でのみ可能"):
        dispatch(
            ledger,
            episode_id="ep-1",
            episode_state=state,
            target="youtube",
            attempted_at="2026-07-19T00:00:00Z",
            publish_fn=publish_fn,
        )
    assert calls == []  # 配信呼び出し自体が行われていない


@pytest.mark.parametrize("state", ["approved", "published"])
def test_dispatch_succeeds_at_or_after_approved(state: EpisodeState) -> None:
    ledger = DistributionLedger()
    record = dispatch(
        ledger,
        episode_id="ep-1",
        episode_state=state,
        target="youtube",
        attempted_at="2026-07-19T00:00:00Z",
        publish_fn=lambda: "ext-1",
    )
    assert record.status == "success"
    assert record.external_id == "ext-1"


def test_dispatch_records_success_with_external_id() -> None:
    ledger = DistributionLedger()
    record = dispatch(
        ledger,
        episode_id="ep-1",
        episode_state="approved",
        target="podcast_rss",
        attempted_at="2026-07-19T00:00:00Z",
        publish_fn=lambda: "guid-abc",
    )
    assert record.episode_id == "ep-1"
    assert record.target == "podcast_rss"
    assert record.external_id == "guid-abc"
    assert ledger.has_succeeded("ep-1", "podcast_rss")


def test_dispatch_does_not_reinvoke_publish_fn_after_success() -> None:
    """Phase 9タスク4 DoD: タイムアウト後の再実行でも二重投稿しない。"""
    ledger = DistributionLedger()
    calls: list[None] = []

    def publish_fn() -> str:
        calls.append(None)
        return "ext-1"

    first = dispatch(
        ledger,
        episode_id="ep-1",
        episode_state="approved",
        target="youtube",
        attempted_at="2026-07-19T00:00:00Z",
        publish_fn=publish_fn,
    )
    # 呼び出し側がタイムアウト等で再実行したケースを模す
    second = dispatch(
        ledger,
        episode_id="ep-1",
        episode_state="approved",
        target="youtube",
        attempted_at="2026-07-19T00:05:00Z",
        publish_fn=publish_fn,
    )
    assert len(calls) == 1  # publish_fnは1回しか呼ばれていない(二重投稿していない)
    assert first == second
    assert second.external_id == "ext-1"


def test_dispatch_records_failure_and_raises() -> None:
    ledger = DistributionLedger()

    def failing_publish_fn() -> str:
        raise RuntimeError("接続タイムアウト")

    with pytest.raises(DistributionError, match="配信に失敗"):
        dispatch(
            ledger,
            episode_id="ep-1",
            episode_state="approved",
            target="amazon_music",
            attempted_at="2026-07-19T00:00:00Z",
            publish_fn=failing_publish_fn,
        )
    record = ledger.get("ep-1", "amazon_music")
    assert record is not None
    assert record.status == "failed"
    assert record.error_message is not None
    assert "接続タイムアウト" in record.error_message


def test_dispatch_retries_after_a_recorded_failure() -> None:
    """失敗は再送禁止の対象にしない——次のdispatchで再試行できる。"""
    ledger = DistributionLedger()
    calls = {"count": 0}

    def flaky_publish_fn() -> str:
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("一時的な障害")
        return "ext-recovered"

    with pytest.raises(DistributionError):
        dispatch(
            ledger,
            episode_id="ep-1",
            episode_state="approved",
            target="youtube",
            attempted_at="2026-07-19T00:00:00Z",
            publish_fn=flaky_publish_fn,
        )
    record = dispatch(
        ledger,
        episode_id="ep-1",
        episode_state="approved",
        target="youtube",
        attempted_at="2026-07-19T00:01:00Z",
        publish_fn=flaky_publish_fn,
    )
    assert calls["count"] == 2
    assert record.status == "success"
    assert record.external_id == "ext-recovered"


def test_different_targets_for_same_episode_are_independent() -> None:
    ledger = DistributionLedger()
    dispatch(
        ledger,
        episode_id="ep-1",
        episode_state="approved",
        target="youtube",
        attempted_at="2026-07-19T00:00:00Z",
        publish_fn=lambda: "yt-1",
    )
    assert ledger.has_succeeded("ep-1", "youtube")
    assert not ledger.has_succeeded("ep-1", "podcast_rss")
    assert not ledger.has_succeeded("ep-1", "amazon_music")


def test_different_episodes_for_same_target_are_independent() -> None:
    ledger = DistributionLedger()
    dispatch(
        ledger,
        episode_id="ep-1",
        episode_state="approved",
        target="youtube",
        attempted_at="2026-07-19T00:00:00Z",
        publish_fn=lambda: "yt-1",
    )
    assert ledger.has_succeeded("ep-1", "youtube")
    assert not ledger.has_succeeded("ep-2", "youtube")
