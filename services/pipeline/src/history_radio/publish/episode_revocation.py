"""episode_revocation.py — エピソード公開取消操作（development-plan.md Phase 11タスク3）。

fail closedの3条件（1つでも満たさなければ取消しない）:
- 理由が空でない
- エピソードが`published`状態である（公開していないものを取り消す操作は無意味）
- まだ取消済みでない（二重取消の防止——同じ理由を重ねて記録しても意味が無い）
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from history_radio.domain.models import AuditEvent
from history_radio.store.episode_revocations import is_publish_revoked, revoke_episode_publication
from history_radio.store.episodes import EpisodeNotFoundError, get_episode


class EpisodeRevocationError(RuntimeError):
    """公開取消操作の拒否（理由なし・未公開・取消済み等）。"""


def revoke_publication_with_reason(
    session: Session, *, episode_id: str, reason: str | None
) -> AuditEvent:
    """エピソード1件の公開を取り消す。1件でも条件を満たさなければ拒否する。"""
    if not (reason and reason.strip()):
        raise EpisodeRevocationError(
            f"episode_id={episode_id!r}: 公開取消には理由の入力が必須"
            "（仕様書§12.4・development-plan.md Phase 11タスク3）"
        )

    episode = get_episode(session, episode_id)  # 無ければ EpisodeNotFoundError
    if episode.state != "published":
        raise EpisodeRevocationError(
            f"episode_id={episode_id!r}: 公開済みでないエピソードは取消できない"
            f"（現在の状態={episode.state!r}）"
        )
    if is_publish_revoked(session, episode_id):
        raise EpisodeRevocationError(f"episode_id={episode_id!r}: 既に公開取消済み")

    return revoke_episode_publication(session, episode_id=episode_id, reason=reason.strip())


__all__ = ["EpisodeNotFoundError", "EpisodeRevocationError", "revoke_publication_with_reason"]
