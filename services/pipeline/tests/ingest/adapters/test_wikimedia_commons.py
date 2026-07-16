"""test_wikimedia_commons.py — Phase 4 DoD: ファイル単位ライセンスの資料単位判定を固定する"""

import json
from typing import Any

import pytest

from history_radio.ingest.adapter import SourceAdapter
from history_radio.ingest.adapters.wikimedia_commons import (
    CommonsFetchError,
    WikimediaCommonsAdapter,
)
from tests.ingest.mock_http import Reply, scripted_fetcher


def _fixture(license_short: str, **extmetadata_overrides: Any) -> str:
    extmetadata: dict[str, Any] = {
        "LicenseShortName": {"value": license_short},
        "Artist": {"value": "小川一真"},
        "ImageDescription": {"value": "東京駅開業時の写真"},
        "LicenseUrl": {"value": "https://creativecommons.org/publicdomain/zero/1.0/"},
    }
    extmetadata.update(extmetadata_overrides)
    return json.dumps(
        {
            "query": {
                "pages": [
                    {
                        "title": "File:Tokyo Station 1914.jpg",
                        "imageinfo": [
                            {
                                "sha1": "f0e1d2c3b4a5",
                                "url": "https://upload.wikimedia.org/wikipedia/commons/x.jpg",
                                "descriptionurl": (
                                    "https://commons.wikimedia.org/wiki/File:Tokyo_Station_1914.jpg"
                                ),
                                "timestamp": "2014-12-01T00:00:00Z",
                                "extmetadata": extmetadata,
                            }
                        ],
                    }
                ]
            }
        }
    )


def test_adapter_satisfies_protocol() -> None:
    assert isinstance(WikimediaCommonsAdapter(), SourceAdapter)


def test_cc0_file_is_free_and_permissions_granted() -> None:
    fetcher, _clock, requests = scripted_fetcher([Reply(text=_fixture("CC0"))])
    doc = WikimediaCommonsAdapter().fetch(fetcher, "File:Tokyo Station 1914.jpg")
    assert doc.rights.normalized_license_id == "cc0"
    assert doc.storage_permission == "granted"
    assert doc.publication_permission == "granted"
    assert doc.content_hash == "sha1:f0e1d2c3b4a5"
    assert "/w/api.php" in requests[0].url  # API優先（§7.1）


def test_unknown_license_file_falls_back_to_unknown_permissions() -> None:
    """未知のライセンス表示はunknownへ倒れ、権限もunknown（fail closed——判定エンジン行き）。"""
    fetcher, _clock, _requests = scripted_fetcher(
        [Reply(text=_fixture("All rights reserved by museum"))]
    )
    doc = WikimediaCommonsAdapter().fetch(fetcher, "File:X.jpg")
    assert doc.rights.normalized_license_id == "unknown"
    assert doc.storage_permission == "unknown"
    assert doc.publication_permission == "unknown"
    assert doc.full_text is None  # スキーマ側の実行時検証とも整合


def test_public_domain_maps_to_pdm_not_auto_free_class_a() -> None:
    """PDMはライセンスでなく状態表示（§5.2）——保存はgrantedだが判定はmanual_review側。"""
    fetcher, _clock, _requests = scripted_fetcher([Reply(text=_fixture("Public domain"))])
    doc = WikimediaCommonsAdapter().fetch(fetcher, "File:X.jpg")
    assert doc.rights.normalized_license_id == "pdm"


def test_missing_license_metadata_raises_instead_of_partial_document() -> None:
    fixture = json.dumps(
        {
            "query": {
                "pages": [
                    {
                        "title": "File:X.jpg",
                        "imageinfo": [
                            {
                                "sha1": "abc",
                                "descriptionurl": "https://commons.wikimedia.org/wiki/File:X.jpg",
                                "extmetadata": {},
                            }
                        ],
                    }
                ]
            }
        }
    )
    fetcher, _clock, _requests = scripted_fetcher([Reply(text=fixture)])
    with pytest.raises(CommonsFetchError, match="ライセンス表示"):
        WikimediaCommonsAdapter().fetch(fetcher, "File:X.jpg")


def test_missing_file_raises() -> None:
    fixture = json.dumps({"query": {"pages": [{"title": "File:Nai.jpg", "missing": True}]}})
    fetcher, _clock, _requests = scripted_fetcher([Reply(text=fixture)])
    with pytest.raises(CommonsFetchError, match="存在しない"):
        WikimediaCommonsAdapter().fetch(fetcher, "File:Nai.jpg")
