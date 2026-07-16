"""validator.py — 台本の公開前検査（仕様書§8.2A・§9.1・Phase 6）。

拒否条件（1件でも該当すれば公開検査を失敗させる — fail closed）:
- §9.1の7段構成が欠落・順序違反
- 外部検証可能な文（kind="claim"）に claim_id が無い
- claim_id が主張台帳に存在しない
- 台帳で `allowed_in_script: false` の主張を使っている
  （独立系統2件未満の主張が台本へ入らない最後の砦）
- 禁止表現を含む（初期値は§6A.2の禁止語辞書を流用——台本は歴史記述のため
  「戦争」等の歴史用語自体は禁止しない。禁止するのは現代の事件・被害の連想を
  呼ぶ表現で、リストは運用で再評価する）
"""

from __future__ import annotations

from history_radio.domain.models import Claim
from history_radio.script.schema import SECTION_KINDS, Script

# 台本の禁止表現の初期値。§6A.2のニュース禁止語と違い、歴史記述に必要な語
# （戦争・災害等）は含めない——現代の被害・事件への便乗連想と、断定を装う
# 表現だけを対象にする（運用で定期的に再評価 — §6A.2と同じ運用）。
DEFAULT_FORBIDDEN_EXPRESSIONS = frozenset(
    {
        "諸説ありますが実は",  # 断定回避を装った断定
        "確実に言えるのは",  # 台帳の qualification を無視した断定強化
        "現代の事件を彷彿",  # 便乗連想の明示
        "いま話題の",  # ニュース因果の示唆（§6A.2「因果関係を示唆しない」）
    }
)


class ScriptValidationError(ValueError):
    """台本の公開前検査の失敗（理由を列挙して1回で全部報告する）。"""

    def __init__(self, problems: list[str]) -> None:
        super().__init__("台本検査失敗:\n- " + "\n- ".join(problems))
        self.problems = problems


def validate_script(
    script: Script,
    ledger: list[Claim],
    *,
    forbidden_expressions: frozenset[str] = DEFAULT_FORBIDDEN_EXPRESSIONS,
) -> None:
    """台本を検査し、問題があれば全件列挙して例外を投げる。問題なしなら黙って返る。"""
    problems: list[str] = []

    section_kinds = [s.kind for s in script.sections]
    if section_kinds != list(SECTION_KINDS):
        problems.append(
            f"§9.1の7段構成に一致しない: {section_kinds}（期待: {list(SECTION_KINDS)}）"
        )

    claims_by_id = {c.claim_id: c for c in ledger}
    for section in script.sections:
        for sentence in section.sentences:
            where = f"[{section.kind}] {sentence.text[:30]!r}"
            if sentence.kind == "claim":
                if sentence.claim_id is None:
                    problems.append(f"{where}: 外部検証可能な文に claim_id が無い（§8.2A）")
                elif sentence.claim_id not in claims_by_id:
                    problems.append(
                        f"{where}: claim_id={sentence.claim_id!r} が主張台帳に存在しない"
                    )
                elif not claims_by_id[sentence.claim_id].allowed_in_script:
                    problems.append(
                        f"{where}: claim_id={sentence.claim_id!r} は allowed_in_script=false"
                        "（独立系統2件未満 — §8.2A/§8.3）"
                    )
            hits = sorted(w for w in forbidden_expressions if w in sentence.text)
            if hits:
                problems.append(f"{where}: 禁止表現を含む: {hits}")

    if problems:
        raise ScriptValidationError(problems)
