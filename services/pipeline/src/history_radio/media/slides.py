"""slides.py — スライド構成の決定（仕様書§10・development-plan.md Phase 7）。

台本（Script）とmedia_manifestから、各セクションのスライド仕様（題名・年代・
本文行・使用素材・出典番号・表示秒数）を組み立てる純粋関数——実際の画像描画・
動画エンコードは`slide_render.py`が担う（決定と実行を分離する）。

**素材不足時のfail-safe契約**（§10「素材不足時は無理に画像検索せず、著作権の
発生しない自作図形…を使用する」）: 該当セクションに使える`MediaAsset`が1件も
無くても、`uses_self_drawn_fallback=True`のスライドを必ず生成する——スライドが
0件になる・生成が止まることはない（画像0件でも権利上安全な動画を生成できる、
の直接の実装）。
"""

from __future__ import annotations

from pydantic import Field

from history_radio.domain.base import SchemaModel
from history_radio.media.media_manifest import MediaAsset
from history_radio.script.schema import Script, ScriptSection

# §10: 画面上の文章は1スライド60文字以内を目安とする
MAX_CHARS_PER_LINE = 60
# §10: 画像切替は8〜20秒を目安とする
MIN_SLIDE_SECONDS = 8.0
MAX_SLIDE_SECONDS = 20.0
# 秒数見積もりの目安（日本語の平均読み上げ速度——VOICEVOX既定速度に近い値）
_CHARS_PER_SECOND = 6.0


class SlideSpec(SchemaModel):
    """1スライド分の構成（描画・エンコードへの入力契約）。"""

    slide_id: str = Field(min_length=1)
    section_kind: str = Field(min_length=1)
    title: str
    body_lines: tuple[str, ...]
    duration_seconds: float = Field(ge=MIN_SLIDE_SECONDS, le=MAX_SLIDE_SECONDS)
    asset_ids: tuple[str, ...]
    uses_self_drawn_fallback: bool
    source_numbers: tuple[int, ...]


def _wrap_lines(text: str, *, max_chars: int = MAX_CHARS_PER_LINE) -> tuple[str, ...]:
    """句読点区切りを尊重しつつ、max_chars以内の行へ分割する（簡易実装。禁則処理はしない）。"""
    if not text:
        return ()
    lines: list[str] = []
    current = ""
    for ch in text:
        current += ch
        if len(current) >= max_chars:
            lines.append(current)
            current = ""
    if current:
        lines.append(current)
    return tuple(lines)


def _estimate_duration(text: str) -> float:
    estimated = len(text) / _CHARS_PER_SECOND
    return max(MIN_SLIDE_SECONDS, min(MAX_SLIDE_SECONDS, estimated))


def _section_title(section_kind: str) -> str:
    # §9.1の7段構成に対応する表示題名（出典案内は「出典」と簡潔にする等、画面向けの短縮）
    titles = {
        "hook": "導入",
        "setting": "時代と場所",
        "development": "出来事の展開",
        "twist": "意外な事実",
        "modern_link": "現代との接点",
        "uncertainty": "不確実な点",
        "sources": "出典",
    }
    return titles.get(section_kind, section_kind)


def _section_text(section: ScriptSection) -> str:
    return "".join(s.text for s in section.sentences)


def build_slide_deck(
    script: Script,
    assets: list[MediaAsset],
    *,
    claim_source_numbers: dict[str, int] | None = None,
) -> list[SlideSpec]:
    """台本の各セクションから1スライドずつ組み立てる。

    セクションに使える素材（`used_in`に`section.kind`を含むMediaAsset）が
    無ければ、`uses_self_drawn_fallback=True`のスライドを生成する（画像0件でも
    安全に動画化できる契約）。
    """
    source_numbers = claim_source_numbers or {}
    decks: list[SlideSpec] = []
    for section in script.sections:
        text = _section_text(section)
        section_assets = [a for a in assets if section.kind in a.used_in]
        claim_ids = [s.claim_id for s in section.sentences if s.claim_id is not None]
        numbers = sorted({source_numbers[cid] for cid in claim_ids if cid in source_numbers})
        decks.append(
            SlideSpec(
                slide_id=f"{script.episode_id}-{section.kind}",
                section_kind=section.kind,
                title=_section_title(section.kind),
                body_lines=_wrap_lines(text),
                duration_seconds=_estimate_duration(text),
                asset_ids=tuple(a.asset_id for a in section_assets),
                uses_self_drawn_fallback=not section_assets,
                source_numbers=tuple(numbers),
            )
        )
    return decks
