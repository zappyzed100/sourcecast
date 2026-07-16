"""wikidata_kana.py — Wikidata読みアダプタ（development-plan.md §8.4。P1814: 仮名表記）。

歴史人物・歴史地名の読み補完（§8.1。CC0）。SPARQLで日本語ラベル一致の項目から
P1814（name in kana）を引く。取得はPoliteFetcher経由（レート制限・タイムアウト・
リトライはcrawl_control層の責務——§7.3と同じレール）。

fail-closed規約（§8.4 検証）: クエリ失敗・応答不正では**例外を上げず空リストを返す**
——呼び出し側（解決器）はその語を`unresolved`として公開前レビューへ回す。
LLMに読みを推測させる代替経路は存在しない（§8.2）。
"""

from __future__ import annotations

from typing import Any

from history_radio.ingest.crawl_control import FetchBlockedError, PoliteFetcher
from history_radio.readings.entry import ReadingEntry, ReadingKind
from history_radio.readings.jmnedict import hiragana_to_katakana

_SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"

_QUERY_TEMPLATE = """SELECT ?item ?kana WHERE {{
  ?item rdfs:label "{label}"@ja .
  ?item wdt:P1814 ?kana .
}} LIMIT 10"""


def _build_url(label: str) -> str:
    from urllib.parse import urlencode

    query = _QUERY_TEMPLATE.format(label=label.replace('"', ""))
    return f"{_SPARQL_ENDPOINT}?{urlencode({'query': query, 'format': 'json'})}"


def fetch_kana_readings(
    fetcher: PoliteFetcher, surface: str, *, kind: ReadingKind, fetched_at: str
) -> list[ReadingEntry]:
    """日本語ラベルが surface に一致する項目のP1814読みを引く。失敗は空リスト。"""
    try:
        response = fetcher.get(_build_url(surface))
        if response.status_code != 200:
            return []  # NO-LOG: 解決器がunresolvedとして記録する（§8.4のfail-closed契約）
        payload: Any = response.json()
        bindings = payload["results"]["bindings"]
    except (FetchBlockedError, ValueError, KeyError, TypeError):
        return []  # NO-LOG: 同上——例外を上げず候補なしへ倒す

    entries: list[ReadingEntry] = []
    seen: set[str] = set()
    for row in bindings:
        kana_raw = row.get("kana", {}).get("value")
        item_url = row.get("item", {}).get("value", "https://www.wikidata.org/")
        if not isinstance(kana_raw, str) or not kana_raw.strip():
            continue
        reading = hiragana_to_katakana(kana_raw.strip())
        if reading in seen:
            continue
        seen.add(reading)
        try:
            entries.append(
                ReadingEntry(
                    surface=surface,
                    reading=reading,
                    kind=kind,
                    context=None,
                    confidence=0.8,  # 典拠付き補完だが同名異人の可能性が残る
                    source_id="wikidata-kana",
                    source_url=item_url,
                    license="CC0 1.0",
                    fetched_at=fetched_at,
                )
            )
        except ValueError:
            continue  # NO-LOG: カタカナ化できない値（ラテン文字等）は候補にしない
    return entries
