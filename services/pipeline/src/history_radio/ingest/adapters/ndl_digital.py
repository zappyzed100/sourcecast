"""ndl_digital.py — NDLデジタルコレクションアダプター（仕様書§5.3）。

権利区分メタデータで機械フィルタし、**「インターネット公開（保護期間満了）」区分のみ**
取得する——「個人向けデジタル化資料送信」「館内限定」区分は取得対象にしない（§5.3。
該当したら例外で止める＝候補にも入れない）。

取得はNDLサーチの資料メタデータAPI（OpenSearch/DC-XML）を想定し、XMLは標準ライブラリの
ElementTreeで読む（外部実体は解決しない — §7.3「XML外部実体を無効化」。Python 3.14の
ElementTreeはDTD外部実体を既定で展開しない）。応答の形は2026-07時点の記録fixtureが正
——実接続で形が変わった場合はパース例外で止まる（fail closed）。
"""

from __future__ import annotations

import hashlib
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone

from history_radio.ingest.crawl_control import PoliteFetcher
from history_radio.ingest.schema import (
    EvidenceLocator,
    FetchedDocument,
    FetchResponseInfo,
    RightsEvidence,
)
from history_radio.rights.license_normalization import normalize_license_id

_DC_NS = {
    "dc": "http://purl.org/dc/elements/1.1/",
    "dcndl": "http://ndl.go.jp/dcndl/terms/",
}

_INTERNET_PD = "ndl-internet-pd"


class NdlFetchError(RuntimeError):
    """NDL API応答が想定の形でない（項目欠落・権利区分欠落等）。"""


class NdlRestrictedError(RuntimeError):
    """「インターネット公開（保護期間満了）」以外の権利区分——取得対象にしない（§5.3）。"""


@dataclass(frozen=True, slots=True)
class NdlDigitalAdapter:
    """resource_ref = 恒久ID（例: "info:ndljp/pid/1234567"）。"""

    @property
    def source_id(self) -> str:
        return "ndl-digital"

    def _api_url(self, pid: str) -> str:
        # NDLサーチ OpenSearch（§5.3の取得経路）。pid完全一致で1件引く
        return f"https://ndlsearch.ndl.go.jp/api/opensearch?cnt=1&mediatype=1&idx=1&any={pid}"

    def fetch(self, fetcher: PoliteFetcher, resource_ref: str) -> FetchedDocument:
        response = fetcher.get(self._api_url(resource_ref))
        try:
            root = ET.fromstring(response.text)
            item = root.find(".//item")
            if item is None:
                raise NdlFetchError(f"該当資料が無い: {resource_ref}")
            title = _text(item, "title")
            rights_text = _text_ns(item, "dc:rights")
            creator = _text_ns(item, "dc:creator") or "不明（dc:creator欄なし）"
            link = _text(item, "link")
            published = _text_ns(item, "dcndl:dateDigitized")
        except ET.ParseError as exc:
            raise NdlFetchError(f"NDL応答XMLを解析できない: {resource_ref}: {exc}") from exc
        if not title or not rights_text or not link:
            raise NdlFetchError(f"必須メタデータ（title/dc:rights/link）が欠落: {resource_ref}")

        normalized = normalize_license_id(rights_text)
        if normalized != _INTERNET_PD:
            raise NdlRestrictedError(
                f"{resource_ref}: 権利区分 {rights_text!r} は取得対象外"
                "（インターネット公開（保護期間満了）のみ収集 — §5.3）"
            )

        content_hash = (
            "sha256:" + hashlib.sha256(f"{resource_ref}|{title}|{rights_text}".encode()).hexdigest()
        )

        return FetchedDocument.model_validate(
            {
                "document_id": f"ndl-digital-{resource_ref.rsplit('/', 1)[-1]}",
                "source_id": self.source_id,
                "original_url": link,
                "canonical_url": link,
                "revision_id": resource_ref,
                "title": title,
                "creator": creator,
                "published_date": published,
                "fetched_at": datetime.now(timezone.utc),
                "excerpt": None,
                "locator": EvidenceLocator(),
                "language": "ja",
                "rights": RightsEvidence.model_validate(
                    {
                        "license_name": rights_text,
                        "normalized_license_id": normalized,
                        "use_class": "A",
                        "rights_statement_text": rights_text,
                        "rights_page_url": link,
                    }
                ),
                "permalink": link,
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


def _text(item: ET.Element, tag: str) -> str | None:
    node = item.find(tag)
    return node.text.strip() if node is not None and node.text else None


def _text_ns(item: ET.Element, tag: str) -> str | None:
    node = item.find(tag, _DC_NS)
    return node.text.strip() if node is not None and node.text else None
