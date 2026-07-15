"""test_engine.py — Phase 3 DoD: fail-closedな最終判定と、判定不能組合せの拒否を固定する"""

from datetime import datetime, timezone

import pytest

from history_radio.rights.engine import (
    RULE_VERSION,
    build_rights_decision,
    decide_from_license,
)


@pytest.mark.parametrize("normalized_license_id", ["cc0", "cc-by", "cc-by-sa", "gov-jp-2.0"])
def test_named_auto_approvable_licenses_allow_public_use_without_exception(
    normalized_license_id: str,
) -> None:
    decision, reasons = decide_from_license(normalized_license_id)
    assert decision == "allow_public_use"
    assert reasons


def test_unknown_license_is_internal_research_only_not_public() -> None:
    decision, _reasons = decide_from_license("unknown")
    assert decision == "internal_research_only"


@pytest.mark.parametrize("normalized_license_id", ["cc0", "cc-by", "cc-by-sa", "gov-jp-2.0"])
def test_third_party_exception_downgrades_auto_approvable_license_to_manual_review(
    normalized_license_id: str,
) -> None:
    decision, _reasons = decide_from_license(normalized_license_id, third_party_exception=True)
    assert decision == "manual_review"


def test_terms_fetch_failure_denies_regardless_of_license() -> None:
    decision, _reasons = decide_from_license("cc0", terms_fetch_failed=True)
    assert decision == "deny"


def test_government_work_allows_even_with_unknown_license_field() -> None:
    decision, _reasons = decide_from_license("unknown", government_work=True)
    assert decision == "allow_public_use"


def test_custom_site_terms_require_manual_review() -> None:
    decision, _reasons = decide_from_license("custom-gallica")
    assert decision == "manual_review"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"normalized_license_id": "unknown"},
        {"normalized_license_id": "pdm"},
        {"normalized_license_id": "noc-us"},
        {"normalized_license_id": "cc-by", "third_party_exception": True},
        {"normalized_license_id": "cc0", "terms_fetch_failed": True},
        {"normalized_license_id": "not-a-real-license-id"},
    ],
)
def test_missing_or_undeterminable_inputs_never_yield_allow_public_use(
    kwargs: dict[str, object],
) -> None:
    decision, _reasons = decide_from_license(**kwargs)  # type: ignore[arg-type]
    assert decision != "allow_public_use"


def test_build_rights_decision_stamps_rule_version_and_computed_at() -> None:
    now = datetime(2026, 7, 16, tzinfo=timezone.utc)
    decision = build_rights_decision(
        decision_id="dec-1",
        document_id="doc-1",
        normalized_license_id="cc0",
        now=now,
    )
    assert decision.decision == "allow_public_use"
    assert decision.rule_version == RULE_VERSION
    assert decision.computed_at == now
    assert decision.reasons
