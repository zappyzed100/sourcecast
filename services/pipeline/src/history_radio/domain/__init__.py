"""domain/__init__.py — 副作用のない型・状態機械（Pydanticモデル）"""

from history_radio.domain.episode_state import (
    ALL_STATES,
    ALLOWED_FORWARD,
    FAILURE_STATES,
    TERMINAL_STATES,
    EpisodeState,
    InvalidTransitionError,
    transition,
)
from history_radio.domain.models import (
    AuditEvent,
    Candidate,
    CandidateDecision,
    Claim,
    Episode,
    Job,
    RightsDecision,
    SourceRecord,
)

__all__ = [
    "ALL_STATES",
    "ALLOWED_FORWARD",
    "FAILURE_STATES",
    "TERMINAL_STATES",
    "AuditEvent",
    "Candidate",
    "CandidateDecision",
    "Claim",
    "Episode",
    "EpisodeState",
    "InvalidTransitionError",
    "Job",
    "RightsDecision",
    "SourceRecord",
    "transition",
]
