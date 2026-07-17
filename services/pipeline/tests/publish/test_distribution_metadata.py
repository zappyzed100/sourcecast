"""test_distribution_metadata.py — Phase 9タスク2 DoD: 全配信先で同じepisode_idを使う"""

from typing import Any

import pytest

from history_radio.publish.distribution_metadata import (
    DistributionMetadataError,
    build_all_distribution_metadata,
    build_amazon_music_metadata,
    build_podcast_metadata,
    build_youtube_metadata,
)
from history_radio.publish.episode_page import EpisodePageData

_SITE = "https://example.jp"


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


def _episode(**overrides: object) -> EpisodePageData:
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
    return EpisodePageData.model_validate(base)


def test_youtube_metadata_places_page_url_near_top_of_description() -> None:
    """仕様書§10D: 説明欄の先頭付近に恒久エピソードページを掲載する。"""
    episode = _episode()
    metadata = build_youtube_metadata(episode, site_base_url=_SITE)
    assert metadata.episode_id == episode.episode_id
    assert metadata.description.startswith("https://example.jp/episodes/2026-07-16-can-opener/")


def test_youtube_metadata_defaults_to_unlisted_privacy() -> None:
    """仕様書§10D: 自動投稿開始前は非公開または限定公開でアップロードする。"""
    metadata = build_youtube_metadata(_episode(), site_base_url=_SITE)
    assert metadata.privacy_status == "unlisted"


def test_podcast_metadata_requires_audio_fields() -> None:
    episode = _episode(audio_url=None, audio_length_bytes=None)
    with pytest.raises(DistributionMetadataError, match="audio_url/audio_length_bytesが無い"):
        build_podcast_metadata(episode, site_base_url=_SITE)


def test_podcast_metadata_carries_enclosure_fields() -> None:
    episode = _episode(audio_url="/audio/x.mp3", audio_length_bytes=120429)
    metadata = build_podcast_metadata(episode, site_base_url=_SITE)
    assert metadata.audio_url == "/audio/x.mp3"
    assert metadata.audio_length_bytes == 120429
    assert metadata.audio_mime_type == "audio/mpeg"


def test_amazon_music_metadata_links_to_permanent_page() -> None:
    episode = _episode()
    metadata = build_amazon_music_metadata(episode, site_base_url=_SITE)
    assert metadata.page_url == "https://example.jp/episodes/2026-07-16-can-opener/"
    assert metadata.page_url in metadata.description


def test_all_distribution_metadata_share_the_same_episode_id() -> None:
    """Phase 9タスク2 DoD: 全配信先で同じepisode_idを冪等キーとして使う。"""
    episode = _episode(audio_url="/audio/x.mp3", audio_length_bytes=120429)
    metadata_set = build_all_distribution_metadata(episode, site_base_url=_SITE)
    assert metadata_set.youtube.episode_id == episode.episode_id
    assert metadata_set.podcast.episode_id == episode.episode_id
    assert metadata_set.amazon_music.episode_id == episode.episode_id


def test_build_all_fails_when_podcast_metadata_cannot_be_built() -> None:
    episode = _episode(audio_url=None, audio_length_bytes=None)
    with pytest.raises(DistributionMetadataError):
        build_all_distribution_metadata(episode, site_base_url=_SITE)
