"""r2_upload.py — Cloudflare R2へのハッシュキー付きmediaアップロード
（仕様書§10C・development-plan.md Phase 8タスク4）。

Cloudflare API v4のR2オブジェクトエンドポイント（`Authorization: Bearer <token>`）を使う——
HUMAN_TASKS.mdでユーザーへ依頼している「Cloudflare API トークン（R2編集権限）＋
アカウントID」がそのままこのクライアントの資格情報になる（S3互換APIのaccess key/secret
とは別物）。エンドポイントの存在・認証ヘッダ形式・HEAD不可（405）は
`api.cloudflare.com`への実プローブで確認済み（2026-07-16実施）——ただし実クレデンシャル
での成功応答は未確認（トークン発行後にHUMAN_TASKS.mdの手順で確認する）。

キーをコンテンツのsha256ハッシュから導出することで、重複防止をキー設計そのものへ
埋め込む——同じバイト列は常に同じキーへ写像されるため、「同じ入力の再実行が
重複オブジェクトを作らない」というDoDは事前チェックの有無に関わらず構造的に満たす。
アップロード前の存在確認はGETをストリーミングモードで発行しヘッダだけ読んで
bodyを読まずに閉じる（R2 API v4にはHEADもオブジェクト一覧APIも無い——405実測済み）。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import httpx

_API_BASE = "https://api.cloudflare.com/client/v4"


class R2UploadError(RuntimeError):
    """R2アップロード/存在確認の失敗。"""


def content_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def object_key(data: bytes, filename: str) -> str:
    """コンテンツのsha256ハッシュから決定的にキーを導出する。

    同じ内容・同じ拡張子なら元のファイル名が違っても同じキーになる——
    重複防止をキー設計そのものへ埋め込むための意図的な設計。
    """
    suffix = Path(filename).suffix
    return f"media/{content_hash(data)}{suffix}"


@dataclass(frozen=True, slots=True)
class ExistingObject:
    key: str
    size: int


@dataclass(frozen=True, slots=True)
class UploadResult:
    key: str
    content_hash: str
    size: int
    uploaded: bool  # False = 既存オブジェクトと一致していたためPUTを省略した


@dataclass(frozen=True, slots=True)
class R2Client:
    client: httpx.Client
    account_id: str
    bucket: str
    api_token: str
    timeout_seconds: float = 60.0

    def _object_url(self, key: str) -> str:
        return f"{_API_BASE}/accounts/{self.account_id}/r2/buckets/{self.bucket}/objects/{key}"

    def _auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_token}"}

    def find_existing(self, key: str) -> ExistingObject | None:
        """既存オブジェクトの有無とサイズだけを確認する（bodyは読まない）。"""
        url = self._object_url(key)
        try:
            with self.client.stream(
                "GET", url, headers=self._auth_headers(), timeout=self.timeout_seconds
            ) as response:
                if response.status_code == 404:
                    return None
                if response.status_code != 200:
                    raise R2UploadError(f"R2オブジェクト確認が異常応答: {response.status_code}")
                size = int(response.headers.get("content-length", "0"))
                return ExistingObject(key=key, size=size)
        except httpx.HTTPError as exc:
            raise R2UploadError(f"R2への接続に失敗: {exc}") from exc

    def upload(self, data: bytes, filename: str, *, content_type: str) -> UploadResult:
        """`data`をハッシュ由来のキーへアップロードする。

        既に同一キー（=同一内容）が同一サイズで存在する場合はPUTを省略する（冪等）。
        サイズが食い違う場合はキー設計の前提（同一キー=同一内容）が崩れているため
        fail closedで拒否する。
        """
        key = object_key(data, filename)
        h = content_hash(data)
        existing = self.find_existing(key)
        if existing is not None:
            if existing.size != len(data):
                raise R2UploadError(
                    f"既存オブジェクトのサイズが不一致（key={key}, "
                    f"既存={existing.size}バイト, 今回={len(data)}バイト）"
                    "——ハッシュ由来キーの前提が崩れている"
                )
            return UploadResult(key=key, content_hash=h, size=len(data), uploaded=False)

        url = self._object_url(key)
        try:
            response = self.client.put(
                url,
                content=data,
                headers={**self._auth_headers(), "Content-Type": content_type},
                timeout=self.timeout_seconds,
            )
        except httpx.HTTPError as exc:
            raise R2UploadError(f"R2アップロード通信失敗: {exc}") from exc
        if response.status_code not in (200, 201):
            raise R2UploadError(
                f"R2アップロードが異常応答: {response.status_code}: {response.text[:200]}"
            )
        return UploadResult(key=key, content_hash=h, size=len(data), uploaded=True)
