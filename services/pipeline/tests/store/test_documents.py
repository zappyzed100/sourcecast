"""test_documents.py — Phase 4 DoD: 本文破棄経路と規約スナップショットの重複抑制を固定する"""

from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from history_radio.ingest.schema import (
    EvidenceLocator,
    FetchedDocument,
    FetchResponseInfo,
    RightsEvidence,
)
from history_radio.store.db import create_sqlite_engine, session_factory
from history_radio.store.documents import (
    get_document,
    list_snapshots,
    save_document,
    save_terms_snapshot,
)
from history_radio.store.orm import Base


@pytest.fixture
def session(tmp_path: Path) -> Iterator[Session]:
    eng: Engine = create_sqlite_engine(tmp_path / "test.db")
    Base.metadata.create_all(eng)
    with session_factory(eng)() as s:
        yield s
    eng.dispose()


def _document(**overrides: Any) -> FetchedDocument:
    base: dict[str, Any] = {
        "document_id": "doc-1",
        "source_id": "wikipedia-ja",
        "original_url": "https://ja.wikipedia.org/wiki/example",
        "canonical_url": "https://ja.wikipedia.org/w/index.php?oldid=1",
        "revision_id": "oldid=1",
        "title": "例",
        "creator": "contributors",
        "fetched_at": datetime(2026, 7, 16, tzinfo=timezone.utc),
        "full_text": "全文",
        "excerpt": "抜粋",
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


def test_store_full_text_false_discards_body_even_if_present(session: Session) -> None:
    """本文を受け取っていても store_full_text=False なら捨てる（永続化経路のfail closed）。"""
    save_document(session, _document(), store_full_text=False)
    row = get_document(session, "doc-1")
    assert row is not None
    assert row.full_text is None
    assert "全文" not in row.payload_json


def test_new_revision_creates_new_document_and_snapshot(session: Session) -> None:
    save_document(session, _document(), store_full_text=True)
    _row, created = save_document(
        session,
        _document(document_id="doc-2", revision_id="oldid=2", content_hash="sha256:h2"),
        store_full_text=True,
    )
    assert created is True
    assert get_document(session, "doc-1") is not None
    assert get_document(session, "doc-2") is not None


def test_same_content_refetch_does_not_add_snapshot(session: Session) -> None:
    _row1, first = save_document(session, _document(), store_full_text=True)
    _row2, second = save_document(session, _document(), store_full_text=True)
    assert first is True
    assert second is False
    assert len(list_snapshots(session, "doc-1")) == 1


def test_terms_snapshot_deduplicates_by_content(session: Session) -> None:
    """Phase 4タスク: 規約スナップショットも同一内容の再取得で増えない。"""
    when = datetime(2026, 7, 16, tzinfo=timezone.utc)
    _row1, first = save_terms_snapshot(
        session,
        source_id="s1",
        terms_url="https://example.org/terms",
        text="規約v1",
        captured_at=when,
    )
    _row2, second = save_terms_snapshot(
        session,
        source_id="s1",
        terms_url="https://example.org/terms",
        text="規約v1",
        captured_at=when,
    )
    _row3, changed = save_terms_snapshot(
        session,
        source_id="s1",
        terms_url="https://example.org/terms",
        text="規約v2",
        captured_at=when,
    )
    assert first is True
    assert second is False  # 同一内容→増えない
    assert changed is True  # 規約が変わった時だけ新しい行
