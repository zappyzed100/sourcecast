"""test_slide_render.py — Phase 7 DoD: 画像0件でも権利上安全な動画を生成できることを固定する

実際のPillow描画・ffmpegエンコードに対する統合テスト（外部ネットワークは使わない）。
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from PIL import Image

from history_radio.media.slide_render import (
    SLIDE_HEIGHT,
    SLIDE_WIDTH,
    SlideRenderError,
    _resolve_font_path,  # pyright: ignore[reportPrivateUsage]
    encode_slide_video,
    render_slide_image,
)
from history_radio.media.slides import SlideSpec


def _spec(**overrides: object) -> SlideSpec:
    base: dict[str, object] = {
        "slide_id": "ep-1-hook",
        "section_kind": "hook",
        "title": "導入",
        "body_lines": ("今日は鉄道開業の話なのだ。",),
        "duration_seconds": 10.0,
        "asset_ids": (),
        "uses_self_drawn_fallback": True,
        "source_numbers": (),
    }
    base.update(overrides)
    return SlideSpec.model_validate(base)


def _make_silent_audio(path: Path, *, duration: float = 5.0) -> None:
    subprocess.run(
        [
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
        ],
        capture_output=True,
        timeout=30,
        check=True,
    )


def test_self_drawn_fallback_renders_a_valid_image(tmp_path: Path) -> None:
    """Phase 7 DoD: 画像0件でも安全なスライド画像を生成できる。"""
    output = tmp_path / "slide.png"
    render_slide_image(_spec(), output)
    assert output.is_file()
    with Image.open(output) as img:
        assert img.size == (SLIDE_WIDTH, SLIDE_HEIGHT)


def test_rendered_image_contains_title_and_body_text_layout(tmp_path: Path) -> None:
    """自作図形が単なる単色でなく、文字が描画されている（背景と異なる画素が存在する）。"""
    output = tmp_path / "slide.png"
    render_slide_image(_spec(), output)
    with Image.open(output) as img:
        colors = img.getcolors(maxcolors=SLIDE_WIDTH * SLIDE_HEIGHT)
    assert colors is not None
    assert len(colors) > 1  # 背景色だけでなくテキストの色も存在する


def test_no_font_candidates_found_raises_instead_of_producing_tofu() -> None:
    """fail closed: 日本語フォントが1つも見つからない環境では文字化けを黙って許容しない。"""
    with pytest.raises(SlideRenderError, match="フォントが見つからない"):
        _resolve_font_path(("/nonexistent/path/a.ttf", "/nonexistent/path/b.ttf"))


def test_invalid_explicit_font_path_raises(tmp_path: Path) -> None:
    output = tmp_path / "slide.png"
    with pytest.raises(SlideRenderError, match="フォントを読み込めない"):
        render_slide_image(_spec(), output, font_path="/nonexistent/font.ttf")


def test_licensed_background_image_is_used_when_available(tmp_path: Path) -> None:
    bg_path = tmp_path / "bg.jpg"
    Image.new("RGB", (800, 600), (200, 100, 50)).save(bg_path)
    output = tmp_path / "slide.png"
    render_slide_image(
        _spec(uses_self_drawn_fallback=False, asset_ids=("img-1",)),
        output,
        background_image=bg_path,
    )
    with Image.open(output) as img:
        assert img.size == (SLIDE_WIDTH, SLIDE_HEIGHT)


def test_missing_background_image_raises(tmp_path: Path) -> None:
    output = tmp_path / "slide.png"
    with pytest.raises(SlideRenderError, match="背景画像"):
        render_slide_image(
            _spec(uses_self_drawn_fallback=False),
            output,
            background_image=tmp_path / "does-not-exist.jpg",
        )


def test_encode_slide_video_produces_playable_mp4(tmp_path: Path) -> None:
    """Phase 7 DoD: 画像0件（=全て自作図形）でも権利上安全な動画を実際に生成できる。"""
    slide1 = tmp_path / "slide1.png"
    slide2 = tmp_path / "slide2.png"
    render_slide_image(_spec(title="導入"), slide1)
    render_slide_image(_spec(title="時代と場所"), slide2)
    audio = tmp_path / "audio.wav"
    _make_silent_audio(audio, duration=4.0)

    output = tmp_path / "episode.mp4"
    encode_slide_video([(slide1, 2.0), (slide2, 2.0)], audio, output)

    assert output.is_file()
    proc = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(output),
        ],
        capture_output=True,
        timeout=30,
        check=True,
    )
    duration = float(proc.stdout.decode("utf-8").strip())
    assert duration >= 3.5  # 音声4秒とスライド4秒の短い方（-shortest）


def test_encode_with_no_slides_raises() -> None:
    with pytest.raises(SlideRenderError, match="1件も無い"):
        encode_slide_video([], Path("dummy.wav"), Path("out.mp4"))


def test_encode_with_missing_image_raises(tmp_path: Path) -> None:
    audio = tmp_path / "audio.wav"
    _make_silent_audio(audio, duration=2.0)
    with pytest.raises(SlideRenderError, match="存在しない"):
        encode_slide_video([(tmp_path / "missing.png", 5.0)], audio, tmp_path / "out.mp4")


def test_encode_with_missing_audio_raises(tmp_path: Path) -> None:
    slide = tmp_path / "slide.png"
    render_slide_image(_spec(), slide)
    with pytest.raises(SlideRenderError, match="音声ファイルが存在しない"):
        encode_slide_video([(slide, 5.0)], tmp_path / "missing.wav", tmp_path / "out.mp4")
