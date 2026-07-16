"""test_voicevox.py — Phase 7 DoD: エンジン停止・タイムアウト・空応答の不完全音声拒否を固定する"""

import json

import pytest

from history_radio.media.voicevox import CREDIT_TEXT, VoicevoxClient, VoicevoxError, inject_readings
from history_radio.readings.resolver import ResolvedReading
from tests.ingest.mock_http import Disconnect, Reply, Timeout, scripted_client

_AUDIO_QUERY_RESPONSE = json.dumps({"accent_phrases": [], "speedScale": 1.0})


def test_check_version_returns_stripped_version_string() -> None:
    client, _requests = scripted_client([Reply(text='"0.14.0"')])
    voicevox = VoicevoxClient(client=client)
    assert voicevox.check_version() == "0.14.0"


def test_check_version_raises_when_engine_is_down() -> None:
    """§9.2 DoD: エンジン停止時は例外を投げる。"""
    client, _requests = scripted_client([Disconnect()])
    voicevox = VoicevoxClient(client=client)
    with pytest.raises(VoicevoxError, match="接続できない"):
        voicevox.check_version()


def test_synthesize_success_returns_audio_bytes() -> None:
    client, requests = scripted_client(
        [Reply(text=_AUDIO_QUERY_RESPONSE), Reply(text="FAKE_WAV_BYTES")]
    )
    voicevox = VoicevoxClient(client=client)
    audio = voicevox.synthesize("こんにちはなのだ")
    assert audio == b"FAKE_WAV_BYTES"
    assert "audio_query" in requests[0].url
    assert "synthesis" in requests[1].url


def test_synthesize_raises_on_timeout_during_synthesis_step() -> None:
    """§9.2 DoD: タイムアウトで不完全な音声を返さない。"""
    client, _requests = scripted_client([Reply(text=_AUDIO_QUERY_RESPONSE), Timeout()])
    voicevox = VoicevoxClient(client=client)
    with pytest.raises(VoicevoxError, match="タイムアウト"):
        voicevox.synthesize("テスト")


def test_synthesize_raises_on_failure_during_audio_query_step() -> None:
    client, _requests = scripted_client([Disconnect()])
    voicevox = VoicevoxClient(client=client)
    with pytest.raises(VoicevoxError, match="audio_query"):
        voicevox.synthesize("テスト")


def test_synthesize_raises_on_non_200_response() -> None:
    client, _requests = scripted_client(
        [Reply(text=_AUDIO_QUERY_RESPONSE), Reply(status=500, text="internal error")]
    )
    voicevox = VoicevoxClient(client=client)
    with pytest.raises(VoicevoxError, match="異常応答"):
        voicevox.synthesize("テスト")


def test_synthesize_raises_on_empty_response_body() -> None:
    """§9.2 DoD: 空応答（不完全）を音声として返さない——途中失敗の再現。"""
    client, _requests = scripted_client([Reply(text=_AUDIO_QUERY_RESPONSE), Reply(text="")])
    voicevox = VoicevoxClient(client=client)
    with pytest.raises(VoicevoxError, match="空"):
        voicevox.synthesize("テスト")


def test_synthesize_raises_on_malformed_audio_query_response() -> None:
    client, _requests = scripted_client([Reply(text="[1, 2, 3]")])  # dictでない
    voicevox = VoicevoxClient(client=client)
    with pytest.raises(VoicevoxError, match="想定の形でない"):
        voicevox.synthesize("テスト")


def test_inject_readings_replaces_surface_with_reading() -> None:
    resolutions = [
        ResolvedReading(
            surface="西郷隆盛",
            reading="サイゴウタカモリ",
            layer="manual",
            source_id="manual-dictionary",
        )
    ]
    result = inject_readings("西郷隆盛は薩摩藩士だったのだ", resolutions)
    assert result == "サイゴウタカモリは薩摩藩士だったのだ"


def test_inject_readings_processes_longer_surfaces_first() -> None:
    """「東京タワー」を「東京」より先に置換し、部分一致による誤置換を防ぐ。"""
    resolutions = [
        ResolvedReading(
            surface="東京", reading="トウキョウ", layer="sudachi", source_id="sudachidict"
        ),
        ResolvedReading(
            surface="東京タワー",
            reading="トウキョウタワー",
            layer="sudachi",
            source_id="sudachidict",
        ),
    ]
    result = inject_readings("東京タワーから東京を見渡すのだ", resolutions)
    assert result == "トウキョウタワーからトウキョウを見渡すのだ"


def test_inject_readings_with_no_resolutions_returns_text_unchanged() -> None:
    assert inject_readings("そのままなのだ", []) == "そのままなのだ"


def test_credit_text_matches_spec_wording() -> None:
    """仕様書§9.2: 「VOICEVOX:ずんだもん」のクレジット文字列。"""
    assert CREDIT_TEXT == "VOICEVOX:ずんだもん"
