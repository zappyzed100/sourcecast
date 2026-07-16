"""test_episode_page.py — Phase 8 DoD: 不正Schema・欠落出典・未知ライセンスの拒否を固定する"""

from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from history_radio.publish.episode_page import (
    EpisodePageData,
    EpisodePageError,
    render_episode_frontmatter,
    validate_episode_page,
)


def _source(**overrides: object) -> dict[str, Any]:
    base: dict[str, Any] = {
        "name": "Wikipedia『鉄道の日』",
        "url": "https://ja.wikipedia.org/wiki/example",
        "license": "CC BY-SA 4.0",
        "normalized_license_id": "cc-by-sa",
        "credit": "Wikipedia contributors",
        "accessed_at": "2026-07-16",
    }
    base.update(overrides)
    return base


def _data(**overrides: object) -> dict[str, Any]:
    base: dict[str, Any] = {
        "episode_id": "2026-07-16-can-opener",
        "revision": 1,
        "title": "缶切りより缶詰の方が50年も先に生まれていた",
        "summary": "概要文",
        "published_at": "2026-07-16",
        "updated_at": "2026-07-16",
        "sources": [_source()],
        "claims": [{"text": "事実文", "source_indexes": [0]}],
        "corrections": [],
        "related_books": [],
    }
    base.update(overrides)
    return base


def test_valid_data_passes_validation_and_renders() -> None:
    data = EpisodePageData.model_validate(_data())
    validate_episode_page(data)  # 例外なし
    text = render_episode_frontmatter(data)
    assert text.startswith("---\n")
    assert text.endswith("---\n")
    front_matter = yaml.safe_load(text.strip("-\n"))
    assert front_matter["episodeId"] == "2026-07-16-can-opener"
    assert front_matter["schemaVersion"] == 1


def test_missing_sources_is_rejected_at_schema_level() -> None:
    """Phase 8 DoD: 欠落出典（sources空）を拒否する——Pydanticのmin_lengthで即拒否。"""
    with pytest.raises(ValidationError):
        EpisodePageData.model_validate(_data(sources=[]))


def test_missing_required_field_is_rejected() -> None:
    """Phase 8 DoD: 不正Schema（必須フィールド欠落）を拒否する。"""
    payload = _data()
    del payload["title"]
    with pytest.raises(ValidationError):
        EpisodePageData.model_validate(payload)


def test_unknown_field_is_rejected() -> None:
    with pytest.raises(ValidationError):
        EpisodePageData.model_validate(_data(surprise_field="x"))


def test_unknown_license_is_rejected() -> None:
    """Phase 8 DoD: 未知ライセンスの資料を含む場合は生成を拒否する。"""
    data = EpisodePageData.model_validate(_data(sources=[_source(normalized_license_id="unknown")]))
    with pytest.raises(EpisodePageError, match="未知/不採用ライセンス"):
        validate_episode_page(data)


@pytest.mark.parametrize("license_id", ["nc", "nd", "inc", "noc-us", "pdm", "custom-example"])
def test_non_approvable_licenses_are_rejected(license_id: str) -> None:
    data = EpisodePageData.model_validate(
        _data(sources=[_source(normalized_license_id=license_id)])
    )
    with pytest.raises(EpisodePageError):
        validate_episode_page(data)


@pytest.mark.parametrize("license_id", ["cc0", "cc-by", "cc-by-sa", "gov-jp-2.0", "ogl"])
def test_approvable_licenses_pass(license_id: str) -> None:
    data = EpisodePageData.model_validate(
        _data(sources=[_source(normalized_license_id=license_id)])
    )
    validate_episode_page(data)  # 例外なし


def test_claim_referencing_out_of_range_source_index_is_rejected() -> None:
    """development-plan.md Phase 8タスク3の前提: 主張‐出典対応の整合性を生成時に守る。"""
    data = EpisodePageData.model_validate(
        _data(claims=[{"text": "根拠の無い主張", "source_indexes": [5]}])
    )
    with pytest.raises(EpisodePageError, match="存在しない出典index"):
        validate_episode_page(data)


