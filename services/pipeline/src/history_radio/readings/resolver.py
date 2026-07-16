"""resolver.py — §8.2の解決順序でレイヤーを合成する解決器（development-plan.md §8.4）。

解決順序（§8.2）:
1. 手動修正辞書（context突き合わせ — context_matching.py）
2. 元号・官職専用辞書（自作・検証済み——現状は元号のみ。官職はmanual.yamlのkind="office"で担う）
3. Wikidata / Web NDL Authorities（歴史人物・歴史地名。1層として統合）
4. 地名辞書（アドレス・ベース・レジストリ）
5. JMnedict（人名・地名の読み候補）
6. SudachiDict（一般語）
7. どの層でも未解決 → `unresolved`

純粋関数——I/Oはしない。各層の候補（`list[ReadingEntry]`）はすでに取得済みのものを
呼び出し側が渡す（取得はingest/adapters相当のI/O層の責務、解決はここ）。

手動辞書だけは特別扱い: 候補があるのに文脈で一意に決められない場合、**下位層へ
フォールバックせずその場でunresolvedにする**（手動辞書が明示的に知っている語の
あいまいさを、下位層の機械的な読みで誤魔化さない——§8.2「LLMに読みを推測させない」
と同じ思想を辞書解決にも適用する）。手動辞書以外の層は「同じsurfaceで読みが
食い違う候補がある」場合のみ層内で曖昧と判定し、次の層へは進まず即unresolvedにする
（上位層を勝手に飛ばして下位層で妥協しない）。
"""

from __future__ import annotations

from typing import Literal

from history_radio.domain.base import SchemaModel
from history_radio.readings.context_matching import select_manual_reading
from history_radio.readings.entry import ReadingEntry

ResolutionLayer = Literal["manual", "era", "wikidata_or_ndl", "address", "jmnedict", "sudachi"]


class ResolvedReading(SchemaModel):
    surface: str
    reading: str
    layer: ResolutionLayer
    source_id: str


class UnresolvedReading(SchemaModel):
    surface: str
    reason: str


Resolution = ResolvedReading | UnresolvedReading


def _pick_unambiguous(surface: str, entries: list[ReadingEntry]) -> ReadingEntry | None:
    """層内で`surface`に一致する候補の読みが1通りに定まるならその1件を返す。

    候補なし → None（次の層へ進んでよい）。読みが割れる（複数の異なる値）→ 曖昧
    ——これも None だが、呼び出し側は候補の有無で「未解決」と「次層へ」を区別する。
    """
    matches = [e for e in entries if e.surface == surface]
    if not matches:
        return None
    distinct_readings = {e.reading for e in matches}
    if len(distinct_readings) > 1:
        return None
    return matches[0]


def resolve_reading(
    surface: str,
    *,
    episode_tags: frozenset[str],
    manual_entries: list[ReadingEntry],
    era_entries: list[ReadingEntry],
    wikidata_or_ndl_entries: list[ReadingEntry],
    address_entries: list[ReadingEntry],
    jmnedict_entries: list[ReadingEntry],
    sudachi_entries: list[ReadingEntry],
) -> Resolution:
    """§8.2の優先順位で`surface`の読みを解決する。"""
    manual_candidates = [e for e in manual_entries if e.surface == surface]
    if manual_candidates:
        selected = select_manual_reading(surface, manual_entries, episode_tags)
        if selected is not None:
            return ResolvedReading(
                surface=surface,
                reading=selected.reading,
                layer="manual",
                source_id=selected.source_id,
            )
        return UnresolvedReading(
            surface=surface,
            reason="手動修正辞書に複数文脈があり episode_tags と一致しない、または曖昧",
        )

    layers: list[tuple[ResolutionLayer, list[ReadingEntry]]] = [
        ("era", era_entries),
        ("wikidata_or_ndl", wikidata_or_ndl_entries),
        ("address", address_entries),
        ("jmnedict", jmnedict_entries),
        ("sudachi", sudachi_entries),
    ]
    for layer, entries in layers:
        if not any(e.surface == surface for e in entries):
            continue  # この層に候補が無い——次の層へ
        selected = _pick_unambiguous(surface, entries)
        if selected is not None:
            return ResolvedReading(
                surface=surface, reading=selected.reading, layer=layer, source_id=selected.source_id
            )
        return UnresolvedReading(
            surface=surface, reason=f"{layer}層内で読みが割れて曖昧（次層へは進まない）"
        )

    return UnresolvedReading(surface=surface, reason="どの層でも解決できない")
