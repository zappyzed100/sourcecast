"""distribution_records.py — 外部配信結果のDB永続化（仕様書§10D・§15・
Phase 9タスク4・Phase 11タスク1「限定公開」）。

`publish/distribution_ledger.py`の`DistributionLedger`はインメモリ実装
（プロセス内・テスト用）——管理API経由の「限定公開」操作はプロセス再起動をまたいで
二重投稿を防ぐ必要があるため、同じインターフェースをDB永続化で実装する
`DbDistributionLedger`をここに置く（`dispatch()`はそのまま再利用し、
配信ロジック自体を再実装しない）。

`(episode_id, target)`単位の行は「直近の状態だけ」を保持する
（`DistributionLedger`と同じ意味論——同じ組み合わせへの再実行は上書きする）。
全試行の履歴は`save_distribution_record`が同一トランザクションで追記する
`AuditEventRow`側に残る（仕様書§15「すべての公開…を追記型監査ログへ記録する」）。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from history_radio.publish.distribution_ledger import (
    DistributionLedger,
    DistributionRecord,
    DistributionTarget,
)
from history_radio.store.orm import AuditEventRow, DistributionRecordRow


def _row_to_domain(row: DistributionRecordRow) -> DistributionRecord:
    return DistributionRecord(
        episode_id=row.episode_id,
        target=row.target,  # type: ignore[arg-type]
        status=row.status,  # type: ignore[arg-type]
        external_id=row.external_id,
        attempted_at=row.attempted_at,
        error_message=row.error_message,
    )


def get_distribution_record(
    session: Session, episode_id: str, target: DistributionTarget
) -> DistributionRecord | None:
    row = session.get(DistributionRecordRow, (episode_id, target))
    return _row_to_domain(row) if row is not None else None


def save_distribution_record(session: Session, record: DistributionRecord) -> DistributionRecord:
    """`(episode_id, target)`の行を最新の記録で置き換え、監査ログへ追記する。"""
    session.merge(
        DistributionRecordRow(
            episode_id=record.episode_id,
            target=record.target,
            status=record.status,
            external_id=record.external_id,
            attempted_at=record.attempted_at,
            error_message=record.error_message,
        )
    )
    session.add(
        AuditEventRow(
            event_id=f"audit-distribution-{record.episode_id}-{record.target}-{record.attempted_at}",
            entity_type="distribution_record",
            entity_id=record.episode_id,
            action=f"distribution_{record.status}",
            actor="distribution_ledger",
            occurred_at=datetime.fromisoformat(record.attempted_at),
            detail=(
                f"target={record.target} status={record.status} "
                f"external_id={record.external_id!r} error={record.error_message!r}"
            ),
        )
    )
    session.commit()
    return record


class DbDistributionLedger(DistributionLedger):
    """`DistributionLedger`と同じインターフェースをDB永続化で実装する。

    `publish/distribution_ledger.dispatch()`はこのサブクラスをそのまま受け取れる
    ——配信の意味論（成功後は再送しない・失敗は再試行可能）を再実装しない。
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, episode_id: str, target: DistributionTarget) -> DistributionRecord | None:
        return get_distribution_record(self._session, episode_id, target)

    def record_success(
        self, episode_id: str, target: DistributionTarget, external_id: str, attempted_at: str
    ) -> DistributionRecord:
        record = DistributionRecord(
            episode_id=episode_id,
            target=target,
            status="success",
            external_id=external_id,
            attempted_at=attempted_at,
        )
        return save_distribution_record(self._session, record)

    def record_failure(
        self, episode_id: str, target: DistributionTarget, error_message: str, attempted_at: str
    ) -> DistributionRecord:
        record = DistributionRecord(
            episode_id=episode_id,
            target=target,
            status="failed",
            attempted_at=attempted_at,
            error_message=error_message,
        )
        return save_distribution_record(self._session, record)


__all__ = ["DbDistributionLedger", "get_distribution_record", "save_distribution_record"]
