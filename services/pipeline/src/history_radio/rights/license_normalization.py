"""license_normalization.py — 権利表示文字列の正規化（仕様書§5.2）。

サイトごとに表記の揺れる権利表示を `normalized_license_id`（config/license_rules.yaml
に列挙されたID）へ写像する。表に無い・空・未知の表示は必ず `"unknown"` に倒す
（fail closed — 未知の表示を無理に既知IDへ寄せない）。
"""

from __future__ import annotations

# 仕様書§5.2の表に現れる原文表記の代表例 → normalized_license_id。
# キーは小文字化して比較する（英字表記の大文字小文字ゆれを吸収する。日本語表記は
# .lower() の影響を受けないため同じ比較で問題ない）。
_KNOWN_LICENSE_TEXTS: dict[str, str] = {
    "cc0": "cc0",
    "cc-zero": "cc0",
    "public domain dedication": "cc0",
    "public domain mark": "pdm",
    "pdm": "pdm",
    "cc by": "cc-by",
    "cc-by": "cc-by",
    "cc by 4.0": "cc-by",
    "cc-by 4.0": "cc-by",
    "cc by-sa": "cc-by-sa",
    "cc-by-sa": "cc-by-sa",
    "cc by-sa 4.0": "cc-by-sa",
    "cc-by-sa 4.0": "cc-by-sa",
    "政府標準利用規約（第2.0版）": "gov-jp-2.0",
    "政府標準利用規約(第2.0版)": "gov-jp-2.0",
    "government of japan standard terms of use (version 2.0)": "gov-jp-2.0",
    "open government licence": "ogl",
    "open government licence (uk)": "ogl",
    "ogl": "ogl",
    "no known copyright": "nkc",
    "no known copyright restrictions": "nkc",
    "no copyright - united states": "noc-us",
    "cc by-nc": "nc",
    "cc-by-nc": "nc",
    "cc by-nd": "nd",
    "cc-by-nd": "nd",
    "in copyright": "inc",
}

# fail-closedの既定値。表に無い・空・None はすべてここへ倒す。
UNKNOWN_LICENSE_ID = "unknown"


def normalize_license_id(raw_license_text: str | None) -> str:
    """権利表示の原文を `normalized_license_id` へ写像する。

    表にない表記・空文字・None は `"unknown"` にする——推測で既知IDへ寄せない。
    """
    if raw_license_text is None:
        return UNKNOWN_LICENSE_ID
    key = raw_license_text.strip().lower()
    if not key:
        return UNKNOWN_LICENSE_ID
    return _KNOWN_LICENSE_TEXTS.get(key, UNKNOWN_LICENSE_ID)


def normalize_custom_terms(source_id: str) -> str:
    """サイト独自規約（区分C）を `custom-<source_id>` へ写像する（仕様書§5.2）。"""
    return f"custom-{source_id}"
