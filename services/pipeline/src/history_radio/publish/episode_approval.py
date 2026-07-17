"""episode_approval.py — 承認操作（仕様書§12.4・§6.1・development-plan.md Phase 11タスク1）。

管理画面の「承認」ボタンが呼ぶ操作。**ここでは検査を再実行しない**——Phase 10の
自動検査ゲート（`publish_gate.evaluate_publish_gate`）が既に評価し
`store/gate_results.py`へ保存済みの結果を参照するだけにする（決定と実行の分離。
ゲート評価自体は生成パイプライン側の責務）。

fail closedの3条件（1つでも満たさなければ承認しない）:
- エピソードの現在状態が`publish_ready`である
  （`domain/episode_state.py`の状態機械を再実装せず`transition()`を呼ぶ——
  段階飛ばし・逆行の防止は状態機械側の契約をそのまま使う）
- ゲート評価結果が存在する（直近の評価を見る——`Episode.revision`は
  `store/episodes.py`の楽観ロック用カウンタで状態遷移のたびに増えるため、
  `PublishGateResult.revision`〔公開コンテンツの版〕とは別物として扱う）
- その評価結果が`publish_ready=True`である
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from history_radio.domain.episode_state import InvalidTransitionError, transition
from history_radio.domain.models import Episode
from history_radio.publish.publish_gate import PublishGateResult
from history_radio.store.episodes import get_episode, update_episode_state
from history_radio.store.gate_results import latest_gate_result_for_episode


class EpisodeApprovalError(RuntimeError):
    """承認操作の拒否（ゲート未評価・不合格・不正な状態遷移等）。"""


def approve_episode(session: Session, *, episode_id: str) -> Episode:
    """エピソードを`approved`へ承認する。1件でも条件を満たさなければ拒否する。"""
    episode = get_episode(session, episode_id)

    try:
        transition(episode.state, "approved")
    except InvalidTransitionError as exc:
        raise EpisodeApprovalError(
            f"episode_id={episode_id!r}: 承認できない（現在の状態={episode.state!r}、"
            "publish_readyでなければ承認操作を受け付けない）"
        ) from exc

    gate_result: PublishGateResult | None = latest_gate_result_for_episode(session, episode_id)
    if gate_result is None:
        raise EpisodeApprovalError(
            f"episode_id={episode_id!r}: 自動検査ゲートの評価結果が無い（承認前にゲート評価が必要）"
        )
    if not gate_result.publish_ready:
        raise EpisodeApprovalError(
            f"episode_id={episode_id!r}: "
            f"自動検査ゲートが不合格（rule_version={gate_result.rule_version!r}）——"
            "承認できない"
        )

    return update_episode_state(
        session,
        episode_id=episode_id,
        expected_revision=episode.revision,
        new_state="approved",
    )
