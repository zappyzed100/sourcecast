"""candidates.py — 候補（`topics`）の永続化（仕様書§13・§6A・Phase 11タスク1）。

候補は選出パイプライン（select/scoring.py等）が1回生成した時点の点数を記録する。
再生成（仕様書§12.3「採用／除外／再生成」の再生成）は新しいcandidate_idで別行を
作る想定のため、更新関数は持たない（挿入・参照のみ）。
"""

from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from history_radio.domain.models import Candidate
from history_radio.store.orm import CandidateRow


def _row_to_domain(row: CandidateRow) -> Candidate:
    return Candidate(
        candidate_id=row.candidate_id,
        topic_title=row.topic_title,
        score=row.score,
        score_breakdown=json.loads(row.score_breakdown_json),
        independent_source_families=row.independent_source_families,
    )


def save_candidate(session: Session, candidate: Candidate, *, created_at: datetime) -> Candidate:
    session.add(
        CandidateRow(
            candidate_id=candidate.candidate_id,
            topic_title=candidate.topic_title,
            score=candidate.score,
            score_breakdown_json=json.dumps(candidate.score_breakdown, ensure_ascii=False),
            independent_source_families=candidate.independent_source_families,
            created_at=created_at,
        )
    )
    session.commit()
    return candidate


def list_candidates(session: Session) -> list[Candidate]:
    """全候補を作成順（古い順）に返す。"""
    rows = session.execute(select(CandidateRow).order_by(CandidateRow.created_at)).scalars().all()
    return [_row_to_domain(row) for row in rows]


def get_candidate(session: Session, candidate_id: str) -> Candidate | None:
    row = session.get(CandidateRow, candidate_id)
    return _row_to_domain(row) if row is not None else None


__all__ = ["get_candidate", "list_candidates", "save_candidate"]
