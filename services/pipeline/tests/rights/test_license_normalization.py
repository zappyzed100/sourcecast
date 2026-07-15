"""test_license_normalization.py — Phase 3 DoD: 権利表示文字列の正規化を固定する（仕様書§5.2）"""

import pytest

from history_radio.rights.license_normalization import (
    normalize_custom_terms,
    normalize_license_id,
)


@pytest.mark.parametrize(
    ("raw_license_text", "expected_id"),
    [
        ("CC0", "cc0"),
        ("Public Domain Dedication", "cc0"),
        ("CC BY", "cc-by"),
        ("CC-BY 4.0", "cc-by"),
        ("CC BY-SA", "cc-by-sa"),
        ("政府標準利用規約（第2.0版）", "gov-jp-2.0"),
        ("Government of Japan Standard Terms of Use (Version 2.0)", "gov-jp-2.0"),
    ],
)
def test_known_license_texts_normalize_to_expected_id(
    raw_license_text: str, expected_id: str
) -> None:
    assert normalize_license_id(raw_license_text) == expected_id


def test_case_and_whitespace_variants_normalize_the_same() -> None:
    assert normalize_license_id("  cc by  ") == "cc-by"
    assert normalize_license_id("Cc By") == "cc-by"


@pytest.mark.parametrize(
    "raw_license_text",
    ["CC BY-NC", "In Copyright", "表示なし・不明", "", "   ", None],
)
def test_unrecognized_or_missing_texts_fall_back_to_unknown_or_named_reject(
    raw_license_text: str | None,
) -> None:
    # CC BY-NC・In Copyright は表中の既知IDへ、空文字・未知表記・Noneは"unknown"へ倒れる。
    result = normalize_license_id(raw_license_text)
    assert result in {"nc", "inc", "unknown"}


def test_completely_unknown_text_is_unknown() -> None:
    assert normalize_license_id("some made up license nobody has heard of") == "unknown"


def test_custom_site_terms_are_scoped_per_source_id() -> None:
    assert normalize_custom_terms("gallica") == "custom-gallica"
    assert normalize_custom_terms("ndl") == "custom-ndl"
