"""schemas.py — ローカル管理API固有のレスポンス型（domainの7モデルに無いものだけここに置く）。

`Candidate`・`Job` 等の一覧は history_radio.domain の型をそのまま返す(§13のエンティティを
API層で複製しない — G5)。ダッシュボード集計のような「APIだけの見え方」の型だけをここで定義する。
"""

from __future__ import annotations

from pydantic import Field

from history_radio.domain.base import SchemaModel


class DashboardSummary(SchemaModel):
    """`GET /api/v1/dashboard`（仕様書§12.1のホーム表示項目）。"""

    schema_version: int = Field(default=1, ge=1, le=1)
    jobs_running: int = Field(ge=0)
    jobs_queued: int = Field(ge=0)
    jobs_failed_today: int = Field(ge=0)
    episodes_published_this_month: int = Field(ge=0)
    openrouter_calls_today: int = Field(ge=0)
    candidates_awaiting_review: int = Field(ge=0)
