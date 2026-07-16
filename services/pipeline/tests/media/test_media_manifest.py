"""test_media_manifest.py — Phase 7 DoD: クレジット欠落素材のレンダリング前拒否を固定する"""

import pytest

from history_radio.media.media_manifest import (
    MediaAsset,
    MediaAssetError,
    credits_for_section,
    validate_media_manifest,
)


def _licensed(**overrides: object) -> MediaAsset:
    base: dict[str, object] = {
        "asset_id": "img-001",
        "origin": "licensed",
        "credit_text": "写真: 国立国会図書館デジタルコレクション",
        "source_url": "https://dl.ndl.go.jp/pid/1234567",
        "normalized_license_id": "ndl-internet-pd",
        "used_in": ["hook"],
    }
    base.update(overrides)
    return MediaAsset.model_validate(base)


def _self_drawn(**overrides: object) -> MediaAsset:
    base: dict[str, object] = {
        "asset_id": "chart-001",
        "origin": "self_drawn",
        "credit_text": "年表: 自作",
        "used_in": ["setting"],
    }
    base.update(overrides)
    return MediaAsset.model_validate(base)


def test_valid_licensed_and_self_drawn_assets_pass() -> None:
    validate_media_manifest([_licensed(), _self_drawn()])  # 例外なし


def test_missing_credit_is_rejected() -> None:
    """Phase 7 DoD: クレジット欠落素材をレンダリング前に拒否する。"""
    with pytest.raises(MediaAssetError, match="クレジットが空") as exc_info:
        validate_media_manifest([_licensed(credit_text="")])
    assert len(exc_info.value.problems) == 1


def test_whitespace_only_credit_is_rejected() -> None:
    with pytest.raises(MediaAssetError, match="クレジットが空"):
        validate_media_manifest([_self_drawn(credit_text="   ")])


def test_licensed_asset_without_source_url_is_rejected() -> None:
    with pytest.raises(MediaAssetError, match="出典URLが無い"):
        validate_media_manifest([_licensed(source_url=None)])


def test_licensed_asset_without_license_id_is_rejected() -> None:
    with pytest.raises(MediaAssetError, match="正規化ライセンスIDが無い"):
        validate_media_manifest([_licensed(normalized_license_id=None)])


def test_self_drawn_asset_does_not_require_source_url() -> None:
    """自作図形は著作権が発生しないだけで、クレジット自体は必須のまま。"""
    validate_media_manifest([_self_drawn()])  # 例外なし


def test_duplicate_asset_id_is_rejected() -> None:
    with pytest.raises(MediaAssetError, match="重複"):
        validate_media_manifest([_licensed(asset_id="dup"), _self_drawn(asset_id="dup")])


def test_all_problems_are_reported_at_once() -> None:
    with pytest.raises(MediaAssetError) as exc_info:
        validate_media_manifest(
            [_licensed(credit_text="", source_url=None), _self_drawn(credit_text="")]
        )
    assert len(exc_info.value.problems) == 3


def test_credits_for_section_filters_by_usage() -> None:
    assets = [
        _licensed(asset_id="a", used_in=["hook", "development"]),
        _self_drawn(asset_id="b", used_in=["development"]),
        _self_drawn(asset_id="c", credit_text="別図: 自作", used_in=["sources"]),
    ]
    assert credits_for_section(assets, "development") == [
        "写真: 国立国会図書館デジタルコレクション",
        "年表: 自作",
    ]
    assert credits_for_section(assets, "sources") == ["別図: 自作"]
    assert credits_for_section(assets, "twist") == []
