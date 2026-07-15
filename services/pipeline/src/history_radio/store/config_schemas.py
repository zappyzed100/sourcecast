"""config_schemas.py — config/*.yaml の形（仕様書§5.14・§5.2・§8.1）をPydanticで型付けする。

domain/base.SchemaModel と同じ基底(extra="forbid"・frozen)を使い、未知キーは
読み込み時点で拒否する。ここはYAMLの「形」だけの定義——重複ID検査・期限切れ検査等の
「複数エントリを跨ぐ」検証は config_loader.py 側で行う（単一エントリの形と、
コレクション全体の整合性検証を分離する — 単一責任）。
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import Field, HttpUrl

from history_radio.domain.base import SchemaModel

UseClass = Literal["A", "B", "C", "D"]
TriState = Literal["allow", "deny", "conditional"]


class SourceRegistryEntry(SchemaModel):
    """`config/source_registry.yaml` の1エントリ（仕様書§5.14・付録B）。"""

    source_id: str = Field(min_length=1)
    status: Literal["candidate", "approved", "suspended", "rejected"]
    use_class: UseClass
    normalized_license_id: str = Field(min_length=1)
    commercial_use: TriState
    modification: TriState
    redistribution: TriState
    attribution: Literal["required", "not_required", "required_if_not_cc0"]
    share_alike: Literal["none", "preserve_per_asset"]
    third_party_exception: Literal["allow", "deny"]
    territory: str = Field(min_length=1)
    terms_url: HttpUrl
    terms_checked_at: date
    recheck_days: int = Field(gt=0)


class SourceRegistryFile(SchemaModel):
    sources: list[SourceRegistryEntry]


class LicenseRule(SchemaModel):
    """`config/license_rules.yaml` の1エントリ（仕様書§5.2の正規化表）。"""

    license_id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    default_use_class: UseClass
    requires_attribution: bool
    notes: str = ""


class LicenseRulesFile(SchemaModel):
    licenses: list[LicenseRule]


class ModelRegistryEntry(SchemaModel):
    """`config/model_registry.yaml` の1エントリ（仕様書§8.1）。無料モデルのみ許可
    （price_prompt/price_completionが0でないエントリはconfig_loaderが拒否する）。"""

    model_id: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    endpoint: HttpUrl
    price_prompt: float = Field(ge=0)
    price_completion: float = Field(ge=0)
    context_length: int = Field(gt=0)
    expires_at: date
    data_policy: str = Field(min_length=1)


class ModelRegistryFile(SchemaModel):
    models: list[ModelRegistryEntry]
