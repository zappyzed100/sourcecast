"""test_search.py — Phase 7 DoD: 単一書誌系統の非表示・関連度計算・題名のみ一致の不採用を固定する"""

import pytest

from history_radio.books.search import (
    BookCandidate,
    BookMatchFeatures,
    compute_relevance,
    group_by_bibliographic_match,
    has_confirmed_identifier,
    independent_system_count,
    is_title_only_match,
    rank_books,
)


def _candidate(**overrides: object) -> BookCandidate:
    base: dict[str, object] = {
        "title": "西郷隆盛と明治維新",
        "authors": ("山田太郎",),
        "isbn": "9784000000000",
        "amazon_asin": None,
        "subject_headings": ("西郷隆盛", "明治維新"),
        "publication_year": 2020,
        "has_audio_edition": False,
        "source_system": "ndl-search",
        "source_url": "https://ndlsearch.ndl.go.jp/books/R100000000-I000001",
    }
    base.update(overrides)
    return BookCandidate.model_validate(base)


def _features(**overrides: object) -> BookMatchFeatures:
    base: dict[str, object] = {
        "title_match": 1.0,
        "subject_match": 1.0,
        "person_match": 1.0,
        "era_match": 1.0,
        "recency": 1.0,
        "has_audio": 1.0,
    }
    base.update(overrides)
    return BookMatchFeatures.model_validate(base)


def test_relevance_formula_matches_spec_example() -> None:
    """§10A初期式: 全特徴量=1 → 35+25+20+10+5+5 = 100。"""
    assert compute_relevance(_features()) == pytest.approx(100.0)


def test_relevance_scales_linearly_with_partial_features() -> None:
    features = _features(
        title_match=0.5, subject_match=0, person_match=0, era_match=0, recency=0, has_audio=0
    )
    assert compute_relevance(features) == pytest.approx(17.5)


def test_title_only_match_is_detected() -> None:
    """§10A「題名だけの曖昧一致は採用しない」。"""
    only_title = _features(title_match=0.9, subject_match=0, person_match=0, era_match=0)
    assert is_title_only_match(only_title) is True


def test_match_with_any_other_signal_is_not_title_only() -> None:
    with_subject = _features(title_match=0.9, subject_match=0.2, person_match=0, era_match=0)
    assert is_title_only_match(with_subject) is False


def test_independent_system_count_counts_distinct_systems() -> None:
    group = [
        _candidate(source_system="ndl-search"),
        _candidate(source_system="open-library"),
        _candidate(source_system="ndl-search"),  # 同一系統の重複は1件と数える
    ]
    assert independent_system_count(group) == 2


def test_isbn_confirmed_candidate_allows_affiliate_link() -> None:
    assert has_confirmed_identifier(_candidate(isbn="9784000000000")) is True


def test_no_identifier_disallows_affiliate_link() -> None:
    """§10A: ISBN/Amazon商品識別子を確認できない候補へアフィリエイトリンクを作らない。"""
    assert has_confirmed_identifier(_candidate(isbn=None, amazon_asin=None)) is False


def test_single_lineage_candidate_is_hidden_from_ranking() -> None:
    """Phase 7 DoD: 書誌系統1件だけの候補を非表示にする。"""
    candidates = [_candidate(source_system="ndl-search")]
    features = {candidates[0].source_url: _features()}
    assert rank_books(candidates, features) == []


def test_two_lineage_candidate_is_ranked() -> None:
    candidates = [
        _candidate(source_system="ndl-search"),
        _candidate(source_system="open-library"),
    ]
    features = {candidates[0].source_url: _features()}
    ranked = rank_books(candidates, features)
    assert len(ranked) == 1
    assert ranked[0].independent_systems == 2


def test_below_threshold_yields_no_related_books() -> None:
    """§10A: 関連度が閾値未満なら無関係な候補で埋めず空にする。"""
    candidates = [
        _candidate(source_system="ndl-search"),
        _candidate(source_system="open-library"),
    ]
    weak_features = _features(
        title_match=0.1, subject_match=0.1, person_match=0.1, era_match=0, recency=0, has_audio=0
    )
    features = {candidates[0].source_url: weak_features}
    assert rank_books(candidates, features, relevance_threshold=40.0) == []


def test_title_only_match_is_excluded_from_ranking() -> None:
    candidates = [
        _candidate(source_system="ndl-search"),
        _candidate(source_system="open-library"),
    ]
    only_title = _features(title_match=1.0, subject_match=0, person_match=0, era_match=0)
    features = {candidates[0].source_url: only_title}
    assert rank_books(candidates, features) == []


def test_ranking_is_sorted_by_relevance_descending() -> None:
    high = _candidate(
        title="高関連度本",
        isbn="9781111111111",
        source_system="ndl-search",
        source_url="https://example.org/high",
    )
    high2 = _candidate(
        title="高関連度本",
        isbn="9781111111111",
        source_system="open-library",
        source_url="https://example.org/high",
    )
    low = _candidate(
        title="低関連度本",
        isbn="9782222222222",
        source_system="ndl-search",
        source_url="https://example.org/low",
    )
    low2 = _candidate(
        title="低関連度本",
        isbn="9782222222222",
        source_system="open-library",
        source_url="https://example.org/low",
    )
    features = {
        "https://example.org/high": _features(),
        # 閾値(40.0)は超えるが高関連度本より低いスコアにする: 35*1.0 + 25*0.3 = 42.5
        "https://example.org/low": _features(
            title_match=1.0, subject_match=0.3, person_match=0, era_match=0, recency=0, has_audio=0
        ),
    }
    ranked = rank_books([high, high2, low, low2], features)
    assert [r.representative.title for r in ranked] == ["高関連度本", "低関連度本"]


def test_group_by_isbn_ignores_title_variations() -> None:
    """ISBNが一致すれば題名表記が多少違っても同一書籍として束ねる。"""
    a = _candidate(title="西郷隆盛と明治維新", isbn="9784000000000", source_system="ndl-search")
    b = _candidate(
        title="西郷隆盛と明治維新（新版）", isbn="9784000000000", source_system="open-library"
    )
    groups = group_by_bibliographic_match([a, b])
    assert len(groups) == 1
    assert independent_system_count(next(iter(groups.values()))) == 2
