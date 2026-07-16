"""test_validator.py — Phase 6 DoD: claim_id欠落・台帳外事実・禁止表現の台本拒否を固定する"""

import pytest

from history_radio.domain.models import Claim
from history_radio.script.schema import (
    SECTION_KINDS,
    Script,
    ScriptSection,
    ScriptSentence,
)
from history_radio.script.validator import ScriptValidationError, validate_script


def _claim(claim_id: str = "claim-001", *, allowed: bool = True) -> Claim:
    return Claim(
        claim_id=claim_id,
        text="1872年に新橋横浜間の鉄道が開業した",
        evidence_ids=["evidence-001"],
        source_family_ids=["family-a", "family-b"],
        reliability_score=0.9,
        allowed_in_script=allowed,
        qualification="断定",
    )


def _script(*, claim_sentence: ScriptSentence | None = None) -> Script:
    """7段構成の最小台本。claim文はdevelopment段へ差し込む。"""
    sections: list[ScriptSection] = []
    for kind in SECTION_KINDS:
        sentences = [ScriptSentence(text=f"{kind}の演出文なのだ。", kind="presentation")]
        if kind == "development" and claim_sentence is not None:
            sentences.append(claim_sentence)
        sections.append(ScriptSection(kind=kind, sentences=sentences))
    return Script(episode_id="ep-1", sections=sections)


def test_valid_script_passes() -> None:
    sentence = ScriptSentence(
        text="1872年、新橋横浜間に日本初の鉄道が開業したのだ。", kind="claim", claim_id="claim-001"
    )
    validate_script(_script(claim_sentence=sentence), [_claim()])  # 例外なし


def test_claim_sentence_without_claim_id_is_rejected() -> None:
    """外部検証可能な文に claim_id が無い場合は公開検査を失敗させる（§8.2A）。"""
    sentence = ScriptSentence(text="日本初の鉄道が開業したのだ。", kind="claim", claim_id=None)
    with pytest.raises(ScriptValidationError, match="claim_id が無い"):
        validate_script(_script(claim_sentence=sentence), [_claim()])


def test_claim_id_not_in_ledger_is_rejected() -> None:
    """台帳にない外部事実を追加してはならない（§8.2A）。"""
    sentence = ScriptSentence(text="外部事実なのだ。", kind="claim", claim_id="claim-999")
    with pytest.raises(ScriptValidationError, match="台帳に存在しない"):
        validate_script(_script(claim_sentence=sentence), [_claim()])


def test_disallowed_claim_is_rejected() -> None:
    """独立系統2件未満（allowed_in_script=false）の主張は台本へ入れない。"""
    sentence = ScriptSentence(text="単一系統の主張なのだ。", kind="claim", claim_id="claim-001")
    with pytest.raises(ScriptValidationError, match="allowed_in_script=false"):
        validate_script(_script(claim_sentence=sentence), [_claim(allowed=False)])


def test_forbidden_expression_is_rejected() -> None:
    sentence = ScriptSentence(
        text="いま話題のニュースと同じことが江戸時代にもあったのだ。", kind="presentation"
    )
    script = _script()
    script = Script(
        episode_id="ep-1",
        sections=[
            ScriptSection(kind=s.kind, sentences=[*s.sentences, sentence])
            if s.kind == "hook"
            else s
            for s in script.sections
        ],
    )
    with pytest.raises(ScriptValidationError, match="禁止表現"):
        validate_script(script, [_claim()])


def test_missing_section_is_rejected() -> None:
    """§9.1の7段構成が欠けた台本を拒否する。"""
    script = Script(
        episode_id="ep-1",
        sections=[
            ScriptSection(
                kind=kind, sentences=[ScriptSentence(text="文なのだ。", kind="presentation")]
            )
            for kind in SECTION_KINDS
            if kind != "uncertainty"  # 6. 不確実な点の明示 を欠落させる
        ],
    )
    with pytest.raises(ScriptValidationError, match="7段構成"):
        validate_script(script, [_claim()])


def test_wrong_section_order_is_rejected() -> None:
    reordered = list(SECTION_KINDS[::-1])
    script = Script(
        episode_id="ep-1",
        sections=[
            ScriptSection(
                kind=kind, sentences=[ScriptSentence(text="文なのだ。", kind="presentation")]
            )
            for kind in reordered
        ],
    )
    with pytest.raises(ScriptValidationError, match="7段構成"):
        validate_script(script, [_claim()])


def test_all_problems_are_reported_at_once() -> None:
    """検査失敗は1件ずつでなく全件列挙で返る（修正の往復を減らす）。"""
    bad1 = ScriptSentence(text="claim_idなしの事実なのだ。", kind="claim", claim_id=None)
    bad2 = ScriptSentence(text="台帳外の事実なのだ。", kind="claim", claim_id="claim-999")
    script = _script(claim_sentence=bad1)
    script = Script(
        episode_id="ep-1",
        sections=[
            ScriptSection(kind=s.kind, sentences=[*s.sentences, bad2]) if s.kind == "twist" else s
            for s in script.sections
        ],
    )
    with pytest.raises(ScriptValidationError) as exc_info:
        validate_script(script, [_claim()])
    assert len(exc_info.value.problems) == 2
