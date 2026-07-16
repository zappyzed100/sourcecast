"""entry.py — 全辞書ソース共通の読みエントリ型（development-plan.md §8.4「基盤」）。

7ソース（SudachiDict・JMnedict・Wikidata・NDL典拠・アドレスレジストリ・元号辞書・
手動修正辞書）すべてがこの型で読みを返す。ライセンス安全策（§8.3）のため、
各レコードは自分の出所（source_id/source_url/license）を必ず持つ——ソースを跨いで
混ぜても、どのレコードがどのライセンス由来かを常に追跡できる。
"""

from __future__ import annotations

import re
from typing import Literal, Self

from pydantic import Field, model_validator

from history_radio.domain.base import SchemaModel

# 読みの種別（§8.1の分類）
ReadingKind = Literal["person", "place", "era", "office", "common"]

# 読みはカタカナで統一する（VOICEVOXのユーザー辞書・AudioQueryへの注入形式。
# 長音・中点・繰返し記号・スペースを許可）
_KATAKANA_PATTERN = re.compile(r"^[ァ-ヶヴー・ヽヾ　 ]+$")


class ReadingEntry(SchemaModel):
    """読み1件。文脈依存の複数読み（例: 判官=ホウガン/ハンガン）は context を変えて複数行にする。"""

    surface: str = Field(min_length=1)
    reading: str = Field(min_length=1)
    kind: ReadingKind
    # 文脈キー（例: "源平合戦" / "現代"）。Noneは文脈非依存の既定読み
    context: str | None = None
    confidence: float = Field(ge=0, le=1)
    # 出所（config/readings/sources.yaml に登録済みのIDであること——
    # 照合は readings/sources_config.py の validate_entries_against_sources）
    source_id: str = Field(min_length=1)
    source_url: str = Field(min_length=1)
    license: str = Field(min_length=1)
    fetched_at: str = Field(min_length=1)  # ISO8601日付（取得スクリプトが記録）

    @model_validator(mode="after")
    def _reading_is_katakana(self) -> Self:
        if not _KATAKANA_PATTERN.match(self.reading):
            raise ValueError(f"reading はカタカナで統一する（VOICEVOX注入形式）: {self.reading!r}")
        return self
