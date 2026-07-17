"""test_artifact_lock.py — Phase 10タスク4 DoD: 承認後に台本やmediaを変更すると再承認が必要になる"""

from typing import Any

import pytest

from history_radio.media.media_manifest import MediaAsset
from history_radio.publish.episode_page import EpisodePageData
from history_radio.publish.publish_gate import (
    ArtifactLockError,
    compute_artifact_hash,
    evaluate_publish_gate,
    verify_artifact_unchanged,
)
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
            asset_id="asset-1", origin="self_drawn", credit_text="自作図解", used_in=["hook"]
        )
    ]


def test_compute_artifact_hash_is_deterministic_for_identical_inputs() -> None:
    hash_a = compute_artifact_hash(
        episode=_episode(), script=_valid_script(), media_assets=_media_assets()
    )
    hash_b = compute_artifact_hash(
        episode=_episode(), script=_valid_script(), media_assets=_media_assets()
    )
    assert hash_a == hash_b


def test_compute_artifact_hash_changes_when_episode_title_changes() -> None:
    hash_a = compute_artifact_hash(
        episode=_episode(), script=_valid_script(), media_assets=_media_assets()
    )
    hash_b = compute_artifact_hash(
        episode=_episode(title="別のタイトル"), script=_valid_script(), media_assets=_media_assets()
    )
    assert hash_a != hash_b


def test_compute_artifact_hash_changes_when_media_assets_change() -> None:
    hash_a = compute_artifact_hash(
        episode=_episode(), script=_valid_script(), media_assets=_media_assets()
    )
    changed_assets = [
        MediaAsset(
            asset_id="asset-1",
            origin="self_drawn",
            credit_text="変更後のクレジット",
            used_in=["hook"],
        )
    ]
    hash_b = compute_artifact_hash(
        episode=_episode(), script=_valid_script(), media_assets=changed_assets
    )
    assert hash_a != hash_b


def test_verify_artifact_unchanged_passes_when_nothing_changed() -> None:
    """Phase 10タスク4 DoD(裏側): 何も変更していなければ再承認は不要。"""
    episode = _episode()
    script = _valid_script()
    media_assets = _media_assets()
    gate_result = evaluate_publish_gate(
        episode=episode,
        script=script,
        claim_ledger=[],
        media_assets=media_assets,
        source_texts={},
        site_base_url=_SITE,
        audio_validation_passed=True,
    )
    verify_artifact_unchanged(
        gate_result, episode=episode, script=script, media_assets=media_assets
    )  # 例外なし


def test_verify_artifact_unchanged_rejects_a_changed_script() -> None:
    """Phase 10タスク4 DoD: 承認後に台本を変更すると再承認が必要になる。"""
    episode = _episode()
    script = _valid_script()
    media_assets = _media_assets()
    gate_result = evaluate_publish_gate(
        episode=episode,
        script=script,
        claim_ledger=[],
        media_assets=media_assets,
        source_texts={},
        site_base_url=_SITE,
        audio_validation_passed=True,
    )

    changed_script = _script(
        claim_sentence=ScriptSentence(
            text="こっそり書き換えた文なのだ。", kind="claim", claim_id="claim-001"
        )
    )
    with pytest.raises(ArtifactLockError, match="再承認が必要"):
        verify_artifact_unchanged(
            gate_result, episode=episode, script=changed_script, media_assets=media_assets
        )


def test_verify_artifact_unchanged_rejects_changed_media() -> None:
    """Phase 10タスク4 DoD: 承認後にmediaを変更すると再承認が必要になる。"""
    episode = _episode()
    script = _valid_script()
    media_assets = _media_assets()
    gate_result = evaluate_publish_gate(
        episode=episode,
        script=script,
        claim_ledger=[],
        media_assets=media_assets,
        source_texts={},
        site_base_url=_SITE,
        audio_validation_passed=True,
    )

    changed_assets = [
        MediaAsset(
            asset_id="asset-1",
            origin="self_drawn",
            credit_text="差し替えたクレジット",
            used_in=["hook"],
        )
    ]
    with pytest.raises(ArtifactLockError, match="再承認が必要"):
        verify_artifact_unchanged(
            gate_result, episode=episode, script=script, media_assets=changed_assets
        )


def test_verify_artifact_unchanged_rejects_changed_episode_metadata() -> None:
    episode = _episode()
    script = _valid_script()
    media_assets = _media_assets()
    gate_result = evaluate_publish_gate(
        episode=episode,
        script=script,
        claim_ledger=[],
        media_assets=media_assets,
        source_texts={},
        site_base_url=_SITE,
        audio_validation_passed=True,
    )

    changed_episode = _episode(title="こっそり変えたタイトル")
    with pytest.raises(ArtifactLockError, match="再承認が必要"):
        verify_artifact_unchanged(
            gate_result, episode=changed_episode, script=script, media_assets=media_assets
        )
