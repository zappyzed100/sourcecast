"""reproduction_detector.py — 転載検知（仕様書§11・development-plan.md Phase 10タスク2）。

台本と各出典原文のあいだで、連続する長い一致（初期値: 和文25文字以上、欧文8語以上）を
検出する。引用として明示・出所表示した文（`ScriptSentence.is_quoted=True`）は
検査対象から除外する（仕様書§11）。

一致検出には標準ライブラリの`difflib.SequenceMatcher`（Ratcliff/Obershelp法）を使う——
新規依存を追加せずに「2文字列間の連続一致ブロック」を効率的に求められるため。
これは全文検索エンジン水準の転載検出ではなく、規則ベースの自動ゲート用の実用的な
実装であることに注意（完全性より新規依存を避けることを優先した——外部サービスへの
問い合わせはtest-network上の制約からも避けたい）。

和文/欧文の判定は一致した部分文字列自体の文字種で行う（CJK文字を含めば和文として
文字数を、含まなければ欧文として空白区切りの語数を数える）。
"""

from __future__ import annotations

import difflib
from typing import Literal

from history_radio.domain.base import SchemaModel
from history_radio.script.schema import Script

DEFAULT_MIN_JAPANESE_CHARS = 25
DEFAULT_MIN_WESTERN_WORDS = 8

MatchKind = Literal["japanese_chars", "western_words"]


class ReproducedSpan(SchemaModel):
    sentence_text: str
    matched_text: str
    source_index: int
    match_length: int
    match_kind: MatchKind


def _contains_cjk(text: str) -> bool:
    return any(
        "぀" <= ch <= "ヿ"  # ひらがな・カタカナ
        or "一" <= ch <= "鿿"  # 漢字
        for ch in text
    )


def _find_spans_in_pair(
    sentence_text: str,
    source_text: str,
    source_index: int,
    *,
    min_japanese_chars: int,
    min_western_words: int,
) -> list[ReproducedSpan]:
    matcher = difflib.SequenceMatcher(None, sentence_text, source_text, autojunk=False)
    spans: list[ReproducedSpan] = []
    for block in matcher.get_matching_blocks():
        if block.size == 0:
            continue
        matched_text = sentence_text[block.a : block.a + block.size]
        if _contains_cjk(matched_text):
            if len(matched_text) >= min_japanese_chars:
                spans.append(
                    ReproducedSpan(
                        sentence_text=sentence_text,
                        matched_text=matched_text,
                        source_index=source_index,
                        match_length=len(matched_text),
                        match_kind="japanese_chars",
                    )
                )
        else:
            word_count = len(matched_text.split())
            if word_count >= min_western_words:
                spans.append(
                    ReproducedSpan(
                        sentence_text=sentence_text,
                        matched_text=matched_text,
                        source_index=source_index,
                        match_length=word_count,
                        match_kind="western_words",
                    )
                )
    return spans


def detect_reproduction(
    script: Script,
    source_texts: dict[int, str],
    *,
    min_japanese_chars: int = DEFAULT_MIN_JAPANESE_CHARS,
    min_western_words: int = DEFAULT_MIN_WESTERN_WORDS,
) -> list[ReproducedSpan]:
    """台本の非引用文と各出典原文を比較し、閾値以上の連続一致を全件返す（無ければ空配列）。"""
    spans: list[ReproducedSpan] = []
    for section in script.sections:
        for sentence in section.sentences:
            if sentence.is_quoted:
                continue
            for source_index, source_text in source_texts.items():
                spans.extend(
                    _find_spans_in_pair(
                        sentence.text,
                        source_text,
                        source_index,
                        min_japanese_chars=min_japanese_chars,
                        min_western_words=min_western_words,
                    )
                )
    return spans
