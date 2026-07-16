"""sudachi.py — SudachiDict(full)アダプタ（development-plan.md §8.4。一般語・基本固有名詞）。

解決順序（§8.2）の最下層——手動修正辞書・元号/官職辞書・Wikidata/NDL・地名辞書・
JMnedictのいずれも解決できなかった語だけがここへ来る想定。そのため confidence は
低め（0.5）に固定する。形態素の型は `TokenLike` Protocol で受け、実運用は
`sudachipy.Morpheme` を渡す——テストは軽量フェイクで実辞書ロードを避けられる。

読みがカタカナで統一できない形態素（数字・記号等）は候補にしない（黙って
スキップする——1語の失敗で文全体の解決を止めない）。
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from history_radio.readings.entry import ReadingEntry, ReadingKind

_SOURCE_ID = "sudachidict"
_LICENSE = "Apache-2.0"
_SOURCE_URL = "https://github.com/WorksApplications/SudachiDict"
_CONFIDENCE = 0.5  # 解決順序の最下層——他ソースが解決できなかった語の候補


class TokenLike(Protocol):
    """SudachiPyのMorpheme互換Protocol（テストは実辞書なしのフェイクで満たせる）。"""

    def surface(self) -> str: ...
    def reading_form(self) -> str: ...
    def part_of_speech(self) -> tuple[str, ...]: ...


def _kind_for_pos(pos: tuple[str, ...]) -> ReadingKind | None:
    """品詞タプルから読み辞書の種別を決める。名詞以外は対象外（Noneでスキップ）。"""
    if not pos or pos[0] != "名詞":
        return None
    if len(pos) > 2 and pos[1] == "固有名詞":
        if pos[2] == "人名":
            return "person"
        if pos[2] == "地名":
            return "place"
    return "common"


def create_tokenizer() -> object:
    """本番用のSudachiPyトークナイザを1個生成する（薄いファクトリ——テスト対象外）。"""
    from sudachipy import Dictionary

    return Dictionary(dict="full").create()


def tokens_to_reading_entries(
    tokens: Sequence[TokenLike], *, fetched_at: str
) -> list[ReadingEntry]:
    """形態素列から読み辞書エントリへ変換する（名詞のみ・カタカナ化不能な語は除外）。"""
    entries: list[ReadingEntry] = []
    for token in tokens:
        kind = _kind_for_pos(token.part_of_speech())
        if kind is None:
            continue
        try:
            entries.append(
                ReadingEntry(
                    surface=token.surface(),
                    reading=token.reading_form(),
                    kind=kind,
                    context=None,
                    confidence=_CONFIDENCE,
                    source_id=_SOURCE_ID,
                    source_url=_SOURCE_URL,
                    license=_LICENSE,
                    fetched_at=fetched_at,
                )
            )
        except ValueError:
            continue  # NO-LOG: 数字・記号等カタカナ化できない語は候補にしない
    return entries


def fetch_sudachi_readings(tokenizer: object, text: str, *, fetched_at: str) -> list[ReadingEntry]:
    """テキストをトークナイズし、読み辞書エントリへ変換する（本番経路）。"""
    from sudachipy import SplitMode

    morphemes: list[TokenLike] = list(tokenizer.tokenize(text, SplitMode.C))  # type: ignore[attr-defined]
    return tokens_to_reading_entries(morphemes, fetched_at=fetched_at)
