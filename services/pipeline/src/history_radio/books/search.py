"""search.py — 関連書籍検索・機械ランキング（仕様書§10A・development-plan.md Phase 7）。

LLMを使用しない。国立国会図書館サーチ・Open Library・Google Books等（収集は
別タスク）から集めた候補を、この module が採点・足切りする純粋関数群。

fail-closed規則（§10A）:
- ISBNまたはAmazon商品識別子を確認できない候補へアフィリエイトリンクを作らない。
- 書名・著者・ISBNが**2つ以上の書誌系統**で一致しない候補は表示しない
  （select/lineage.pyの「情報の系統数」と同じ思想——出典の数でなく独立した
  書誌データベースの数で数える）。
- 関連度が閾値未満なら、無関係な候補で埋めず「関連書籍なし」とする
  （空リストを返すことでこれを表す——呼び出し側が埋め合わせをしない限り自然に成立）。
"""

from __future__ import annotations

from pydantic import Field

from history_radio.domain.base import SchemaModel

# §10Aの機械ランキング初期式の重み
_TITLE_WEIGHT = 35.0
_SUBJECT_WEIGHT = 25.0
_PERSON_WEIGHT = 20.0
_ERA_WEIGHT = 10.0
_RECENCY_WEIGHT = 5.0
_HAS_AUDIO_WEIGHT = 5.0

DEFAULT_RELEVANCE_THRESHOLD = 40.0
_MIN_INDEPENDENT_SYSTEMS = 2


class BookCandidate(SchemaModel):
    """1つの書誌システムから得た候補1件。"""

    title: str = Field(min_length=1)
    authors: tuple[str, ...]
    isbn: str | None = None
    amazon_asin: str | None = None
    subject_headings: tuple[str, ...] = ()
    publication_year: int | None = None
    has_audio_edition: bool = False
    # 検索先システム（例: "ndl-search" / "open-library" / "google-books"）——
    # 「2つ以上の書誌系統で一致」の系統をこれで数える
    source_system: str = Field(min_length=1)
    source_url: str = Field(min_length=1)


class BookMatchFeatures(SchemaModel):
    """§10Aの入力特徴量（すべて0〜1へ正規化済み）。"""

    title_match: float = Field(ge=0, le=1)
    subject_match: float = Field(ge=0, le=1)
    person_match: float = Field(ge=0, le=1)
    era_match: float = Field(ge=0, le=1)
    recency: float = Field(ge=0, le=1)
    has_audio: float = Field(ge=0, le=1)


def compute_relevance(features: BookMatchFeatures) -> float:
    """§10Aの機械ランキング式で関連度を計算する。"""
    return (
        features.title_match * _TITLE_WEIGHT
        + features.subject_match * _SUBJECT_WEIGHT
        + features.person_match * _PERSON_WEIGHT
        + features.era_match * _ERA_WEIGHT
        + features.recency * _RECENCY_WEIGHT
        + features.has_audio * _HAS_AUDIO_WEIGHT
    )


def _bibliographic_key(candidate: BookCandidate) -> tuple[str, str]:
    """同一の実在書籍とみなすためのキー。ISBNがあれば最優先、無ければ題名+筆頭著者。"""
    if candidate.isbn:
        return ("isbn", candidate.isbn)
    author = candidate.authors[0] if candidate.authors else ""
    return ("title-author", f"{candidate.title}|{author}")


def group_by_bibliographic_match(
    candidates: list[BookCandidate],
) -> dict[tuple[str, str], list[BookCandidate]]:
    """同一書籍とみなせる候補をまとめる（キーは実装詳細——呼び出し側は件数だけ見る）。"""
    groups: dict[tuple[str, str], list[BookCandidate]] = {}
    for c in candidates:
        groups.setdefault(_bibliographic_key(c), []).append(c)
    return groups


def independent_system_count(group: list[BookCandidate]) -> int:
    return len({c.source_system for c in group})


def is_title_only_match(features: BookMatchFeatures) -> bool:
    """§10A「題名だけの曖昧一致は採用しない」——題名以外が全て0の候補を検出する。"""
    return (
        features.title_match > 0
        and features.subject_match == 0
        and features.person_match == 0
        and features.era_match == 0
    )


def has_confirmed_identifier(candidate: BookCandidate) -> bool:
    """§10A: ISBNまたはAmazon商品識別子を確認できるか（アフィリエイトリンク可否の前提）。"""
    return candidate.isbn is not None or candidate.amazon_asin is not None


class RankedBook(SchemaModel):
    representative: BookCandidate
    relevance: float
    independent_systems: int
    affiliate_link_allowed: bool


def rank_books(
    candidates: list[BookCandidate],
    features_by_source_url: dict[str, BookMatchFeatures],
    *,
    relevance_threshold: float = DEFAULT_RELEVANCE_THRESHOLD,
) -> list[RankedBook]:
    """§10Aの全規則を適用して候補を採点・足切りする。

    足切り規則（該当すれば候補ごと除外）:
    - 独立した書誌システムが2件未満（`group_by_bibliographic_match`で束ねた後）
    - 題名だけの曖昧一致（他の特徴量が全て0）
    - 関連度が閾値未満
    残った候補は関連度の降順で返す。閾値未満で全滅すれば空リスト
    （＝「関連書籍なし」——埋め合わせをしない）。
    """
    groups = group_by_bibliographic_match(candidates)
    ranked: list[RankedBook] = []
    for group in groups.values():
        if independent_system_count(group) < _MIN_INDEPENDENT_SYSTEMS:
            continue
        representative = group[0]
        features = features_by_source_url.get(representative.source_url)
        if features is None:
            continue
        if is_title_only_match(features):
            continue
        relevance = compute_relevance(features)
        if relevance < relevance_threshold:
            continue
        ranked.append(
            RankedBook(
                representative=representative,
                relevance=relevance,
                independent_systems=independent_system_count(group),
                affiliate_link_allowed=has_confirmed_identifier(representative),
            )
        )
    ranked.sort(key=lambda r: r.relevance, reverse=True)
    return ranked
