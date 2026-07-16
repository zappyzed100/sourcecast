"""media_manifest.py — スライド動画で使う画像の権利・クレジット・使用箇所の記録
（仕様書§10・development-plan.md Phase 7）。

「各画像に内部素材IDを持たせ、概要欄のクレジットへ対応させる」契約を型で表す。
**クレジット欠落素材はレンダリング前に拒否する**（fail closed）——素材不足時の
自作図形（`origin="self_drawn"`）も、著作権が発生しないだけで作成者表記まで
省略してよいわけではないため、クレジット必須の対象から外さない。
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from history_radio.domain.base import SchemaModel

# licensed: 権利判定を経た外部素材（写真・地図タイル等）。self_drawn: 著作権が
# 発生しない自作図形・年表・比較図（§10「素材不足時は…自作図形・地図・年表を使用」）
AssetOrigin = Literal["licensed", "self_drawn"]


class MediaAssetError(ValueError):
    """media_manifestの検証失敗（クレジット欠落・出典欠落等）。全件列挙して報告する。"""

    def __init__(self, problems: list[str]) -> None:
        super().__init__("media_manifest検査失敗:\n- " + "\n- ".join(problems))
        self.problems = problems


class MediaAsset(SchemaModel):
    """1素材の権利・クレジット・使用箇所。"""

    asset_id: str = Field(min_length=1)
    origin: AssetOrigin
    credit_text: str
    # licensedのみ必須（出典URL・正規化ライセンスID）。self_drawnはNoneのままでよい
    source_url: str | None = None
    normalized_license_id: str | None = None
    # 使用箇所（スライドの節ID等）。1箇所も使われない資産は載せない——
    # 「使用箇所」の記録という本モジュールの目的自体が成立しない
    used_in: list[str] = Field(min_length=1)


def validate_media_manifest(assets: list[MediaAsset]) -> None:
    """レンダリング前検査。問題があれば全件列挙して例外を投げる（fail closed）。"""
    problems: list[str] = []
    seen_ids: set[str] = set()
    for asset in assets:
        where = f"[{asset.asset_id}]"
        if asset.asset_id in seen_ids:
            problems.append(f"{where}: asset_idが重複している")
        seen_ids.add(asset.asset_id)

        if not asset.credit_text.strip():
            problems.append(f"{where}: クレジットが空——レンダリング前に拒否")
        if asset.origin == "licensed":
            if asset.source_url is None:
                problems.append(f"{where}: licensed素材に出典URLが無い")
            if asset.normalized_license_id is None:
                problems.append(f"{where}: licensed素材に正規化ライセンスIDが無い")

    if problems:
        raise MediaAssetError(problems)


def credits_for_section(assets: list[MediaAsset], section_id: str) -> list[str]:
    """概要欄クレジット表示用: 指定節で使われた素材のクレジット文字列を返す。"""
    return [a.credit_text for a in assets if section_id in a.used_in]
