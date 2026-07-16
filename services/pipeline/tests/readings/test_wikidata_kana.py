"""test_wikidata_kana.py — §8.4 DoD: fixtureベースの読み取得とクエリ失敗時のfail-closedを固定する"""

import json

from history_radio.readings.wikidata_kana import fetch_kana_readings
from tests.ingest.mock_http import Disconnect, Reply, scripted_fetcher

_FIXTURE_OK = json.dumps(
    {
        "results": {
            "bindings": [
                {
                    "item": {"value": "http://www.wikidata.org/entity/Q193353"},
                    "kana": {"value": "さいごう たかもり"},
                },
                {
                    "item": {"value": "http://www.wikidata.org/entity/Q193353"},
                    "kana": {"value": "さいごう たかもり"},  # 重複行（別プロパティ経由）
                },
            ]
        }
    }
)


def test_kana_reading_is_fetched_and_katakanized() -> None:
    fetcher, _clock, requests = scripted_fetcher([Reply(text=_FIXTURE_OK)])
    entries = fetch_kana_readings(fetcher, "西郷隆盛", kind="person", fetched_at="2026-07-17")
    assert len(entries) == 1  # 重複読みは1件へ
    assert entries[0].reading == "サイゴウ タカモリ"
    assert entries[0].source_id == "wikidata-kana"
    assert entries[0].license == "CC0 1.0"
    assert "query.wikidata.org" in requests[0].url


def test_query_failure_returns_empty_instead_of_raising() -> None:
    """§8.4 検証: クエリ失敗時は例外を投げず、語はunresolved候補へ落ちる。"""
    fetcher, _clock, _requests = scripted_fetcher([Disconnect()], max_retries=0)
    assert fetch_kana_readings(fetcher, "西郷隆盛", kind="person", fetched_at="2026-07-17") == []


def test_http_error_returns_empty() -> None:
    fetcher, _clock, _requests = scripted_fetcher([Reply(status=403, text="forbidden")])
    assert fetch_kana_readings(fetcher, "誰か", kind="person", fetched_at="2026-07-17") == []


def test_malformed_payload_returns_empty() -> None:
    fetcher, _clock, _requests = scripted_fetcher([Reply(text='{"unexpected": true}')])
    assert fetch_kana_readings(fetcher, "誰か", kind="person", fetched_at="2026-07-17") == []


def test_no_kana_results_returns_empty() -> None:
    """P1814未登録（§8.1「読み未登録の項目も多い」）——空で返り解決器が次の層へ進む。"""
    empty = json.dumps({"results": {"bindings": []}})
    fetcher, _clock, _requests = scripted_fetcher([Reply(text=empty)])
    assert fetch_kana_readings(fetcher, "無名", kind="person", fetched_at="2026-07-17") == []


def test_non_kana_value_is_skipped() -> None:
    """ラテン文字等カタカナ化できない値は候補にしない（ReadingEntryの検証で落とす）。"""
    latin = json.dumps(
        {
            "results": {
                "bindings": [
                    {
                        "item": {"value": "http://www.wikidata.org/entity/Q1"},
                        "kana": {"value": "Saigo Takamori"},
                    }
                ]
            }
        }
    )
    fetcher, _clock, _requests = scripted_fetcher([Reply(text=latin)])
    assert fetch_kana_readings(fetcher, "西郷", kind="person", fetched_at="2026-07-17") == []
