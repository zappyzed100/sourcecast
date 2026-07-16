"""test_collector.py — Phase 4 DoD: approved限定収集と非許可本文の不永続化を固定する"""

from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from history_radio.ingest.collector import (
    CollectOutcome,
    SourceNotApprovedError,
    collect_document,
)
from history_radio.ingest.crawl_control import PoliteFetcher
from history_radio.ingest.schema import (
    EvidenceLocator,
    FetchedDocument,
    FetchResponseInfo,
    RightsEvidence,
)
from history_radio.store.config_schemas import SourceRegistryEntry
from history_radio.store.db import create_sqlite_engine, session_factory
from history_radio.store.orm import Base, DocumentRow, RightsDecisionRow
from history_radio.store.rights import list_rights_decisions_for_document
from tests.ingest.mock_http import Reply, scripted_fetcher


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Engine]:
    eng = create_sqlite_engine(tmp_path / "test.db")
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    with session_factory(engine)() as s:
        yield s


def _fetcher() -> PoliteFetcher:
    fetcher, _clock, _requests = scripted_fetcher([Reply(status=200)])
    return fetcher


def _source_entry(**overrides: Any) -> SourceRegistryEntry:
    base: dict[str, Any] = {
        "source_id": "wikipedia-ja",
        "status": "approved",
        "use_class": "A",
        "normalized_license_id": "cc-by-sa",
        "commercial_use": "allow",
        "modification": "allow",
        "redistribution": "conditional",
        "attribution": "required",
        "share_alike": "preserve_per_asset",
        "third_party_exception": "deny",
        "territory": "JP",
        "terms_url": "https://ja.wikipedia.org/wiki/Wikipedia:著作権",
        "terms_checked_at": "2026-07-01",
        "recheck_days": 90,
    }
    base.update(overrides)
    return SourceRegistryEntry.model_validate(base)


def _document(**overrides: Any) -> FetchedDocument:
    base: dict[str, Any] = {
        "document_id": "wikipedia-ja-987654",
        "source_id": "wikipedia-ja",
        "original_url": "https://ja.wikipedia.org/wiki/example",
        "canonical_url": "https://ja.wikipedia.org/w/index.php?oldid=987654",
        "revision_id": "oldid=987654",
        "title": "例記事",
        "creator": "Wikipedia contributors",
        "fetched_at": datetime(2026, 7, 16, tzinfo=timezone.utc),
        "full_text": "本文テキスト",
        "excerpt": "根拠抜粋",
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
        "permalink": "https://ja.wikipedia.org/w/index.php?oldid=987654",
        "content_hash": "sha256:abc123",
        "response": FetchResponseInfo(
            fetch_method="api", http_status=200, robots_txt_allowed=True, terms_checked=True
        ),
        "storage_permission": "granted",
        "publication_permission": "denied",
    }
    base.update(overrides)
    return FetchedDocument.model_validate(base)


class StubAdapter:
    """Protocolを満たす最小アダプター。fetchが呼ばれた回数を記録する。"""

    def __init__(self, doc: FetchedDocument) -> None:
        self._doc = doc
        self.fetch_calls = 0

    @property
    def source_id(self) -> str:
        return self._doc.source_id

    def fetch(self, fetcher: PoliteFetcher, resource_ref: str) -> FetchedDocument:
        self.fetch_calls += 1
        return self._doc


def test_candidate_source_is_rejected_before_any_fetch(session: Session) -> None:
    """Phase 4タスク: candidateソースは収集されない——HTTP取得自体が走らない。"""
    adapter = StubAdapter(_document())
    with pytest.raises(SourceNotApprovedError, match="candidate"):
        collect_document(
            session,
            adapter=adapter,
            fetcher=_fetcher(),
            resource_ref="例記事",
            source=_source_entry(status="candidate"),
            decision_id="dec-t1",
        )
    assert adapter.fetch_calls == 0
    assert session.execute(select(DocumentRow)).scalars().all() == []
    assert session.execute(select(RightsDecisionRow)).scalars().all() == []


