"""orm.py — SQLAlchemy 2 宣言的テーブル定義（仕様書§13: episodes・jobs・audit_events）。

domain/models.py のPydanticモデルとは別物として持つ（DTOとORM行を混同しない —
plan.md §2.2「domain/ = 副作用のない型」「store/ = DB・ファイル実装」の分離）。
Job・AuditEventのテーブルはPhase 1では定義のみ（実際のリポジトリ関数は、ジョブや
監査ログを実際に書き込む後続フェーズで追加する）。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class EpisodeRow(Base):
    __tablename__ = "episodes"

    episode_id: Mapped[str] = mapped_column(String, primary_key=True)
    state: Mapped[str] = mapped_column(String, nullable=False)
    revision: Mapped[int] = mapped_column(nullable=False, default=1)
    title: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False)
    updated_at: Mapped[datetime] = mapped_column(nullable=False)


class JobRow(Base):
    __tablename__ = "jobs"

    job_id: Mapped[str] = mapped_column(String, primary_key=True)
    episode_id: Mapped[str | None] = mapped_column(String, nullable=True)
    kind: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    error: Mapped[str | None] = mapped_column(String, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)


class AuditEventRow(Base):
    __tablename__ = "audit_events"

    event_id: Mapped[str] = mapped_column(String, primary_key=True)
    entity_type: Mapped[str] = mapped_column(String, nullable=False)
    entity_id: Mapped[str] = mapped_column(String, nullable=False)
    action: Mapped[str] = mapped_column(String, nullable=False)
    actor: Mapped[str] = mapped_column(String, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(nullable=False)
    detail: Mapped[str] = mapped_column(String, nullable=False, default="")


class RightsDecisionRow(Base):
    """`rights_records`（仕様書§5A・Phase 3）: 資料単位の権利判定結果。

    主キーは `document_id` ではなく `decision_id`——同じ資料を新ルールで再判定しても
    行を上書きせず追記する（append-only。store/rights.py に更新・削除関数を置かない
    ことで構造的に保証する）。
    """

    __tablename__ = "rights_records"

    decision_id: Mapped[str] = mapped_column(String, primary_key=True)
    document_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    decision: Mapped[str] = mapped_column(String, nullable=False)
    rule_version: Mapped[str] = mapped_column(String, nullable=False)
    reasons_json: Mapped[str] = mapped_column(String, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(nullable=False)
