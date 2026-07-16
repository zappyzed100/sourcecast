"""test_extraction.py — Phase 6 DoD: §8.2出力の拒否条件と根拠完全一致・出所注入を固定する"""

import json
from datetime import datetime, timezone
from typing import Any

import pytest

from history_radio.ingest.schema import (
    EvidenceLocator,
    FetchedDocument,
    FetchResponseInfo,
    RightsEvidence,
)
from history_radio.llm.extraction import (
    ExtractedFact,
    ExtractionValidationError,
    FactLocator,
    attach_provenance,
    parse_extraction,
    verify_evidence_quote,
)

_FULL_TEXT = "明治五年九月十二日、新橋横浜間の鉄道が開業した。式典には明治天皇が臨席した。"


def _document(**overrides: Any) -> FetchedDocument:
    base: dict[str, Any] = {
        "document_id": "wikipedia-ja-1",
        "source_id": "wikipedia-ja",
        "original_url": "https://ja.wikipedia.org/wiki/example",
        "canonical_url": "https://ja.wikipedia.org/w/index.php?oldid=1",
        "revision_id": "oldid=1",
        "title": "日本の鉄道開業",
        "creator": "Wikipedia contributors",
        "fetched_at": datetime(2026, 7, 16, tzinfo=timezone.utc),
        "full_text": _FULL_TEXT,
        "locator": EvidenceLocator(),
        "language": "ja",
        "rights": RightsEvidence.model_validate(
            {
                "license_name": "CC BY-SA 4.0",
                "normalized_license_id": "cc-by-sa",
                "use_class": "A",
                "rights_statement_text": "CC BY-SA 4.0",
                "rights_page_url": "https://ja.wikipedia.org/wiki/example",
            }
        ),
        "permalink": "https://ja.wikipedia.org/w/index.php?oldid=1",
        "content_hash": "sha256:h1",
        "response": FetchResponseInfo(
            fetch_method="api", http_status=200, robots_txt_allowed=True, terms_checked=True
        ),
        "storage_permission": "granted",
        "publication_permission": "denied",
    }
    base.update(overrides)
    return FetchedDocument.model_validate(base)


def _quote(start: int, end: int) -> str:
    return _FULL_TEXT[start:end]


def _valid_payload() -> dict[str, Any]:
    return {
        "summary_ja": "新橋横浜間の鉄道開業について",
        "facts": [
            {
                "claim": "1872年に新橋横浜間の鉄道が開業した",
                "evidence_quote": _quote(0, 22),
                "source_id": "wikipedia-ja",
                "locator": {"start_offset": 0, "end_offset": 22},
            }
        ],
        "people": ["明治天皇"],
        "places": ["新橋", "横浜"],
        "dates": ["1872-10-14"],
        "uncertainties": [],
    }


def test_valid_extraction_parses() -> None:
    extraction = parse_extraction(json.dumps(_valid_payload()))
    assert extraction.facts[0].source_id == "wikipedia-ja"


def test_invalid_json_is_rejected() -> None:
    with pytest.raises(ExtractionValidationError, match="JSONとして不正"):
        parse_extraction("{summary_ja: 壊れたJSON")


def test_extra_keys_are_rejected() -> None:
    payload = _valid_payload()
    payload["source_url"] = "https://evil.example/injected"  # LLMが出所を主張しても拒否
    with pytest.raises(ExtractionValidationError, match="スキーマに一致しない"):
        parse_extraction(json.dumps(payload))


def test_missing_required_key_is_rejected() -> None:
    payload = _valid_payload()
    del payload["uncertainties"]
    with pytest.raises(ExtractionValidationError, match="スキーマに一致しない"):
        parse_extraction(json.dumps(payload))


def test_exact_quote_passes_verification() -> None:
    fact = ExtractedFact(
        claim="鉄道が開業した",
        evidence_quote=_quote(0, 22),
        source_id="wikipedia-ja",
        locator=FactLocator(start_offset=0, end_offset=22),
    )
    verify_evidence_quote(fact, _document())  # 例外なし


def test_one_character_alteration_is_rejected() -> None:
    """Phase 6 DoD: 1文字改変した抜粋が拒否される。"""
    altered = _quote(0, 22).replace("鉄道", "鉃道", 1)
    fact = ExtractedFact(
        claim="鉄道が開業した",
        evidence_quote=altered,
        source_id="wikipedia-ja",
        locator=FactLocator(start_offset=0, end_offset=22),
    )
    with pytest.raises(ExtractionValidationError, match="一致しない"):
        verify_evidence_quote(fact, _document())


def test_out_of_range_locator_is_rejected() -> None:
    """存在しない根拠位置（本文長を超えるオフセット）を拒否する。"""
    fact = ExtractedFact(
        claim="x",
        evidence_quote="y",
        source_id="wikipedia-ja",
        locator=FactLocator(start_offset=0, end_offset=99999),
    )
    with pytest.raises(ExtractionValidationError, match="範囲外"):
        verify_evidence_quote(fact, _document())


def test_document_without_stored_text_cannot_be_cited() -> None:
    fact = ExtractedFact(
        claim="x",
        evidence_quote=_quote(0, 22),
        source_id="wikipedia-ja",
        locator=FactLocator(start_offset=0, end_offset=22),
    )
    no_text = _document(full_text=None, storage_permission="denied")
    with pytest.raises(ExtractionValidationError, match="保存本文が無い"):
        verify_evidence_quote(fact, no_text)


def test_provenance_is_injected_from_document_not_llm() -> None:
    """URL・取得日・ライセンスはプログラム注入（§8.2）——資料の値がそのまま載る。"""
    fact = ExtractedFact(
        claim="鉄道が開業した",
        evidence_quote=_quote(0, 22),
        source_id="wikipedia-ja",
        locator=FactLocator(start_offset=0, end_offset=22),
    )
    record = attach_provenance(fact, _document())
    assert record.source_url == "https://ja.wikipedia.org/w/index.php?oldid=1"
    assert record.fetched_at == "2026-07-16T00:00:00+00:00"
    assert record.normalized_license_id == "cc-by-sa"
