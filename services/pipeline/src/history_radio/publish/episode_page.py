"""episode_page.py — 公開エピソードページの生成（仕様書§10B・§10C・development-plan.md Phase 8）。

Pythonからバージョン付き公開Markdown（`apps/site/src/content/episodes/<episode_id>.md`）を
生成する。フィールドはAstroの content collection スキーマ（`apps/site/src/content.config.ts`）
と1対1で対応させ、キーはcamelCaseで書き出す——Python↔TypeScriptの契約はここでも
「型を公開JSON契約の第1強制層にする」（PLAN.md §2.3）を踏襲し、**Python側の生成時点**で
不正Schema・欠落出典・未知ライセンスを拒否する（Astroのbuildで初めて気づくのではなく、
生成の入口で fail closed にする——二重の網の1層目）。

出典の`normalized_license_id`が`rights.engine.AUTO_APPROVABLE_LICENSE_IDS`に無い
（=`allow_public_use`を経ていない）資料は公開ページの出典に使えない。
"""

from __future__ import annotations

import re
from typing import cast

import yaml
from pydantic import Field

from history_radio.domain.base import SchemaModel
from history_radio.rights.engine import AUTO_APPROVABLE_LICENSE_IDS

_EPISODE_ID_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}-[a-z0-9-]+$")


class EpisodePageError(ValueError):
    """公開ページ生成の検証失敗（全件列挙して報告する）。"""

    def __init__(self, problems: list[str]) -> None:
        super().__init__("episode_page検証失敗:\n- " + "\n- ".join(problems))
        self.problems = problems


class SourceEntry(SchemaModel):
    name: str = Field(min_length=1)
    url: str = Field(min_length=1)
    license: str = Field(min_length=1)
    # 内部監査用（Astroのzodスキーマは未知キーを無視するため公開表示には影響しない）。
    # ここが AUTO_APPROVABLE_LICENSE_IDS に無ければ生成自体を拒否する
    normalized_license_id: str = Field(min_length=1)
    credit: str = Field(min_length=1)
    accessed_at: str = Field(min_length=1)


class ClaimEntry(SchemaModel):
    text: str = Field(min_length=1)
    source_indexes: list[int] = Field(min_length=1)


class CorrectionEntry(SchemaModel):
    date: str = Field(min_length=1)
    description: str = Field(min_length=1)


class RelatedBookEntry(SchemaModel):
    title: str = Field(min_length=1)
    author: str = Field(min_length=1)
    isbn: str | None = None
    url: str = Field(min_length=1)


class ChapterEntry(SchemaModel):
    title: str = Field(min_length=1)
    start_seconds: float = Field(ge=0)


class EpisodePageData(SchemaModel):
    """`apps/site/src/content.config.ts`のepisodesスキーマと1対1対応する生成入力。"""

    schema_version: int = 1
    episode_id: str = Field(min_length=1)
    revision: int = Field(ge=1)
    title: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    published_at: str = Field(min_length=1)
    updated_at: str = Field(min_length=1)
    sources: list[SourceEntry] = Field(min_length=1)
    claims: list[ClaimEntry] = Field(default_factory=list)
    corrections: list[CorrectionEntry] = Field(default_factory=list)
    related_books: list[RelatedBookEntry] = Field(default_factory=list)
    audio_url: str | None = None
    chapters: list[ChapterEntry] | None = None


def validate_episode_page(data: EpisodePageData) -> None:
    """§10B・development-plan.md Phase 8の検証を行う。問題は全件列挙して報告する。"""
    problems: list[str] = []

    if not _EPISODE_ID_PATTERN.match(data.episode_id):
        problems.append(
            f"episode_idの形式が不正: {data.episode_id!r}（期待形式: <公開日YYYY-MM-DD>-<不変ID>）"
        )

    for i, source in enumerate(data.sources):
        if source.normalized_license_id not in AUTO_APPROVABLE_LICENSE_IDS:
            problems.append(
                f"sources[{i}] ({source.name!r}): 未知/不採用ライセンスの資料は公開できない"
                f"（normalized_license_id={source.normalized_license_id!r}）"
            )

    n_sources = len(data.sources)
    for i, claim in enumerate(data.claims):
        out_of_range = [idx for idx in claim.source_indexes if not (0 <= idx < n_sources)]
        if out_of_range:
            problems.append(
                f"claims[{i}] ({claim.text[:30]!r}...): "
                f"存在しない出典indexを参照している: {out_of_range}"
            )

    if problems:
        raise EpisodePageError(problems)


def _to_camel_case(snake: str) -> str:
    head, *tail = snake.split("_")
    return head + "".join(w.capitalize() for w in tail)


def _camelize_keys(value: object) -> object:
    if isinstance(value, dict):
        items = cast("dict[str, object]", value).items()
        return {_to_camel_case(k): _camelize_keys(v) for k, v in items}
    if isinstance(value, list):
        return [_camelize_keys(v) for v in cast("list[object]", value)]
    return value


def render_episode_frontmatter(data: EpisodePageData) -> str:
    """検証済みの`EpisodePageData`から、フロントマター付きMarkdown全文を生成する。

    呼び出し前に`validate_episode_page`を通すこと——ここでは検証しない
    （検証と描画を分離する。resolver.py/slides.pyと同じ「決定と実行の分離」方針）。
    """
    payload = _camelize_keys(data.model_dump(exclude_none=True))
    front_matter = yaml.safe_dump(payload, allow_unicode=True, sort_keys=False)
    return f"---\n{front_matter}---\n"
