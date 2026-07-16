"""voicevox.py — VOICEVOXクライアント（仕様書§9.2・§10・development-plan.md Phase 7）。

VOICEVOX ENGINEのローカルHTTP API（既定 `http://127.0.0.1:50021`）を叩く。
話者はずんだもん・ノーマルスタイル（speaker id=3。VOICEVOX公式の`/speakers`
エンドポイントで公開されている固定ID——秘匿情報ではない）。

fail-closed契約（§9.2「エンジン停止、タイムアウト、途中失敗で不完全MP3を公開対象に
しない」）: エンジン未起動・タイムアウト・非200応答・空応答はすべて例外を投げる。
呼び出し側が例外を握りつぶして空/部分的な音声を公開経路へ流すことがないよう、
戻り値は「完全に生成できた音声バイト列」だけを保証する。

読み仮名の注入（development-plan.md §8.4 残タスク）は、VOICEVOXのアクセント句API
ではなく**テキスト置換**で行う（§8.4「対象表記をカナ読みへ置換する」——文字数の
多い表記から置換することで部分一致による誤置換を防ぐ）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

import httpx

from history_radio.readings.resolver import ResolvedReading

ZUNDAMON_NORMAL_SPEAKER_ID = 3
DEFAULT_BASE_URL = "http://127.0.0.1:50021"
DEFAULT_TIMEOUT_SECONDS = 60.0

# §9.2: 動画概要欄・Podcast説明欄・恒久ページ・音声末尾で共通して使うクレジット文字列
CREDIT_TEXT = "VOICEVOX:ずんだもん"


class VoicevoxError(RuntimeError):
    """VOICEVOX呼び出しの失敗（未起動・タイムアウト・非200応答・空応答）。"""


def inject_readings(text: str, resolutions: list[ResolvedReading]) -> str:
    """解決済みの読みで表記をカナへ置換する。文字数の多い表記を先に処理する
    （例: 「東京タワー」を「東京」より先に置換し、部分一致による誤置換を防ぐ）。
    """
    ordered = sorted(resolutions, key=lambda r: len(r.surface), reverse=True)
    result = text
    for r in ordered:
        result = result.replace(r.surface, r.reading)
    return result


@dataclass(frozen=True, slots=True)
class VoicevoxClient:
    """VOICEVOX ENGINEへのHTTPクライアント（テストは`httpx.MockTransport`を注入）。"""

    client: httpx.Client
    base_url: str = DEFAULT_BASE_URL
    speaker: int = ZUNDAMON_NORMAL_SPEAKER_ID
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS

    def check_version(self) -> str:
        """起動確認（§9.2「エンジン停止」の検出はここで行う）。"""
        try:
            response = self.client.get(f"{self.base_url}/version", timeout=self.timeout_seconds)
        except httpx.HTTPError as exc:
            raise VoicevoxError(f"VOICEVOX ENGINEに接続できない: {exc}") from exc
        if response.status_code != 200:
            raise VoicevoxError(f"VOICEVOX ENGINE /version が異常応答: {response.status_code}")
        return response.text.strip().strip('"')

    def synthesize(self, text: str) -> bytes:
        """テキストを音声合成する（audio_query→synthesisの2段階）。

        いずれかの段階で失敗すれば例外を投げ、部分的な音声バイト列を返さない。
        """
        query = self._audio_query(text)
        return self._synthesis(query)

    def _audio_query(self, text: str) -> dict[str, Any]:
        try:
            response = self.client.post(
                f"{self.base_url}/audio_query",
                params={"text": text, "speaker": self.speaker},
                timeout=self.timeout_seconds,
            )
        except httpx.HTTPError as exc:
            raise VoicevoxError(f"audio_query通信失敗: {exc}") from exc
        if response.status_code != 200:
            raise VoicevoxError(
                f"audio_query異常応答: {response.status_code}: {response.text[:200]}"
            )
        payload: Any = response.json()
        if not isinstance(payload, dict):
            raise VoicevoxError("audio_query応答が想定の形でない（辞書でない）")
        return cast("dict[str, Any]", payload)

    def _synthesis(self, query: dict[str, Any]) -> bytes:
        try:
            response = self.client.post(
                f"{self.base_url}/synthesis",
                params={"speaker": self.speaker},
                json=query,
                timeout=self.timeout_seconds,
            )
        except httpx.HTTPError as exc:
            raise VoicevoxError(f"synthesis通信失敗（タイムアウト等）: {exc}") from exc
        if response.status_code != 200:
            raise VoicevoxError(f"synthesis異常応答: {response.status_code}: {response.text[:200]}")
        if not response.content:
            raise VoicevoxError("synthesis応答が空——不完全な音声を公開対象にしない")
        return response.content
