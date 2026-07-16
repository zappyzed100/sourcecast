"""wikimedia_commons.py — Wikimedia Commonsアダプター（仕様書§5.3: 画像・メディアの資料単位判定）。

MediaWiki API の imageinfo/extmetadata からファイル単位のライセンス表示を取り、
`rights/license_normalization.py` で正規化する——Commonsはファイルごとにライセンスが
異なる（CC0/CC BY/CC BY-SA/PD混在）ため、**ソース一括でなく資料単位**で権利証拠を
残すのが本アダプターの要点。ライセンス表示が取れないファイルは例外で止める（fail closed）。

メディア本体（画像バイナリ）はここでは取得しない——メタデータ・ライセンス証拠・
参照URL（恒久リンク・原画像URL）だけを FetchedDocument に載せ、実ダウンロードは
Phase 7（メディア生成）が media_manifest と共に行う。
"""

from __future__ import annotations

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
from history_radio.rights.license_normalization import normalize_license_id

# 正規化IDがこの集合に入るファイルのみメタデータ保存を「許可」として扱う。
# それ以外（unknown等）は保存はするが権限unknownのまま——判定エンジンが
# internal_research_only/manual_review へ倒す（fail closed）。
_FREE_LICENSE_IDS = frozenset({"cc0", "cc-by", "cc-by-sa", "pdm"})


class CommonsFetchError(RuntimeError):
    """Commons API応答が想定の形でない（ファイル欠落・ライセンス表示欠落等）。"""


@dataclass(frozen=True, slots=True)
class WikimediaCommonsAdapter:
    """resource_ref = ファイルタイトル（例: "File:Tokyo_Station_1914.jpg"）。"""

    @property
    def source_id(self) -> str:
        return "wikimedia-commons"

    def _api_url(self, file_title: str) -> str:
        base = "https://commons.wikimedia.org/w/api.php"
        params = (
            "action=query&prop=imageinfo&iiprop=extmetadata|url|sha1|timestamp"
            "&format=json&formatversion=2&titles="
        )
        return f"{base}?{params}{file_title}"

    def fetch(self, fetcher: PoliteFetcher, resource_ref: str) -> FetchedDocument:
        response = fetcher.get(self._api_url(resource_ref))
        payload: Any = response.json()
        try:
            page = payload["query"]["pages"][0]
            if page.get("missing"):
                raise CommonsFetchError(f"ファイルが存在しない: {resource_ref}")
            title = page["title"]
            info = page["imageinfo"][0]
            sha1 = info["sha1"]
            description_url = info["descriptionurl"]
            meta = info["extmetadata"]
            license_short = meta["LicenseShortName"]["value"]
        except (KeyError, IndexError, TypeError) as exc:
            raise CommonsFetchError(
                f"Commons API応答が想定の形でない（ライセンス表示を確認できない）: "
                f"{resource_ref}: {exc!r}"
            ) from exc

        normalized = normalize_license_id(license_short)
        is_free = normalized in _FREE_LICENSE_IDS
        artist = _meta_value(meta, "Artist") or "不明（Commons Artist欄なし）"
        description = _meta_value(meta, "ImageDescription")
        license_url = _meta_value(meta, "LicenseUrl")

        return FetchedDocument.model_validate(
            {
                "document_id": f"wikimedia-commons-{sha1}",
                "source_id": self.source_id,
                "original_url": info.get("url", description_url),
                "canonical_url": description_url,
                "revision_id": f"sha1={sha1}",
                "title": title,
                "creator": artist,
                "published_date": info.get("timestamp"),
                "fetched_at": datetime.now(timezone.utc),
                "excerpt": description,
                "locator": EvidenceLocator(),
                "language": "und",  # メディアは言語非依存（BCP 47 undetermined）
                "rights": RightsEvidence.model_validate(
                    {
                        "license_name": license_short,
                        "license_url": license_url,
                        "normalized_license_id": normalized,
                        "use_class": "A" if is_free else "B",
                        "rights_statement_text": license_short,
                        "rights_page_url": description_url,
                    }
                ),
                "permalink": description_url,
                "content_hash": f"sha1:{sha1}",
                "response": FetchResponseInfo(
                    fetch_method="api",
                    http_status=response.status_code,
                    etag=response.headers.get("ETag"),
                    last_modified=response.headers.get("Last-Modified"),
                    robots_txt_allowed=True,
                    terms_checked=True,
                ),
                "storage_permission": "granted" if is_free else "unknown",
                "publication_permission": "granted" if is_free else "unknown",
            }
        )


def _meta_value(meta: dict[str, Any], key: str) -> str | None:
    entry: Any = meta.get(key)
    if isinstance(entry, dict):
        value: Any = entry.get("value")  # type: ignore[reportUnknownMemberType]
        if isinstance(value, str) and value.strip():
            return value
    return None
