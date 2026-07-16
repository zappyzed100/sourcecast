"""extraction.py — LLM要約出力の受け取りと検証（仕様書§8.2）。

LLMには取得済み本文とメタデータだけを渡し、§8.2のJSONを返させる。この module は
その出力を**信用せずに**検証する側:

- 形はPydantic（extra="forbid"）で受ける——JSON不正・余分なキーは即拒否。
- URL・取得日・ライセンスはLLM出力に**含まれない**（スキーマにフィールドが無い）。
  公開用の事実レコードへは `attach_provenance` がプログラムから注入する（§8.2の
  「URL、取得日、ライセンスはプログラムから注入する」）。
- 根拠抜粋（evidence_quote）は保存本文と**完全一致**することを検証する——locator の
  文字オフセットで切り出した部分文字列と一致しなければ拒否（1文字の改変も通さない）。
"""

from __future__ import annotations

import json

from pydantic import Field, ValidationError

from history_radio.domain.base import SchemaModel
from history_radio.ingest.schema import FetchedDocument


class ExtractionValidationError(ValueError):
    """LLM出力の検証失敗（JSON不正・余分なキー・根拠不一致等）。"""


class FactLocator(SchemaModel):
    """§8.2 locator: 保存本文内の文字オフセット（page/paragraph_idは資料種別による）。"""

    page: int | None = None
    paragraph_id: str | None = None
    start_offset: int = Field(ge=0)
    end_offset: int = Field(ge=0)


class ExtractedFact(SchemaModel):
    claim: str = Field(min_length=1)
    evidence_quote: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    locator: FactLocator


class SummaryExtraction(SchemaModel):
    """§8.2のLLM出力全体。URL・取得日・ライセンスのフィールドは意図的に存在しない。"""

    summary_ja: str = Field(min_length=1)
    facts: list[ExtractedFact]
    people: list[str]
    places: list[str]
    dates: list[str]
    uncertainties: list[str]


class ProvenancedFact(SchemaModel):
    """公開用の事実レコード（出所情報はプログラム注入——LLM出力を経由しない）。"""

    claim: str
    evidence_quote: str
    source_id: str
    locator: FactLocator
    source_url: str
    fetched_at: str
    normalized_license_id: str


def parse_extraction(raw_json: str) -> SummaryExtraction:
    """LLMの生出力をパースする。JSON不正・余分なキー・欠落は例外（fail closed）。"""
    try:
        payload = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise ExtractionValidationError(f"LLM出力がJSONとして不正: {exc}") from exc
    try:
        return SummaryExtraction.model_validate(payload)
    except ValidationError as exc:
        raise ExtractionValidationError(f"LLM出力が§8.2スキーマに一致しない: {exc}") from exc


def verify_evidence_quote(fact: ExtractedFact, document: FetchedDocument) -> None:
    """根拠抜粋が保存本文のlocator位置と完全一致することを検証する（§8.2・Phase 6）。

    完全一致でなければ例外——1文字の改変・言い換え・空白の差も通さない。
    """
    if fact.source_id != document.source_id:
        raise ExtractionValidationError(
            f"根拠のsource_id不一致: fact={fact.source_id!r} document={document.source_id!r}"
        )
    text = document.full_text
    if text is None:
        raise ExtractionValidationError(
            f"{document.document_id}: 保存本文が無い資料を根拠にできない"
            "（storage_permissionを通過した資料のみ引用可能）"
        )
    start, end = fact.locator.start_offset, fact.locator.end_offset
    if end > len(text) or start >= end:
        raise ExtractionValidationError(
            f"{document.document_id}: locator [{start}, {end}) が保存本文の範囲外"
        )
    stored = text[start:end]
    if stored != fact.evidence_quote:
        raise ExtractionValidationError(
            f"{document.document_id}: 根拠抜粋が保存本文と一致しない"
            f"（locator位置の本文: {stored[:50]!r}… / LLM出力: {fact.evidence_quote[:50]!r}…）"
        )


def attach_provenance(fact: ExtractedFact, document: FetchedDocument) -> ProvenancedFact:
    """検証済みの事実へ、URL・取得日・ライセンスをプログラムから注入する（§8.2）。"""
    verify_evidence_quote(fact, document)
    return ProvenancedFact(
        claim=fact.claim,
        evidence_quote=fact.evidence_quote,
        source_id=fact.source_id,
        locator=fact.locator,
        source_url=str(document.permalink),
        fetched_at=document.fetched_at.isoformat(),
        normalized_license_id=document.rights.normalized_license_id,
    )
