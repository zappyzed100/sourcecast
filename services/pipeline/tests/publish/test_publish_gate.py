"""test_publish_gate.py — Phase 10タスク1 DoD: 各項目を1つずつ失敗させたケースが
すべてpublish_ready=falseになる（AND評価であることの直接証明）。
"""

from typing import Any

from history_radio.domain.models import Claim
from history_radio.media.media_manifest import MediaAsset
from history_radio.publish.episode_page import EpisodePageData
from history_radio.publish.publish_gate import evaluate_publish_gate
from history_radio.script.schema import SECTION_KINDS, Script, ScriptSection, ScriptSentence

_SITE = "https://example.jp"


def _source(**overrides: object) -> dict[str, Any]:
    base: dict[str, Any] = {
        "name": "Wikipedia『東京タワー』",
        "url": "https://ja.wikipedia.org/wiki/example",
        "license": "CC BY-SA 4.0",
        "normalized_license_id": "cc-by-sa",
        "credit": "Wikipedia contributors",
        "accessed_at": "2026-07-19",
    }
    base.update(overrides)
    return base


def _episode(**overrides: object) -> EpisodePageData:
    base: dict[str, Any] = {
        "episode_id": "2026-07-19-tokyo-tower",
        "revision": 1,
        "title": "東京タワーの色の話",
        "summary": "概要文",
        "published_at": "2026-07-19",
        "updated_at": "2026-07-19",
        "sources": [_source()],
        "claims": [{"text": "事実文", "source_indexes": [0]}],
        "corrections": [],
        "related_books": [],
        "audio_url": "/audio/2026-07-19-tokyo-tower.mp3",
        "audio_length_bytes": 120429,
    }
    base.update(overrides)
    return EpisodePageData.model_validate(base)


def _claim(claim_id: str = "claim-001", *, allowed: bool = True) -> Claim:
    return Claim(
        claim_id=claim_id,
        text="東京タワーは白と橙色に塗られている",
        evidence_ids=["evidence-001"],
        source_family_ids=["family-a", "family-b"],
        reliability_score=0.9,
        allowed_in_script=allowed,
        qualification="断定",
    )


def _script(*, claim_sentence: ScriptSentence | None = None) -> Script:
    sections: list[ScriptSection] = []
    for kind in SECTION_KINDS:
        sentences = [ScriptSentence(text=f"{kind}の演出文なのだ。", kind="presentation")]
        if kind == "development" and claim_sentence is not None:
            sentences.append(claim_sentence)
        sections.append(ScriptSection(kind=kind, sentences=sentences))
    return Script(episode_id="2026-07-19-tokyo-tower", sections=sections)


def _valid_script() -> Script:
    sentence = ScriptSentence(
        text="東京タワーは白と橙色に塗られているのだ。", kind="claim", claim_id="claim-001"
    )
    return _script(claim_sentence=sentence)


def _media_assets() -> list[MediaAsset]:
    return [
        MediaAsset(
            asset_id="asset-1",
            origin="self_drawn",
            credit_text="自作図解",
            used_in=["hook"],
        )
    ]


def _gate_kwargs(**overrides: object) -> dict[str, Any]:
    base: dict[str, Any] = {
        "episode": _episode(),
        "script": _valid_script(),
        "claim_ledger": [_claim()],
        "media_assets": _media_assets(),
        "source_texts": {0: "出典本文はここに置くが台本とは無関係の内容にしてある。"},
        "site_base_url": _SITE,
        "audio_validation_passed": True,
        "audio_validation_problems": (),
    }
    base.update(overrides)
    return base


def test_all_checks_pass_and_publish_ready_is_true() -> None:
    result = evaluate_publish_gate(**_gate_kwargs())
    assert result.publish_ready is True
    assert all(c.passed for c in result.checks)
    assert result.episode_id == "2026-07-19-tokyo-tower"
    assert result.rule_version


def _check(result: Any, name: str) -> Any:
    return next(c for c in result.checks if c.name == name)


