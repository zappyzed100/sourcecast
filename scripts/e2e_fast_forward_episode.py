"""e2e_fast_forward_episode.py — E2Eテスト専用シード: エピソードをpublish_ready状態まで
一気に進め、合格する自動検査ゲート評価結果を記録する。

実際の生成パイプライン（Phase 6〜8: LLM台本生成・VOICEVOX音声合成・スライド動画生成・
Phase 10の自動検査ゲート実行）が管理API・管理画面へまだ接続されていないため、
Phase 11タスク1のPlaywright E2E（候補→審査→承認→限定公開）で候補採用後の
エピソードを承認画面まで進められるよう、テスト実行中にこのスクリプトで
状態遷移とゲート結果を直接投入する。本番コードから呼ばれることはない
——ここで飛ばしている段階を実際に自動化するのはPhase 11タスク2（実ジョブ接続）
以降の仕事。
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

from history_radio.publish.publish_gate import GateCheckResult, PublishGateResult
from history_radio.store.db import create_sqlite_engine, session_factory
from history_radio.store.episodes import get_episode, update_episode_state
from history_radio.store.gate_results import save_gate_result
from history_radio.store.orm import Base

_REMAINING_STATES = (
    "rights_passed",
    "topic_selected",
    "facts_verified",
    "script_generated",
    "script_verified",
    "media_generated",
    "publish_ready",
)


def main() -> int:
    db_path = Path(sys.argv[1])
    episode_id = sys.argv[2]

    engine = create_sqlite_engine(db_path)
    Base.metadata.create_all(engine)
    session_maker = session_factory(engine)

    with session_maker() as session:
        revision = get_episode(session, episode_id).revision
        for state in _REMAINING_STATES:
            update_episode_state(
                session, episode_id=episode_id, expected_revision=revision, new_state=state
            )
            revision += 1

        save_gate_result(
            session,
            PublishGateResult(
                episode_id=episode_id,
                revision=1,
                rule_version="e2e-seed",
                publish_ready=True,
                checks=(GateCheckResult(name="rights_and_episode_schema", passed=True),),
                artifact_hash="e2e-seed-hash",
            ),
            result_id=f"gate-{episode_id}-e2e",
            evaluated_at=datetime.now(timezone.utc),
        )

    print(  # noqa: T201
        f"[e2e-seed] episode {episode_id!r} fast-forwarded to publish_ready with passing gate"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
