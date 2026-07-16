"""test_manual_dictionary.py — §8.4 DoD: 不正エントリ拒否と文脈別複数読みの引き分けを固定する"""

from pathlib import Path

import pytest

from history_radio.readings.manual_dictionary import (
    ManualDictionaryError,
    load_manual_dictionary,
)

REPO_ROOT = Path(__file__).resolve().parents[4]
MANUAL_YAML = REPO_ROOT / "config" / "readings" / "manual.yaml"


def test_real_manual_yaml_loads_and_has_context_dependent_readings() -> None:
    """判官=ホウガン（源平合戦）/ハンガン（現代）がcontextキーで正しく引き分けられる。"""
    entries = load_manual_dictionary(MANUAL_YAML, fetched_at="2026-07-17")
    hangan_entries = {e.context: e.reading for e in entries if e.surface == "判官"}
    assert hangan_entries == {"源平合戦": "ホウガン", "現代": "ハンガン"}


def test_context_free_entry_has_single_default() -> None:
    entries = load_manual_dictionary(MANUAL_YAML, fetched_at="2026-07-17")
    daijodaijin = [e for e in entries if e.surface == "太政大臣"]
    assert len(daijodaijin) == 1
    assert daijodaijin[0].context is None


def test_duplicate_surface_and_context_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "manual.yaml"
    path.write_text(
        """entries:
  - surface: 判官
    reading: ホウガン
    kind: office
    context: 源平合戦
    confidence: 1.0
  - surface: 判官
    reading: ホウガン
    kind: office
    context: 源平合戦
    confidence: 1.0
""",
        encoding="utf-8",
    )
    with pytest.raises(ManualDictionaryError, match="重複登録"):
        load_manual_dictionary(path, fetched_at="2026-07-17")


def test_two_default_readings_for_same_surface_are_rejected(tmp_path: Path) -> None:
    """§8.4 検証: 不正エントリ（既定読みが2件）を起動時に拒否する——
    2件目の(surface, context=None)は必ず重複キーとして検出される。"""
    path = tmp_path / "manual.yaml"
    path.write_text(
        """entries:
  - surface: 東京
    reading: トウキョウ
    kind: place
    context: null
    confidence: 1.0
  - surface: 東京
    reading: トーキョー
    kind: place
    context: null
    confidence: 0.5
""",
        encoding="utf-8",
    )
    with pytest.raises(ManualDictionaryError, match="重複登録"):
        load_manual_dictionary(path, fetched_at="2026-07-17")


def test_invalid_kind_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "manual.yaml"
    path.write_text(
        """entries:
  - surface: 何か
    reading: ナニカ
    kind: not-a-real-kind
    context: null
    confidence: 1.0
""",
        encoding="utf-8",
    )
    with pytest.raises(ManualDictionaryError):
        load_manual_dictionary(path, fetched_at="2026-07-17")


def test_empty_file_loads_as_empty_list(tmp_path: Path) -> None:
    path = tmp_path / "manual.yaml"
    path.write_text("entries: []\n", encoding="utf-8")
    assert load_manual_dictionary(path, fetched_at="2026-07-17") == []
