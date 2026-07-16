"""context_matching.py — 手動修正辞書の文脈突き合わせ規則（development-plan.md §8.4）。

エピソードの時代・地域タグ（`episode_tags`）と`manual.yaml`エントリの`context`を
突き合わせ、その表記に使う読みを1つに決める。**LLMに読みを推測させない**（§8.2）
——タグと一致する文脈が無い、または複数の文脈が同時に一致する場合はどちらの読みも
採用せず`None`（unresolved）へ倒す。
"""

from __future__ import annotations

from history_radio.readings.entry import ReadingEntry


def select_manual_reading(
    surface: str, entries: list[ReadingEntry], episode_tags: frozenset[str]
) -> ReadingEntry | None:
    """`surface`について、`episode_tags`に基づき採用する1件を選ぶ。

    決められない場合は`None`——**手動辞書に候補が無かった場合とは呼び出し側で
    区別する**（`entries`に`surface`一致が1件も無いか否かは呼び出し側が判定する。
    ここでの`None`は「候補はあったが一意に決められない」ケースも含む）。
    """
    candidates = [e for e in entries if e.surface == surface]
    if not candidates:
        return None

    context_matches = [e for e in candidates if e.context is not None and e.context in episode_tags]
    if len(context_matches) > 1:
        return None  # 複数の文脈が同時に一致——曖昧なので採用しない（fail closed）
    if context_matches:
        return context_matches[0]

    context_free = [e for e in candidates if e.context is None]
    if len(context_free) == 1:
        return context_free[0]

    # 文脈依存エントリしか無く、どれもepisode_tagsと一致しない場合は既定読みへ
    # フォールバックしない——「どちらの読みも採用せずunresolvedへ倒す」契約（§8.2）。
    return None
