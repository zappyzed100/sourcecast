"""ndl_authorities.py — Web NDL Authoritiesアダプタ（development-plan.md §8.4）。

重要人物・団体の読み・別名・生没年を取得する（§8.1）。典拠の見出し語は
`"姓, 名, 生年-没年"` の形（例:「西郷, 隆盛, 1827-1877」）——読み（transcription）も
同形で並ぶため、日付を含む区切りを落として姓名だけを連結する。

2段階の取得（§7.1のAPI優先・実測で確認した実際のエンドポイント）:
1. SPARQL（`https://id.ndl.go.jp/auth/ndla/sparql`）で見出し語をCONTAINS検索し、
   カンマ・空白・日付を除いた正規化名が完全一致する候補だけに絞る
2. 候補エンティティのJSON-LD（`<entity-uri>.json`）を取得し、prefLabel/altLabelの
   transcriptionから読みを組み立てる

fail-closed契約はwikidata_kana.pyと同じ: 通信・解析のいかなる失敗も例外を上げず
空リストへ（解決器がunresolvedとして扱う）。出典表示「Web NDL Authoritiesから取得」
はsources.yamlのattribution_textが正——ここでは複製しない。
"""

from __future__ import annotations

import re
from typing import Any, cast
from urllib.parse import urlencode

from history_radio.ingest.crawl_control import FetchBlockedError, PoliteFetcher
from history_radio.readings.entry import ReadingEntry, ReadingKind
from history_radio.readings.jmnedict import hiragana_to_katakana

_SPARQL_ENDPOINT = "https://id.ndl.go.jp/auth/ndla/sparql"
_SOURCE_ID = "ndl-web-authorities"
_LICENSE = "国立国会図書館の利用条件に従う（出典明示で利用可）"
_CONFIDENCE = 0.85

_SPARQL_QUERY = """PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?s ?label WHERE {{
  ?s rdfs:label ?label .
  FILTER(CONTAINS(?label, "{needle}"))
}} LIMIT 20"""

_SPLIT_PATTERN = re.compile(r"[,、]")
_HAS_DIGIT = re.compile(r"\d")


def _normalize_name_parts(literal: str) -> str:
    """「姓, 名, 生没年」形式から日付部分を落として姓名だけを連結する。"""
    parts = [p.strip() for p in _SPLIT_PATTERN.split(literal) if p.strip()]
    kept = [p for p in parts if not _HAS_DIGIT.search(p)]
    return "".join(kept)


def _search_url(needle: str) -> str:
    query = _SPARQL_QUERY.format(needle=needle.replace('"', ""))
    return f"{_SPARQL_ENDPOINT}?{urlencode({'query': query, 'format': 'json'})}"


def _entity_json_url(entity_uri: str) -> str:
    return entity_uri.replace("http://", "https://", 1) + ".json"


def fetch_ndl_authority_readings(
    fetcher: PoliteFetcher, name: str, *, kind: ReadingKind, fetched_at: str
) -> list[ReadingEntry]:
    """`name`（例:"西郷隆盛"）に一致する典拠を検索し、読み・別名の候補を返す。

    候補が複数（同姓同名等）ある場合は全件返す——一意化は呼び出し側（解決器）が
    生没年等の追加コンテキストで行う。一致が無い・通信/解析に失敗すれば空リスト。
    """
    if len(name) < 2:
        return []
    try:
        search_response = fetcher.get(_search_url(name[:2]))
        if search_response.status_code != 200:
            return []  # NO-LOG: 解決器がunresolvedとして記録する
        bindings: list[dict[str, Any]] = search_response.json()["results"]["bindings"]
    except FetchBlockedError, ValueError, KeyError, TypeError:
        return []  # NO-LOG: 同上——fail closed

    normalized_target = _normalize_name_parts(name)
    entries: list[ReadingEntry] = []
    for binding in bindings:
        label = binding.get("label", {}).get("value", "")
        if _normalize_name_parts(label) != normalized_target:
            continue
        entity_uri = binding.get("s", {}).get("value")
        if not entity_uri:
            continue
        entries.extend(
            _fetch_entity_readings(fetcher, entity_uri, kind=kind, fetched_at=fetched_at)
        )
    return entries


def _fetch_entity_readings(
    fetcher: PoliteFetcher, entity_uri: str, *, kind: ReadingKind, fetched_at: str
) -> list[ReadingEntry]:
    try:
        response = fetcher.get(_entity_json_url(entity_uri))
        if response.status_code != 200:
            return []  # NO-LOG: fail closed
        data: Any = response.json()
    except FetchBlockedError, ValueError, KeyError, TypeError:
        return []  # NO-LOG: fail closed

    entries: list[ReadingEntry] = []
    labels = [data.get("prefLabel")] + list(data.get("altLabel") or [])
    seen: set[tuple[str, str]] = set()
    for label_obj in labels:
        if not isinstance(label_obj, dict):
            continue
        label_dict = cast("dict[str, Any]", label_obj)
        literal = label_dict.get("literalForm")
        transcription = label_dict.get("transcription")
        if not isinstance(literal, str) or not isinstance(transcription, str):
            continue
        surface = _normalize_name_parts(literal)
        reading_source = _normalize_name_parts(transcription)
        if not surface or not reading_source:
            continue
        reading = hiragana_to_katakana(reading_source)
        key = (surface, reading)
        if key in seen:
            continue
        seen.add(key)
        try:
            entries.append(
                ReadingEntry(
                    surface=surface,
                    reading=reading,
                    kind=kind,
                    context=None,
                    confidence=_CONFIDENCE,
                    source_id=_SOURCE_ID,
                    source_url=entity_uri,
                    license=_LICENSE,
                    fetched_at=fetched_at,
                )
            )
        except ValueError:
            continue  # NO-LOG: カタカナ化できない値は候補にしない
    return entries
