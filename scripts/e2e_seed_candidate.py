"""e2e_seed_candidate.py — E2Eテスト専用シード: 候補を1件DBへ直接投入する。

実際の収集・選出パイプライン（Phase 4・Phase 5）が管理API・管理画面へまだ
接続されていないため、Phase 11タスク1のPlaywright E2E（候補→審査→承認→限定公開）
が候補一覧画面から操作を始められるよう、テスト実行前にこのスクリプトで候補を
直接投入する。本番コードから呼ばれることはない。
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

from history_radio.domain.models import Candidate
from history_radio.store.candidates import save_candidate
from history_radio.store.db import create_sqlite_engine, session_factory
from history_radio.store.orm import Base


def main() -> int:
    db_path = Path(sys.argv[1])
    candidate_id = sys.argv[2]
    topic_title = sys.argv[3] if len(sys.argv) > 3 else "E2Eテスト用の題材"

    db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_sqlite_engine(db_path)
    Base.metadata.create_all(engine)
    session_maker = session_factory(engine)
    with session_maker() as session:
        save_candidate(
            session,
            Candidate(
                candidate_id=candidate_id,
                topic_title=topic_title,
                score=80.0,
                score_breakdown={"e2e": 1.0},
                independent_source_families=2,
            ),
            created_at=datetime.now(timezone.utc),
        )
    print(f"[e2e-seed] candidate {candidate_id!r} seeded into {db_path}")  # noqa: T201
    return 0


if __name__ == "__main__":
    sys.exit(main())
