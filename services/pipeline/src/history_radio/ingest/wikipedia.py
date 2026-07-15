"""wikipedia.py — Wikipediaアダプター（仕様書§5.3: MediaWiki API・oldid恒久URL・CC BY-SA）。

§5.3の規約をコードに固定する:
- 出典はoldid付き恒久URLで保存する（revision_id = oldid）。
- テキストはCC BY-SAで許諾済みのため全文ローカル保存可（storage_permission=granted）。
- ただし台本へは事実抽出のみ行い、文章の言い換え転載をしない——本文の公開再配布は
  プロジェクト方針として行わない（publication_permission=denied。SA継承を公開物へ
  広げない — §5.2のcc-by-sa注記）。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from history_radio.ingest.crawl_control import PoliteFetcher
from history_radio.ingest.schema import (
    EvidenceLocator,
    FetchedDocument,
    FetchResponseInfo,
    RightsEvidence,
)


class WikipediaFetchError(RuntimeError):
    """MediaWiki API応答が想定の形でない（ページ欠落・リビジョン欠落等）。"""


@dataclass(frozen=True, slots=True)
class WikipediaAdapter:
    """MediaWiki API経由でページの最新リビジョンを1件取得する（§7.1: API優先）。"""

    language: str = "ja"

    @property
    def source_id(self) -> str:
        return f"wikipedia-{self.language}"

    def _api_url(self, title: str) -> str:
        base = f"https://{self.language}.wikipedia.org/w/api.php"
        params = (
            "action=query&prop=revisions&rvprop=ids|timestamp|content&rvslots=main"
            "&format=json&formatversion=2&titles="
        )
        return f"{base}?{params}{title}"

    def fetch(self, fetcher: PoliteFetcher, resource_ref: str) -> FetchedDocument:
        """resource_ref = ページタイトル。応答の欠落は例外で停止する（fail closed）。"""
        response = fetcher.get(self._api_url(resource_ref))
        payload: Any = response.json()
        try:
            page = payload["query"]["pages"][0]
            if page.get("missing"):
                raise WikipediaFetchError(f"ページが存在しない: {resource_ref}")
            title = page["title"]
            revision = page["revisions"][0]
            oldid = revision["revid"]
            content = revision["slots"]["main"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise WikipediaFetchError(
                f"MediaWiki API応答が想定の形でない: {resource_ref}: {exc!r}"
            ) from exc

        page_url = f"https://{self.language}.wikipedia.org/wiki/{title}"
        permalink = f"https://{self.language}.wikipedia.org/w/index.php?oldid={oldid}"
        content_hash = "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest()

        return FetchedDocument.model_validate(
            {
                "document_id": f"{self.source_id}-{oldid}",
                "source_id": self.source_id,
                "original_url": page_url,
                "canonical_url": permalink,
                "revision_id": f"oldid={oldid}",
                "title": title,
                "creator": "Wikipedia contributors",
                "published_date": revision.get("timestamp"),
                "fetched_at": datetime.now(timezone.utc),
                "full_text": content,
                "locator": EvidenceLocator(),
                "language": self.language,
                "rights": RightsEvidence.model_validate(
                    {
                        "license_name": "CC BY-SA 4.0",
                        "license_url": "https://creativecommons.org/licenses/by-sa/4.0/",
                        "normalized_license_id": "cc-by-sa",
                        "use_class": "A",
                        "rights_statement_text": (
                            "Text is available under the Creative Commons "
                            "Attribution-ShareAlike License 4.0"
                        ),
                        "rights_page_url": page_url,
                    }
                ),
                "permalink": permalink,
                "content_hash": content_hash,
                "response": FetchResponseInfo(
                    fetch_method="api",
                    http_status=response.status_code,
                    etag=response.headers.get("ETag"),
                    last_modified=response.headers.get("Last-Modified"),
                    robots_txt_allowed=True,
                    terms_checked=True,
                ),
                "storage_permission": "granted",
                "publication_permission": "denied",
            }
        )
