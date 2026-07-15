"""episode_state.py — エピソードの状態機械（仕様書 §6.1）を純粋関数で定義する。

collected -> rights_passed -> topic_selected -> facts_verified -> script_generated
  -> script_verified -> media_generated -> publish_ready -> approved -> published

ゲート失敗は rejected、外部障害は blocked（仕様書§6.1・§14）。どちらも本モジュールでは
終端として扱う——再開・再試行は Job 側の別実行として表現し（仕様書§14「工程単位で
再実行」）、エピソードの状態を巻き戻す辺としては定義しない（段階飛ばし・逆行の防止を
型で保証するのが本モジュールの責務）。
"""

from __future__ import annotations

from typing import Literal, get_args

EpisodeState = Literal[
    "collected",
    "rights_passed",
    "topic_selected",
    "facts_verified",
    "script_generated",
    "script_verified",
    "media_generated",
    "publish_ready",
    "approved",
    "published",
    "rejected",
    "blocked",
]

ALL_STATES: frozenset[EpisodeState] = frozenset(get_args(EpisodeState))

# 前進辺のみ（順序固定・段階飛ばし禁止 — §6.1の状態機械そのもの）
_FORWARD_SEQUENCE: tuple[EpisodeState, ...] = (
    "collected",
    "rights_passed",
    "topic_selected",
    "facts_verified",
    "script_generated",
    "script_verified",
    "media_generated",
    "publish_ready",
    "approved",
    "published",
)
ALLOWED_FORWARD: dict[EpisodeState, EpisodeState] = {
    _FORWARD_SEQUENCE[i]: _FORWARD_SEQUENCE[i + 1] for i in range(len(_FORWARD_SEQUENCE) - 1)
}

TERMINAL_STATES: frozenset[EpisodeState] = frozenset({"published", "rejected", "blocked"})
FAILURE_STATES: frozenset[EpisodeState] = frozenset({"rejected", "blocked"})


class InvalidTransitionError(ValueError):
    """許可されない状態遷移（段階飛ばし・逆行・終端からの遷移等）。"""

    def __init__(self, current: EpisodeState, target: EpisodeState) -> None:
        super().__init__(f"不正な状態遷移: {current!r} -> {target!r}")
        self.current = current
        self.target = target


def transition(current: EpisodeState, target: EpisodeState) -> EpisodeState:
    """current から target への遷移が許可されているかを検査し、許可なら target を返す。

    許可される遷移:
      - 前進辺（ALLOWED_FORWARD どおり。段階飛ばし・逆行は不可）
      - 終端でない状態から rejected / blocked へ（ゲート失敗・外部障害はいつでも起こり得る）
    許可されない遷移は InvalidTransitionError を送出する（副作用なし・例外で意図を示す）。
    """
    if current in TERMINAL_STATES:
        raise InvalidTransitionError(current, target)
    if target in FAILURE_STATES:
        return target
    if ALLOWED_FORWARD.get(current) != target:
        raise InvalidTransitionError(current, target)
    return target
