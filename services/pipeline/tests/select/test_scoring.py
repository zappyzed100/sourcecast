"""test_scoring.py — Phase 5 DoD: §6A.1の候補点計算を固定入力の期待点数で固定する"""

import pytest
from pydantic import ValidationError

from history_radio.select.scoring import (
    CandidateFeatures,
    ScoreWeights,
    compute_candidate_score,
)


def test_initial_formula_matches_spec_example() -> None:
    """§6A.1初期式: 全特徴量=1 → 30+10+15+10+25-30-15 = 45。"""
    features = CandidateFeatures(
        date_match=1,
        season_match=1,
        news_word_match=1,
        proper_noun_match=1,
        source_richness=1,
        past_similarity=1,
        recent_category_overlap=1,
    )
    score, breakdown = compute_candidate_score(features)
    assert score == pytest.approx(45.0)
    assert breakdown["date_match"] == pytest.approx(30.0)
    assert breakdown["past_similarity"] == pytest.approx(-30.0)


def test_partial_features_scale_linearly() -> None:
    """日付一致0.5・資料充実度0.8のみ → 30*0.5 + 25*0.8 = 35。"""
    features = CandidateFeatures(
        date_match=0.5,
        season_match=0,
        news_word_match=0,
        proper_noun_match=0,
        source_richness=0.8,
        past_similarity=0,
        recent_category_overlap=0,
    )
    score, breakdown = compute_candidate_score(features)
    assert score == pytest.approx(35.0)
    assert breakdown["season_match"] == 0.0


def test_penalties_can_drive_score_negative() -> None:
    features = CandidateFeatures(
        date_match=0,
        season_match=0,
        news_word_match=0,
        proper_noun_match=0,
        source_richness=0,
        past_similarity=1,
        recent_category_overlap=1,
    )
    score, _ = compute_candidate_score(features)
    assert score == pytest.approx(-45.0)


def test_custom_weights_are_respected() -> None:
    """重みは管理画面から変更可能（§6A.1）——注入した重みが計算に反映される。"""
    features = CandidateFeatures(
        date_match=1,
        season_match=0,
        news_word_match=0,
        proper_noun_match=0,
        source_richness=0,
        past_similarity=0,
        recent_category_overlap=0,
    )
    score, _ = compute_candidate_score(features, ScoreWeights(date_match=50.0))
    assert score == pytest.approx(50.0)


@pytest.mark.parametrize("bad_value", [-0.1, 1.1])
def test_out_of_range_features_are_rejected_not_clipped(bad_value: float) -> None:
    """正規化されていない特徴量は例外——黙ってクリップしない。"""
    with pytest.raises(ValidationError):
        CandidateFeatures(
            date_match=bad_value,
            season_match=0,
            news_word_match=0,
            proper_noun_match=0,
            source_richness=0,
            past_similarity=0,
            recent_category_overlap=0,
        )


def test_breakdown_sums_to_score() -> None:
    """点数内訳は必ず合計＝候補点（Candidateへの保存契約 — score_breakdown）。"""
    features = CandidateFeatures(
        date_match=0.3,
        season_match=0.7,
        news_word_match=0.2,
        proper_noun_match=0.9,
        source_richness=0.5,
        past_similarity=0.4,
        recent_category_overlap=0.1,
    )
    score, breakdown = compute_candidate_score(features)
    assert score == pytest.approx(sum(breakdown.values()))
