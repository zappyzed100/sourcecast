"""distribution_metadata.py — YouTube・Podcast・Amazon Music向けメタデータ生成
（仕様書§10D・development-plan.md Phase 9タスク2）。

`EpisodePageData`という単一の正本から各配信先向けメタデータを導出する純粋関数群
（決定と実行の分離——episode_page.py/slides.pyと同じ方針。実際のアップロードAPI呼び出しは
ここでは行わない）。全メタデータが`episode_id`を共通の冪等キーとして持つことを
`build_all_distribution_metadata`が構造的に保証する（Phase 9タスク2 DoD）。
"""

from __future__ import annotations

from typing import Literal

from history_radio.domain.base import SchemaModel
from history_radio.publish.episode_page import EpisodePageData


class DistributionMetadataError(ValueError):
    """配信メタデータ生成の失敗（必須データの欠落等）。"""


class YouTubeMetadata(SchemaModel):
    episode_id: str
    title: str
    description: str
    tags: tuple[str, ...] = ()
    # 仕様書§10D「自動投稿開始前は非公開または限定公開でアップロードする」
    privacy_status: Literal["private", "unlisted"] = "unlisted"


class PodcastMetadata(SchemaModel):
    episode_id: str
    title: str
    description: str
    audio_url: str
    audio_length_bytes: int
    audio_mime_type: Literal["audio/mpeg"] = "audio/mpeg"
    page_url: str
    published_at: str


class AmazonMusicMetadata(SchemaModel):
    """Amazon MusicはPodcast RSSを取得する方式のため、専用アップロード用の
    フィールドは持たない（仕様書§10D「Amazon側がRSSを取得する方式とし、各回を
    Audibleへ直接アップロードしない」）。"""

    episode_id: str
    description: str
    page_url: str


class DistributionMetadataSet(SchemaModel):
    youtube: YouTubeMetadata
    podcast: PodcastMetadata
    amazon_music: AmazonMusicMetadata


def _page_url(episode: EpisodePageData, *, site_base_url: str) -> str:
    return f"{site_base_url.rstrip('/')}/episodes/{episode.episode_id}/"


def build_youtube_metadata(episode: EpisodePageData, *, site_base_url: str) -> YouTubeMetadata:
    page_url = _page_url(episode, site_base_url=site_base_url)
    # 仕様書§10D「説明欄の先頭付近に恒久エピソードページを掲載する」
    description = f"{page_url}\n\n{episode.summary}"
    return YouTubeMetadata(
        episode_id=episode.episode_id, title=episode.title, description=description
    )


def build_podcast_metadata(episode: EpisodePageData, *, site_base_url: str) -> PodcastMetadata:
    if episode.audio_url is None or episode.audio_length_bytes is None:
        raise DistributionMetadataError(
            f"episode_id={episode.episode_id!r}: audio_url/audio_length_bytesが無いため"
            "Podcast配信メタデータを生成できない"
        )
    return PodcastMetadata(
        episode_id=episode.episode_id,
        title=episode.title,
        description=episode.summary,
        audio_url=episode.audio_url,
        audio_length_bytes=episode.audio_length_bytes,
        page_url=_page_url(episode, site_base_url=site_base_url),
        published_at=episode.published_at,
    )


def build_amazon_music_metadata(
    episode: EpisodePageData, *, site_base_url: str
) -> AmazonMusicMetadata:
    page_url = _page_url(episode, site_base_url=site_base_url)
    # 仕様書§10D「RSSの説明欄に恒久エピソードページを掲載し、そのページで関連書籍・
    # Audible作品を案内する」——関連書籍案内自体は恒久ページ側の責務なのでここではリンクのみ。
    description = f"{episode.summary}\n\n関連書籍・出典情報: {page_url}"
    return AmazonMusicMetadata(
        episode_id=episode.episode_id, description=description, page_url=page_url
    )


def build_all_distribution_metadata(
    episode: EpisodePageData, *, site_base_url: str
) -> DistributionMetadataSet:
    """全配信先向けメタデータをまとめて生成する。

    全メタデータが同じ`episode_id`を冪等キーとして持つことをこの関数が保証する
    （development-plan.md Phase 9タスク2 DoD: 「全配信先で同じepisode_idを冪等キーとして使う」）。
    """
    youtube = build_youtube_metadata(episode, site_base_url=site_base_url)
    podcast = build_podcast_metadata(episode, site_base_url=site_base_url)
    amazon_music = build_amazon_music_metadata(episode, site_base_url=site_base_url)

    ids = {youtube.episode_id, podcast.episode_id, amazon_music.episode_id}
    if ids != {episode.episode_id}:
        raise DistributionMetadataError(f"配信先メタデータのepisode_idが一致しない（バグ）: {ids}")

    return DistributionMetadataSet(youtube=youtube, podcast=podcast, amazon_music=amazon_music)
