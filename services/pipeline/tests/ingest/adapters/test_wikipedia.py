"""test_wikipedia.py — Phase 4 DoD: 記録済みfixtureでWikipediaアダプターを固定する"""

import json

import pytest

from history_radio.ingest.adapter import SourceAdapter
from history_radio.ingest.adapters.wikipedia import WikipediaAdapter, WikipediaFetchError
from tests.ingest.mock_http import Reply, scripted_fetcher

# MediaWiki API (formatversion=2) の記録済み応答の縮約版
_FIXTURE_OK = json.dumps(
    {
        "query": {
            "pages": [
                {
                    "pageid": 1296,
                    "title": "西郷隆盛",
                    "revisions": [
                        {
                            "revid": 987654,
                            "timestamp": "2026-07-01T00:00:00Z",
                            "slots": {"main": {"content": "'''西郷隆盛'''は薩摩藩出身の…"}},
                        }
                    ],
                }
            ]
        }
    }
)

_FIXTURE_MISSING_PAGE = json.dumps(
    {"query": {"pages": [{"title": "存在しない記事", "missing": True}]}}
)

_FIXTURE_MALFORMED = json.dumps({"query": {}})


def test_adapter_satisfies_protocol() -> None:
    assert isinstance(WikipediaAdapter(), SourceAdapter)


def test_fetch_builds_document_from_recorded_fixture() -> None:
    fetcher, _clock, requests = scripted_fetcher([Reply(text=_FIXTURE_OK)])
    doc = WikipediaAdapter(language="ja").fetch(fetcher, "西郷隆盛")

    assert doc.source_id == "wikipedia-ja"
    assert doc.title == "西郷隆盛"
    assert doc.revision_id == "oldid=987654"
    # §5.3: 出典はoldid付き恒久URLで保存する
    assert str(doc.permalink) == "https://ja.wikipedia.org/w/index.php?oldid=987654"
    assert doc.rights.normalized_license_id == "cc-by-sa"
    assert doc.content_hash.startswith("sha256:")
    # APIエンドポイントへのリクエストだった（HTMLクロールでない — §7.1）
    assert "/w/api.php" in requests[0].url


def test_storage_granted_but_publication_denied() -> None:
    """§5.3: CC BY-SAで全文ローカル保存可。ただし本文の公開再配布はしない（SA継承を防ぐ）。"""
    fetcher, _clock, _requests = scripted_fetcher([Reply(text=_FIXTURE_OK)])
    doc = WikipediaAdapter().fetch(fetcher, "西郷隆盛")
    assert doc.storage_permission == "granted"
    assert doc.publication_permission == "denied"
    assert doc.full_text is not None


def test_missing_page_raises_instead_of_partial_document() -> None:
    fetcher, _clock, _requests = scripted_fetcher([Reply(text=_FIXTURE_MISSING_PAGE)])
    with pytest.raises(WikipediaFetchError, match="存在しない"):
        WikipediaAdapter().fetch(fetcher, "存在しない記事")


def test_malformed_api_response_raises_instead_of_partial_document() -> None:
    fetcher, _clock, _requests = scripted_fetcher([Reply(text=_FIXTURE_MALFORMED)])
    with pytest.raises(WikipediaFetchError, match="想定の形でない"):
        WikipediaAdapter().fetch(fetcher, "西郷隆盛")


def test_same_content_produces_same_hash() -> None:
    """§7.3: 同一内容はハッシュで再取得を抑制する——その前提となるハッシュの決定性。"""
    fetcher1, _c1, _r1 = scripted_fetcher([Reply(text=_FIXTURE_OK)])
    fetcher2, _c2, _r2 = scripted_fetcher([Reply(text=_FIXTURE_OK)])
    doc1 = WikipediaAdapter().fetch(fetcher1, "西郷隆盛")
    doc2 = WikipediaAdapter().fetch(fetcher2, "西郷隆盛")
    assert doc1.content_hash == doc2.content_hash
