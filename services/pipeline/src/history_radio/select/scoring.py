"""scoring.py — 候補点計算（仕様書§6A.1）。LLM不使用の純粋関数。

候補点 = 日付一致×30 + 季節一致×10 + ニュース語一致×15
       + 固有名詞一致×10 + 資料充実度×25
       - 既出類似度×30 - 直近カテゴリ重複×15

各特徴量は0〜1へ正規化済みであることを実行時検証する（範囲外は例外——黙って
クリップしない）。重みは管理画面から変更可能にする契約のため引数で注入でき、
既定値が§6A.1の初期式。点数内訳（score_breakdown）を必ず返し、`Candidate` に
そのまま保存する（選出理由の追跡可能性 — §2「生成過程を第三者が追跡できる」）。
"""

from __future__ import annotations

from pydantic import Field

from history_radio.domain.base import SchemaModel


class CandidateFeatures(SchemaModel):
    """§6A.1の入力特徴量（すべて0〜1へ正規化済み）。"""

    date_match: float = Field(ge=0, le=1)
    season_match: float = Field(ge=0, le=1)
    news_word_match: float = Field(ge=0, le=1)
    proper_noun_match: float = Field(ge=0, le=1)
    source_richness: float = Field(ge=0, le=1)
    past_similarity: float = Field(ge=0, le=1)
    recent_category_overlap: float = Field(ge=0, le=1)


class ScoreWeights(SchemaModel):
    """重み（管理画面から変更可能——既定値は§6A.1の初期式）。"""

    date_match: float = 30.0
    season_match: float = 10.0
    news_word_match: float = 15.0
    proper_noun_match: float = 10.0
    source_richness: float = 25.0
    past_similarity: float = 30.0  # 減点
    recent_category_overlap: float = 15.0  # 減点


def compute_candidate_score(
    features: CandidateFeatures, weights: ScoreWeights | None = None
) -> tuple[float, dict[str, float]]:
    """(候補点, 点数内訳) を返す。内訳は加点・減点を項目別に符号付きで持つ。"""
    w = weights or ScoreWeights()
    breakdown = {
        "date_match": features.date_match * w.date_match,
        "season_match": features.season_match * w.season_match,
        "news_word_match": features.news_word_match * w.news_word_match,
        "proper_noun_match": features.proper_noun_match * w.proper_noun_match,
        "source_richness": features.source_richness * w.source_richness,
        "past_similarity": -features.past_similarity * w.past_similarity,
        "recent_category_overlap": (-features.recent_category_overlap * w.recent_category_overlap),
    }
    return sum(breakdown.values()), breakdown
