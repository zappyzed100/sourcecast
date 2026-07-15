"""db.py — SQLite接続の基盤（WAL・busy_timeout・単一writer前提 — plan.md §1.3・Phase 1）。

WAL(Write-Ahead Logging)モードは複数の読み取りと1つの書き込みを同時に許す
（読み取りは書き込みをブロックしない）。busy_timeoutは、書き込みロック競合が
起きた側を即エラーにせず一定時間リトライ待機させる。単一writerはSQLite自体の
制約（同時に書き込めるconnectionは1つ）をそのまま設計に採用しているだけで、
アプリ側で追加の排他制御は行わない——楽観ロック（revision列）で上書き競合を検出する
（plan.md §2.3・store/episodes.py）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

DEFAULT_BUSY_TIMEOUT_MS = 5_000


def _set_sqlite_pragma(
    dbapi_connection: Any, _connection_record: Any, *, busy_timeout_ms: int
) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute(f"PRAGMA busy_timeout={busy_timeout_ms}")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def create_sqlite_engine(
    db_path: Path | str, *, busy_timeout_ms: int = DEFAULT_BUSY_TIMEOUT_MS
) -> Engine:
    """WAL・busy_timeoutを設定したSQLiteエンジンを作る。

    `db_path` が ":memory:" の場合はインメモリDB（テスト用。プロセス内の複数
    connectionで共有するには呼び出し側で単一connectionを使い回す必要がある）。
    """
    url = f"sqlite:///{db_path}"
    engine = create_engine(url, future=True)

    def _on_connect(conn: Any, rec: Any) -> None:
        _set_sqlite_pragma(conn, rec, busy_timeout_ms=busy_timeout_ms)

    event.listen(engine, "connect", _on_connect)
    return engine


def session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)
