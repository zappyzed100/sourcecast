"""gate_results.py — 自動検査ゲート結果の永続化（`publish_gate_results`・
仕様書§11・§13・§15・development-plan.md Phase 10タスク3）。

追記のみ（append-only）: この module は挿入・参照の関数しか持たない。更新・削除関数を
意図的に置かないことで、「同じepisode_id・revisionを再評価しても過去の評価結果が
消えない」契約を構造的に保証する（rights.pyと同じ方針）。「公開済み版から当時の
検査結果を再表示できる」（Phase 10タスク3 DoD）は、(episode_id, revision)で
検索することで満たす——`revision`は`PublishGateResult.revision`（評価対象の
`EpisodePageData.revision`）から来るため、episode_publisher.pyのバージョン管理と
同じ粒度で当時の検査結果を特定できる。

**「管理画面から追跡できる」という DoD の管理画面側UI配線は本コミットの対象外**
——apps/adminの実DB接続はPhase 11「Phase 2の画面を実DBと実ジョブへ接続」で扱う。
ここではその配線が使う永続化・参照関数を用意する。
"""

from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from history_radio.publish.publish_gate import GateCheckResult, PublishGateResult
from history_radio.store.orm import AuditEventRow, PublishGateResultRow


def _row_to_domain(row: PublishGateResultRow) -> PublishGateResult:
    checks_raw = json.loads(row.checks_json)
    checks = tuple(GateCheckResult.model_validate(c) for c in checks_raw)
    return PublishGateResult(
        episode_id=row.episode_id,
        revision=row.revision,
        rule_version=row.rule_version,
        publish_ready=row.publish_ready,
        checks=checks,
        artifact_hash=row.artifact_hash,
    )


def save_gate_result(
    session: Session, result: PublishGateResult, *, result_id: str, evaluated_at: datetime
) -> PublishGateResult:
    """`PublishGateResult` を1件追記し、対応する監査ログイベントも同時に記録する。

    仕様書§15「すべての公開・訂正・削除・権利判定変更を追記型監査ログへ記録する」に
    従い、publish_gate_results への挿入と audit_events への挿入を同一トランザクションで行う。
    """
    checks_json = json.dumps([c.model_dump(mode="json") for c in result.checks], ensure_ascii=False)
    session.add(
        PublishGateResultRow(
            result_id=result_id,
            episode_id=result.episode_id,
            revision=result.revision,
            rule_version=result.rule_version,
            publish_ready=result.publish_ready,
            checks_json=checks_json,
            artifact_hash=result.artifact_hash,
            evaluated_at=evaluated_at,
        )
    )
    session.add(
        AuditEventRow(
            event_id=f"audit-gate-{result_id}",
            entity_type="publish_gate_result",
            entity_id=result.episode_id,
            action="publish_gate_evaluated",
            actor="publish_gate",
            occurred_at=evaluated_at,
            detail=(
                f"revision={result.revision} publish_ready={result.publish_ready} "
                f"rule_version={result.rule_version}"
            ),
        )
    )
    session.commit()
    return result


def list_gate_results_for_episode(session: Session, episode_id: str) -> list[PublishGateResult]:
    """あるエピソードの全評価履歴を、評価時刻の古い順にすべて返す（再評価を含む）。"""
    rows = (
        session.execute(
            select(PublishGateResultRow)
            .where(PublishGateResultRow.episode_id == episode_id)
            .order_by(PublishGateResultRow.evaluated_at)
        )
        .scalars()
        .all()
    )
    return [_row_to_domain(row) for row in rows]


def latest_gate_result_for_revision(
    session: Session, episode_id: str, revision: int
) -> PublishGateResult | None:
    """指定revisionに対する最新の評価結果を返す（無ければ`None`）。

    development-plan.md Phase 10タスク3 DoD: 公開済み版から当時の検査結果を
    再表示できる——公開時のrevisionでこの関数を呼べば、その版に対する検査結果を得られる。
    """
    results = [
        r for r in list_gate_results_for_episode(session, episode_id) if r.revision == revision
    ]
    return results[-1] if results else None


__all__ = [
    "latest_gate_result_for_revision",
    "list_gate_results_for_episode",
    "save_gate_result",
]
