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
実装）。エピソード生成ジョブ（Phase 11タスク2）は実DB（store/jobs.py）へ接続済み——
実行はバックグラウンドスレッド（jobs/runner.py）で行い、状態・進捗・ログはDBへ都度
反映する（ブラウザ再読込後もDBの現在値を読むだけで正しい状態へ復帰する）。
エピソードの削除・公開取消（Phase 11タスク3「破壊的操作は確認、理由入力、監査ログを
必須にする」）はどちらも理由必須でfail closed——削除は公開済みでないエピソードの行を
実際に削除し（publish/episode_deletion.py）、公開取消はpublished状態のエピソードの
行・状態は変えず監査ログへ取消の事実だけを記録する（publish/episode_revocation.py・
仕様書§10B「公開済みページの削除・URL変更を原則禁止する」）。
ダッシュボードは引き続きfixture。
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, sessionmaker

from history_radio.api import fixtures
from history_radio.api.db import get_session, get_session_maker
from history_radio.api.schemas import (
    DashboardSummary,
    DeleteEpisodeRequest,
    ReviewCandidateRequest,
    RevokeEpisodePublicationRequest,
)
from history_radio.domain.episode_state import FAILURE_STATES
from history_radio.domain.models import (
    AuditEvent,
    Candidate,
    CandidateDecision,
    Episode,
    Job,
    JobLogEntry,
)
from history_radio.jobs.events import stream_job_events
from history_radio.jobs.runner import run_episode_generation_job
from history_radio.publish.episode_approval import EpisodeApprovalError, approve_episode
from history_radio.publish.episode_deletion import (
    EpisodeDeletionError,
    delete_episode_with_reason,
)
from history_radio.publish.episode_publishing import EpisodePublishError, publish_episode_limited
from history_radio.publish.episode_revocation import (
    EpisodeRevocationError,
    revoke_publication_with_reason,
)
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
from history_radio.store.jobs import (
    JobAlreadyTerminalError,
    JobNotFoundError,
    create_job,
    get_job,
    list_job_logs,
    list_jobs,
    request_cancel,
)

app = FastAPI(title="history-radio admin API", version="1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        # E2E専用ポート(playwright.config.ts) — 既定の5173は開発機で別プロジェクトの
        # devサーバーと衝突し得るため、Playwrightは--strictPortで専用ポートに固定する。
        "http://localhost:5183",
        "http://127.0.0.1:5183",
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


@app.post("/api/v1/episodes/{episode_id}/delete", status_code=204)
def delete_episode_endpoint(
    episode_id: str, body: DeleteEpisodeRequest, session: Session = Depends(get_session)
) -> None:
    try:
        delete_episode_with_reason(session, episode_id=episode_id, reason=body.reason)
    except EpisodeNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except EpisodeDeletionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/v1/episodes/{episode_id}/revoke", response_model=AuditEvent)
def revoke_episode_publication_endpoint(
    episode_id: str,
    body: RevokeEpisodePublicationRequest,
    session: Session = Depends(get_session),
) -> AuditEvent:
    try:
        return revoke_publication_with_reason(session, episode_id=episode_id, reason=body.reason)
    except EpisodeNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except EpisodeRevocationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/v1/episodes/{episode_id}/generate", response_model=Job, status_code=202)
def start_episode_generation_endpoint(
    episode_id: str,
    session: Session = Depends(get_session),
    session_maker: sessionmaker[Session] = Depends(get_session_maker),
) -> Job:
    try:
        episode = get_episode(session, episode_id)
    except EpisodeNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if episode.state in FAILURE_STATES:
        raise HTTPException(
            status_code=400,
            detail=f"エピソードは終端の失敗状態（{episode.state}）にあるため生成を開始できない",
        )
    job = create_job(
        session,
        job_id=f"job-{episode_id}-{uuid4().hex[:8]}",
        episode_id=episode_id,
        kind="episode_generation",
    )
    threading.Thread(
        target=run_episode_generation_job,
        kwargs={
            "session_maker": session_maker,
            "job_id": job.job_id,
            "episode_id": episode_id,
        },
        daemon=True,
    ).start()
    return job


@app.get("/api/v1/jobs", response_model=list[Job])
def get_jobs(session: Session = Depends(get_session)) -> list[Job]:
    return list_jobs(session)


@app.get("/api/v1/jobs/{job_id}", response_model=Job)
def get_job_endpoint(job_id: str, session: Session = Depends(get_session)) -> Job:
    try:
        return get_job(session, job_id)
    except JobNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/v1/jobs/{job_id}/logs", response_model=list[JobLogEntry])
def get_job_logs_endpoint(
    job_id: str, session: Session = Depends(get_session)
) -> list[JobLogEntry]:
    try:
        get_job(session, job_id)
    except JobNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return list_job_logs(session, job_id)


@app.get("/api/v1/jobs/{job_id}/events")
def job_events_endpoint(
    request: Request,
    job_id: str,
    session: Session = Depends(get_session),
    session_maker: sessionmaker[Session] = Depends(get_session_maker),
) -> StreamingResponse:
    try:
        get_job(session, job_id)
    except JobNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return StreamingResponse(
        stream_job_events(session_maker, job_id, is_disconnected=request.is_disconnected),
        media_type="text/event-stream",
    )


@app.post("/api/v1/jobs/{job_id}/cancel", response_model=Job)
def cancel_job_endpoint(job_id: str, session: Session = Depends(get_session)) -> Job:
    try:
        return request_cancel(session, job_id)
    except JobNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except JobAlreadyTerminalError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/v1/jobs/{job_id}/retry", response_model=Job, status_code=202)
def retry_job_endpoint(
    job_id: str,
    session: Session = Depends(get_session),
    session_maker: sessionmaker[Session] = Depends(get_session_maker),
) -> Job:
    try:
        original = get_job(session, job_id)
    except JobNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if original.status not in ("failed", "blocked", "cancelled"):
        raise HTTPException(
            status_code=400,
            detail=f"終端の失敗状態のジョブのみ再実行できる（現在: {original.status}）",
        )
    if original.episode_id is None:
        raise HTTPException(status_code=400, detail="episode_idの無いジョブは再実行できない")
    new_job = create_job(
        session,
        job_id=f"job-{original.episode_id}-{uuid4().hex[:8]}",
        episode_id=original.episode_id,
        kind=original.kind,
        retry_of=original.job_id,
    )
    threading.Thread(
        target=run_episode_generation_job,
        kwargs={
            "session_maker": session_maker,
            "job_id": new_job.job_id,
            "episode_id": original.episode_id,
        },
        daemon=True,
    ).start()
    return new_job
