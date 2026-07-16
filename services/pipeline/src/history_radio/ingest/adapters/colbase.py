"""colbase.py — ColBase（国立博物館所蔵品統合検索システム）アダプター（仕様書§5.3）。

ColBaseの掲載画像・データは出典表示を条件に利用できる（利用規約はCC BY 4.0相当——
政府標準利用規約と同じ扱い。規約ページ: https://colbase.nich.go.jp/pages/terms_of_use）。
資料単位のライセンス表示欄は無いため、**規約ベース（ソース単位）**の権利証拠として
`cc-by` を記録し、出典表示文字列（所蔵館名）を creator に残す。

APIはコレクション項目のJSON（2026-07時点の記録fixtureが形の正）。実接続で形が
変わった場合はパース例外で止まる（fail closed）。
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

_TERMS_URL = "https://colbase.nich.go.jp/pages/terms_of_use"


class ColBaseFetchError(RuntimeError):
    """ColBase API応答が想定の形でない（項目欠落・必須メタデータ欠落等）。"""


@dataclass(frozen=True, slots=True)
class ColBaseAdapter:
    """resource_ref = 項目ID（例: "TNM-A-10569"。館コード付きの一意ID）。"""

    @property
    def source_id(self) -> str:
        return "colbase"

    def _api_url(self, item_id: str) -> str:
        return f"https://colbase.nich.go.jp/api/collection_items/{item_id}?locale=ja"

    def fetch(self, fetcher: PoliteFetcher, resource_ref: str) -> FetchedDocument:
        response = fetcher.get(self._api_url(resource_ref))
        payload: Any = response.json()
        try:
            item = payload["item"]
            title = item["title"]
            museum = item["museum"]
            page_url = item["url"]
        except (KeyError, TypeError) as exc:
            raise ColBaseFetchError(
                f"ColBase API応答が想定の形でない: {resource_ref}: {exc!r}"
            ) from exc

        description = item.get("description")
        era = item.get("era")
        content_hash = (
            "sha256:" + hashlib.sha256(f"{resource_ref}|{title}|{museum}".encode()).hexdigest()
        )

        return FetchedDocument.model_validate(
            {
                "document_id": f"colbase-{resource_ref}",
                "source_id": self.source_id,
                "original_url": page_url,
                "canonical_url": page_url,
                "revision_id": resource_ref,
                "title": title,
                "creator": museum,  # 出典表示の主体（所蔵館）——CC BY相当のクレジット対象
                "published_date": era,
                "fetched_at": datetime.now(timezone.utc),
                "excerpt": description,
                "locator": EvidenceLocator(),
                "language": "ja",
                "rights": RightsEvidence.model_validate(
                    {
                        "license_name": "ColBase利用規約（CC BY 4.0相当）",
                        "license_url": _TERMS_URL,
                        "normalized_license_id": "cc-by",
                        "use_class": "A",
                        "rights_statement_text": (
                            "ColBaseのコンテンツは出典表示により利用可（CC BY 4.0相当）"
                        ),
                        "rights_page_url": _TERMS_URL,
                    }
                ),
                "permalink": page_url,
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
                "publication_permission": "granted",
            }
        )
