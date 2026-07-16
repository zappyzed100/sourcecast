"""news_filter.py — ニュース連動の安全フィルター（仕様書§6A.2）。LLM不使用。

契約:
- ニュース本文を歴史情報の出典に使用しない——ニュースは**題材選出用の単語取得だけ**。
  この module が返す `NewsDerivedTerms` はURLフィールドを持たない（extra="forbid"の
  frozenモデル）ため、ニュースURLが公開出典一覧へ混入する経路が型レベルで存在しない。
- 禁止語が1件でも含まれるニュースは関連付け対象から除外する。判定に迷うニュース
  （カテゴリ不明・イベント型不明）は採用しない（fail closed）。
- 許可カテゴリ**と**許可イベント型の**両方**に一致することを必要とする——禁止語に
  該当しないことだけを安全判定の根拠にしない。
- 個人名はニュース連動語に使わない。国・地域・一般名詞・技術名だけを採用する。
- MVPは一般ニュースRSSを使わず、§5.12の官公庁・大学・研究機関の公式発表のみ対象
  （どのソースを読むかは収集側の設定——この module は与えられた見出し・語を検査する）。
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from history_radio.domain.base import SchemaModel

# §6A.2の初期設定: ニュース連動対象の許可カテゴリ
DEFAULT_ALLOWED_CATEGORIES = frozenset({"科学", "宇宙", "考古学", "文化財", "技術", "交通", "祝祭"})

# §6A.2の禁止語辞書（初期値。運用で定期的に再評価・追記する——config化はPhase 11で
# 管理画面と併せて行い、それまでは引数で差し替え可能にしておく）
DEFAULT_FORBIDDEN_WORDS = frozenset(
    {
        "死亡",
        "殺人",
        "傷害",
        "事故",
        "災害",
        "行方不明",
        "戦争",
        "テロ",
        "侵攻",
        "空爆",
        "人質",
        "性犯罪",
        "性的暴行",
        "虐待",
        "差別",
        "ヘイト",
        "疫病",
        "感染拡大",
        "重病",
        "自殺",
        "自傷",
        "葬儀",
        "追悼",
        "被害者",
        "不祥事",
        "逮捕",
        "告発",
        "炎上",
        "速報",
        "緊急",
    }
)

# 語の種別: 個人名（person）は原則採用しない（§6A.2）
TermKind = Literal["country", "region", "common_noun", "technology", "person"]
_ADOPTABLE_TERM_KINDS = frozenset({"country", "region", "common_noun", "technology"})

# 「交通」カテゴリで許可されるイベント型（§6A.2: 事故・運休・災害情報を除き、
# 許可イベント型だけに限定する）。他カテゴリもイベント型一致を必須とする
DEFAULT_ALLOWED_EVENT_TYPES = frozenset(
    {"新路線", "保存車両", "技術史", "記念日", "研究成果", "発見", "公開", "式典"}
)


class NewsTerm(SchemaModel):
    text: str = Field(min_length=1)
    kind: TermKind


class NewsDerivedTerms(SchemaModel):
    """題材選出に渡してよい語の集合。**URLを持たない**——公開出典一覧へ混入し得ない。"""

    terms: tuple[str, ...]
    category: str
    event_type: str


class NewsRejected(SchemaModel):
    """不採用の判定結果と理由（監査・再評価用）。"""

    reasons: tuple[str, ...]


def evaluate_news_item(
    *,
    headline: str,
    category: str | None,
    event_type: str | None,
    terms: list[NewsTerm],
    allowed_categories: frozenset[str] = DEFAULT_ALLOWED_CATEGORIES,
    allowed_event_types: frozenset[str] = DEFAULT_ALLOWED_EVENT_TYPES,
    forbidden_words: frozenset[str] = DEFAULT_FORBIDDEN_WORDS,
) -> NewsDerivedTerms | NewsRejected:
    """ニュース1件を検査し、採用なら選出用語（URLなし）を、不採用なら理由を返す。"""
    reasons: list[str] = []

    if category is None:
        reasons.append("カテゴリ不明（判定に迷うニュースは採用しない — §6A.2）")
    elif category not in allowed_categories:
        reasons.append(f"許可カテゴリ外: {category}")

    if event_type is None:
        reasons.append("イベント型不明（許可カテゴリ・許可イベント型の両方一致が必要）")
    elif event_type not in allowed_event_types:
        reasons.append(f"許可イベント型外: {event_type}")

    hit_words = sorted(w for w in forbidden_words if w in headline)
    if hit_words:
        reasons.append(f"禁止語を含む: {hit_words}（1件でも含めば除外 — §6A.2）")

    if reasons:
        return NewsRejected(reasons=tuple(reasons))

    adoptable = tuple(
        t.text
        for t in terms
        if t.kind in _ADOPTABLE_TERM_KINDS and not any(w in t.text for w in forbidden_words)
    )
    return NewsDerivedTerms(terms=adoptable, category=category or "", event_type=event_type or "")
