"""jmnedict.py — JMnedictパーサ（development-plan.md §8.4。人名・地名の読み候補）。

JMnedict（XML）から表記・読み・種別を取り出し、共通のReadingEntryへ変換する。
**CC BY-SAのSA継承対策（§8.3）**: JMnedict由来レコードは source_id="jmnedict" を
必ず持ち、保存は store_jsonl.py のソース別ファイルへ——他ソースと混ぜて再配布しない。

辞書本体（JMnedict.xml ~100MB）はコミットせず、取得スクリプト（§8.4の後続タスク）が
artifacts/readings/ へ保存する。この module はパースだけを担い、テストはサンプルXMLの
記録fixtureで行う（実ネットワーク・実ファイル不要）。

XMLは標準ElementTreeで読む（外部実体は解決しない — §7.3と同じ規律。JMnedictの
実体参照（&surname;等）はDTD内部宣言なので resolve_entities なしで解決される——
ただしETはDTDを処理しないため、事前に内部実体をテキスト置換で剥がす）。
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from history_radio.readings.entry import ReadingEntry, ReadingKind

# JMnedictのname_type実体 → ReadingKind の対応（採用する種別だけ列挙——
# 企業名・商品名等は読み辞書の対象外なので落とす）
_NAME_TYPE_TO_KIND: dict[str, ReadingKind] = {
    "surname": "person",
    "masc": "person",
    "fem": "person",
    "given": "person",
    "person": "person",
    "place": "place",
    "station": "place",
}

_ENTITY_PATTERN = re.compile(r"&([a-zA-Z]+);")

_HIRAGANA_TO_KATAKANA = str.maketrans(
    {chr(h): chr(h + 0x60) for h in range(ord("ぁ"), ord("ゖ") + 1)}
)


class JmnedictParseError(ValueError):
    """JMnedict XMLが想定の形でない。"""


def _strip_internal_entities(xml_text: str) -> str:
    """DTD内部実体参照（&surname;等）を実体名の文字列へ置換する。

    ElementTreeはDTDを処理せず未定義実体でパースエラーになるため、
    `&name;` → `name` に落としてから読む（name_typeの値として使う）。
    """
    return _ENTITY_PATTERN.sub(lambda m: m.group(1), xml_text)


def hiragana_to_katakana(reading: str) -> str:
    """JMnedictの読み（ひらがな）をカタカナへ（ReadingEntryのカタカナ統一規約）。"""
    return reading.translate(_HIRAGANA_TO_KATAKANA)


def parse_jmnedict(xml_text: str, *, fetched_at: str) -> list[ReadingEntry]:
    """JMnedict XMLをパースし、人名・地名のReadingEntry列へ変換する。

    採用しないname_type（企業・商品等）のエントリと、表記（k_ele）の無い
    エントリ（かな見出しのみ）は読み辞書の対象外として落とす。
    """
    try:
        root = ET.fromstring(_strip_internal_entities(xml_text))
    except ET.ParseError as exc:
        raise JmnedictParseError(f"JMnedict XMLを解析できない: {exc}") from exc

    entries: list[ReadingEntry] = []
    for entry in root.iter("entry"):
        surfaces = [k.text for k in entry.iter("keb") if k.text]
        readings = [r.text for r in entry.iter("reb") if r.text]
        name_types = [t.text for t in entry.iter("name_type") if t.text]
        kinds: list[ReadingKind] = sorted(
            {_NAME_TYPE_TO_KIND[t] for t in name_types if t in _NAME_TYPE_TO_KIND}
        )
        if not surfaces or not readings or not kinds:
            continue
        for surface in surfaces:
            for reading in readings:
                for kind in kinds:
                    entries.append(
                        ReadingEntry(
                            surface=surface,
                            reading=hiragana_to_katakana(reading),
                            kind=kind,
                            context=None,
                            confidence=0.7,  # 候補扱い——同名異読が多く単独では確定しない
                            source_id="jmnedict",
                            source_url="https://www.edrdg.org/enamdict/enamdict_doc.html",
                            license="CC BY-SA 4.0",
                            fetched_at=fetched_at,
                        )
                    )
    return entries
