"""episode_publishing.py — 限定公開操作（仕様書§10D・§6.1・development-plan.md Phase 11タスク1）。

管理画面の「限定公開」ボタンが呼ぶ操作。`approved`状態のエピソードを`published`へ
進め、配信台帳（`distribution_ledger.dispatch`）へYouTube限定公開の試行を記録する
——YouTubeの「限定公開（unlisted）」が仕様書§10D「自動投稿開始前は非公開または
限定公開でアップロードする」に対応する公開区分そのものであり、
`distribution_metadata.YouTubeMetadata.privacy_status`の既定値も`unlisted`にしてある。

**ここでは配信ロジック・状態機械を再実装しない**——`domain/episode_state.py`の
`transition()`と`distribution_ledger.dispatch()`をそのまま呼ぶだけにする
（決定と実行の分離）。

**実際のYouTube Data APIへはまだ接続していない**——`publish_fn`は仮の識別子を
返すだけのプレースホルダー（HUMAN_TASKS.mdでYouTube連携の認証情報取得を
依頼するまでの暫定実装。実クライアント実装時にこの関数を差し替える）。
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from history_radio.domain.episode_state import InvalidTransitionError, transition
from history_radio.domain.models import Episode
from history_radio.publish.distribution_ledger import DistributionError, dispatch
from history_radio.store.distribution_records import DbDistributionLedger
from history_radio.store.episodes import get_episode, update_episode_state


class EpisodePublishError(RuntimeError):
    """限定公開操作の拒否（不正な状態遷移・配信失敗等）。"""


def _placeholder_publish_fn(episode_id: str) -> str:
    """実際のYouTube Data API等へまだ接続していないため、識別子だけを生成する
    プレースホルダー（HUMAN_TASKS.md参照。実クレデンシャル取得後に差し替える）。
    """
    return f"placeholder-youtube-{episode_id}"


def publish_episode_limited(session: Session, *, episode_id: str) -> Episode:
    """エピソードを限定公開する。approved状態でなければfail closedで拒否する。"""
    episode = get_episode(session, episode_id)

    try:
        transition(episode.state, "published")
    except InvalidTransitionError as exc:
        raise EpisodePublishError(
            f"episode_id={episode_id!r}: 限定公開できない（現在の状態={episode.state!r}、"
            "approvedでなければ公開操作を受け付けない）"
        ) from exc

    ledger = DbDistributionLedger(session)
    try:
        dispatch(
            ledger,
            episode_id=episode_id,
            episode_state=episode.state,
            target="youtube",
            attempted_at=datetime.now(timezone.utc).isoformat(),
            publish_fn=lambda: _placeholder_publish_fn(episode_id),
        )
    except DistributionError as exc:
        raise EpisodePublishError(str(exc)) from exc

    return update_episode_state(
        session,
        episode_id=episode_id,
        expected_revision=episode.revision,
        new_state="published",
    )
