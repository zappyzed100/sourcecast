"""episode_deletion.py — エピソード削除操作（仕様書§10B「公開済みページの削除・URL変更を
原則禁止する」・development-plan.md Phase 11タスク3）。

fail closedの2条件（1つでも満たさなければ削除しない）:
- 理由が空でない（破壊的操作は理由入力を必須にする — 仕様書§12.4の方針を削除にも適用）
- エピソードが`published`状態でない（公開済みページは削除しない——取り下げたい場合は
  `episode_revocation.py`の「公開取消」を使う。こちらは行そのものを削除しない）
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from history_radio.store.episode_deletion import delete_episode
from history_radio.store.episodes import EpisodeNotFoundError, get_episode


class EpisodeDeletionError(RuntimeError):
    """削除操作の拒否（理由なし・公開済み等）。"""


def delete_episode_with_reason(session: Session, *, episode_id: str, reason: str | None) -> None:
    """エピソード1件を削除する。1件でも条件を満たさなければ拒否する。"""
    if not (reason and reason.strip()):
        raise EpisodeDeletionError(
            f"episode_id={episode_id!r}: 削除には理由の入力が必須"
            "（仕様書§12.4・development-plan.md Phase 11タスク3）"
        )

    episode = get_episode(session, episode_id)  # 無ければ EpisodeNotFoundError
    if episode.state == "published":
        raise EpisodeDeletionError(
            f"episode_id={episode_id!r}: 公開済みのエピソードは削除できない"
            "（仕様書§10B「公開済みページの削除・URL変更を原則禁止する」"
            "——取り下げたい場合は公開取消を使う）"
        )

    delete_episode(session, episode_id=episode_id, reason=reason.strip())


__all__ = ["EpisodeDeletionError", "EpisodeNotFoundError", "delete_episode_with_reason"]
