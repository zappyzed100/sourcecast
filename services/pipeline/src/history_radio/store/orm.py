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


class DocumentRow(Base):
    """`documents`（仕様書§7.2・Phase 4）: 取得資料のメタデータと（許可時のみ）全文。

    full_text が NULL のまま残るのは、権利判定が `allow_public_use` でない資料
    （candidate/internal_research_only 等）——本文を保存しない契約はこの列の
    NULL可否ではなく store/documents.py の書き込み経路が守る。メタデータ・抜粋・
    ハッシュは §7.2 どおり常に保存してよい。
    """

    __tablename__ = "documents"

    document_id: Mapped[str] = mapped_column(String, primary_key=True)
    source_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    canonical_url: Mapped[str] = mapped_column(String, nullable=False)
    permalink: Mapped[str] = mapped_column(String, nullable=False)
    revision_id: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    language: Mapped[str] = mapped_column(String, nullable=False)
    normalized_license_id: Mapped[str] = mapped_column(String, nullable=False)
    use_class: Mapped[str] = mapped_column(String, nullable=False)
    storage_permission: Mapped[str] = mapped_column(String, nullable=False)
    publication_permission: Mapped[str] = mapped_column(String, nullable=False)
    content_hash: Mapped[str] = mapped_column(String, nullable=False, index=True)
    excerpt: Mapped[str | None] = mapped_column(String, nullable=True)
    full_text: Mapped[str | None] = mapped_column(String, nullable=True)
    payload_json: Mapped[str] = mapped_column(String, nullable=False)
    first_fetched_at: Mapped[datetime] = mapped_column(nullable=False)


class FetchSnapshotRow(Base):
    """`fetch_snapshots`（§7.2・Phase 4）: 取得1回分の証跡（URL・日時・応答・ハッシュ）。

    同一 document_id・同一 content_hash の再取得ではスナップショットを増やさない
    （§7.3「同一内容はハッシュで再取得を抑制する」の保存面 — store/documents.py）。
    """

    __tablename__ = "fetch_snapshots"

    snapshot_id: Mapped[str] = mapped_column(String, primary_key=True)
    document_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    original_url: Mapped[str] = mapped_column(String, nullable=False)
    content_hash: Mapped[str] = mapped_column(String, nullable=False)
    fetch_method: Mapped[str] = mapped_column(String, nullable=False)
    http_status: Mapped[int] = mapped_column(nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(nullable=False)


class LlmRunRow(Base):
    """`llm_runs`（仕様書§8.1・Phase 6）: LLM実行1回分の記録とキャッシュのキー。

    キャッシュキーは (model_id, prompt_version, input_hash)——同じ入力と版では
    保存済み出力を返し、二重課金呼び出しをしない（llm/cache.py）。
    """

    __tablename__ = "llm_runs"

    run_id: Mapped[str] = mapped_column(String, primary_key=True)
    model_id: Mapped[str] = mapped_column(String, nullable=False)
    prompt_version: Mapped[str] = mapped_column(String, nullable=False)
    input_hash: Mapped[str] = mapped_column(String, nullable=False, index=True)
    output_hash: Mapped[str] = mapped_column(String, nullable=False)
    output_text: Mapped[str] = mapped_column(String, nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(nullable=False)
    completion_tokens: Mapped[int] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False)


class TermsSnapshotRow(Base):
    """`terms_snapshots`（§5.2・§7.2・Phase 4）: 規約ページの取得時点スナップショット。

    同一 source_id・同一 content_hash では増やさない（規約が変わった時だけ新しい行）。
    """

    __tablename__ = "terms_snapshots"

    terms_snapshot_id: Mapped[str] = mapped_column(String, primary_key=True)
    source_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    terms_url: Mapped[str] = mapped_column(String, nullable=False)
    content_hash: Mapped[str] = mapped_column(String, nullable=False)
    text: Mapped[str] = mapped_column(String, nullable=False)
    captured_at: Mapped[datetime] = mapped_column(nullable=False)
