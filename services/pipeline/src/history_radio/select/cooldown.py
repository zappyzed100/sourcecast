"""cooldown.py — 類似題材・同一人物・同一事件のクールダウン（仕様書§6A.1「直近使用」）。

過去回で使ったエンティティ（人物・事件・国・時代等）を一定期間、候補順位から
除外する純粋関数。日付は呼び出し側が渡す（現在時刻を内部で取らない — AGENTS.md §8
のClock注入と同じ規律）。
"""

from __future__ import annotations

from datetime import date, timedelta

from pydantic import Field

from history_radio.domain.base import SchemaModel

DEFAULT_COOLDOWN_DAYS = 30


class PastUsage(SchemaModel):
    """過去回でのエンティティ使用記録1件。"""

    entity: str = Field(min_length=1)
    used_on: date


def cooling_entities(
    history: list[PastUsage], *, today: date, cooldown_days: int = DEFAULT_COOLDOWN_DAYS
) -> frozenset[str]:
    """クールダウン期間内のエンティティ集合を返す（境界日はまだ期間内）。"""
    threshold = today - timedelta(days=cooldown_days)
    return frozenset(u.entity for u in history if u.used_on >= threshold)


def is_cooling_down(
    candidate_entities: frozenset[str],
    history: list[PastUsage],
    *,
    today: date,
    cooldown_days: int = DEFAULT_COOLDOWN_DAYS,
) -> bool:
    """候補のエンティティが1つでも期間内なら真（順位から除外する）。"""
    return bool(
        candidate_entities & cooling_entities(history, today=today, cooldown_days=cooldown_days)
    )


def filter_cooled_candidates(
    candidates: list[tuple[str, frozenset[str]]],
    history: list[PastUsage],
    *,
    today: date,
    cooldown_days: int = DEFAULT_COOLDOWN_DAYS,
) -> list[str]:
    """(candidate_id, エンティティ集合) の列から、期間内重複のない候補IDだけを順序維持で返す。"""
    cooling = cooling_entities(history, today=today, cooldown_days=cooldown_days)
    return [cid for cid, entities in candidates if not (entities & cooling)]
