"""ledger.py — 主張台帳の構築（仕様書§8.2A）。

台本生成前に、公開可能な事実だけを claim_ledger として確定する。台本モデルは
この台帳にない外部事実を追加してはならない（検査は script/validator.py）。

規則:
- 独立系統2件未満の主張は `allowed_in_script: false`（§8.3「独立した根拠系統
  2件未満の候補は総合点に関係なく不採用」の主張版）。
- 単一系統の主張は qualification="資料帰属" を強制する——中心的主張にせず
  「当該資料にはこう記される」と明示する契約（§6.2）。
"""

from __future__ import annotations

from pydantic import Field

from history_radio.domain.base import SchemaModel
from history_radio.domain.models import Claim, ClaimQualification


class ClaimInput(SchemaModel):
    """台帳構築の入力1件（検証済みの事実と、その根拠の系統割り当て）。"""

    claim_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    evidence_ids: list[str] = Field(min_length=1)
    # 各根拠が属する系統ID（select/lineage.py の系統判定結果から割り当てる）
    source_family_ids: list[str] = Field(min_length=1)
    reliability_score: float = Field(ge=0, le=1)
    qualification: ClaimQualification


def build_claim(entry: ClaimInput) -> Claim:
    """1主張を台帳エントリへ確定する。独立系統2件未満は台本使用不可。"""
    independent_families = len(set(entry.source_family_ids))
    allowed = independent_families >= 2
    qualification: ClaimQualification = entry.qualification
    if independent_families < 2:
        # 単一系統: 断定を許さず資料帰属へ倒す（§6.2「当該資料にはこう記される」）
        qualification = "資料帰属"
    return Claim(
        claim_id=entry.claim_id,
        text=entry.text,
        evidence_ids=entry.evidence_ids,
        source_family_ids=sorted(set(entry.source_family_ids)),
        reliability_score=entry.reliability_score,
        allowed_in_script=allowed,
        qualification=qualification,
    )


def build_claim_ledger(entries: list[ClaimInput]) -> list[Claim]:
    """台帳全体を構築する。claim_idの重複は例外（同一IDの主張が2定義あると追跡不能）。"""
    seen: set[str] = set()
    for e in entries:
        if e.claim_id in seen:
            raise ValueError(f"claim_id重複: {e.claim_id}（1主張1IDにする — §8.2A）")
        seen.add(e.claim_id)
    return [build_claim(e) for e in entries]
