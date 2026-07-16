"""address_registry.py — デジタル庁アドレス・ベース・レジストリの変換スクリプト
（development-plan.md §8.4。現代地名の読み）。

レジストリは**ライブ検索APIではなく、都道府県別CSVの一括ダウンロード配布**
（`catalog.registries.digital.go.jp` の町字マスター等）——本session環境からは
当該ドメインへの接続が確立できず（DNS解決不可。Wikipedia/Wikidata/NDL等の
既知ドメインは到達可能なため、環境固有の到達可否と判断）実CSVヘッダーを
直接確認できていない。そのためこの module は**列名をパラメータで受け取る**
header駆動の変換器として実装し、正しい列名は実CSV取得時に確認・指定する
（ポジション依存にしない——将来ヘッダー順が変わっても壊れない）。

PDL1.0が求める「出典と加工した旨」の表示（development-plan.md §8.4）は、
`config/readings/sources.yaml`のdigital-agency-abr attribution_textと同一文言を
`ReadingEntry.license`へ複製することで、**レコード単位**で満たす（1件ずつ検査可能）。
CSV取得スクリプト自体はSudachiDict/JMnedictと同じ理由——実データ確認後の別タスク。
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from history_radio.readings.entry import ReadingEntry
from history_radio.readings.jmnedict import hiragana_to_katakana

_SOURCE_ID = "digital-agency-abr"
_LICENSE_WITH_ATTRIBUTION = "アドレス・ベース・レジストリ（デジタル庁）を加工して作成"
_SOURCE_URL = "https://www.digital.go.jp/policies/base_registry_address"
_CONFIDENCE = 0.9


@dataclass(frozen=True, slots=True)
class AddressColumns:
    """CSVのどの列が地名・読み仮名かを指定する（実ヘッダー名は取得時に確認して渡す）。"""

    name_column: str
    kana_column: str


def convert_address_rows(
    rows: Iterable[dict[str, str]], columns: AddressColumns, *, fetched_at: str
) -> list[ReadingEntry]:
    """CSV行（ヘッダー付き辞書のイテラブル）を現代地名のReadingEntryへ変換する。

    列が欠けている行・読みが空の行は黙ってスキップする（1行の欠損で全体を
    止めない——§7.3の過大レスポンス拒否と同じ「部分的でも動く」設計方針）。
    同一表記・同一読みの重複は1件へ統合する。
    """
    seen: set[tuple[str, str]] = set()
    entries: list[ReadingEntry] = []
    for row in rows:
        name = row.get(columns.name_column, "").strip()
        kana_raw = row.get(columns.kana_column, "").strip()
        if not name or not kana_raw:
            continue
        # レジストリの_カナ列はひらがな表記の場合もあるため統一しておく
        # （カタカナ入力はtranslateの対象外文字なので無害）
        kana = hiragana_to_katakana(kana_raw)
        key = (name, kana)
        if key in seen:
            continue
        seen.add(key)
        try:
            entries.append(
                ReadingEntry(
                    surface=name,
                    reading=kana,
                    kind="place",
                    context=None,
                    confidence=_CONFIDENCE,
                    source_id=_SOURCE_ID,
                    source_url=_SOURCE_URL,
                    license=_LICENSE_WITH_ATTRIBUTION,
                    fetched_at=fetched_at,
                )
            )
        except ValueError:
            continue  # NO-LOG: 読み仮名列がカタカナ化できない値（ひらがな以外の混入等）
    return entries
