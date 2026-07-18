"""main.py — localhost FastAPI（仕様書§12・plan.md §3.2）。

`127.0.0.1` のみにbind し外部公開しない(plan.md §1.3)。管理画面(apps/admin)からの
開発時クロスオリジン呼び出しのみCORSを許可する——本番はビルド済み管理画面を同一オリジンで
配信する構成を想定し、許可オリジンはlocalhost/127.0.0.1の開発用ポートに限定する。

候補一覧・審査、エピソード一覧・承認・限定公開（Phase 11タスク1）は実DB
（store/candidates.py・store/candidate_decisions.py・store/episodes.py・
publish/episode_approval.py・publish/episode_publishing.py・
store/distribution_records.py）へ接続済み。承認はPhase 10の自動検査ゲート結果
（store/gate_results.py）を参照するだけで、ここで検査を再実行しない。限定公開の
実際のYouTube Data APIへはまだ接続していない（HUMAN_TASKS.md参照——プレースホルダー
実装）。ダッシュボード・ジョブ一覧は引き続きfixture（実ジョブ接続はPhase 11タスク2）。
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from history_radio.api import fixtures
from history_radio.api.db import get_session
from history_radio.api.schemas import DashboardSummary, ReviewCandidateRequest
from history_radio.domain.models import Candidate, CandidateDecision, Episode, Job
from history_radio.publish.episode_approval import EpisodeApprovalError, approve_episode
from history_radio.publish.episode_publishing import EpisodePublishError, publish_episode_limited
from history_radio.select.candidate_review import CandidateReviewError, review_candidate
from history_radio.store.candidate_decisions import (
    list_decisions_for_candidate,
    save_candidate_decision,
)
from history_radio.store.candidates import get_candidate, list_candidates
from history_radio.store.episodes import (
    EpisodeNotFoundError,
    create_episode,
    get_episode,
    list_episodes,
)

app = FastAPI(title="history-radio admin API", version="1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/api/v1/dashboard", response_model=DashboardSummary)
def get_dashboard() -> DashboardSummary:
    return fixtures.dashboard_summary()


@app.get("/api/v1/candidates", response_model=list[Candidate])
def get_candidates(session: Session = Depends(get_session)) -> list[Candidate]:
    return list_candidates(session)


@app.get("/api/v1/candidates/{candidate_id}/decisions", response_model=list[CandidateDecision])
def get_candidate_decisions(
    candidate_id: str, session: Session = Depends(get_session)
) -> list[CandidateDecision]:
    if get_candidate(session, candidate_id) is None:
        raise HTTPException(status_code=404, detail=f"候補が見つからない: {candidate_id}")
    return list_decisions_for_candidate(session, candidate_id)


def _ensure_episode_for_adopted_candidate(session: Session, candidate: Candidate) -> None:
    """採用された候補にエピソードが無ければ作る（Phase 11タスク1「候補→審査→承認→
    限定公開」を1件のエピソードとして繋げるための連携）。

    `episode_id`には`candidate_id`をそのまま流用する——公開ページ用の
    `<公開日>-<英語スラグ>`形式（episode_page.pyの`_EPISODE_ID_PATTERN`）は
    実際の公開直前（Phase 8）で確定すればよく、管理画面の状態管理用`Episode.episode_id`
    （domain/models.pyの`Episode`）には形式の制約が無い——両者は別の識別子として
    扱ってよい（公開用IDへの変換は将来、実際に公開する段になってから行う）。
    再審査（採用のあとの再度の採用操作）で重複作成しないよう、既存チェックを行う。
    """
    try:
        get_episode(session, candidate.candidate_id)
    except EpisodeNotFoundError:
        create_episode(session, episode_id=candidate.candidate_id, title=candidate.topic_title)


@app.post("/api/v1/candidates/{candidate_id}/review", response_model=CandidateDecision)
def review_candidate_endpoint(
    candidate_id: str,
    body: ReviewCandidateRequest,
    session: Session = Depends(get_session),
) -> CandidateDecision:
    candidate = get_candidate(session, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail=f"候補が見つからない: {candidate_id}")
    try:
        decision = review_candidate(
            decision_id=f"decision-{candidate_id}-{uuid4().hex[:8]}",
            candidate_id=candidate_id,
            decision=body.decision,
            reason=body.reason,
            decided_at=datetime.now(timezone.utc),
        )
    except CandidateReviewError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    saved = save_candidate_decision(session, decision)
    if saved.decision == "adopted":
        _ensure_episode_for_adopted_candidate(session, candidate)
    return saved


@app.get("/api/v1/episodes", response_model=list[Episode])
def get_episodes(session: Session = Depends(get_session)) -> list[Episode]:
    return list_episodes(session)


@app.post("/api/v1/episodes/{episode_id}/approve", response_model=Episode)
def approve_episode_endpoint(episode_id: str, session: Session = Depends(get_session)) -> Episode:
    try:
        return approve_episode(session, episode_id=episode_id)
    except EpisodeNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except EpisodeApprovalError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/v1/episodes/{episode_id}/publish", response_model=Episode)
def publish_episode_endpoint(episode_id: str, session: Session = Depends(get_session)) -> Episode:
    try:
        return publish_episode_limited(session, episode_id=episode_id)
    except EpisodeNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except EpisodePublishError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/v1/jobs", response_model=list[Job])
def get_jobs() -> list[Job]:
    return fixtures.jobs()
