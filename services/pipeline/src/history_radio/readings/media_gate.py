"""media_gate.py — unresolved語による音声生成ジョブの停止（development-plan.md §8.4）。

`unresolved`語を1件でも含む台本は音声生成ジョブに進めない（fail closed）。
"""

from __future__ import annotations

from history_radio.domain.models import JobStatus
from history_radio.readings.resolver import Resolution, UnresolvedReading


def unresolved_surfaces(resolutions: list[Resolution]) -> list[str]:
    return [r.surface for r in resolutions if isinstance(r, UnresolvedReading)]


def decide_media_job_status(resolutions: list[Resolution]) -> JobStatus:
    """全語が解決済みなら`queued`、1件でもunresolvedがあれば`blocked`を返す。"""
    return "blocked" if unresolved_surfaces(resolutions) else "queued"
