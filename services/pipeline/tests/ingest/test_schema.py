"""test_schema.py — Phase 4 DoD: 取得結果スキーマの必須フィールド・保存許可の実行時検証を固定する"""

from datetime import datetime, timezone
from typing import Any

import pytest
from pydantic import ValidationError

from history_radio.ingest.schema import (
    EvidenceLocator,
    FetchedDocument,
    FetchResponseInfo,
    RightsEvidence,
)


def _valid_document_kwargs(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "document_id": "doc-1",
        "source_id": "wikipedia-ja",
        "original_url": "https://ja.wikipedia.org/wiki/example",
        "canonical_url": "https://ja.wikipedia.org/wiki/example",
        "revision_id": "oldid=12345",
        "title": "例記事",
        "creator": "Wikipedia contributors",
        "fetched_at": datetime(2026, 7, 16, tzinfo=timezone.utc),
        "excerpt": "根拠となる短い抜粋",
        "locator": EvidenceLocator(paragraph_id="p-3", start_offset=0, end_offset=42),
        "language": "ja",
        "rights": RightsEvidence.model_validate(
            {
                "license_name": "CC BY-SA 4.0",
                "license_url": "https://creativecommons.org/licenses/by-sa/4.0/",
                "normalized_license_id": "cc-by-sa",
                "use_class": "A",
                "rights_statement_text": "Text is available under CC BY-SA 4.0",
                "rights_page_url": "https://ja.wikipedia.org/wiki/example",
            }
        ),
        "permalink": "https://ja.wikipedia.org/w/index.php?oldid=12345",
        "content_hash": "sha256:abc123",
        "response": FetchResponseInfo(
            fetch_method="api",
            http_status=200,
            robots_txt_allowed=True,
            terms_checked=True,
        ),
        "storage_permission": "granted",
        "publication_permission": "granted",
    }
    base.update(overrides)
    return base


def test_valid_document_is_accepted() -> None:
    doc = FetchedDocument(**_valid_document_kwargs())
    assert doc.source_id == "wikipedia-ja"
    assert doc.rights.normalized_license_id == "cc-by-sa"


@pytest.mark.parametrize(
    "missing_field",
    [
        "source_id",
        "original_url",
        "revision_id",
        "title",
        "fetched_at",
        "locator",
        "language",
        "rights",
        "content_hash",
        "response",
        "storage_permission",
        "publication_permission",
    ],
)
def test_missing_required_field_is_rejected(missing_field: str) -> None:
    kwargs = _valid_document_kwargs()
    del kwargs[missing_field]
    with pytest.raises(ValidationError):
        FetchedDocument(**kwargs)


def test_unknown_field_is_rejected() -> None:
    with pytest.raises(ValidationError):
        FetchedDocument(**_valid_document_kwargs(surprise_field="x"))


def test_full_text_without_storage_permission_is_rejected() -> None:
    """§7.2: 保存根拠を確認できない資料の原文全文を保持できない（fail closed）。"""
    with pytest.raises(ValidationError, match="storage_permission"):
        FetchedDocument(
            **_valid_document_kwargs(full_text="全文テキスト", storage_permission="unknown")
        )
    with pytest.raises(ValidationError, match="storage_permission"):
        FetchedDocument(
            **_valid_document_kwargs(full_text="全文テキスト", storage_permission="denied")
        )


def test_full_text_with_granted_storage_permission_is_accepted() -> None:
    doc = FetchedDocument(
        **_valid_document_kwargs(full_text="全文テキスト", storage_permission="granted")
    )
    assert doc.full_text == "全文テキスト"


def test_storage_and_publication_permissions_are_independent() -> None:
    """§7.2: 内部保存が許されても公開再配布できるとは限らない——別フィールドで独立。"""
    doc = FetchedDocument(
        **_valid_document_kwargs(storage_permission="granted", publication_permission="denied")
    )
    assert doc.storage_permission == "granted"
    assert doc.publication_permission == "denied"


def test_locator_rejects_reversed_offsets() -> None:
    with pytest.raises(ValidationError, match="start_offset"):
        EvidenceLocator(start_offset=100, end_offset=10)


def test_response_info_rejects_out_of_range_http_status() -> None:
    with pytest.raises(ValidationError):
        FetchResponseInfo(
            fetch_method="api", http_status=999, robots_txt_allowed=True, terms_checked=True
        )
