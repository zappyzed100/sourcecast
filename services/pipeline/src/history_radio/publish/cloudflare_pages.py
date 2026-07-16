"""cloudflare_pages.py — Cloudflare Pagesのロールバック自動化
（仕様書§10C・development-plan.md Phase 8タスク6）。

Cloudflare PagesのRollbackは「既存デプロイへ配信対象を差し替えるだけ」で、新しい
URLを発行しない——本番URLも各`/episodes/<ID>/`の恒久URLも変わらない（Cloudflare公式の
Rollback機能そのものの性質であり、ここで何かを保証しているわけではない）。R2上の
mediaオブジェクトはPagesのロールバックでは一切変更されない（r2_upload.py は
削除APIを持たず、既存オブジェクトを不変に保つ設計——§10Cの「R2バケットには削除用
ライフサイクルルールを設定しない」を参照）。RSS（Phase 9で実装）のGUIDは
episode_idから決定的に導出する設計にする予定のため、Pagesのロールバックが
GUIDへ影響することも無い想定——ただし実際のRSS実装が無い現時点ではこの一文は
設計意図であり、Phase 9実装後に検証すること。

エンドポイントの存在・認証ヘッダ形式はapi.cloudflare.comへの実プローブで確認済み
（2026-07-16実施）:
- `GET /accounts/{account_id}/pages/projects/{project_name}/deployments`
- `POST /accounts/{account_id}/pages/projects/{project_name}/deployments/{deployment_id}/rollback`
いずれも認証ヘッダ無しでは9106（認証エラー）を返し、ルーティング自体は解決される
ことを確認した。ただし実クレデンシャルでの成功応答の中身（各デプロイ要素のJSON
キー名）は未確認——Cloudflare API v4共通の`{success, result, ...}`エンベロープに
従うことを前提に、デプロイ要素は`id`・`created_on`・`environment`キーを持つとして
実装している。HUMAN_TASKS.mdのPagesプロジェクト作成後、実際の応答と照合すること。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

import httpx

_API_BASE = "https://api.cloudflare.com/client/v4"


class PagesRollbackError(RuntimeError):
    """Pagesデプロイ一覧取得・rollback呼び出しの失敗。"""


@dataclass(frozen=True, slots=True)
class Deployment:
    id: str
    created_on: str
    environment: str  # "production" | "preview"
    url: str


@dataclass(frozen=True, slots=True)
class PagesClient:
    client: httpx.Client
    account_id: str
    project_name: str
    api_token: str
    timeout_seconds: float = 60.0

    def _base_url(self) -> str:
        return f"{_API_BASE}/accounts/{self.account_id}/pages/projects/{self.project_name}"

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_token}"}

    def list_deployments(self, *, environment: str = "production") -> list[Deployment]:
        """指定environmentのデプロイ一覧を新しい順で返す。"""
        url = f"{self._base_url()}/deployments"
        try:
            response = self.client.get(url, headers=self._headers(), timeout=self.timeout_seconds)
        except httpx.HTTPError as exc:
            raise PagesRollbackError(f"デプロイ一覧の取得に失敗: {exc}") from exc
        if response.status_code != 200:
            raise PagesRollbackError(f"デプロイ一覧取得が異常応答: {response.status_code}")

        raw_payload: Any = response.json()
        if not isinstance(raw_payload, dict):
            raise PagesRollbackError(f"デプロイ一覧応答が不正: {response.text[:200]}")
        payload = cast("dict[str, Any]", raw_payload)
        if not payload.get("success"):
            raise PagesRollbackError(f"デプロイ一覧応答が不正: {response.text[:200]}")
        raw_results = payload.get("result")
        if not isinstance(raw_results, list):
            raise PagesRollbackError("デプロイ一覧応答にresultが無い")

        deployments: list[Deployment] = []
        for item in cast("list[Any]", raw_results):
            if not isinstance(item, dict):
                continue
            item = cast("dict[str, Any]", item)
            try:
                deployment = Deployment(
                    id=str(item["id"]),
                    created_on=str(item["created_on"]),
                    environment=str(item["environment"]),
                    url=str(item.get("url", "")),
                )
            except KeyError as exc:
                raise PagesRollbackError(f"デプロイ要素に必須フィールドが無い: {exc}") from exc
            if deployment.environment == environment:
                deployments.append(deployment)

        deployments.sort(key=lambda d: d.created_on, reverse=True)
        return deployments

    def rollback_to_previous(self, *, environment: str = "production") -> Deployment:
        """現在の直前のデプロイへロールバックする。

        直前版が存在しない（デプロイが1件以下）場合は、ロールバック先が無いのに
        「成功」を返すことを避けるためfail closedで拒否する。
        """
        deployments = self.list_deployments(environment=environment)
        if len(deployments) < 2:
            raise PagesRollbackError(
                f"ロールバック先が無い（{environment}のデプロイが{len(deployments)}件）"
            )
        previous = deployments[1]
        self._call_rollback(previous.id)
        return previous

    def _call_rollback(self, deployment_id: str) -> None:
        url = f"{self._base_url()}/deployments/{deployment_id}/rollback"
        try:
            response = self.client.post(url, headers=self._headers(), timeout=self.timeout_seconds)
        except httpx.HTTPError as exc:
            raise PagesRollbackError(f"ロールバック呼び出しに失敗: {exc}") from exc
        if response.status_code != 200:
            raise PagesRollbackError(
                f"ロールバックが異常応答: {response.status_code}: {response.text[:200]}"
            )
