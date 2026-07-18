"""recovery.py — PC再起動・プロセスクラッシュ後の中断ジョブ検出（development-plan.md
Phase 12タスク4「PC再起動後に中断ジョブを検出し、二重実行せず再開または手動確認へ送る」）。

このシステムは単一プロセス・単一マシン前提（plan.md §1.3・store/db.pyのSQLite
単一writer前提）——分散ワーカーが存在しないため、「アプリ起動時点でstatus='running'の
ジョブが残っている」こと自体が「前回のプロセスが（`succeeded`/`failed`/`cancelled`へ
正しく遷移させる前に）異常終了した」ことの十分な証拠になる。ハートビートやPID記録は
不要——起動時の一括スキャンだけで検出できる。

**二重実行せず**（Phase 12タスク4 DoD）: 検出したジョブは自動で再実行しない。
`blocked`へ落として監査ログに理由を記録し、**手動確認へ送る**——操作者が
`cli.py resume`または管理画面の再実行ボタンで意図的に再開するまで、
このジョブの続きは走らない（jobs/runner.pyの`run_episode_generation_job()`は
現在の状態から続きを行う設計なので、再開時に工程を重複実行することもない
——仕様書§14「動画生成失敗：中間成果物を保持し、工程単位で再実行」と同じ考え方）。
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.orm import Session, sessionmaker

from history_radio.domain.models import Job
from history_radio.store.jobs import list_jobs, mark_blocked
from history_radio.store.orm import AuditEventRow

ORPHANED_JOB_REASON = (
    "サーバー再起動またはクラッシュにより中断された（起動時点でrunningのまま残っていた）"
    "——二重実行を避けるため自動再開はせず、手動確認へ送る"
)


def recover_orphaned_jobs(session_maker: sessionmaker[Session]) -> list[Job]:
    """起動時に1回呼ぶ。status='running'のまま残っているジョブをすべて`blocked`へ落とし、
    実際に変更したジョブの一覧を返す（0件なら前回は正常終了している）。
    仕様書§15の方針に従い、システム自身が操作者の代わりに行った状態変更として
    監査ログへも記録する。
    """
    with session_maker() as session:
        orphaned_ids = [job.job_id for job in list_jobs(session) if job.status == "running"]
        recovered: list[Job] = []
        for job_id in orphaned_ids:
            recovered.append(mark_blocked(session, job_id, error=ORPHANED_JOB_REASON))
            session.add(
                AuditEventRow(
                    event_id=f"audit-job-orphan-{job_id}-{uuid4().hex[:8]}",
                    entity_type="job",
                    entity_id=job_id,
                    action="orphan_recovered",
                    actor="system_startup",
                    occurred_at=datetime.now(timezone.utc),
                    detail=ORPHANED_JOB_REASON,
                )
            )
            session.commit()
        return recovered


__all__ = ["ORPHANED_JOB_REASON", "recover_orphaned_jobs"]
