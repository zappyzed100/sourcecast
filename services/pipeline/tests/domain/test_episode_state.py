"""test_episode_state.py — Phase 1 DoD: 全許可遷移と代表的な禁止遷移を表駆動で固定する"""

import pytest

from history_radio.domain.episode_state import (
    ALL_STATES,
    InvalidTransitionError,
    transition,
)

ALLOWED_TRANSITIONS = [
    ("collected", "rights_passed"),
    ("rights_passed", "topic_selected"),
    ("topic_selected", "facts_verified"),
    ("facts_verified", "script_generated"),
    ("script_generated", "script_verified"),
    ("script_verified", "media_generated"),
    ("media_generated", "publish_ready"),
    ("publish_ready", "approved"),
    ("approved", "published"),
]

# 非終端状態からはいつでもゲート失敗/外部障害へ倒れてよい
FAILURE_TRANSITIONS = [
    (state, failure)
    for state in ("collected", "topic_selected", "media_generated", "publish_ready")
    for failure in ("rejected", "blocked")
]

FORBIDDEN_TRANSITIONS = [
    ("collected", "topic_selected"),  # 段階飛ばし
    ("collected", "script_generated"),  # 段階飛ばし
    ("script_generated", "collected"),  # 逆行
    ("published", "collected"),  # 逆行
    ("published", "approved"),  # 終端からの遷移
    ("rejected", "collected"),  # 終端からの遷移
    ("blocked", "collected"),  # 終端からの遷移
    ("collected", "collected"),  # 自己ループ（前進辺に無い）
]


@pytest.mark.parametrize(("current", "target"), ALLOWED_TRANSITIONS)
def test_allowed_forward_transitions(current: str, target: str) -> None:
    assert transition(current, target) == target  # type: ignore[arg-type]


@pytest.mark.parametrize(("current", "target"), FAILURE_TRANSITIONS)
def test_failure_transitions_allowed_from_any_nonterminal_state(current: str, target: str) -> None:
    assert transition(current, target) == target  # type: ignore[arg-type]


@pytest.mark.parametrize(("current", "target"), FORBIDDEN_TRANSITIONS)
def test_forbidden_transitions_rejected(current: str, target: str) -> None:
    with pytest.raises(InvalidTransitionError):
        transition(current, target)  # type: ignore[arg-type]


def test_all_states_covered_by_either_forward_or_failure_or_terminal() -> None:
    """状態機械の状態一覧が仕様書§6.1どおり12個であることを固定する（回帰の早期検知）。"""
    assert len(ALL_STATES) == 12
