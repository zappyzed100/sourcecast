"""fetch_manifest.py — 辞書取得の再現性記録（development-plan.md §8.4）。

外部辞書取得スクリプトの実行結果（取得日・件数・ハッシュ）を記録し、再実行時の
差分検出を可能にする。ハッシュはエントリ集合を安定ソートしてから計算するため、
**同一内容なら取得順序が変わってもハッシュは変わらない**（同一入力での再取得が
同一ハッシュになる契約——store/documents.pyのcontent_hash重複抑制と同じ考え方）。
"""

from __future__ import annotations

import hashlib

from history_radio.domain.base import SchemaModel
from history_radio.readings.entry import ReadingEntry


class FetchManifestEntry(SchemaModel):
    source_id: str
    fetched_at: str
    entry_count: int
    content_hash: str


def _content_hash(entries: list[ReadingEntry]) -> str:
    serialized = sorted(e.model_dump_json() for e in entries)
    digest = hashlib.sha256("\n".join(serialized).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def build_fetch_manifest(
    source_id: str, entries: list[ReadingEntry], *, fetched_at: str
) -> FetchManifestEntry:
    """1回分の取得結果からマニフェストを作る。"""
    return FetchManifestEntry(
        source_id=source_id,
        fetched_at=fetched_at,
        entry_count=len(entries),
        content_hash=_content_hash(entries),
    )
