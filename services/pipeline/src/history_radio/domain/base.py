"""base.py — 全ドメインモデル共通の基底（副作用のない型・規則のみ。I/Oはstore/へ — plan.md §2.2）"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class SchemaModel(BaseModel):
    """ドメインモデルの基底。未知フィールドを拒否し、生成後は不変にする。

    不変にする理由: 状態遷移・改訂はすべて新しいインスタンスを返す純粋関数として
    実装する（plan.md §2.2「domain/ = 副作用のない型・規則」）。値を直接書き換える
    経路を型レベルで塞ぐ。
    """

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)
