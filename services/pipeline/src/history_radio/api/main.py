"""main.py — localhost FastAPI（仕様書§12・plan.md §3.2）。

`127.0.0.1` のみにbind し外部公開しない(plan.md §1.3)。管理画面(apps/admin)からの
開発時クロスオリジン呼び出しのみCORSを許可する——本番はビルド済み管理画面を同一オリジンで
配信する構成を想定し、許可オリジンはlocalhost/127.0.0.1の開発用ポートに限定する。
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from history_radio.api import fixtures
from history_radio.api.schemas import DashboardSummary
from history_radio.domain.models import Candidate, Job

app = FastAPI(title="history-radio admin API", version="1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/api/v1/dashboard", response_model=DashboardSummary)
def get_dashboard() -> DashboardSummary:
    return fixtures.dashboard_summary()


@app.get("/api/v1/candidates", response_model=list[Candidate])
def get_candidates() -> list[Candidate]:
    return fixtures.candidates()


@app.get("/api/v1/jobs", response_model=list[Job])
def get_jobs() -> list[Job]:
    return fixtures.jobs()
