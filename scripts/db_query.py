"""db_query.py — ローカルSQLiteへの読み取り専用クエリ（観察レール — plan.md §1.3・§2.1）。

使い方: uv run scripts/db_query.py "SELECT * FROM episodes"
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

DB_PATH = Path("artifacts/history_radio.sqlite3")


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print('使い方: uv run scripts/db_query.py "SELECT ..."', file=sys.stderr)
        return 2
    if not DB_PATH.is_file():
        print(
            f"[db] {DB_PATH} が無い（先に `uv run scripts/dev.py up` でマイグレーション）",
            file=sys.stderr,
        )
        return 1

    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    try:
        cursor = conn.execute(argv[0])
        columns = [d[0] for d in cursor.description or []]
        if columns:
            print(" | ".join(columns))
        for row in cursor.fetchall():
            print(" | ".join(str(v) for v in row))
        return 0
    except sqlite3.Error as exc:
        print(f"[db] クエリ失敗: {exc}", file=sys.stderr)
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
