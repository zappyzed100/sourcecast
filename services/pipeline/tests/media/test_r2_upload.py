"""test_r2_upload.py — Phase 8タスク4 DoD: 同じ入力の再実行が重複オブジェクトを作らない"""

import hashlib

import pytest

from history_radio.media.r2_upload import (
    R2Client,
    R2UploadError,
    content_hash,
    object_key,
)
from tests.ingest.mock_http import Disconnect, RecordedRequest, Reply, ScriptItem, scripted_client


def _r2_client(script: list[ScriptItem]) -> tuple[R2Client, list[RecordedRequest]]:
    client, requests = scripted_client(script)
    return (
        R2Client(
            client=client,
            account_id="0123456789abcdef0123456789abcdef",
            bucket="history-radio-media",
            api_token="test-token",
        ),
        requests,
    )


def test_content_hash_matches_sha256() -> None:
    assert content_hash(b"abc") == hashlib.sha256(b"abc").hexdigest()


def test_object_key_depends_only_on_content_and_extension() -> None:
    data = b"hello world"
    assert object_key(data, "photo.jpg") == object_key(data, "different-name.jpg")


def test_object_key_changes_with_content() -> None:
    assert object_key(b"content A", "a.jpg") != object_key(b"content B", "a.jpg")


def test_object_key_changes_with_extension() -> None:
    data = b"same bytes"
    assert object_key(data, "a.jpg") != object_key(data, "a.png")


def test_upload_of_new_content_puts_object() -> None:
    """存在しないキーへはGETで確認後にPUTする。"""
    client, requests = _r2_client([Reply(status=404), Reply(status=200)])
    result = client.upload(b"new content", "clip.mp3", content_type="audio/mpeg")
    assert result.uploaded is True
    assert result.content_hash == content_hash(b"new content")
    assert len(requests) == 2  # GET(存在確認) + PUT


def test_reupload_of_identical_content_is_idempotent_and_skips_put() -> None:
    """Phase 8タスク4 DoD: 同じ入力の再実行が重複オブジェクトを作らない(PUTを省略する)。"""
    data = b"same bytes twice"
    client, requests = _r2_client([Reply(status=200, headers={"content-length": str(len(data))})])
    result = client.upload(data, "clip.mp3", content_type="audio/mpeg")
    assert result.uploaded is False
    assert len(requests) == 1  # GETのみ、PUTは呼ばれない


def test_size_mismatch_on_existing_key_is_rejected() -> None:
    """ハッシュ由来キーの前提(同一キー=同一内容)が崩れた場合はfail closedで拒否する。"""
    client, _requests = _r2_client([Reply(status=200, headers={"content-length": "999"})])
    with pytest.raises(R2UploadError, match="サイズが不一致"):
        client.upload(b"actual content", "clip.mp3", content_type="audio/mpeg")


def test_unexpected_existence_check_status_is_rejected() -> None:
    client, _requests = _r2_client([Reply(status=500)])
    with pytest.raises(R2UploadError, match="異常応答"):
        client.upload(b"content", "clip.mp3", content_type="audio/mpeg")


def test_put_failure_is_rejected() -> None:
    client, _requests = _r2_client([Reply(status=404), Reply(status=403, text="forbidden")])
    with pytest.raises(R2UploadError, match="異常応答"):
        client.upload(b"content", "clip.mp3", content_type="audio/mpeg")


def test_network_error_during_existence_check_is_rejected() -> None:
    client, _requests = _r2_client([Disconnect()])
    with pytest.raises(R2UploadError, match="接続に失敗"):
        client.upload(b"content", "clip.mp3", content_type="audio/mpeg")


def test_find_existing_returns_none_for_missing_object() -> None:
    client, _requests = _r2_client([Reply(status=404)])
    assert client.find_existing("media/does-not-exist.jpg") is None


def test_authorization_header_uses_bearer_token() -> None:
    client, requests = _r2_client([Reply(status=404)])
    client.find_existing("media/x.jpg")
    assert requests[0].headers.get("authorization") == "Bearer test-token"
