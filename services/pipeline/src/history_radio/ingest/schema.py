"""schema.py — 共通取得結果スキーマ（仕様書§7.2の必須保存項目）。

全ソースアダプターはこの型で結果を返す（ソース固有の差はアダプター内へ閉じ込める —
development-plan.md §2「ソースごとの差はアダプターへ閉じ込める」）。

§7.2の要点をそのまま型にする:
- `storage_permission` と `publication_permission` は**分離**する（内部保存が許されても
  公開再配布できるとは限らない）。
- 原文全文（full_text）を保持できるのは保存根拠を確認できた場合のみ——
  `storage_permission` が `granted` でないのに full_text を持つインスタンスは
  実行時検証で拒否する（fail closed）。
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Self

from pydantic import Field, HttpUrl, model_validator

from history_radio.domain.base import SchemaModel

FetchMethod = Literal["api", "rss", "dump", "iiif", "html"]
PermissionState = Literal["granted", "denied", "unknown"]
UseClass = Literal["A", "B", "C", "D"]


class EvidenceLocator(SchemaModel):
    """根拠位置（§7.2: ページ番号・段落ID・文字オフセット・IIIF Canvas等）。"""

    page: int | None = None
    paragraph_id: str | None = None
    start_offset: int | None = Field(default=None, ge=0)
    end_offset: int | None = Field(default=None, ge=0)
    iiif_canvas: str | None = None

    @model_validator(mode="after")
    def _offsets_ordered(self) -> Self:
        if (
            self.start_offset is not None
            and self.end_offset is not None
            and self.end_offset < self.start_offset
        ):
            raise ValueError("end_offset は start_offset 以上でなければならない")
        return self


class RightsEvidence(SchemaModel):
    """権利表示の証拠（§7.2: ライセンス名・URL・正規化ID・利用区分・原文・スクリーンショット）。"""

    license_name: str = Field(min_length=1)
    license_url: HttpUrl | None = None
    normalized_license_id: str = Field(min_length=1)
    use_class: UseClass
    rights_statement_text: str = Field(min_length=1)
    rights_page_url: HttpUrl
    rights_screenshot_ref: str | None = None


class FetchResponseInfo(SchemaModel):
    """取得経路とHTTP応答情報（§7.2）。robots.txt・規約確認の結果もここに残す。"""

    fetch_method: FetchMethod
    http_status: int = Field(ge=100, le=599)
    etag: str | None = None
    last_modified: str | None = None
    robots_txt_allowed: bool
    terms_checked: bool


class FetchedDocument(SchemaModel):
    """1回の資料取得の結果（§7.2の必須保存項目を1レコードに束ねる）。

    full_text は `storage_permission == "granted"` の場合のみ保持できる。
    それ以外は excerpt（必要最小限の根拠抜粋）・ハッシュ・位置・メタデータのみ。
    """

    schema_version: Literal[1] = 1
    document_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    original_url: HttpUrl
    canonical_url: HttpUrl
    revision_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    creator: str = Field(min_length=1)
    published_date: str | None = None
    created_date: str | None = None
    fetched_at: datetime
    full_text: str | None = None
    excerpt: str | None = None
    locator: EvidenceLocator
    language: str = Field(min_length=1)
    rights: RightsEvidence
    permalink: HttpUrl
    external_archive_url: HttpUrl | None = None
    content_hash: str = Field(min_length=1)
    response: FetchResponseInfo
    storage_permission: PermissionState
    publication_permission: PermissionState
    retention_deadline: datetime | None = None

    @model_validator(mode="after")
    def _full_text_requires_storage_permission(self) -> Self:
        if self.full_text is not None and self.storage_permission != "granted":
            raise ValueError(
                "full_text は storage_permission='granted' の場合のみ保持できる"
                "（§7.2: 保存根拠を確認できない資料は根拠抜粋・ハッシュ・メタデータのみ）"
            )
        return self
