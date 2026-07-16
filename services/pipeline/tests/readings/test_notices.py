"""test_notices.py — §8.4基盤 DoD: NOTICES生成の決定性・追加反映・ドリフト検出を固定する"""

from pathlib import Path

from history_radio.readings.notices import build_notices
from history_radio.readings.sources_config import ReadingSourceMeta, load_reading_sources

REPO_ROOT = Path(__file__).resolve().parents[4]


def _sources() -> list[ReadingSourceMeta]:
    return load_reading_sources(REPO_ROOT / "config" / "readings" / "sources.yaml")


def test_committed_notices_match_regeneration() -> None:
    """ドリフト検査: sources.yamlだけ変えて再生成し忘れるとここで落ちる。"""
    committed = (REPO_ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    assert committed == build_notices(_sources())


def test_adding_a_source_adds_its_attribution_line() -> None:
    """§8.4 検証: sources.yamlにソースを1件追加すると出典行が増える。"""
    sources = _sources()
    added = [
        *sources,
        ReadingSourceMeta.model_validate(
            {
                "source_id": "new-dict",
                "name": "新辞書",
                "license": "CC0",
                "url": "https://example.org/new",
                "attribution_text": "新辞書（テスト用）",
                "redistribution_allowed": True,
                "first_party": False,
            }
        ),
    ]
    before = build_notices(sources)
    after = build_notices(added)
    assert "新辞書（テスト用）" not in before
    assert "新辞書（テスト用）" in after


def test_generation_is_deterministic() -> None:
    sources = _sources()
    assert build_notices(sources) == build_notices(list(reversed(sources)))


def test_first_party_and_third_party_are_separated() -> None:
    """§8.3: 自作資産と外部由来が混ざらない——別セクションで出力される。"""
    text = build_notices(_sources())
    third_party_section = text.split("## 自作データ")[0]
    first_party_section = text.split("## 自作データ")[1]
    assert "SudachiDict" in third_party_section
    assert "手動修正辞書" in first_party_section
    assert "SudachiDict" not in first_party_section
