"""sources_config.py — 辞書ソースのメタデータ（config/readings/sources.yaml — §8.4）。

store/config_loader.py と同じパターン（Pydanticで形・ローダーで横断検証）。
ライセンス表記（attribution_text）の欠けたソースは登録できない——
THIRD_PARTY_NOTICES.md の生成元がここなので、ここで欠けると公開表記も欠ける
（fail closed の位置をデータ入口に置く）。
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import Field, ValidationError

from history_radio.domain.base import SchemaModel
from history_radio.readings.entry import ReadingEntry


class ReadingSourcesError(ValueError):
    """config/readings/sources.yaml の検証失敗、または未登録ソースの参照。"""


class ReadingSourceMeta(SchemaModel):
    """辞書ソース1件のメタデータ（§8.1の表の機械可読版）。"""

    source_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    license: str = Field(min_length=1)
    license_url: str | None = None
    url: str = Field(min_length=1)
    # 公開サイト・THIRD_PARTY_NOTICES.md に載せる出典表記（欠けたら登録不可）
    attribution_text: str = Field(min_length=1)
    # 派生辞書としての再配布可否（JMnedictはSA継承のため専用テーブル分離 — §8.3）
    redistribution_allowed: bool
    # 完全自作（このツールの資産）か外部由来か（§8.3: 混ざらないよう分離管理）
    first_party: bool
    notes: str = ""


class ReadingSourcesFile(SchemaModel):
    sources: list[ReadingSourceMeta]


def load_reading_sources(path: Path) -> list[ReadingSourceMeta]:
    try:
        with path.open(encoding="utf-8") as f:
            raw = yaml.safe_load(f)
    except (OSError, yaml.YAMLError) as exc:
        raise ReadingSourcesError(f"{path}: 読み込み失敗: {exc}") from exc
    try:
        parsed = ReadingSourcesFile.model_validate(raw)
    except ValidationError as exc:
        raise ReadingSourcesError(f"{path}: {exc}") from exc
    seen: set[str] = set()
    for s in parsed.sources:
        if s.source_id in seen:
            raise ReadingSourcesError(f"{path}: source_id重複: {s.source_id}")
        seen.add(s.source_id)
    return parsed.sources


def validate_entries_against_sources(
    entries: list[ReadingEntry], sources: list[ReadingSourceMeta]
) -> None:
    """未登録の source_id を持つ ReadingEntry を拒否する（§8.4 検証）。"""
    known = {s.source_id for s in sources}
    unknown = sorted({e.source_id for e in entries} - known)
    if unknown:
        raise ReadingSourcesError(
            f"sources.yaml に未登録の source_id: {unknown}"
            "（先にソースのライセンス・出典表記を登録する — §8.4）"
        )
