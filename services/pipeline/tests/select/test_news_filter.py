"""test_news_filter.py — Phase 5 DoD: 不適切連想の自動採用拒否とURL非混入を固定する"""

import pytest

from history_radio.select.news_filter import (
    NewsDerivedTerms,
    NewsRejected,
    NewsTerm,
    evaluate_news_item,
)


def _terms() -> list[NewsTerm]:
    return [
        NewsTerm(text="鉄道", kind="technology"),
        NewsTerm(text="北海道", kind="region"),
        NewsTerm(text="山田太郎", kind="person"),
    ]


def test_safe_science_news_yields_terms_without_url() -> None:
    result = evaluate_news_item(
        headline="新型探査機が小惑星のサンプル分析結果を公開",
        category="宇宙",
        event_type="研究成果",
        terms=[
            NewsTerm(text="小惑星", kind="common_noun"),
            NewsTerm(text="探査機", kind="technology"),
        ],
    )
    assert isinstance(result, NewsDerivedTerms)
    assert result.terms == ("小惑星", "探査機")
    # ニュースURLが公開出典一覧へ混入しない——そもそもURLフィールドが存在しない
    assert not hasattr(result, "url")
    assert "url" not in NewsDerivedTerms.model_fields


@pytest.mark.parametrize(
    ("headline", "expected_word"),
    [
        ("鉄道事故で複数の死亡者", "死亡"),
        ("戦争の犠牲者を追悼する式典", "追悼"),
        ("感染拡大を受けた緊急対応", "緊急"),
        ("元俳優を逮捕", "逮捕"),
    ],
)
def test_forbidden_word_in_headline_rejects_entire_item(headline: str, expected_word: str) -> None:
    """§6A.2: 禁止語が1件でも含まれるニュースからは単語を一切採用しない。"""
    result = evaluate_news_item(
        headline=headline, category="交通", event_type="記念日", terms=_terms()
    )
    assert isinstance(result, NewsRejected)
    assert any(expected_word in r for r in result.reasons)


def test_disaster_association_case_is_not_auto_adopted() -> None:
    """代表的な不適切連想ケース: 災害ニュース×関連地域の歴史回、は自動採用されない。"""
    result = evaluate_news_item(
        headline="台風による災害で交通網が寸断",
        category="交通",
        event_type="記念日",
        terms=[NewsTerm(text="鉄道", kind="technology")],
    )
    assert isinstance(result, NewsRejected)


def test_unknown_category_is_rejected_fail_closed() -> None:
    """判定に迷うニュース（カテゴリ不明）は採用しない。"""
    result = evaluate_news_item(
        headline="新技術の展示会が開幕", category=None, event_type="公開", terms=_terms()
    )
    assert isinstance(result, NewsRejected)


def test_allowed_category_alone_is_not_sufficient_event_type_also_required() -> None:
    """§6A.2: 許可カテゴリと許可イベント型の両方一致が必要——片方では通らない。"""
    result = evaluate_news_item(
        headline="新路線の開業を発表", category="交通", event_type=None, terms=_terms()
    )
    assert isinstance(result, NewsRejected)


def test_disallowed_category_is_rejected_even_if_clean() -> None:
    result = evaluate_news_item(
        headline="芸能人の結婚を発表", category="芸能", event_type="式典", terms=_terms()
    )
    assert isinstance(result, NewsRejected)


def test_person_names_are_never_adopted_as_terms() -> None:
    """§6A.2: 個人名は連動語に使わない——国・地域・一般名詞・技術名のみ。"""
    result = evaluate_news_item(
        headline="保存車両の一般公開が決定",
        category="交通",
        event_type="保存車両",
        terms=_terms(),
    )
    assert isinstance(result, NewsDerivedTerms)
    assert "山田太郎" not in result.terms
    assert set(result.terms) == {"鉄道", "北海道"}