def test_allow_public_use_document_stores_full_text(session: Session) -> None:
    adapter = StubAdapter(_document())
    outcome = collect_document(
        session,
        adapter=adapter,
        fetcher=_fetcher(),
        resource_ref="例記事",
        source=_source_entry(),
        decision_id="dec-t2",
    )
    assert outcome == CollectOutcome(
        document_id="wikipedia-ja-987654",
        decision="allow_public_use",
        stored_full_text=True,
        created_new_snapshot=True,
    )
    row = session.get(DocumentRow, "wikipedia-ja-987654")
    assert row is not None and row.full_text == "本文テキスト"


def test_internal_research_only_document_never_persists_full_text(session: Session) -> None:
    """Phase 4タスク: internal_research_onlyの全文が永続化されない。"""
    doc = _document(
        document_id="unknown-doc-1",
        rights=RightsEvidence.model_validate(
            {
                "license_name": "表示なし",
                "normalized_license_id": "unknown",
                "use_class": "B",
                "rights_statement_text": "権利表示なし",
                "rights_page_url": "https://example.org/page",
            }
        ),
    )
    outcome = collect_document(
        session,
        adapter=StubAdapter(doc),
        fetcher=_fetcher(),
        resource_ref="x",
        source=_source_entry(normalized_license_id="unknown"),
        decision_id="dec-t3",
    )
    assert outcome.decision == "internal_research_only"
    assert outcome.stored_full_text is False
    row = session.get(DocumentRow, "unknown-doc-1")
    assert row is not None
    assert row.full_text is None  # 本文は残らない
    assert row.content_hash == "sha256:abc123"  # メタデータ・ハッシュは残る（§7.2）
    assert "本文テキスト" not in row.payload_json  # JSON経由でも本文が漏れない


def test_third_party_exception_source_downgrades_to_manual_review(session: Session) -> None:
    outcome = collect_document(
        session,
        adapter=StubAdapter(_document()),
        fetcher=_fetcher(),
        resource_ref="例記事",
        source=_source_entry(third_party_exception="allow"),
        decision_id="dec-t4",
    )
    assert outcome.decision == "manual_review"
    assert outcome.stored_full_text is False


def test_terms_fetch_failure_denies_and_stores_no_full_text(session: Session) -> None:
    doc = _document(
        response=FetchResponseInfo(
            fetch_method="api", http_status=200, robots_txt_allowed=True, terms_checked=False
        )
    )
    outcome = collect_document(
        session,
        adapter=StubAdapter(doc),
        fetcher=_fetcher(),
        resource_ref="例記事",
        source=_source_entry(),
        decision_id="dec-t5",
    )
    assert outcome.decision == "deny"
    assert outcome.stored_full_text is False


def test_every_collect_appends_a_rights_decision(session: Session) -> None:
    """§5A: 取得のたびに判定し直し、判定履歴が追記される（使い回さない）。"""
    adapter = StubAdapter(_document())
    for i in range(2):
        collect_document(
            session,
            adapter=adapter,
            fetcher=_fetcher(),
            resource_ref="例記事",
            source=_source_entry(),
            decision_id=f"dec-t6-{i}",
        )
    decisions = list_rights_decisions_for_document(session, "wikipedia-ja-987654")
    assert [d.decision_id for d in decisions] == ["dec-t6-0", "dec-t6-1"]


def test_refetch_of_same_content_does_not_duplicate_snapshot(session: Session) -> None:
    """Phase 4タスク: 同じ内容の再取得で重複スナップショットを作らない。"""
    adapter = StubAdapter(_document())
    first = collect_document(
        session,
        adapter=adapter,
        fetcher=_fetcher(),
        resource_ref="例記事",
        source=_source_entry(),
        decision_id="dec-t7-a",
    )
    second = collect_document(
        session,
        adapter=adapter,
        fetcher=_fetcher(),
        resource_ref="例記事",
        source=_source_entry(),
        decision_id="dec-t7-b",
    )
    assert first.created_new_snapshot is True
    assert second.created_new_snapshot is False
