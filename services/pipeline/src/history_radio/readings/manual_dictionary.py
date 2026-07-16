"""manual_dictionary.py — 手動修正辞書のローダー（development-plan.md §8.4）。

`config/readings/manual.yaml`——人間が検証した正。ReadingEntry型をそのまま使う
（surface/reading/kind/context/confidence はすでに§8.4基盤で定義済み）。

文脈依存の複数読み（例: 判官=ホウガン〔源平合戦〕/ハンガン〔現代〕）を表現できるが、
同一 surface・同一 context（`None`を含む）の重複登録は起動時に拒否する（fail closed）。
`context=None`（文脈非依存の既定読み）は surface ごとに1件しか登録できない——
2件目を登録しようとすると、必ず同じ (surface, context=None) キーで重複検出に掛かる
（既定読みが複数登録されて「どちらが既定か決められない」状態は、この重複検出だけで
構造的に排除される——別立ての検査は要らない）。
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import Field, ValidationError

from history_radio.domain.base import SchemaModel
from history_radio.readings.entry import ReadingEntry

_SOURCE_ID = "manual-dictionary"
_LICENSE = "本プロジェクトの資産"
_SOURCE_URL = "config/readings/manual.yaml"


class ManualDictionaryError(ValueError):
    """manual.yaml の検証失敗（重複エントリ・曖昧な既定読み等）。"""


class _RawManualEntry(SchemaModel):
    """manual.yamlの1エントリの生の形（出所フィールドを注入する前）。"""

    surface: str = Field(min_length=1)
    reading: str = Field(min_length=1)
    kind: str
    context: str | None = None
    confidence: float


class _RawManualFile(SchemaModel):
    entries: list[_RawManualEntry]


def load_manual_dictionary(path: Path, *, fetched_at: str) -> list[ReadingEntry]:
    try:
        with path.open(encoding="utf-8") as f:
            raw = yaml.safe_load(f)
    except (OSError, yaml.YAMLError) as exc:
        raise ManualDictionaryError(f"{path}: 読み込み失敗: {exc}") from exc

    try:
        parsed = _RawManualFile.model_validate(raw or {"entries": []})
    except ValidationError as exc:
        raise ManualDictionaryError(f"{path}: {exc}") from exc

    entries: list[ReadingEntry] = []
    for i, item in enumerate(parsed.entries):
        try:
            entries.append(
                ReadingEntry(
                    surface=item.surface,
                    reading=item.reading,
                    kind=item.kind,  # type: ignore[arg-type]
                    context=item.context,
                    confidence=item.confidence,
                    source_id=_SOURCE_ID,
                    source_url=_SOURCE_URL,
                    license=_LICENSE,
                    fetched_at=fetched_at,
                )
            )
        except ValidationError as exc:
            raise ManualDictionaryError(f"{path}: entries[{i}]の検証失敗: {exc}") from exc

    _validate_no_duplicates(entries, path)
    return entries


def _validate_no_duplicates(entries: list[ReadingEntry], path: Path) -> None:
    seen: set[tuple[str, str | None]] = set()
    for e in entries:
        key = (e.surface, e.context)
        if key in seen:
            raise ManualDictionaryError(f"{path}: {e.surface!r}（context={e.context!r}）の重複登録")
        seen.add(key)
