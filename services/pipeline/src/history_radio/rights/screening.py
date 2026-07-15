"""screening.py — 日本法での機械スクリーニング（仕様書§5A）を純粋関数で実装する。

各関数は「その規則単独での満了状況」だけを返し、実際に `allow_public_use` にするかは
`rights/engine.py` 側の方針（年代計算だけでは自動許可しない — §5A冒頭）が決める。
年数計算は呼び出しのたびに `today` を渡し直す契約とし、結果をキャッシュしない
（§5A冒頭「年数計算は資料取得のたびに現在日付で再計算する」）。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

ScreeningStatus = Literal["expired", "not_expired", "undeterminable"]

# 1967年以前に没した著作者・公表された無名/団体名義著作物は、旧50年制で既に
# 満了しており2018年の保護期間延長で復活しない（§5A-2・3）。
_PRE_EXTENSION_CUTOFF_YEAR = 1967
# 死後保護期間（年）。没年+70年の12/31まで保護、+71年の1/1にPD入り（§5A-1）。
_PERSONAL_PROTECTION_YEARS = 70
_ANONYMOUS_OR_CORPORATE_PROTECTION_YEARS = 70
# 1953年以前公開の映画は保護期間満了（2003年末満了・最高裁判例で確定 — §5A-4）。
_FILM_CUTOFF_YEAR = 1953
# 国立国会図書館の案内に基づく写真の旧法特例カットオフ（§5A-5）。
_PHOTO_CUTOFF_YEAR = 1957


@dataclass(frozen=True, slots=True)
class RuleOutcome:
    status: ScreeningStatus
    reason: str


def personal_authorship_outcome(death_year: int | None, *, today: date) -> RuleOutcome:
    """§5A-1・2: 個人名義の著作物。没年から死後70年（暦年主義）で判定する。"""
    if death_year is None:
        return RuleOutcome("undeterminable", "個人著作物: 没年が確認できない")
    if death_year <= _PRE_EXTENSION_CUTOFF_YEAR:
        return RuleOutcome(
            "expired",
            f"個人著作物: 没年{death_year}年は1967年以前のため旧50年制で満了済み"
            "（延長で復活しない）",
        )
    pd_from_year = death_year + _PERSONAL_PROTECTION_YEARS + 1
    if today.year >= pd_from_year:
        return RuleOutcome(
            "expired", f"個人著作物: 没年{death_year}年+70年の12/31までで保護期間満了"
        )
    return RuleOutcome(
        "not_expired", f"個人著作物: 没年{death_year}年+70年の保護期間中（{today}時点）"
    )


def anonymous_or_corporate_outcome(publication_year: int | None, *, today: date) -> RuleOutcome:
    """§5A-3: 無名・変名・団体名義。公表後70年で判定する。"""
    if publication_year is None:
        return RuleOutcome("undeterminable", "無名/団体名義著作物: 公表年が確認できない")
    if publication_year <= _PRE_EXTENSION_CUTOFF_YEAR:
        return RuleOutcome(
            "expired",
            f"無名/団体名義著作物: 公表{publication_year}年は1967年以前のため満了済み",
        )
    pd_from_year = publication_year + _ANONYMOUS_OR_CORPORATE_PROTECTION_YEARS + 1
    if today.year >= pd_from_year:
        return RuleOutcome(
            "expired", f"無名/団体名義著作物: 公表{publication_year}年+70年で保護期間満了"
        )
    return RuleOutcome(
        "not_expired", f"無名/団体名義著作物: 公表{publication_year}年+70年の保護期間中"
    )


def film_outcome(publication_year: int | None, *, today: date) -> RuleOutcome:
    """§5A-4: 映画。1953年以前公開は満了済み、それ以降は公表後70年で判定する。"""
    if publication_year is None:
        return RuleOutcome("undeterminable", "映画: 公開年が確認できない")
    if publication_year <= _FILM_CUTOFF_YEAR:
        return RuleOutcome(
            "expired", f"映画: 公開{publication_year}年は1953年以前のため保護期間満了（確定判例）"
        )
    pd_from_year = publication_year + _ANONYMOUS_OR_CORPORATE_PROTECTION_YEARS + 1
    if today.year >= pd_from_year:
        return RuleOutcome("expired", f"映画: 公開{publication_year}年+70年で保護期間満了")
    return RuleOutcome("not_expired", f"映画: 公開{publication_year}年+70年の保護期間中")


def photo_outcome(publication_year: int | None) -> RuleOutcome:
    """§5A-5: 写真（旧法特例）。1957年以前公表は満了候補だが、写り込み・所蔵規約等の
    別確認が要るため常に人手確認対象とする（自動許可の解禁までは`undeterminable`扱い）。
    """
    if publication_year is None:
        return RuleOutcome("undeterminable", "写真: 公表年が確認できない")
    if publication_year <= _PHOTO_CUTOFF_YEAR:
        return RuleOutcome(
            "undeterminable",
            f"写真: 公表{publication_year}年は1957年以前で満了候補だが、翻案・写り込み・"
            "所蔵サイト規約の確認が必要なため自動許可しない（人手確認対象）",
        )
    return RuleOutcome("not_expired", f"写真: 公表{publication_year}年は1957年より後")


def government_work_outcome() -> RuleOutcome:
    """§5A-8: 著作権法13条。法令・告示・訓令・通達・判決等は権利の目的とならない。"""
    return RuleOutcome("expired", "著作権法13条: 権利の目的とならない資料（法令・告示・判決等）")


def gov_standard_terms_outcome(*, third_party_exception: bool) -> RuleOutcome:
    """§5A-9: 政府標準利用規約2.0。CC BY 4.0互換として扱うが、第三者著作物・ロゴ等の
    例外表示があるページはその部分を除外する必要があるため人手確認へ倒す。
    """
    if third_party_exception:
        return RuleOutcome(
            "undeterminable",
            "政府標準利用規約2.0: 第三者著作物・ロゴ等の例外表示があるため自動許可しない",
        )
    return RuleOutcome("expired", "政府標準利用規約2.0: CC BY 4.0互換として採用（例外表示なし）")


def foreign_wartime_outcome(
    *,
    nationality_confirmed: bool,
    acquisition_date_confirmed: bool,
    treaty_confirmed: bool,
) -> RuleOutcome:
    """§5A-6: 戦時加算。対象国・取得時期・条約により加算日数が異なり、一律日数では
    安全側にならないため、年代計算だけでの自動判定は行わない（常に`undeterminable`）。
    """
    if nationality_confirmed and acquisition_date_confirmed and treaty_confirmed:
        return RuleOutcome(
            "undeterminable",
            "戦時加算: 国籍・取得日・条約は確認済みだが、加算日数は国別に異なり"
            "年代計算のみでの自動許可は行わない（人手確認対象）",
        )
    return RuleOutcome(
        "undeterminable",
        "戦時加算: 国籍・著作権取得日・対象条約を確定できない外国作品は自動許可しない",
    )


def neighboring_rights_outcome() -> RuleOutcome:
    """§5A-7: 著作隣接権（音源）。歴史音源はMVP対象外——常に人手承認を必須とする。"""
    return RuleOutcome(
        "undeterminable", "著作隣接権（音源）: 歴史音源はMVP対象外のため常に人手承認が必要"
    )


def translation_outcome(translator_death_year: int | None, *, today: date) -> RuleOutcome:
    """§5A-10: 翻訳・翻刻・校訂。原文がPDでも翻訳者に別の権利が発生し得るため、
    翻訳者自身の没年で個人著作物と同じ規則を再適用する。
    """
    outcome = personal_authorship_outcome(translator_death_year, today=today)
    return RuleOutcome(outcome.status, f"翻訳者の権利再判定 — {outcome.reason}")
