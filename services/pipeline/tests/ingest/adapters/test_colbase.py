"""test_colbase.py — Phase 4 DoD: 規約ベース（CC BY相当）の権利証拠と出典表示の記録を固定する"""

import json

import pytest

from history_radio.ingest.adapter import SourceAdapter
from history_radio.ingest.adapters.colbase import ColBaseAdapter, ColBaseFetchError
from tests.ingest.mock_http import Reply, scripted_fetcher

_FIXTURE_OK = json.dumps(
    {
        "item": {
            "title": "遮光器土偶",
            "museum": "東京国立博物館",
            "url": "https://colbase.nich.go.jp/collection_items/tnm/J-38392?locale=ja",
            "description": "青森県つがる市木造亀ヶ岡出土",
            "era": "縄文時代（晩期）",
        }
    }
)


def test_adapter_satisfies_protocol() -> None:
    assert isinstance(ColBaseAdapter(), SourceAdapter)


def test_item_is_collected_as_cc_by_with_museum_attribution() -> None:
    fetcher, _clock, requests = scripted_fetcher([Reply(text=_FIXTURE_OK)])
    doc = ColBaseAdapter().fetch(fetcher, "TNM-J-38392")

    assert doc.rights.normalized_license_id == "cc-by"
    assert doc.storage_permission == "granted"
    assert doc.publication_permission == "granted"
    # CC BY相当のクレジット対象（出典表示の主体）が残る
    assert doc.creator == "東京国立博物館"
    assert str(doc.rights.rights_page_url) == "https://colbase.nich.go.jp/pages/terms_of_use"
    assert "/api/collection_items/" in requests[0].url  # API優先（§7.1）


def test_missing_required_metadata_raises_instead_of_partial_document() -> None:
    broken = json.dumps({"item": {"title": "所蔵館欄なし"}})
    fetcher, _clock, _requests = scripted_fetcher([Reply(text=broken)])
    with pytest.raises(ColBaseFetchError, match="想定の形でない"):
        ColBaseAdapter().fetch(fetcher, "TNM-X-0")


def test_same_item_produces_same_content_hash() -> None:
    fetcher1, _c1, _r1 = scripted_fetcher([Reply(text=_FIXTURE_OK)])
    fetcher2, _c2, _r2 = scripted_fetcher([Reply(text=_FIXTURE_OK)])
    doc1 = ColBaseAdapter().fetch(fetcher1, "TNM-J-38392")
    doc2 = ColBaseAdapter().fetch(fetcher2, "TNM-J-38392")
    assert doc1.content_hash == doc2.content_hash
