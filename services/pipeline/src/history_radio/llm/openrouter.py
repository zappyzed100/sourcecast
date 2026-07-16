"""openrouter.py — OpenRouter実クライアント（仕様書§8.1。llm/cache.pyのLlmCaller実装）。

APIキーは環境変数 `OPENROUTER_API_KEY` からのみ読む——Git・SQLite・ログへ保存しない
（development-plan.md §2「資格情報をGit、SQLite、ログへ保存しない」）。例外メッセージにも
キーを含めない。

ルーティング制約（§8.1）: モデルIDは呼び出し側（model_registry.yaml を通過した固定ID）
が渡す。学習利用を許可するプロバイダーへのルーティングは `provider.data_collection=deny`
で無効化する。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx

from history_radio.llm.cache import LlmResult

OPENROUTER_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_TIMEOUT_SECONDS = 180.0
_API_KEY_ENV = "OPENROUTER_API_KEY"


class OpenRouterError(RuntimeError):
    """OpenRouter呼び出しの失敗（HTTPエラー・応答形の不一致）。キーは含めない。"""


@dataclass(frozen=True, slots=True)
class OpenRouterCaller:
    """llm/cache.py の LlmCaller Protocol 実装。clientは注入（テストはフェイクtransport）。"""

    client: httpx.Client
    api_key: str
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    # 構造化出力の強制（§8.1「JSON Schema」検証の前段。対応モデルのみtrueにする）
    require_json: bool = True

    @classmethod
    def from_env(cls, client: httpx.Client) -> OpenRouterCaller:
        api_key = os.environ.get(_API_KEY_ENV, "").strip()
        if not api_key:
            raise OpenRouterError(
                f"環境変数 {_API_KEY_ENV} が未設定（キーはenv経由のみ——ファイルに書かない）"
            )
        return cls(client=client, api_key=api_key)

    def __call__(self, *, model_id: str, prompt: str) -> LlmResult:
        body: dict[str, Any] = {
            "model": model_id,
            "messages": [{"role": "user", "content": prompt}],
            # §8.1: 学習利用を許可するプロバイダーへのルーティングを無効化
            "provider": {"data_collection": "deny"},
        }
        if self.require_json:
            body["response_format"] = {"type": "json_object"}
        try:
            response = self.client.post(
                OPENROUTER_ENDPOINT,
                json=body,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=self.timeout_seconds,
            )
        except httpx.HTTPError as exc:
            # NO-LOG: 単一ログ出口は未実装（§7の出口はPhase 11で配線）。例外に文脈を
            # 載せて上位へ——ここでprintしない。キーを含めないことが最優先
            raise OpenRouterError(f"OpenRouter通信失敗: {type(exc).__name__}: {exc}") from exc
        if response.status_code != 200:
            raise OpenRouterError(
                f"OpenRouter応答エラー: HTTP {response.status_code}: {response.text[:300]}"
            )
        payload: Any = response.json()
        try:
            content = payload["choices"][0]["message"]["content"]
            usage = payload.get("usage", {})
        except (KeyError, IndexError, TypeError) as exc:
            raise OpenRouterError(f"OpenRouter応答が想定の形でない: {exc!r}") from exc
        if not isinstance(content, str) or not content.strip():
            # reasoning系モデルはcontentがnull/空でreasoningフィールドに出すことがある
            raise OpenRouterError(
                f"OpenRouter応答のcontentが空（model={model_id}。reasoning系は"
                "content空になり得る——本パイプラインの対象外モデル）"
            )
        return LlmResult(
            output_text=content,
            prompt_tokens=int(usage.get("prompt_tokens", 0)),
            completion_tokens=int(usage.get("completion_tokens", 0)),
        )
