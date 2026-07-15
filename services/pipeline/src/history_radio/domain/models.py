"""models.py — Phase 1のドメイン契約（仕様書§13の主要エンティティをPydanticで型付けする）。

ここで定義した型からJSON Schemaを生成し、packages/contracts/schema/ へコミットする
（生成コマンドは scripts/generate_contracts.py。plan.md §2.3の「二重管理しない」契約）。
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field, HttpUrl

from history_radio.domain.base import SchemaModel
from history_radio.domain.episode_state import EpisodeState

UseClass = Literal["A", "B", "C", "D"]
SourceStatus = Literal["candidate", "approved", "suspended", "rejected"]
RightsDecisionValue = Literal["allow_public_use", "internal_research_only", "manual_review", "deny"]
ClaimQualification = Literal["断定", "資料帰属", "伝承", "推定"]
JobStatus = Literal["queued", "running", "succeeded", "failed", "blocked"]


class SourceRecord(SchemaModel):
    """`sources`/`source_registry`（仕様書§5.14・§5.2）: ソース単位の利用区分・権利条件。"""

    schema_version: Literal[1] = 1
    source_id: str = Field(min_length=1)
    status: SourceStatus
    use_class: UseClass
    normalized_license_id: str = Field(min_length=1)
    commercial_use: Literal["allow", "deny", "conditional"]
    modification: Literal["allow", "deny", "conditional"]
    redistribution: Literal["allow", "deny", "conditional"]
    attribution: Literal["required", "not_required", "required_if_not_cc0"]
    share_alike: Literal["none", "preserve_per_asset"]
    third_party_exception: Literal["allow", "deny"]
    territory: str = Field(min_length=1)
    terms_url: HttpUrl
    terms_checked_at: datetime
    recheck_days: int = Field(gt=0)


class RightsDecision(SchemaModel):
    """`rights_records`（仕様書§5A）: 資料単位の機械スクリーニング結果。

    年数計算は資料取得のたびに現在日付で再計算する契約（§5A冒頭）——computed_at が
    その再計算時点を記録し、判定結果を使い回さないことを保証する。
    """

    schema_version: Literal[1] = 1
    decision_id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    decision: RightsDecisionValue
    rule_version: str = Field(min_length=1)
    reasons: list[str] = Field(min_length=1)
    computed_at: datetime


class Candidate(SchemaModel):
    """`topics`（仕様書§6A）: 機械選出の候補点と内訳。LLM不使用。"""

    schema_version: Literal[1] = 1
    candidate_id: str = Field(min_length=1)
    topic_title: str = Field(min_length=1)
    score: float
    score_breakdown: dict[str, float]
    independent_source_families: int = Field(ge=0)


class Claim(SchemaModel):
    """`claim_ledger`（仕様書§8.2A）: 台本生成前に確定する公開可能な主張の台帳。"""

    schema_version: Literal[1] = 1
    claim_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    evidence_ids: list[str] = Field(min_length=1)
    source_family_ids: list[str] = Field(min_length=1)
    reliability_score: float = Field(ge=0, le=1)
    allowed_in_script: bool
    qualification: ClaimQualification


class Episode(SchemaModel):
    """`episodes`（仕様書§13・§6.1）: エピソード単位の状態と識別子。"""

    schema_version: Literal[1] = 1
    episode_id: str = Field(min_length=1)
    state: EpisodeState
    revision: int = Field(ge=1)
    title: str = Field(min_length=1)
    created_at: datetime
    updated_at: datetime


class Job(SchemaModel):
    """`jobs`（仕様書§13・§14）: 処理工程単位の実行状態とエラー。"""

    schema_version: Literal[1] = 1
    job_id: str = Field(min_length=1)
    episode_id: str | None = None
    kind: str = Field(min_length=1)
    status: JobStatus
    error: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


class AuditEvent(SchemaModel):
    """追記型監査ログ（仕様書§15: 公開・訂正・削除・権利判定変更を必ず記録する）。"""

    schema_version: Literal[1] = 1
    event_id: str = Field(min_length=1)
    entity_type: str = Field(min_length=1)
    entity_id: str = Field(min_length=1)
    action: str = Field(min_length=1)
    actor: str = Field(min_length=1)
    occurred_at: datetime
    detail: str = ""
