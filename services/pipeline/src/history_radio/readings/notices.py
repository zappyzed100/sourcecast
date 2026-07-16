"""notices.py — THIRD_PARTY_NOTICES.md の機械生成（development-plan.md §8.4）。

手書きにするとソース追加時に更新し忘れる——sources.yaml を正本として全文を生成する
（ドリフトは tests/readings/test_notices.py が「再生成==コミット済み」で検出。
STRUCTURE.md と同じ「生成物だがコミットする」扱い — repo_scan の GENERATED_PATTERNS）。
"""

from __future__ import annotations

from history_radio.readings.sources_config import ReadingSourceMeta

_HEADER = """<!-- THIRD_PARTY_NOTICES.md —
読み辞書データソースの出典・ライセンス一覧（機械生成・手編集禁止） -->
# サードパーティ辞書データの出典とライセンス

本ファイルは `config/readings/sources.yaml` から
`uv run scripts/readings/generate_third_party_notices.py` で生成される（手編集禁止）。
辞書データ本体はリポジトリにコミットしない——取得スクリプトが取得日・件数・ハッシュを
記録する（development-plan.md §8.3）。ライセンス原文は `licenses/` に置く。
"""


def build_notices(sources: list[ReadingSourceMeta]) -> str:
    """sources.yaml の全ソースから THIRD_PARTY_NOTICES.md の全文を決定的に生成する。"""
    lines: list[str] = [_HEADER]
    third_party = [s for s in sources if not s.first_party]
    first_party = [s for s in sources if s.first_party]

    lines.append("## サードパーティデータ\n")
    for s in sorted(third_party, key=lambda x: x.source_id):
        lines.append(f"### {s.name}\n")
        lines.append(f"- ライセンス: {s.license}")
        if s.license_url:
            lines.append(f"- ライセンスURL: {s.license_url}")
        lines.append(f"- 配布元: {s.url}")
        lines.append(f"- 出典表記: {s.attribution_text}")
        lines.append(f"- 派生辞書としての再配布: {'可' if s.redistribution_allowed else '不可'}")
        if s.notes:
            lines.append(f"- 備考: {s.notes}")
        lines.append("")

    lines.append("## 自作データ（本プロジェクトの資産）\n")
    for s in sorted(first_party, key=lambda x: x.source_id):
        lines.append(f"### {s.name}\n")
        lines.append(f"- 置き場: {s.url}")
        lines.append(f"- 表記: {s.attribution_text}")
        if s.notes:
            lines.append(f"- 備考: {s.notes}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
