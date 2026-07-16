"""documents.py — 取得資料の永続化とスナップショット重複抑制（仕様書§7.2・Phase 4）。

本文（full_text）を書くかどうかは呼び出し側（ingest/collector.py）の権利判定が決める
——この層は `store_full_text=False` なら本文を**受け取っていても捨てる**（fail closed。
誤って渡されても永続化経路が守る）。メタデータ・抜粋・ハッシュ・スナップショットは
§7.2どおり常に保存する。
"""

from __future__ import annotations

import hashlib
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from history_radio.ingest.schema import FetchedDocument
from history_radio.store.orm import DocumentRow, FetchSnapshotRow, TermsSnapshotRow


def save_document(
    session: Session, doc: FetchedDocument, *, store_full_text: bool
) -> tuple[DocumentRow, bool]:
    """資料を保存し、(行, 新スナップショットを作ったか) を返す。

    - 同じ document_id が既にあれば行は更新しない（版が同じ＝内容が同じ契約。
      新しい版は新しい document_id で来る — ingest/adapters/wikipedia.py の oldid 等）。
    - 同じ content_hash のスナップショットが既にあれば追加しない
      （§7.3「同一内容はハッシュで再取得を抑制する」の保存面）。
    """
    row = session.get(DocumentRow, doc.document_id)
    if row is None:
        row = DocumentRow(
            document_id=doc.document_id,
            source_id=doc.source_id,
            canonical_url=str(doc.canonical_url),
            permalink=str(doc.permalink),
            revision_id=doc.revision_id,
            title=doc.title,
            language=doc.language,
            normalized_license_id=doc.rights.normalized_license_id,
            use_class=doc.rights.use_class,
            storage_permission=doc.storage_permission,
            publication_permission=doc.publication_permission,
            content_hash=doc.content_hash,
            excerpt=doc.excerpt,
            full_text=doc.full_text if store_full_text else None,
            payload_json=doc.model_dump_json(
                exclude={"full_text"} if not store_full_text else None
            ),
            first_fetched_at=doc.fetched_at,
        )
        session.add(row)

    existing_snapshot = session.execute(
        select(FetchSnapshotRow).where(
            FetchSnapshotRow.document_id == doc.document_id,
            FetchSnapshotRow.content_hash == doc.content_hash,
        )
    ).scalar_one_or_none()
    created_snapshot = existing_snapshot is None
    if created_snapshot:
        session.add(
            FetchSnapshotRow(
                snapshot_id=f"snap-{doc.document_id}-{doc.content_hash[-16:]}",
                document_id=doc.document_id,
                original_url=str(doc.original_url),
                content_hash=doc.content_hash,
                fetch_method=doc.response.fetch_method,
                http_status=doc.response.http_status,
                fetched_at=doc.fetched_at,
            )
        )
    session.commit()
    return row, created_snapshot


def save_terms_snapshot(
    session: Session, *, source_id: str, terms_url: str, text: str, captured_at: datetime
) -> tuple[TermsSnapshotRow, bool]:
    """規約スナップショットを保存する。同一 source_id・同一内容なら追加しない。"""
    content_hash = "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()
    existing = session.execute(
        select(TermsSnapshotRow).where(
            TermsSnapshotRow.source_id == source_id,
            TermsSnapshotRow.content_hash == content_hash,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing, False
    row = TermsSnapshotRow(
        terms_snapshot_id=f"terms-{source_id}-{content_hash[-16:]}",
        source_id=source_id,
        terms_url=terms_url,
        content_hash=content_hash,
        text=text,
        captured_at=captured_at,
    )
    session.add(row)
    session.commit()
    return row, True


def get_document(session: Session, document_id: str) -> DocumentRow | None:
    return session.get(DocumentRow, document_id)


def list_snapshots(session: Session, document_id: str) -> list[FetchSnapshotRow]:
    return list(
        session.execute(
            select(FetchSnapshotRow)
            .where(FetchSnapshotRow.document_id == document_id)
            .order_by(FetchSnapshotRow.fetched_at)
        )
        .scalars()
        .all()
    )
