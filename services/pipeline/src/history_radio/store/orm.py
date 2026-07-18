"""orm.py — SQLAlchemy 2 宣言的テーブル定義（仕様書§13: episodes・jobs・audit_events）。

domain/models.py のPydanticモデルとは別物として持つ（DTOとORM行を混同しない —
plan.md §2.2「domain/ = 副作用のない型」「store/ = DB・ファイル実装」の分離）。
AuditEventのテーブルはPhase 1では定義のみ（実際のリポジトリ関数は、監査ログを
実際に書き込む後続フェーズで追加する）。Jobは`store/jobs.py`（Phase 11タスク2）が
実際のリポジトリ関数を持つ。
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
    progress: Mapped[float] = mapped_column(nullable=False, default=0.0)
    cancel_requested: Mapped[bool] = mapped_column(nullable=False, default=False)
    retry_of: Mapped[str | None] = mapped_column(String, nullable=True)
    error: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)


class JobLogRow(Base):
    """`jobs`1件分の実行ログ（Phase 11タスク2「ログ追跡」）。主キーは`(job_id, seq)`——
    ジョブ内で1始まりの連番を振り、追記のみ（更新・削除関数を置かない。他のappend-only
    テーブルと同じ方針）。
    """

    __tablename__ = "job_log_entries"

    job_id: Mapped[str] = mapped_column(String, primary_key=True)
    seq: Mapped[int] = mapped_column(primary_key=True)
    level: Mapped[str] = mapped_column(String, nullable=False)
    message: Mapped[str] = mapped_column(String, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(nullable=False)


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


class PublishGateResultRow(Base):
    """`publication_versions`系（仕様書§11・§13・Phase 10タスク3）: 自動検査ゲートの
    評価結果1回分。

    主キーは `result_id`——同じepisode_id・revisionを何度再評価しても行を上書きせず
    追記する（append-only。store/gate_results.py に更新・削除関数を置かないことで
    構造的に保証する）。「公開済み版から当時の検査結果を再表示できる」（Phase 10
    タスク3 DoD）は、この行を(episode_id, revision)で検索することで満たす。
    """

    __tablename__ = "publish_gate_results"

    result_id: Mapped[str] = mapped_column(String, primary_key=True)
    episode_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    revision: Mapped[int] = mapped_column(nullable=False)
    rule_version: Mapped[str] = mapped_column(String, nullable=False)
    publish_ready: Mapped[bool] = mapped_column(nullable=False)
    checks_json: Mapped[str] = mapped_column(String, nullable=False)
    artifact_hash: Mapped[str] = mapped_column(String, nullable=False)
    evaluated_at: Mapped[datetime] = mapped_column(nullable=False)


class CandidateRow(Base):
    """`topics`（仕様書§13・§6A・Phase 11タスク1）: 機械選出の候補点と内訳の永続化。

    再生成（仕様書§12.3「採用／除外／再生成」の再生成）は新しいcandidate_idで
    別行を作る想定のため、更新関数は置かない（store/candidates.pyは挿入・参照のみ）。
    """

    __tablename__ = "candidates"

    candidate_id: Mapped[str] = mapped_column(String, primary_key=True)
    topic_title: Mapped[str] = mapped_column(String, nullable=False)
    score: Mapped[float] = mapped_column(nullable=False)
    score_breakdown_json: Mapped[str] = mapped_column(String, nullable=False)
    independent_source_families: Mapped[int] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False, index=True)


class CandidateDecisionRow(Base):
    """候補の審査結果（仕様書§12.3・§12.4・Phase 11タスク1・3）。

    主キーは `decision_id`——同じcandidate_idを再審査しても行を上書きせず追記する
    （append-only。store/candidate_decisions.py に更新・削除関数を置かないことで
    構造的に保証する。rights.py/gate_results.pyと同じ方針）。
    """

    __tablename__ = "candidate_decisions"

    decision_id: Mapped[str] = mapped_column(String, primary_key=True)
    candidate_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    decision: Mapped[str] = mapped_column(String, nullable=False)
    reason: Mapped[str] = mapped_column(String, nullable=False, default="")
    decided_at: Mapped[datetime] = mapped_column(nullable=False)


class DistributionRecordRow(Base):
    """`(episode_id, target)`単位の直近の配信結果（仕様書§10D・Phase 9タスク4・
    Phase 11タスク1「限定公開」）。

    複合主キーは`(episode_id, target)`——`publish/distribution_ledger.py`の
    インメモリ`DistributionLedger`と同じ「直近の状態だけ保持する」意味論を
    そのままテーブルへ写す（同じ組み合わせへの再実行は行を上書きする）。
    全試行の履歴は`audit_events`側で追記保存する
    （`store/distribution_records.py`が保存と同時に記録する）。
    """

    __tablename__ = "distribution_records"

    episode_id: Mapped[str] = mapped_column(String, primary_key=True)
    target: Mapped[str] = mapped_column(String, primary_key=True)
    status: Mapped[str] = mapped_column(String, nullable=False)
    external_id: Mapped[str | None] = mapped_column(String, nullable=True)
    attempted_at: Mapped[str] = mapped_column(String, nullable=False)
    error_message: Mapped[str | None] = mapped_column(String, nullable=True)