def test_every_claim_reaches_at_least_one_valid_source_url() -> None:
    """Phase 8タスク3 DoD: 全公開主張から1件以上の有効な出典URLへ到達できる。"""
    data = EpisodePageData.model_validate(
        _data(
            sources=[
                _source(name="出典A", url="https://ja.wikipedia.org/wiki/a"),
                _source(name="出典B", url="https://ja.wikipedia.org/wiki/b"),
            ],
            claims=[
                {"text": "出典Aのみに基づく主張", "source_indexes": [0]},
                {"text": "出典A・Bの両方に基づく主張", "source_indexes": [0, 1]},
            ],
        )
    )
    validate_episode_page(data)  # 例外なし

    for claim in data.claims:
        reachable_urls = [data.sources[i].url for i in claim.source_indexes]
        assert len(reachable_urls) >= 1
        assert all(url.startswith(("http://", "https://")) for url in reachable_urls)


def test_audio_url_without_length_bytes_is_rejected() -> None:
    """Phase 9タスク1の前提: RSSのenclosureはurlとlengthの両方が無いと生成できない。"""
    data = EpisodePageData.model_validate(
        _data(audio_url="/audio/2026-07-16-can-opener.mp3", audio_length_bytes=None)
    )
    with pytest.raises(EpisodePageError, match="audio_urlとaudio_length_bytesは対で必須"):
        validate_episode_page(data)


def test_audio_length_bytes_without_url_is_rejected() -> None:
    data = EpisodePageData.model_validate(_data(audio_url=None, audio_length_bytes=123456))
    with pytest.raises(EpisodePageError, match="audio_urlとaudio_length_bytesは対で必須"):
        validate_episode_page(data)


def test_audio_url_and_length_bytes_together_pass() -> None:
    data = EpisodePageData.model_validate(
        _data(audio_url="/audio/2026-07-16-can-opener.mp3", audio_length_bytes=123456)
    )
    validate_episode_page(data)  # 例外なし


def test_zero_or_negative_audio_length_bytes_is_rejected_at_schema_level() -> None:
    with pytest.raises(ValidationError):
        EpisodePageData.model_validate(_data(audio_url="/audio/x.mp3", audio_length_bytes=0))


def test_malformed_episode_id_is_rejected() -> None:
    data = EpisodePageData.model_validate(_data(episode_id="not-a-valid-id!!"))
    with pytest.raises(EpisodePageError, match="形式が不正"):
        validate_episode_page(data)


def test_all_problems_are_reported_at_once() -> None:
    data = EpisodePageData.model_validate(
        _data(
            episode_id="bad id",
            sources=[_source(normalized_license_id="unknown")],
            claims=[{"text": "x", "source_indexes": [9]}],
        )
    )
    with pytest.raises(EpisodePageError) as exc_info:
        validate_episode_page(data)
    assert len(exc_info.value.problems) == 3


def test_frontmatter_keys_are_camel_case() -> None:
    data = EpisodePageData.model_validate(_data())
    text = render_episode_frontmatter(data)
    front_matter = yaml.safe_load(text.strip("-\n"))
    assert "episodeId" in front_matter
    assert "publishedAt" in front_matter
    assert "sourceIndexes" in front_matter["claims"][0]
    assert "episode_id" not in front_matter


def test_chapters_and_audio_url_are_omitted_when_absent() -> None:
    data = EpisodePageData.model_validate(_data())
    text = render_episode_frontmatter(data)
    front_matter = yaml.safe_load(text.strip("-\n"))
    assert "chapters" not in front_matter
    assert "audioUrl" not in front_matter


def test_chapters_and_audio_url_are_included_when_present() -> None:
    data = EpisodePageData.model_validate(
        _data(audio_url="/audio/x.mp3", chapters=[{"title": "導入", "start_seconds": 0}])
    )
    text = render_episode_frontmatter(data)
    front_matter = yaml.safe_load(text.strip("-\n"))
    assert front_matter["audioUrl"] == "/audio/x.mp3"
    assert front_matter["chapters"][0]["startSeconds"] == 0
