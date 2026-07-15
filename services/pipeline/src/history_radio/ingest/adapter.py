"""adapter.py — ソースアダプターのProtocol（仕様書§7.1: API→RSS→ダンプ→HTMLの優先順）。

各ソース（Wikipedia・Wikimedia Commons・NDLデジコレ・ColBase等）はこのProtocolを
実装する独立モジュールとして書く。Protocolに寄せるのは「ソース固有の差を
アダプター内へ閉じ込め、収集オーケストレータはこの型だけを知る」ため
（development-plan.md §2）。

実装アダプターへの共通要求（§7.1・§7.3。オーケストレータ側で機械強制されるものも
含めてここに明文化する）:
- 取得方式はAPI→RSS→提供データセット→HTMLクロールの優先順。HTMLは他が無い場合のみ。
- robots.txt禁止パスを取得しない。ログイン・CAPTCHA・アクセス制御を回避しない。
- HTTPクライアントは自前で作らず、注入された `httpx.Client` を使う
  （ドメイン別セマフォ・待機・Retry-After遵守はオーケストレータ層の責務）。
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import httpx

from history_radio.ingest.schema import FetchedDocument


@runtime_checkable
class SourceAdapter(Protocol):
    """1ソース分の取得実装。source_id は config/source_registry.yaml のIDと一致させる。"""

    @property
    def source_id(self) -> str: ...

    def fetch(self, client: httpx.Client, resource_ref: str) -> FetchedDocument:
        """resource_ref（ソース固有の資料識別子）を1件取得して共通スキーマで返す。

        取得失敗・権利表示欠落は例外を投げる（欠けたままの FetchedDocument を
        組み立てない——必須フィールドはスキーマ側が実行時検証で拒否する）。
        """
        ...
