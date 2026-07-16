"""era_dictionary.py — 元号読み辞書のローダーと検証（development-plan.md §8.4）。

config/readings/eras.yaml が正本（年代・QIDはWikidata由来、読みは自作——§8.1）。
検証: 元号名の一意性・年代の整合（start<=end）・大宝（701年）以降の連続性
（改元は年の途中で起きるため±2年の重なり/隙間まで許容。701年より前は元号の
空白期間が史実として存在するため連続性を要求しない）・無期限元号（現元号）は1件のみ。

verified: false のエントリは confidence 0.9、人手検証済み（true）は 1.0 として
ReadingEntry へ変換する——§8.4「人手で一度検証」を機械的に区別可能にする。
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import Field, ValidationError

from history_radio.domain.base import SchemaModel
from history_radio.readings.entry import ReadingEntry

_CONTINUITY_FROM_YEAR = 701  # 大宝——これ以降は元号が連続する（史実）
_MAX_GAP_YEARS = 2  # 改元は年の途中——年単位比較の丸めを吸収する許容幅

_ERAS_YAML_REPO_PATH = "config/readings/eras.yaml"


class EraDictionaryError(ValueError):
    """eras.yaml の検証失敗（重複・年代不整合・連続性の破れ等）。"""


class EraRecord(SchemaModel):
    name: str = Field(min_length=1)
    reading: str = Field(min_length=1)
    start_year: int = Field(ge=600)
    end_year: int | None = Field(default=None, ge=600)
    wikidata_qid: str = Field(pattern=r"^Q\d+$")
    verified: bool


class _ErasFile(SchemaModel):
    eras: list[EraRecord]


def load_era_dictionary(path: Path) -> list[EraRecord]:
    try:
        with path.open(encoding="utf-8") as f:
            raw = yaml.safe_load(f)
    except (OSError, yaml.YAMLError) as exc:
        raise EraDictionaryError(f"{path}: 読み込み失敗: {exc}") from exc
    try:
        parsed = _ErasFile.model_validate(raw)
    except ValidationError as exc:
        raise EraDictionaryError(f"{path}: {exc}") from exc
    _validate(parsed.eras, path)
    return sorted(parsed.eras, key=lambda e: (e.start_year, e.name))


def _validate(eras: list[EraRecord], path: Path) -> None:
    seen: set[str] = set()
    for e in eras:
        if e.name in seen:
            raise EraDictionaryError(f"{path}: 元号名の重複: {e.name}")
        seen.add(e.name)
        if e.end_year is not None and e.end_year < e.start_year:
            raise EraDictionaryError(
                f"{path}: {e.name}: end_year({e.end_year}) < start_year({e.start_year})"
            )

    open_ended = [e.name for e in eras if e.end_year is None]
    if len(open_ended) != 1:
        raise EraDictionaryError(
            f"{path}: 無期限（end_year: null）の元号は現元号1件のみ: {open_ended}"
        )

    # 大宝以降の連続性: start順に走査し、直前までの最大end年から2年超の空白を拒否
    ordered = sorted(
        (e for e in eras if e.start_year >= _CONTINUITY_FROM_YEAR),
        key=lambda e: e.start_year,
    )
    max_end: int | None = None
    for e in ordered:
        if max_end is not None and e.start_year > max_end + _MAX_GAP_YEARS:
            raise EraDictionaryError(
                f"{path}: {e.name}({e.start_year}〜)の前に{max_end}年までしか元号が無い"
                f"（{_CONTINUITY_FROM_YEAR}年以降の空白 — 欠落の疑い）"
            )
        if e.end_year is not None:
            max_end = e.end_year if max_end is None else max(max_end, e.end_year)


def to_reading_entries(eras: list[EraRecord], *, fetched_at: str) -> list[ReadingEntry]:
    """元号辞書を共通のReadingEntryへ変換する（source_id=era-dictionary固定）。"""
    return [
        ReadingEntry(
            surface=e.name,
            reading=e.reading,
            kind="era",
            context=None,
            confidence=1.0 if e.verified else 0.9,
            source_id="era-dictionary",
            source_url=_ERAS_YAML_REPO_PATH,
            license="本プロジェクトの資産",
            fetched_at=fetched_at,
        )
        for e in eras
    ]
