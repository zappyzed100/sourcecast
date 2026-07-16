"""engine.py — 権利判定の最終決定（仕様書§5A・§5.2）。

方針（§5A冒頭）: 自動で `allow_public_use` にできるのは、公式メタデータが明示的に
CC0・CC BY・CC BY-SA・政府標準利用規約2.0、または著作権法13条（法令等）を示し、
例外素材がない資料に限る。没年・公表年からの年代計算だけで満了と分かった資料
（`rights/screening.py` の各関数）は、専門家レビューで個別に解禁されるまで
`manual_review` に留める——本エンジンはその解禁の仕組みをまだ持たない
（Phase 3時点では解禁経路自体が未実装）。

判定不能・入力不足・規約取得失敗は必ず `manual_review` か `deny` に倒す（fail closed）。
"""

from __future__ import annotations

from datetime import datetime, timezone

from history_radio.domain.models import RightsDecision, RightsDecisionValue

RULE_VERSION = "5a-v1"

# §5.2表＋§5A冒頭: 公式メタデータの時点で自動採用してよいライセンスID
# （第三者著作物の例外表示が無いことが条件）。ndl-internet-pd はNDLデジタルコレクションの
# 「インターネット公開（保護期間満了）」区分——§5A冒頭が明示的に自動採用対象へ挙げる
# 公式メタデータ（区分のフィルタはアダプター側 ingest/adapters/ndl_digital.py が行う）。
AUTO_APPROVABLE_LICENSE_IDS = frozenset(
    {"cc0", "cc-by", "cc-by-sa", "gov-jp-2.0", "ogl", "ndl-internet-pd"}
)

# §5.2表: 不採用だが事実調査目的の利用は検討可（区分Bとしての内部利用のみ）。
RESEARCH_ONLY_LICENSE_IDS = frozenset({"nc", "nd", "inc", "unknown"})

# §5.2表: 自動採用しない。§5Aのスクリーニング後も原則人手確認が必要。
MANUAL_REVIEW_LICENSE_IDS = frozenset({"noc-us", "nkc", "pdm"})


def decide_from_license(
    normalized_license_id: str,
    *,
    third_party_exception: bool = False,
    government_work: bool = False,
    terms_fetch_failed: bool = False,
) -> tuple[RightsDecisionValue, list[str]]:
    """公式メタデータのライセンス表示・13条該当性から判定する（年代計算は使わない）。"""
    if terms_fetch_failed:
        return "deny", ["規約の取得に失敗したため権利状況を確認できず不採用（fail closed）"]

    if government_work:
        return "allow_public_use", ["著作権法13条: 権利の目的とならない資料（法令・告示・判決等）"]

    if normalized_license_id in AUTO_APPROVABLE_LICENSE_IDS:
        if third_party_exception:
            return "manual_review", [
                f"{normalized_license_id}: 第三者著作物の例外表示があるため自動許可しない"
            ]
        return "allow_public_use", [f"{normalized_license_id}: 公式メタデータによる採用ライセンス"]

    if normalized_license_id in RESEARCH_ONLY_LICENSE_IDS:
        return "internal_research_only", [
            f"{normalized_license_id}: 不採用ライセンスのため公開不可"
            "（事実調査目的の内部利用のみ検討可）"
        ]

    if normalized_license_id in MANUAL_REVIEW_LICENSE_IDS:
        return "manual_review", [f"{normalized_license_id}: 自動採用不可のため人手確認が必要"]

    if normalized_license_id.startswith("custom-"):
        return "manual_review", [
            f"{normalized_license_id}: サイト独自規約のため規約スナップショットと"
            "利用条件フィールドの人手確認が必要"
        ]

    return "manual_review", [f"{normalized_license_id}: 未定義の正規化IDのため人手確認が必要"]


def build_rights_decision(
    *,
    decision_id: str,
    document_id: str,
    normalized_license_id: str,
    third_party_exception: bool = False,
    government_work: bool = False,
    terms_fetch_failed: bool = False,
    now: datetime | None = None,
) -> RightsDecision:
    """`RightsDecision`（`rights_records`）を1件組み立てる。

    `computed_at` は呼び出し時点の現在時刻を刻む——同じ資料を後日再判定した場合、
    新しい `decision_id` で別レコードとして残る（旧判定は上書きしない — Phase 3タスクd）。
    """
    decision, reasons = decide_from_license(
        normalized_license_id,
        third_party_exception=third_party_exception,
        government_work=government_work,
        terms_fetch_failed=terms_fetch_failed,
    )
    return RightsDecision(
        decision_id=decision_id,
        document_id=document_id,
        decision=decision,
        rule_version=RULE_VERSION,
        reasons=reasons,
        computed_at=now or datetime.now(timezone.utc),
    )
