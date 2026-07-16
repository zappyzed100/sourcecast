"""test_entry.py — §8.4基盤 DoD: 読みエントリの型検査（未知キー・欠落・カナ統一）を固定する"""

from typing import Any

import pytest
from pydantic import ValidationError

from history_radio.readings.entry import ReadingEntry


def _entry(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "surface": "判官",
        "reading": "ホウガン",
        "kind": "office",
        "context": "源平合戦",
        "confidence": 0.9,
        "source_id": "manual-dictionary",
        "source_url": "config/readings/manual.yaml",
        "license": "本プロジェクトの資産",
        "fetched_at": "2026-07-17",
    }
    base.update(overrides)
    return base


def test_valid_entry_is_accepted() -> None:
    entry = ReadingEntry.model_validate(_entry())
    assert entry.reading == "ホウガン"


def test_context_dependent_readings_are_distinct_rows() -> None:
    """同一表記の文脈依存複数読み（判官=ホウガン/ハンガン）は行を分けて表現できる。"""
    houga = ReadingEntry.model_validate(_entry(context="源平合戦", reading="ホウガン"))
    hanga = ReadingEntry.model_validate(_entry(context="現代", reading="ハンガン"))
    assert houga.surface == hanga.surface
    assert houga.reading != hanga.reading


@pytest.mark.parametrize(
    "missing", ["surface", "reading", "kind", "confidence", "source_id", "license", "fetched_at"]
)
def test_missing_required_field_is_rejected(missing: str) -> None:
    payload = _entry()
    del payload[missing]
    with pytest.raises(ValidationError):
        ReadingEntry.model_validate(payload)


def test_unknown_field_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ReadingEntry.model_validate(_entry(surprise="x"))


@pytest.mark.parametrize("bad_reading", ["ほうがん", "hougan", "判官", "ホウガン(判官)"])
def test_non_katakana_reading_is_rejected(bad_reading: str) -> None:
    """読みはカタカナ統一（VOICEVOX注入形式）——ひらがな・ローマ字・漢字混じりを拒否。"""
    with pytest.raises(ValidationError, match="カタカナ"):
        ReadingEntry.model_validate(_entry(reading=bad_reading))


@pytest.mark.parametrize("bad_confidence", [-0.1, 1.1])
def test_out_of_range_confidence_is_rejected(bad_confidence: float) -> None:
    with pytest.raises(ValidationError):
        ReadingEntry.model_validate(_entry(confidence=bad_confidence))
