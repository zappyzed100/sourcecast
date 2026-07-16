"""test_episode_publisher.py — Phase 8タスク2 DoD: 再生成が旧版を上書きせず、新版を追加する"""

from pathlib import Path
from typing import Any

import pytest

from history_radio.publish.episode_page import EpisodePageData, EpisodePageError
from history_radio.publish.episode_publisher import (
    EpisodePublishConflictError,
    publish_episode,
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


def _data(**overrides: object) -> EpisodePageData:
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


def test_first_publish_creates_current_and_version_files(tmp_path: Path) -> None:
    result = publish_episode(tmp_path, _data(), "本文なのだ。")
    assert result.is_new_revision
    assert result.current_path == tmp_path / "2026-07-16-can-opener.md"
    assert result.version_path == tmp_path / "2026-07-16-can-opener" / "versions" / "1.md"
    assert result.current_path.is_file()
    assert result.version_path.is_file()
    assert result.current_path.read_text(encoding="utf-8") == result.version_path.read_text(
        encoding="utf-8"
    )


def test_republishing_same_revision_with_identical_content_is_idempotent(
    tmp_path: Path,
) -> None:
    publish_episode(tmp_path, _data(), "本文なのだ。")
    result = publish_episode(tmp_path, _data(), "本文なのだ。")
    assert result.is_new_revision is False


def test_republishing_same_revision_with_different_content_is_rejected(
    tmp_path: Path,
) -> None:
    publish_episode(tmp_path, _data(), "本文なのだ。")
    with pytest.raises(EpisodePublishConflictError, match="既に異なる内容で公開済み"):
        publish_episode(tmp_path, _data(), "書き換えた本文なのだ。")


def test_new_higher_revision_does_not_overwrite_old_version_file(tmp_path: Path) -> None:
    """Phase 8タスク2 DoD: 再生成が旧版を上書きせず、新版と訂正履歴を追加する。"""
    publish_episode(tmp_path, _data(revision=1), "第1版の本文なのだ。")
    result = publish_episode(
        tmp_path,
        _data(
            revision=2,
            corrections=[{"date": "2026-07-17", "description": "誤字を訂正したのだ。"}],
        ),
        "第2版の本文なのだ。",
    )
    assert result.is_new_revision

    old_version_path = tmp_path / "2026-07-16-can-opener" / "versions" / "1.md"
    assert old_version_path.is_file()
    assert "第1版の本文なのだ。" in old_version_path.read_text(encoding="utf-8")

    new_version_path = tmp_path / "2026-07-16-can-opener" / "versions" / "2.md"
    assert new_version_path.is_file()
    assert "第2版の本文なのだ。" in new_version_path.read_text(encoding="utf-8")

    current_text = result.current_path.read_text(encoding="utf-8")
    assert "第2版の本文なのだ。" in current_text
    assert "誤字を訂正したのだ。" in current_text


def test_publishing_lower_revision_after_current_exists_is_rejected(tmp_path: Path) -> None:
    publish_episode(tmp_path, _data(revision=2), "第2版の本文なのだ。")
    with pytest.raises(EpisodePublishConflictError, match="より大きくなければならない"):
        publish_episode(tmp_path, _data(revision=1), "第1版の本文なのだ。")


def test_publishing_same_revision_number_after_current_exists_is_rejected(
    tmp_path: Path,
) -> None:
    publish_episode(tmp_path, _data(revision=1), "本文なのだ。")
    (tmp_path / "2026-07-16-can-opener" / "versions" / "1.md").unlink()
    with pytest.raises(EpisodePublishConflictError, match="より大きくなければならない"):
        publish_episode(tmp_path, _data(revision=1), "別の本文なのだ。")


def test_invalid_episode_data_is_rejected_before_writing_anything(tmp_path: Path) -> None:
    data = _data(sources=[_source(normalized_license_id="unknown")])
    with pytest.raises(EpisodePageError, match="未知/不採用ライセンス"):
        publish_episode(tmp_path, data, "本文なのだ。")
    assert list(tmp_path.iterdir()) == []
