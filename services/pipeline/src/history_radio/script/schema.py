"""schema.py — 台本の構造（仕様書§9.1の7段構成と文の分類§8.2A）。

台本完成後、各文を `claim`（外部検証可能な事実文＝claim_id必須）・`presentation`
（演出文）・`opinion`（意見）・`transition`（接続表現）のいずれかに分類する契約
（§8.2A）。分類はLLM出力を人手レビューで確定する運用——この module は分類済みの
台本の「形」を持ち、規則検査は validator.py が行う。
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from history_radio.domain.base import SchemaModel

# §9.1の7段構成（順序もこの通りに固定）
SECTION_KINDS: tuple[str, ...] = (
    "hook",  # 1. 15秒以内の引き
    "setting",  # 2. 時代・場所の説明
    "development",  # 3. 出来事の展開
    "twist",  # 4. 意外な点または通説との違い
    "modern_link",  # 5. 現代との接点
    "uncertainty",  # 6. 不確実な点の明示
    "sources",  # 7. 出典案内
)

SentenceKind = Literal["claim", "presentation", "opinion", "transition"]


class ScriptSentence(SchemaModel):
    """台本の1文。外部検証可能な事実文（kind="claim"）は claim_id 必須（§8.2A）。"""

    text: str = Field(min_length=1)
    kind: SentenceKind
    claim_id: str | None = None


class ScriptSection(SchemaModel):
    kind: str = Field(min_length=1)
    sentences: list[ScriptSentence]


class Script(SchemaModel):
    """§9.1の7段構成の台本。"""

    schema_version: Literal[1] = 1
    episode_id: str = Field(min_length=1)
    sections: list[ScriptSection]
