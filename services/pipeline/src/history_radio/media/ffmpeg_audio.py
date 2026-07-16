"""ffmpeg_audio.py — FFmpegによる音声品質検査（仕様書§10・development-plan.md Phase 7）。

音量正規化の判定材料（volumedetectフィルタの実測値）、無音・破損・長さ・codecを検査する。
`validate_audio`は見つかった問題を**全件列挙**して1回で報告する（script/validator.pyと
同じ設計方針——修正の往復を減らす）。

FFmpeg/FFprobeの子プロセスには必ずタイムアウトを付ける（development-plan.md §1.3
「FFmpeg、VOICEVOXのプロセスには必ずタイムアウト、終了コード検査…を実装する」）。
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_TIMEOUT_SECONDS = 60
DEFAULT_MIN_DURATION_SECONDS = 1.0
DEFAULT_SILENCE_MAX_VOLUME_DB = -50.0
DEFAULT_MIN_MEAN_VOLUME_DB = -45.0
DEFAULT_MAX_MEAN_VOLUME_DB = -15.0
DEFAULT_ALLOWED_CODECS = frozenset({"pcm_s16le", "mp3", "aac"})

_VOLUME_PATTERN = re.compile(r"(mean|max)_volume:\s*(-?[\d.]+|-inf)\s*dB")


class AudioProcessError(RuntimeError):
    """ffmpeg/ffprobeの起動・タイムアウト・想定外の失敗（子プロセスの制御自体の失敗）。"""


class AudioValidationError(ValueError):
    """音声品質検査の失敗（理由を全件列挙する）。"""

    def __init__(self, problems: list[str]) -> None:
        super().__init__("音声品質検査失敗:\n- " + "\n- ".join(problems))
        self.problems = problems


@dataclass(frozen=True, slots=True)
class AudioProbe:
    duration_seconds: float
    codec: str
    sample_rate: int


def _run(args: list[str], *, timeout_seconds: float) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(args, capture_output=True, timeout=timeout_seconds, check=False)
    except subprocess.TimeoutExpired as exc:
        raise AudioProcessError(f"{args[0]}がタイムアウトした（{timeout_seconds}秒）") from exc
    except OSError as exc:
        raise AudioProcessError(f"{args[0]}を起動できない: {exc}") from exc


def probe_audio(path: Path, *, timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS) -> AudioProbe:
    """ffprobeでcodec・サンプルレート・長さを取得する。破損ファイルは例外を投げる。"""
    proc = _run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration:stream=codec_name,sample_rate",
            "-of",
            "json",
            str(path),
        ],
        timeout_seconds=timeout_seconds,
    )
    if proc.returncode != 0:
        raise AudioValidationError([f"破損または読み込み不能な音声ファイル: {path.name}"])
    try:
        data: Any = json.loads(proc.stdout.decode("utf-8", "replace"))
        stream = data["streams"][0]
        return AudioProbe(
            duration_seconds=float(data["format"]["duration"]),
            codec=stream["codec_name"],
            sample_rate=int(stream["sample_rate"]),
        )
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise AudioValidationError([f"ffprobe出力が想定の形でない: {path.name}: {exc!r}"]) from exc


def measure_volume(
    path: Path, *, timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
) -> tuple[float, float]:
    """volumedetectフィルタで(mean_volume, max_volume)をdBで返す（無音判定・音量正規化の材料）。"""
    proc = _run(
        ["ffmpeg", "-i", str(path), "-af", "volumedetect", "-f", "null", "-"],
        timeout_seconds=timeout_seconds,
    )
    stderr = proc.stderr.decode("utf-8", "replace")
    values: dict[str, float] = {}
    for match in _VOLUME_PATTERN.finditer(stderr):
        key, raw = match.group(1), match.group(2)
        values[key] = float("-inf") if raw == "-inf" else float(raw)
    if "mean" not in values or "max" not in values:
        raise AudioValidationError([f"音量情報を取得できない: {path.name}"])
    return values["mean"], values["max"]


def validate_audio(
    path: Path,
    *,
    min_duration_seconds: float = DEFAULT_MIN_DURATION_SECONDS,
    silence_max_volume_db: float = DEFAULT_SILENCE_MAX_VOLUME_DB,
    min_mean_volume_db: float = DEFAULT_MIN_MEAN_VOLUME_DB,
    max_mean_volume_db: float = DEFAULT_MAX_MEAN_VOLUME_DB,
    allowed_codecs: frozenset[str] = DEFAULT_ALLOWED_CODECS,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> AudioProbe:
    """音声を検査し、問題があれば全件列挙して例外を投げる。問題なしならAudioProbeを返す。"""
    if not path.is_file():
        raise AudioValidationError([f"ファイルが存在しない: {path}"])

    probe = probe_audio(path, timeout_seconds=timeout_seconds)
    mean_volume, max_volume = measure_volume(path, timeout_seconds=timeout_seconds)

    problems: list[str] = []
    if probe.duration_seconds < min_duration_seconds:
        problems.append(
            f"長さが基準未満: {probe.duration_seconds:.2f}秒 < {min_duration_seconds}秒"
        )
    if probe.codec not in allowed_codecs:
        problems.append(f"許可されていないcodec: {probe.codec}（許可: {sorted(allowed_codecs)}）")
    if max_volume <= silence_max_volume_db:
        problems.append(f"無音と判定: max_volume={max_volume}dB <= {silence_max_volume_db}dB")
    if not (min_mean_volume_db <= mean_volume <= max_mean_volume_db):
        problems.append(
            f"基準外音量: mean_volume={mean_volume}dB"
            f"（許容範囲 [{min_mean_volume_db}, {max_mean_volume_db}]dB外）"
        )

    if problems:
        raise AudioValidationError(problems)
    return probe
