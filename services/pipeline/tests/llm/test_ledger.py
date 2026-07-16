"""test_ledger.py — Phase 6 DoD: 独立2系統未満の主張の台本使用不可を固定する"""

import pytest

from history_radio.llm.ledger import ClaimInput, build_claim, build_claim_ledger


def _entry(**overrides: object) -> ClaimInput:
    base: dict[str, object] = {
        "claim_id": "claim-001",
        "text": "1872年に新橋横浜間の鉄道が開業した",
        "evidence_ids": ["evidence-001", "evidence-002"],
        "source_family_ids": ["family-a", "family-b"],
        "reliability_score": 0.9,
        "qualification": "断定",
    }
    base.update(overrides)
    return ClaimInput.model_validate(base)


def test_two_independent_families_allow_script_use() -> None:
    claim = build_claim(_entry())
    assert claim.allowed_in_script is True
    assert claim.qualification == "断定"


def test_single_family_claim_is_not_allowed_in_script() -> None:
    """Phase 6 DoD: 1系統だけの主張が allowed_in_script: false になる。"""
    claim = build_claim(_entry(source_family_ids=["family-a"]))
    assert claim.allowed_in_script is False


def test_single_family_claim_is_forced_to_attribution_qualification() -> None:
    """§6.2: 単一資料の事実は断定にせず「資料帰属」を強制する。"""
    claim = build_claim(_entry(source_family_ids=["family-a"], qualification="断定"))
    assert claim.qualification == "資料帰属"


def test_duplicate_family_ids_do_not_inflate_independence() -> None:
    """同じ系統IDを2回書いても独立2系統にはならない（重複は集合で数える）。"""
    claim = build_claim(_entry(source_family_ids=["family-a", "family-a"]))
    assert claim.allowed_in_script is False


def test_ledger_rejects_duplicate_claim_ids() -> None:
    with pytest.raises(ValueError, match="claim_id重複"):
        build_claim_ledger([_entry(), _entry()])


def test_ledger_builds_all_entries() -> None:
    ledger = build_claim_ledger(
        [
            _entry(),
            _entry(claim_id="claim-002", source_family_ids=["family-a"]),
        ]
    )
    assert [c.allowed_in_script for c in ledger] == [True, False]
