"""db.py — 管理APIのDB接続（仕様書§12・development-plan.md Phase 11タスク1）。

DBパスは環境変数`HISTORY_RADIO_DB_PATH`で指定する。未指定時はリポジトリ直下の
`data/history_radio.sqlite3`を既定値にする（`data/`は`.gitignore`の`*.sqlite3`
パターンで実行時ファイルとして除外される）。

エンジン・セッションファクトリの生成は`get_session()`が初めて呼ばれた時点まで遅延する
——本moduleを import しただけでファイルを作成しない（テストは`app.dependency_overrides`
で`get_session`を差し替えるため、この遅延初期化パスに触れることが無い）。
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from history_radio.store.db import create_sqlite_engine, session_factory
from history_radio.store.orm import Base

DEFAULT_DB_PATH = Path("data/history_radio.sqlite3")

_engine: Engine | None = None
_session_maker: sessionmaker[Session] | None = None


def _resolve_db_path() -> Path:
    raw = os.environ.get("HISTORY_RADIO_DB_PATH")
    return Path(raw) if raw else DEFAULT_DB_PATH


def _get_session_maker() -> sessionmaker[Session]:
    global _engine, _session_maker
    if _session_maker is None:
        db_path = _resolve_db_path()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        _engine = create_sqlite_engine(db_path)
        Base.metadata.create_all(_engine)
        _session_maker = session_factory(_engine)
    return _session_maker


def get_session() -> Iterator[Session]:
    session_maker = _get_session_maker()
    session = session_maker()
    try:
        yield session
    finally:
        session.close()


def get_session_maker() -> sessionmaker[Session]:
    """バックグラウンドスレッド（jobs/runner.py — Phase 11タスク2）がリクエストの
    スコープを超えて自前のセッションを作るための公開アクセサ。`get_session()`と
    同じ遅延初期化エンジンを共有する。
    """
    return _get_session_maker()


def get_db_path() -> Path:
    """管理API・CLI（cli.py — Phase 11タスク4）が同じDBファイルを指すことを保証する
    公開アクセサ。`HISTORY_RADIO_DB_PATH`環境変数を`_resolve_db_path()`と同じ規則で解決する。
    """
    return _resolve_db_path()
