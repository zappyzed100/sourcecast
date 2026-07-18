"""domain/__init__.py — 副作用のない型・状態機械（Pydanticモデル）"""

from history_radio.domain.episode_state import (
    ALL_STATES,
    ALLOWED_FORWARD,
    FAILURE_STATES,
    FORWARD_SEQUENCE,
    TERMINAL_STATES,
    EpisodeState,
    InvalidTransitionError,
    remaining_forward_states,
    transition,
)
from history_radio.domain.models import (
    AuditEvent,
    Candidate,
    CandidateDecision,
    Claim,
    Episode,
    Job,
    JobLogEntry,
    RightsDecision,
    SourceRecord,
)

__all__ = [
    "ALL_STATES",
    "ALLOWED_FORWARD",
    "FAILURE_STATES",
    "FORWARD_SEQUENCE",
    "TERMINAL_STATES",
    "AuditEvent",
    "Candidate",
    "CandidateDecision",
    "Claim",
    "Episode",
    "EpisodeState",
    "InvalidTransitionError",
    "Job",
    "JobLogEntry",
    "RightsDecision",
    "SourceRecord",
    "remaining_forward_states",
    "transition",
]