def test_rights_and_episode_schema_failure_alone_fails_the_gate() -> None:
    bad_episode = _episode(sources=[_source(normalized_license_id="unknown")])
    result = evaluate_publish_gate(**_gate_kwargs(episode=bad_episode))
    assert result.publish_ready is False
    assert _check(result, "rights_and_episode_schema").passed is False
    assert _check(result, "script_and_claims").passed is True
    assert _check(result, "media_manifest").passed is True


def test_script_and_claims_failure_alone_fails_the_gate() -> None:
    bad_script = _script(
        claim_sentence=ScriptSentence(
            text="claim_idなしの事実なのだ。", kind="claim", claim_id=None
        )
    )
    result = evaluate_publish_gate(**_gate_kwargs(script=bad_script))
    assert result.publish_ready is False
    assert _check(result, "script_and_claims").passed is False
    assert _check(result, "rights_and_episode_schema").passed is True
    assert _check(result, "media_manifest").passed is True


def test_reproduction_similarity_failure_alone_fails_the_gate() -> None:
    long_ja = "東京タワーの外観は白と橙色で塗り分けられており航空法上の規定に従っている"
    script = _script(
        claim_sentence=ScriptSentence(text=long_ja, kind="claim", claim_id="claim-001")
    )
    result = evaluate_publish_gate(
        **_gate_kwargs(script=script, source_texts={0: f"出典冒頭。{long_ja}。出典末尾。"})
    )
    assert result.publish_ready is False
    assert _check(result, "reproduction_similarity").passed is False
    assert _check(result, "rights_and_episode_schema").passed is True
    assert _check(result, "media_manifest").passed is True


def test_forbidden_words_failure_alone_fails_the_gate() -> None:
    script = _script(
        claim_sentence=ScriptSentence(
            text="事故が発生したのだ。", kind="claim", claim_id="claim-001"
        )
    )
    result = evaluate_publish_gate(**_gate_kwargs(script=script))
    assert result.publish_ready is False
    assert _check(result, "forbidden_words").passed is False
    assert _check(result, "rights_and_episode_schema").passed is True
    assert _check(result, "script_and_claims").passed is True


def test_media_manifest_failure_alone_fails_the_gate() -> None:
    bad_assets = [
        MediaAsset(asset_id="asset-1", origin="self_drawn", credit_text="", used_in=["hook"])
    ]
    result = evaluate_publish_gate(**_gate_kwargs(media_assets=bad_assets))
    assert result.publish_ready is False
    assert _check(result, "media_manifest").passed is False
    assert _check(result, "rights_and_episode_schema").passed is True
    assert _check(result, "script_and_claims").passed is True


def test_audio_failure_alone_fails_the_gate() -> None:
    result = evaluate_publish_gate(
        **_gate_kwargs(
            audio_validation_passed=False, audio_validation_problems=("無音区間が長すぎる",)
        )
    )
    assert result.publish_ready is False
    assert _check(result, "audio").passed is False
    assert _check(result, "audio").reasons == ("無音区間が長すぎる",)
    assert _check(result, "rights_and_episode_schema").passed is True
    assert _check(result, "media_manifest").passed is True


def test_rss_and_url_consistency_failure_alone_fails_the_gate() -> None:
    # audio_url/audio_length_bytesを両方ともNoneにする(episode_page側の対必須検証は
    # 「どちらか片方だけ欠落」を拒否する規則なので、両方Noneはそちらは通る——
    # RSS配信には実際の音声が必要という、より強い要求をrss_and_url_consistencyだけが検査する)。
    bad_episode = _episode(audio_url=None, audio_length_bytes=None)
    result = evaluate_publish_gate(**_gate_kwargs(episode=bad_episode))
    assert result.publish_ready is False
    assert _check(result, "rss_and_url_consistency").passed is False
    assert _check(result, "rights_and_episode_schema").passed is True
    assert _check(result, "media_manifest").passed is True


def test_gate_result_reports_rule_version_for_every_check() -> None:
    """development-plan.md Phase 10タスク3の前提: 規則版を結果へ含める。"""
    result = evaluate_publish_gate(**_gate_kwargs())
    assert result.rule_version == "2026-07-19.1"
    assert len(result.checks) == 7
