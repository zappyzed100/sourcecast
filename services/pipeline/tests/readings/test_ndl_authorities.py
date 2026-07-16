"""test_ndl_authorities.py — §8.4 DoD: 出典表示付与とクエリ失敗時のfail-closedを固定する"""

import json

from history_radio.readings.ndl_authorities import fetch_ndl_authority_readings
from tests.ingest.mock_http import Disconnect, Reply, scripted_fetcher

# 実APIから記録した縮約フィクスチャ（2026-07-17: id.ndl.go.jp/auth/ndla/sparql・
# id.ndl.go.jp/auth/ndlna/00064796.json）
_SEARCH_RESPONSE = json.dumps(
    {
        "results": {
            "bindings": [
                {
                    "s": {"value": "http://id.ndl.go.jp/auth/ndlna/00064796"},
                    "label": {"value": "西郷, 隆盛, 1827-1877"},
                },
                {
                    "s": {"value": "http://id.ndl.go.jp/auth/ndlna/001321463"},
                    "label": {"value": "西郷隆盛遺訓研究会"},  # 正規化しても不一致→除外
                },
            ]
        }
    }
)

_ENTITY_RESPONSE = json.dumps(
    {
        "prefLabel": {
            "literalForm": "西郷, 隆盛, 1827-1877",
            "transcription": "サイゴウ, タカモリ, 1827-1877",
        },
        "altLabel": [
            {"literalForm": "西郷, 南洲", "transcription": "サイゴウ, ナンシュウ"},
            {"literalForm": "西郷, 隆永"},  # transcriptionなし→スキップ
        ],
    }
)


def test_matching_entity_yields_reading_with_dates_stripped() -> None:
    fetcher, _clock, requests = scripted_fetcher(
        [Reply(text=_SEARCH_RESPONSE), Reply(text=_ENTITY_RESPONSE)]
    )
    entries = fetch_ndl_authority_readings(
        fetcher, "西郷隆盛", kind="person", fetched_at="2026-07-17"
    )
    by_surface = {e.surface: e for e in entries}
    assert by_surface["西郷隆盛"].reading == "サイゴウタカモリ"
    assert by_surface["西郷隆盛"].source_id == "ndl-web-authorities"
    assert "id.ndl.go.jp/auth/ndla/sparql" in requests[0].url


def test_alt_label_reading_is_included() -> None:
    """§8.1: 別名の読みも取得する。"""
    fetcher, _clock, _requests = scripted_fetcher(
        [Reply(text=_SEARCH_RESPONSE), Reply(text=_ENTITY_RESPONSE)]
    )
    entries = fetch_ndl_authority_readings(
        fetcher, "西郷隆盛", kind="person", fetched_at="2026-07-17"
    )
    surfaces = {e.surface for e in entries}
    assert "西郷南洲" in surfaces


def test_non_matching_organization_entity_is_excluded() -> None:
    """姓名分割形式でない団体名は正規化しても一致せず候補から除外される。"""
    fetcher, _clock, _requests = scripted_fetcher(
        [Reply(text=_SEARCH_RESPONSE), Reply(text=_ENTITY_RESPONSE)]
    )
    entries = fetch_ndl_authority_readings(
        fetcher, "西郷隆盛", kind="person", fetched_at="2026-07-17"
    )
    assert all("研究会" not in e.surface for e in entries)


def test_no_search_results_returns_empty() -> None:
    empty = json.dumps({"results": {"bindings": []}})
    fetcher, _clock, _requests = scripted_fetcher([Reply(text=empty)])
    assert (
        fetch_ndl_authority_readings(fetcher, "無名人物", kind="person", fetched_at="2026-07-17")
        == []
    )


def test_search_failure_returns_empty_instead_of_raising() -> None:
    """§8.4 fail-closed契約: 通信失敗時は例外を投げずunresolved候補へ落とす。"""
    fetcher, _clock, _requests = scripted_fetcher([Disconnect()], max_retries=0)
    assert (
        fetch_ndl_authority_readings(fetcher, "西郷隆盛", kind="person", fetched_at="2026-07-17")
        == []
    )


def test_entity_fetch_failure_returns_empty() -> None:
    fetcher, _clock, _requests = scripted_fetcher(
        [Reply(text=_SEARCH_RESPONSE), Reply(status=500, text="error")]
    )
    assert (
        fetch_ndl_authority_readings(fetcher, "西郷隆盛", kind="person", fetched_at="2026-07-17")
        == []
    )


def test_malformed_entity_json_returns_empty() -> None:
    fetcher, _clock, _requests = scripted_fetcher(
        [Reply(text=_SEARCH_RESPONSE), Reply(text='{"unexpected": true}')]
    )
    entries = fetch_ndl_authority_readings(
        fetcher, "西郷隆盛", kind="person", fetched_at="2026-07-17"
    )
    assert entries == []


def test_short_name_returns_empty_without_network_call() -> None:
    """1文字の検索は検索キー生成が成立しないため、通信せず空を返す。"""
    fetcher, _clock, requests = scripted_fetcher([Reply(text=_SEARCH_RESPONSE)])
    assert fetch_ndl_authority_readings(fetcher, "西", kind="person", fetched_at="x") == []
    assert requests == []
