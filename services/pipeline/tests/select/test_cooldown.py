"""test_cooldown.py — Phase 5 DoD: クールダウン期間内の重複候補が順位から除外されることを固定する"""

from datetime import date

from history_radio.select.cooldown import (
    PastUsage,
    cooling_entities,
    filter_cooled_candidates,
    is_cooling_down,
)


def test_entity_used_within_cooldown_excludes_candidate() -> None:
    history = [PastUsage(entity="西郷隆盛", used_on=date(2026, 7, 1))]
    assert is_cooling_down(
        frozenset({"西郷隆盛"}), history, today=date(2026, 7, 16), cooldown_days=30
    )


def test_entity_outside_cooldown_is_available_again() -> None:
    history = [PastUsage(entity="西郷隆盛", used_on=date(2026, 5, 1))]
    assert not is_cooling_down(
        frozenset({"西郷隆盛"}), history, today=date(2026, 7, 16), cooldown_days=30
    )


def test_cooldown_boundary_day_is_still_cooling() -> None:
    """境界: ちょうどcooldown_days前の使用はまだ期間内（>=判定）。"""
    history = [PastUsage(entity="鉄道", used_on=date(2026, 6, 16))]
    assert cooling_entities(history, today=date(2026, 7, 16), cooldown_days=30) == frozenset(
        {"鉄道"}
    )
    # 1日過ぎれば解除
    assert cooling_entities(history, today=date(2026, 7, 17), cooldown_days=30) == frozenset()


def test_filter_removes_only_overlapping_candidates_and_keeps_order() -> None:
    history = [
        PastUsage(entity="関ヶ原の戦い", used_on=date(2026, 7, 10)),
        PastUsage(entity="伊藤博文", used_on=date(2026, 7, 12)),
    ]
    candidates = [
        ("cand-1", frozenset({"縄文土器", "青森"})),
        ("cand-2", frozenset({"関ヶ原の戦い", "徳川家康"})),  # 期間内エンティティを含む
        ("cand-3", frozenset({"月面探査"})),
        ("cand-4", frozenset({"伊藤博文"})),  # 期間内
    ]
    assert filter_cooled_candidates(candidates, history, today=date(2026, 7, 16)) == [
        "cand-1",
        "cand-3",
    ]


def test_no_history_filters_nothing() -> None:
    candidates = [("cand-1", frozenset({"任意"}))]
    assert filter_cooled_candidates(candidates, [], today=date(2026, 7, 16)) == ["cand-1"]
