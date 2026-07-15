"""test_models.py — Phase 1 DoD: 必須項目欠落・未知schema_versionの拒否を固定する"""

from datetime import datetime, timezone
from typing import Any

import pytest
from pydantic import ValidationError

from history_radio.domain import (
    AuditEvent,
    Candidate,
    Claim,
    Episode,
    Job,
    RightsDecision,
    SourceRecord,
)

NOW = datetime(2026, 7, 16, tzinfo=timezone.utc)

VALID_PAYLOADS: dict[type, dict[str, Any]] = {
    SourceRecord: {
        "source_id": "wikimedia_commons",
        "status": "approved",
        "use_class": "A",
        "normalized_license_id": "cc0",
        "commercial_use": "conditional",
        "modification": "conditional",
        "redistribution": "conditional",
        "attribution": "required_if_not_cc0",
        "share_alike": "preserve_per_asset",
        "third_party_exception": "deny",
        "territory": "global",
        "terms_url": "https://commons.wikimedia.org/wiki/Commons:Reusing_content_outside_Wikimedia",
        "terms_checked_at": NOW,
        "recheck_days": 90,
    },
    RightsDecision: {
        "decision_id": "rd-001",
        "document_id": "doc-001",
        "decision": "allow_public_use",
        "rule_version": "5A@1",
        "reasons": ["公表後70年経過"],
        "computed_at": NOW,
    },
    Candidate: {
        "candidate_id": "cand-001",
        "topic_title": "example",
        "score": 42.0,
        "score_breakdown": {"date_match": 1.0},
        "independent_source_families": 2,
    },
    Claim: {
        "claim_id": "claim-001",
        "text": "公開可能な事実文",
        "evidence_ids": ["evidence-001"],
        "source_family_ids": ["family-a"],
        "reliability_score": 0.8,
        "allowed_in_script": True,
        "qualification": "断定",
    },
    Episode: {
        "episode_id": "ep-001",
        "state": "collected",
        "revision": 1,
        "title": "example",
        "created_at": NOW,
        "updated_at": NOW,
    },
    Job: {
        "job_id": "job-001",
        "kind": "ingest",
        "status": "queued",
    },
    AuditEvent: {
        "event_id": "audit-001",
        "entity_type": "episode",
        "entity_id": "ep-001",
        "action": "publish",
        "actor": "system",
        "occurred_at": NOW,
    },
}


@pytest.mark.parametrize("model_cls", list(VALID_PAYLOADS))
def test_valid_payload_constructs(model_cls: type) -> None:
    instance = model_cls(**VALID_PAYLOADS[model_cls])
    assert instance.schema_version == 1


@pytest.mark.parametrize("model_cls", list(VALID_PAYLOADS))
def test_missing_required_field_rejected(model_cls: type) -> None:
    payload = dict(VALID_PAYLOADS[model_cls])
    first_key = next(iter(payload))
    del payload[first_key]
    with pytest.raises(ValidationError):
        model_cls(**payload)


@pytest.mark.parametrize("model_cls", list(VALID_PAYLOADS))
def test_unknown_schema_version_rejected(model_cls: type) -> None:
    payload = dict(VALID_PAYLOADS[model_cls]) | {"schema_version": 2}
    with pytest.raises(ValidationError):
        model_cls(**payload)


@pytest.mark.parametrize("model_cls", list(VALID_PAYLOADS))
def test_unknown_extra_field_rejected(model_cls: type) -> None:
    payload = dict(VALID_PAYLOADS[model_cls]) | {"__unknown_field__": "x"}
    with pytest.raises(ValidationError):
        model_cls(**payload)


def test_models_are_frozen() -> None:
    episode = Episode(**VALID_PAYLOADS[Episode])
    with pytest.raises(ValidationError):
        episode.title = "変更後"  # type: ignore[misc]
