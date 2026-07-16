"""slide_render.py — スライド画像の描画と動画エンコード（仕様書§10・Phase 7）。

`slides.SlideSpec`（決定済みの構成）を実際の1920×1080 PNGへ描画し、FFmpegで
静止画列＋音声を結合してMP4を書き出す。決定（slides.py）と実行（本module）を
分離しているため、描画・エンコードの失敗は構成ロジックに影響しない。

自作図形フォールバック（`uses_self_drawn_fallback=True`）は、著作権が発生しない
単色背景＋タイトル・本文のテキストカードとして描画する（§10「著作権の発生しない
自作図形…を使用する」の最小実装。地図・年表・比較図の高度な自動生成は将来の
拡張として残す——このタスクは「画像0件でも安全に動画化できる」ことの充足を優先する）。

日本語フォントが1つも見つからない環境では、文字化け（tofu表示）を黙って許容せず
`SlideRenderError`で止める（fail closed）。
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from history_radio.media.slides import SlideSpec

SLIDE_WIDTH = 1920
SLIDE_HEIGHT = 1080
VIDEO_FPS = 30

_TITLE_FONT_SIZE = 72
_BODY_FONT_SIZE = 48
_SELF_DRAWN_BACKGROUND = (30, 40, 60)
_LICENSED_BACKGROUND = (10, 10, 10)
_TEXT_COLOR = (255, 255, 255)

# 環境非依存にするため候補パスを複数持つ（Windows既定導入のNoto Sans JP・
# Linuxでのfonts-noto-cjk導入パス）。最初に見つかった1件を使う
_FONT_CANDIDATES = (
    r"C:\Windows\Fonts\NotoSansJP-Bold.ttf",
    r"C:\Windows\Fonts\meiryo.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJKjp-Bold.otf",
)


class SlideRenderError(RuntimeError):
    """スライド描画・動画エンコードの失敗（フォント未検出・FFmpeg失敗等）。"""


def _resolve_font_path(candidates: tuple[str, ...] = _FONT_CANDIDATES) -> str:
    for path in candidates:
        if Path(path).is_file():
            return path
    raise SlideRenderError(
        "日本語フォントが見つからない（候補: "
        f"{list(candidates)}）——文字化けした動画を生成しない（fail closed）"
    )


def render_slide_image(
    spec: SlideSpec,
    output_path: Path,
    *,
    background_image: Path | None = None,
    font_path: str | None = None,
) -> None:
    """1スライドをPNGへ描画する。`background_image`は`uses_self_drawn_fallback=False`
    の場合のみ使う（フォールバック時は単色背景のテキストカード）。"""
    resolved_font_path = font_path if font_path is not None else _resolve_font_path()

    if spec.uses_self_drawn_fallback or background_image is None:
        image = Image.new("RGB", (SLIDE_WIDTH, SLIDE_HEIGHT), _SELF_DRAWN_BACKGROUND)
    else:
        try:
            source = Image.open(background_image).convert("RGB")
        except OSError as exc:
            raise SlideRenderError(f"背景画像を開けない: {background_image}: {exc}") from exc
        image = Image.new("RGB", (SLIDE_WIDTH, SLIDE_HEIGHT), _LICENSED_BACKGROUND)
        fitted = source.copy()
        fitted.thumbnail((SLIDE_WIDTH, SLIDE_HEIGHT))
        offset = ((SLIDE_WIDTH - fitted.width) // 2, (SLIDE_HEIGHT - fitted.height) // 2)
        image.paste(fitted, offset)

    draw = ImageDraw.Draw(image)
    try:
        title_font = ImageFont.truetype(resolved_font_path, _TITLE_FONT_SIZE)
        body_font = ImageFont.truetype(resolved_font_path, _BODY_FONT_SIZE)
    except OSError as exc:
        raise SlideRenderError(f"フォントを読み込めない: {resolved_font_path!r}: {exc}") from exc

    draw.text((60, 50), spec.title, font=title_font, fill=_TEXT_COLOR)
    line_y = 180
    for line in spec.body_lines:
        draw.text((60, line_y), line, font=body_font, fill=_TEXT_COLOR)
        line_y += _BODY_FONT_SIZE + 20

    if spec.source_numbers:
        credit = "出典: " + "・".join(f"[{n}]" for n in spec.source_numbers)
        draw.text((60, SLIDE_HEIGHT - 80), credit, font=body_font, fill=_TEXT_COLOR)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path, format="PNG")


def _run_ffmpeg(args: list[str], *, timeout_seconds: float) -> None:
    try:
        proc = subprocess.run(args, capture_output=True, timeout=timeout_seconds, check=False)
    except subprocess.TimeoutExpired as exc:
        raise SlideRenderError(f"ffmpegがタイムアウトした（{timeout_seconds}秒）") from exc
    except OSError as exc:
        raise SlideRenderError(f"ffmpegを起動できない: {exc}") from exc
    if proc.returncode != 0:
        raise SlideRenderError(
            f"ffmpeg動画エンコード失敗: {proc.stderr.decode('utf-8', 'replace')[:500]}"
        )


def encode_slide_video(
    slide_images: list[tuple[Path, float]],
    audio_path: Path,
    output_path: Path,
    *,
    timeout_seconds: float = 300.0,
) -> None:
    """(画像パス, 表示秒数)の列と音声を結合してMP4を書き出す。

    1件も無い・画像が実在しない場合は例外を投げ、不完全な動画を書き出さない。
    """
    if not slide_images:
        raise SlideRenderError("スライド画像が1件も無い——空の動画を書き出さない")
    for path, _duration in slide_images:
        if not path.is_file():
            raise SlideRenderError(f"スライド画像が存在しない: {path}")
    if not audio_path.is_file():
        raise SlideRenderError(f"音声ファイルが存在しない: {audio_path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    concat_list_path = output_path.with_suffix(".concat.txt")
    lines: list[str] = []
    for path, duration in slide_images:
        lines.append(f"file '{path.resolve().as_posix()}'")
        lines.append(f"duration {duration}")
    # concatデムクサーは最終エントリの duration を無視するため、最後の画像をもう一度書く
    lines.append(f"file '{slide_images[-1][0].resolve().as_posix()}'")
    concat_list_path.write_text("\n".join(lines), encoding="utf-8")

    try:
        _run_ffmpeg(
            [
                "ffmpeg",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat_list_path),
                "-i",
                str(audio_path),
                "-vf",
                f"fps={VIDEO_FPS},scale={SLIDE_WIDTH}:{SLIDE_HEIGHT}",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-shortest",
                str(output_path),
            ],
            timeout_seconds=timeout_seconds,
        )
    finally:
        concat_list_path.unlink(missing_ok=True)
