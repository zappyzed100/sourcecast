"""fixtures.py — Phase 2時点のダミーデータ（実データ接続は候補選出・ジョブ実行の各フェーズで行う）。

plan.md Phase 2「`apps/admin` とlocalhost FastAPIをfixtureで接続する」に対応する暫定実装。
"""

from __future__ import annotations

from history_radio.api.schemas import DashboardSummary
from history_radio.domain.models import Candidate


def dashboard_summary() -> DashboardSummary:
    return DashboardSummary(
        jobs_running=1,
        jobs_queued=2,
        jobs_failed_today=0,
        episodes_published_this_month=3,
        openrouter_calls_today=14,
        candidates_awaiting_review=2,
    )


def candidates() -> list[Candidate]:
    return [
        Candidate(
            candidate_id="cand-001",
            topic_title="缶切りより缶詰の方が50年も先に生まれていた",
            score=78.5,
            score_breakdown={"date_match": 0.2, "source_richness": 0.9},
            independent_source_families=2,
        ),
        Candidate(
            candidate_id="cand-002",
            topic_title="日本初の鉄道が新橋─横浜間で開業した日",
            score=65.0,
            score_breakdown={"date_match": 0.8, "source_richness": 0.6},
            independent_source_families=2,
        ),
    ]
