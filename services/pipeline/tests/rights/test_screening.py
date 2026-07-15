"""test_screening.py — Phase 3 DoD: §5Aの各判定規則の許可最小ケース・境界・拒否ケースを固定する"""

from datetime import date

from history_radio.rights.screening import (
    anonymous_or_corporate_outcome,
    film_outcome,
    foreign_wartime_outcome,
    gov_standard_terms_outcome,
    government_work_outcome,
    neighboring_rights_outcome,
    personal_authorship_outcome,
    photo_outcome,
    translation_outcome,
)


class TestPersonalAuthorshipOutcome:
    def test_death_before_1967_cutoff_is_expired_even_without_date_math(self) -> None:
        outcome = personal_authorship_outcome(1960, today=date(2026, 7, 16))
        assert outcome.status == "expired"

    def test_death_plus_70_years_boundary_expires_on_january_1st(self) -> None:
        # 没年1970年（1967年カットオフの対象外）+ 70年 = 2040年12/31まで保護、2041年から満了。
        assert personal_authorship_outcome(1970, today=date(2040, 12, 31)).status == "not_expired"
        assert personal_authorship_outcome(1970, today=date(2041, 1, 1)).status == "expired"

    def test_missing_death_year_is_undeterminable(self) -> None:
        assert personal_authorship_outcome(None, today=date(2026, 7, 16)).status == "undeterminable"

    def test_recent_death_is_not_expired(self) -> None:
        assert personal_authorship_outcome(2020, today=date(2026, 7, 16)).status == "not_expired"


class TestAnonymousOrCorporateOutcome:
    def test_publication_before_1967_cutoff_is_expired(self) -> None:
        assert anonymous_or_corporate_outcome(1960, today=date(2026, 7, 16)).status == "expired"

    def test_publication_plus_70_years_boundary(self) -> None:
        assert (
            anonymous_or_corporate_outcome(1970, today=date(2040, 12, 31)).status == "not_expired"
        )
        assert anonymous_or_corporate_outcome(1970, today=date(2041, 1, 1)).status == "expired"

    def test_missing_publication_year_is_undeterminable(self) -> None:
        assert (
            anonymous_or_corporate_outcome(None, today=date(2026, 7, 16)).status == "undeterminable"
        )


class TestFilmOutcome:
    def test_published_1953_or_earlier_is_expired(self) -> None:
        assert film_outcome(1953, today=date(2026, 7, 16)).status == "expired"
        assert film_outcome(1900, today=date(2026, 7, 16)).status == "expired"

    def test_published_1954_is_not_expired_until_70_years_pass(self) -> None:
        assert film_outcome(1954, today=date(2024, 12, 31)).status == "not_expired"
        assert film_outcome(1954, today=date(2025, 1, 1)).status == "expired"

    def test_missing_publication_year_is_undeterminable(self) -> None:
        assert film_outcome(None, today=date(2026, 7, 16)).status == "undeterminable"


class TestPhotoOutcome:
    def test_published_1957_or_earlier_is_undeterminable_pending_manual_review(self) -> None:
        # 満了候補であっても、翻案・写り込み・所蔵規約の確認が要るため人手確認へ倒す。
        outcome = photo_outcome(1957)
        assert outcome.status == "undeterminable"

    def test_published_after_1957_is_not_expired(self) -> None:
        assert photo_outcome(1958).status == "not_expired"

    def test_missing_publication_year_is_undeterminable(self) -> None:
        assert photo_outcome(None).status == "undeterminable"


def test_government_work_is_always_expired_under_article_13() -> None:
    assert government_work_outcome().status == "expired"


class TestGovStandardTermsOutcome:
    def test_no_third_party_exception_is_expired(self) -> None:
        assert gov_standard_terms_outcome(third_party_exception=False).status == "expired"

    def test_third_party_exception_is_undeterminable(self) -> None:
        assert gov_standard_terms_outcome(third_party_exception=True).status == "undeterminable"


def test_foreign_wartime_outcome_never_auto_approves() -> None:
    # 3条件すべて確認できていても、加算日数は国別に異なるため常にundeterminable。
    fully_confirmed = foreign_wartime_outcome(
        nationality_confirmed=True,
        acquisition_date_confirmed=True,
        treaty_confirmed=True,
    )
    assert fully_confirmed.status == "undeterminable"

    unconfirmed = foreign_wartime_outcome(
        nationality_confirmed=False,
        acquisition_date_confirmed=False,
        treaty_confirmed=False,
    )
    assert unconfirmed.status == "undeterminable"


def test_neighboring_rights_never_auto_approves() -> None:
    assert neighboring_rights_outcome().status == "undeterminable"


class TestTranslationOutcome:
    def test_translator_death_before_1967_cutoff_is_expired(self) -> None:
        assert translation_outcome(1960, today=date(2026, 7, 16)).status == "expired"

    def test_missing_translator_death_year_is_undeterminable(self) -> None:
        assert translation_outcome(None, today=date(2026, 7, 16)).status == "undeterminable"
