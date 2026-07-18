"""events.py — ジョブ進捗のSSE配信（development-plan.md §3.2「ジョブ進捗はWebSocketでは
なくSSEを基本とする」・Phase 11タスク2）。

DBが正本のまま——配信側は状態を持たず、`jobs`/`job_log_entries`テーブルを
一定間隔でポーリングして配信するだけ（ジョブの実行自体はjobs/runner.pyが
別スレッドで行い、ここはそれを覗き見るだけの読み取り専用ストリーム）。
ジョブが終端状態（succeeded/failed/blocked/cancelled）へ達したら最後の1件を
送ってストリームを閉じる。

**非同期ジェネレータにしている理由（実機で踏んだ罠）**: 最初はこの関数を同期の
`time.sleep()`ループとして書いていた——FastAPIは同期`def`のパスオペレーションを
限られたスレッドプールで実行するため、SSE接続1本がジョブの生存期間（最大数秒）
まるごとスレッドを1つ占有し続けてしまい、同時に複数のSSE接続が開くとスレッドプールが
枯渇して`/dashboard`のようなDB無関係のエンドポイントまで応答不能になった
（Phase 11タスク2の開発中に実際に発生・再現）。`asyncio.sleep()`を使う非同期
ジェネレータならイベントループ上で協調的に待つだけでスレッドを占有しない。
"""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncIterator, Awaitable, Callable

from sqlalchemy.orm import Session, sessionmaker

from history_radio.store.jobs import TERMINAL_JOB_STATUSES, get_job, list_job_logs

DEFAULT_POLL_INTERVAL_SECONDS = 0.2


def _resolve_poll_interval_seconds() -> float:
    """`HISTORY_RADIO_JOB_SSE_POLL_SECONDS`環境変数（未指定時は`DEFAULT_POLL_INTERVAL_SECONDS`）。

    jobs/runner.pyの`_resolve_default_step_delay_seconds()`と同じ「環境変数で
    上書き可能・呼び出しのたびに再解決」方式——テストがポーリング間隔を0にできる。
    """
    raw = os.environ.get("HISTORY_RADIO_JOB_SSE_POLL_SECONDS")
    return float(raw) if raw else DEFAULT_POLL_INTERVAL_SECONDS


async def stream_job_events(
    session_maker: sessionmaker[Session],
    job_id: str,
    *,
    poll_interval_seconds: float | None = None,
    is_disconnected: Callable[[], Awaitable[bool]] | None = None,
    on_before_poll: Callable[[int], None] | None = None,
) -> AsyncIterator[str]:
    """`job_id`の状態・新規ログをSSE形式（`data: {...}\\n\\n`）で配信し続ける。

    毎回新しいセッションを開いて読む——同一セッションを使い回すと、SQLiteの
    読み取りトランザクションが最初に読んだ時点のスナップショットに固定され、
    別スレッド（jobs/runner.py）が書き込んだ最新値が見えなくなる（store/db.pyの
    WAL前提: 読み取りは書き込みをブロックしないが、セッション自体の再作成無しに
    「最新値を見る」ことは保証されない）。DB自体の読み取りは十分高速なローカル
    SQLiteのため、イベントループを直接ブロックして呼んでいる（スレッドプールへの
    委譲はしない——この規模の管理ツールでは不要な複雑化になる）。

    既に終端状態のジョブへ接続した場合も、最初の1件（保存済み全ログ込み）を
    送ってすぐ閉じる——ブラウザ再読込直後の再購読でも取りこぼしなく
    現在の正しい状態を受け取れる（Phase 11タスク2 DoD）。

    `is_disconnected`はクライアント切断検出用フック（FastAPIエンドポイントから
    `request.is_disconnected`を渡す）——ブラウザがページ遷移・再読込でSSE接続を
    切った後もサーバー側だけがポーリングを続けないようにする。

    `on_before_poll`はテスト専用フック（各ポーリング直前に0始まりの回数付きで
    呼ばれる）——テストがsleepに頼らず「2回目のポーリングまでにジョブが
    別スレッド相当で更新された」状況を決定的に再現するために使う
    （services/pipeline/tests/jobs/test_events.py）。
    """
    interval = (
        poll_interval_seconds
        if poll_interval_seconds is not None
        else _resolve_poll_interval_seconds()
    )
    last_seq = 0
    poll_count = 0
    while True:
        if is_disconnected is not None and await is_disconnected():
            return

        if on_before_poll is not None:
            on_before_poll(poll_count)
        poll_count += 1

        with session_maker() as session:
            job = get_job(session, job_id)
            new_logs = list_job_logs(session, job_id, since_seq=last_seq)
        if new_logs:
            last_seq = new_logs[-1].seq
        payload = {
            "job": job.model_dump(mode="json"),
            "logs": [log.model_dump(mode="json") for log in new_logs],
        }
        yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
        if job.status in TERMINAL_JOB_STATUSES:
            return
        await asyncio.sleep(interval)


__all__ = ["DEFAULT_POLL_INTERVAL_SECONDS", "stream_job_events"]
