"""test_ffmpeg_audio.py — Phase 7 DoD: 基準外音量・破損音声・無音・長さ不足の拒否を固定する

実際のffmpeg/ffprobe（ローカル導入済み）に対して行う統合テスト——フィクスチャ音声は
各テストがffmpegで都度生成する（外部ネットワークは使わない。test-networkの対象外）。
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from history_radio.media.ffmpeg_audio import (
    AudioValidationError,
    validate_audio,
)


def _make_wav(path: Path, *, duration: float, volume_db: float | None) -> None:
    if volume_db is None:
        args = [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=44100:cl=mono",
            "-t",
            str(duration),
            "-c:a",
            "pcm_s16le",
            str(path),
        ]
    else:
        args = [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=440:duration={duration}",
            "-af",
            f"volume={volume_db}dB",
            "-c:a",
            "pcm_s16le",
            str(path),
        ]
    subprocess.run(args, capture_output=True, timeout=30, check=True)


@pytest.fixture
def normal_wav(tmp_path: Path) -> Path:
    path = tmp_path / "normal.wav"
    _make_wav(path, duration=2.0, volume_db=-18.0)
    return path


def test_normal_audio_passes_validation(normal_wav: Path) -> None:
    probe = validate_audio(normal_wav)
    assert probe.codec == "pcm_s16le"
    assert probe.duration_seconds >= 1.9


def test_silent_audio_is_rejected(tmp_path: Path) -> None:
    """Phase 7 DoD: 無音を公開ゲートが拒否する。"""
    path = tmp_path / "silent.wav"
    _make_wav(path, duration=2.0, volume_db=None)
    with pytest.raises(AudioValidationError, match="無音") as exc_info:
        validate_audio(path)
    assert any("基準外音量" in p for p in exc_info.value.problems)  # 無音は音量超過も伴う


def test_out_of_range_volume_is_rejected(tmp_path: Path) -> None:
    """Phase 7 DoD: 基準外音量を公開ゲートが拒否する（大きすぎる音量）。

    lavfiのsine音源は素の状態でmean_volume約-21dBのため、既定範囲[-45,-15]dBの
    上限を超えさせるには増幅が要る（+10dBで実測mean約-11dB — 範囲外）。
    """
    path = tmp_path / "loud.wav"
    _make_wav(path, duration=2.0, volume_db=10.0)
    with pytest.raises(AudioValidationError, match="基準外音量"):
        validate_audio(path)


def test_too_short_audio_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "short.wav"
    _make_wav(path, duration=0.2, volume_db=-18.0)
    with pytest.raises(AudioValidationError, match="長さが基準未満"):
        validate_audio(path, min_duration_seconds=1.0)


def test_corrupt_file_is_rejected(tmp_path: Path) -> None:
    """Phase 7 DoD: 破損音声を公開ゲートが拒否する。"""
    path = tmp_path / "corrupt.wav"
    path.write_bytes(b"this is not a valid wav file at all" * 10)
    with pytest.raises(AudioValidationError, match="破損"):
        validate_audio(path)


def test_missing_file_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(AudioValidationError, match="存在しない"):
        validate_audio(tmp_path / "does-not-exist.wav")


def test_disallowed_codec_is_rejected(tmp_path: Path, normal_wav: Path) -> None:
    with pytest.raises(AudioValidationError, match="許可されていないcodec"):
        validate_audio(normal_wav, allowed_codecs=frozenset({"mp3"}))


def test_all_problems_are_reported_at_once(tmp_path: Path) -> None:
    """検査失敗は全件列挙——修正の往復を減らす（script/validator.pyと同じ設計）。"""
    path = tmp_path / "short_and_silent.wav"
    _make_wav(path, duration=0.3, volume_db=None)
    with pytest.raises(AudioValidationError) as exc_info:
        validate_audio(path, min_duration_seconds=1.0)
    assert len(exc_info.value.problems) >= 2  # 長さ不足 + 無音（+基準外音量）
