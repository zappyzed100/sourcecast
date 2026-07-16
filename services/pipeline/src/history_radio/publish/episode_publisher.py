"""episode_publisher.py — バージョン管理付きの公開書き出し（仕様書§10B・Phase 8タスク2）。

`episode_page.py`が生成するフロントマター＋本文を、Astroのcontent collectionディレクトリへ
書き出す。旧版を上書きしないことが要件——新しいrevisionを公開する度に

- `<episodeId>/versions/<revision>.md` へ不変の記録として追加する（既存なら再書き込みしない）
- `<episodeId>.md`（現行版ポインタ）だけを新しい内容へ更新する

という2段書き込みにする。同じrevisionを同じ内容で再実行するのは冪等（何もしない）——
既に公開した版を異なる内容で書き換えようとする操作はfail closedで拒否する
（rights/engine.py等と同じ「事故は起きた後で正すのでなく、起きる前に拒否する」方針）。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from history_radio.publish.episode_page import (
    EpisodePageData,
    render_episode_frontmatter,
    validate_episode_page,
)


class EpisodePublishConflictError(ValueError):
    """既に公開済みのrevisionを異なる内容・順序で扱おうとした場合に送出する。"""


@dataclass(frozen=True)
class PublishResult:
    current_path: Path
    version_path: Path
    is_new_revision: bool


def _read_frontmatter_revision(path: Path) -> int:
    text = path.read_text(encoding="utf-8")
    _, front_matter, _ = text.split("---", 2)
    parsed = yaml.safe_load(front_matter)
    return int(parsed["revision"])


def publish_episode(content_dir: Path, data: EpisodePageData, body: str) -> PublishResult:
    """`content_dir`（例: `apps/site/src/content/episodes`）へ1版を公開する。

    呼び出し前に`data`は未検証でよい——ここで`validate_episode_page`を通す。
    """
    validate_episode_page(data)

    content = render_episode_frontmatter(data) + "\n" + body.strip() + "\n"

    current_path = content_dir / f"{data.episode_id}.md"
    version_path = content_dir / data.episode_id / "versions" / f"{data.revision}.md"

    if version_path.is_file():
        existing = version_path.read_text(encoding="utf-8")
        if existing != content:
            raise EpisodePublishConflictError(
                f"revision {data.revision} は既に異なる内容で公開済み: {version_path}"
                "（公開済みの版は書き換えられない）"
            )
        return PublishResult(
            current_path=current_path, version_path=version_path, is_new_revision=False
        )

    if current_path.is_file():
        previous_revision = _read_frontmatter_revision(current_path)
        if data.revision <= previous_revision:
            raise EpisodePublishConflictError(
                f"revisionは既存の現行版（{previous_revision}）より大きくなければならない"
                f"（指定: {data.revision}）"
            )

    version_path.parent.mkdir(parents=True, exist_ok=True)
    version_path.write_text(content, encoding="utf-8")
    current_path.write_text(content, encoding="utf-8")
    return PublishResult(current_path=current_path, version_path=version_path, is_new_revision=True)
