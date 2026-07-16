"""collector.py — 収集の入口（仕様書§7・Phase 4）: approved限定・権利判定ゲート・保存。

順序の契約（development-plan.md Phase 3「事実収集より先に判定器を完成させる」）:
1. `status: approved` のソースだけを収集する——approvedでなければ**取得自体を行わない**
   （candidateのソースへHTTPを撃たない。§5.14の運用区分をコードで強制する）。
2. 取得した資料はその場で権利判定（rights/engine.py）し、判定を追記保存する
   （§5A「年数計算は資料取得のたびに再計算」——判定の使い回しをしない）。
3. 本文（full_text）を永続化するのは判定が `allow_public_use` の資料のみ。
   candidate はそもそも取得されず、internal_research_only 等はメタデータ・抜粋・
   ハッシュだけが残る（Phase 4タスク「権利判定を通過しない本文を保存しない」）。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from history_radio.domain.models import RightsDecisionValue
from history_radio.ingest.adapter import SourceAdapter
from history_radio.ingest.crawl_control import PoliteFetcher
from history_radio.rights.engine import build_rights_decision
from history_radio.store.config_schemas import SourceRegistryEntry
from history_radio.store.documents import save_document
from history_radio.store.rights import save_rights_decision


class SourceNotApprovedError(RuntimeError):
    """approved以外のソースを収集しようとした（取得は行われていない）。"""

    def __init__(self, source_id: str, status: str) -> None:
        super().__init__(
            f"ソース {source_id!r} は status={status!r} のため収集しない"
            "（approvedのみ収集 — §5.14・Phase 4）"
        )
        self.source_id = source_id
        self.status = status


@dataclass(frozen=True, slots=True)
class CollectOutcome:
    """収集1件の結果（何が保存され、何が保存されなかったかを呼び出し側へ明示する）。"""

    document_id: str
    decision: RightsDecisionValue
    stored_full_text: bool
    created_new_snapshot: bool


def collect_document(
    session: Session,
    *,
    adapter: SourceAdapter,
    fetcher: PoliteFetcher,
    resource_ref: str,
    source: SourceRegistryEntry,
    decision_id: str | None = None,
) -> CollectOutcome:
    """1資料を取得→権利判定→保存する。approved以外のソースは取得前に拒否する。"""
    if source.status != "approved":
        raise SourceNotApprovedError(source.source_id, source.status)

    doc = adapter.fetch(fetcher, resource_ref)

    decision = build_rights_decision(
        decision_id=decision_id or f"dec-{uuid.uuid4().hex}",
        document_id=doc.document_id,
        normalized_license_id=doc.rights.normalized_license_id,
        # source_registry の third_party_exception="allow" は「第三者著作物の例外表示が
        # 存在し得る」の意味（§5.2のフィールド化）——engine側では例外あり扱いにして
        # manual_review へ倒す。"deny"（混入なしを確認済み）のみ自動判定に乗せる。
        third_party_exception=(source.third_party_exception == "allow"),
        terms_fetch_failed=not doc.response.terms_checked,
    )
    save_rights_decision(session, decision)

    # 本文の永続化は allow_public_use かつ資料自体の保存許可がある場合のみ（fail closed）
    store_full_text = (
        decision.decision == "allow_public_use" and doc.storage_permission == "granted"
    )
    _row, created_snapshot = save_document(session, doc, store_full_text=store_full_text)

    return CollectOutcome(
        document_id=doc.document_id,
        decision=decision.decision,
        stored_full_text=store_full_text and doc.full_text is not None,
        created_new_snapshot=created_snapshot,
    )
