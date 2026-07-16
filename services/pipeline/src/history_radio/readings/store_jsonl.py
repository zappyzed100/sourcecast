"""store_jsonl.py — 読みエントリのソース別JSONL保存（development-plan.md §8.3・§8.4）。

「データソースごとに別テーブルで保持」の実装。1ソース=1ファイル
（artifacts/readings/<source_id>.jsonl）とし、**ファイルのsource_idと一致しない
エントリの書き込みを拒否する**——JMnedict由来（CC BY-SA）のレコードが他ソースの
テーブルへ紛れ込む経路を構造的に塞ぐ（SA継承を派生辞書全体へ広げない）。
"""

from __future__ import annotations

import json
from pathlib import Path

from history_radio.readings.entry import ReadingEntry


class SourceMixingError(ValueError):
    """ソース別テーブルへ別ソースのエントリを書こうとした（§8.3違反）。"""


def path_for_source(base_dir: Path, source_id: str) -> Path:
    return base_dir / f"{source_id}.jsonl"


def save_entries(base_dir: Path, source_id: str, entries: list[ReadingEntry]) -> Path:
    """ソース別ファイルへ全件書き込む（洗い替え）。source_id不一致は1件でも拒否。"""
    mismatched = sorted({e.source_id for e in entries if e.source_id != source_id})
    if mismatched:
        raise SourceMixingError(
            f"{source_id} のテーブルへ別ソース {mismatched} のエントリは書けない"
            "（ソース別分離 — §8.3）"
        )
    base_dir.mkdir(parents=True, exist_ok=True)
    path = path_for_source(base_dir, source_id)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for e in entries:
            f.write(e.model_dump_json() + "\n")
    return path


def load_entries(base_dir: Path, source_id: str) -> list[ReadingEntry]:
    """ソース別ファイルから読み込む。ファイル内のsource_id不一致も拒否（fail closed）。"""
    path = path_for_source(base_dir, source_id)
    entries: list[ReadingEntry] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            entry = ReadingEntry.model_validate(json.loads(line))
            if entry.source_id != source_id:
                raise SourceMixingError(
                    f"{path.name} 内に別ソース {entry.source_id!r} のエントリが混入している"
                )
            entries.append(entry)
    return entries
