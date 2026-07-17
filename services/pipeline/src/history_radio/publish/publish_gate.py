"""publish_gate.py — 自動検査ゲート（仕様書§11・development-plan.md Phase 10タスク1）。

既存の各検査関数（rights・claim台帳・media・配信メタデータ）と、本Phaseで追加した
転載検知・禁止語検査を1つのAND評価へ束ねる。**ここでは検査ロジックを再実装しない**
——各`validate_*`/`build_*`関数を呼び出し、例外を`GateCheckResult`へ変換するだけ
（決定と実行の分離を保ったまま、既存の検査を1箇所から呼べるようにする）。

publish_readyはAND評価: 1項目でも失敗すれば全体が`publish_ready=false`になる
（development-plan.md Phase 10タスク1 DoD）。

**スコープの明示**（仕様書§11の全17項目のうち、本ゲートが構造的に検査するのは以下）:
- rights_and_episode_schema: 出典ライセンス許可・episode_id形式・audio/RSS前提の整合性
  （episode_page.validate_episode_page）
- script_and_claims: 7段構成・claim_id紐付け・独立系統2件未満の主張の不使用・
  台本の禁止表現（script.validator.validate_script）
- reproduction_similarity: 転載検知（本Phaseで追加のreproduction_detector）
- forbidden_words: 台本本文の危険語検査（news_filter.DEFAULT_FORBIDDEN_WORDSを流用）
- media_manifest: 画像等のクレジット・出典URL・ライセンスID欠落
  （media_manifest.validate_media_manifest）
- audio: 無音・音量範囲・破損の検査結果（呼び出し側が`ffmpeg_audio.validate_audio`を
  実ファイルに対して事前実行した結果を渡す——このゲート関数自体はI/Oを行わない
  「決定」関数のままにするため、実行結果を受け取るだけにしてある）
- rss_and_url_consistency: RSS配信に必要なaudio_url/audio_length_bytesの存在と、
  YouTube/Podcast/Amazon Music向けメタデータが同じepisode_idを持つこと
  （distribution_metadata.build_all_distribution_metadata）

以下は仕様書§11に列挙されているが、本ゲートでは検査しない（対応する実装が
まだ無いか、実クレデンシャル・実生成物が必要なため——development-plan.md
Phase 10タスク1の実装メモに記載）: OpenRouterモデルレジストリとの整合性、
前回動画との類似度、条件付き素材の§5A判定ログ添付、規約再確認期限。
"""

from __future__ import annotations

from typing import Literal

from history_radio.domain.base import SchemaModel
from history_radio.domain.models import Claim
from history_radio.media.media_manifest import MediaAsset, MediaAssetError, validate_media_manifest
from history_radio.publish.distribution_metadata import (
    DistributionMetadataError,
    build_all_distribution_metadata,
)
from history_radio.publish.episode_page import (
    EpisodePageData,
    EpisodePageError,
    validate_episode_page,
)
from history_radio.script.reproduction_detector import detect_reproduction
from history_radio.script.schema import Script
from history_radio.script.validator import ScriptValidationError, validate_script
from history_radio.select.news_filter import DEFAULT_FORBIDDEN_WORDS

RULE_VERSION = "2026-07-19.1"

GateCheckName = Literal[
    "rights_and_episode_schema",
    "script_and_claims",
    "reproduction_similarity",
    "forbidden_words",
    "media_manifest",
    "audio",
    "rss_and_url_consistency",
]


class GateCheckResult(SchemaModel):
    name: GateCheckName
    passed: bool
    reasons: tuple[str, ...] = ()


class PublishGateResult(SchemaModel):
    schema_version: Literal[1] = 1
    episode_id: str
    rule_version: str
    publish_ready: bool
    checks: tuple[GateCheckResult, ...]


def _reasons_from_exception(exc: Exception) -> tuple[str, ...]:
    problems = getattr(exc, "problems", None)
    if problems:
        return tuple(str(p) for p in problems)
    return (str(exc),)


def _check_rights_and_episode_schema(episode: EpisodePageData) -> GateCheckResult:
    try:
        validate_episode_page(episode)
    except EpisodePageError as exc:
        return GateCheckResult(
            name="rights_and_episode_schema", passed=False, reasons=_reasons_from_exception(exc)
        )
    return GateCheckResult(name="rights_and_episode_schema", passed=True)


def _check_script_and_claims(script: Script, claim_ledger: list[Claim]) -> GateCheckResult:
    try:
        validate_script(script, claim_ledger)
    except ScriptValidationError as exc:
        return GateCheckResult(
            name="script_and_claims", passed=False, reasons=_reasons_from_exception(exc)
        )
    return GateCheckResult(name="script_and_claims", passed=True)


def _check_reproduction_similarity(script: Script, source_texts: dict[int, str]) -> GateCheckResult:
    spans = detect_reproduction(script, source_texts)
    if not spans:
        return GateCheckResult(name="reproduction_similarity", passed=True)
    reasons = tuple(
        f"出典index={span.source_index}との{span.match_kind}一致"
        f"（長さ{span.match_length}）: {span.matched_text[:40]!r}"
        for span in spans
    )
    return GateCheckResult(name="reproduction_similarity", passed=False, reasons=reasons)


def _check_forbidden_words(
    script: Script, forbidden_words: frozenset[str] = DEFAULT_FORBIDDEN_WORDS
) -> GateCheckResult:
    reasons: list[str] = []
    for section in script.sections:
        for sentence in section.sentences:
            hits = sorted(w for w in forbidden_words if w in sentence.text)
            if hits:
                reasons.append(f"{sentence.text[:30]!r}: 禁止語を含む {hits}")
    if reasons:
        return GateCheckResult(name="forbidden_words", passed=False, reasons=tuple(reasons))
    return GateCheckResult(name="forbidden_words", passed=True)


def _check_media_manifest(media_assets: list[MediaAsset]) -> GateCheckResult:
    try:
        validate_media_manifest(media_assets)
    except MediaAssetError as exc:
        return GateCheckResult(
            name="media_manifest", passed=False, reasons=_reasons_from_exception(exc)
        )
    return GateCheckResult(name="media_manifest", passed=True)


def _check_rss_and_url_consistency(
    episode: EpisodePageData, *, site_base_url: str
) -> GateCheckResult:
    try:
        build_all_distribution_metadata(episode, site_base_url=site_base_url)
    except DistributionMetadataError as exc:
        return GateCheckResult(
            name="rss_and_url_consistency", passed=False, reasons=_reasons_from_exception(exc)
        )
    return GateCheckResult(name="rss_and_url_consistency", passed=True)


def evaluate_publish_gate(
    *,
    episode: EpisodePageData,
    script: Script,
    claim_ledger: list[Claim],
    media_assets: list[MediaAsset],
    source_texts: dict[int, str],
    site_base_url: str,
    audio_validation_passed: bool,
    audio_validation_problems: tuple[str, ...] = (),
) -> PublishGateResult:
    """全項目をAND評価する。1項目でも失敗すれば`publish_ready=False`になる。"""
    checks = (
        _check_rights_and_episode_schema(episode),
        _check_script_and_claims(script, claim_ledger),
        _check_reproduction_similarity(script, source_texts),
        _check_forbidden_words(script),
        _check_media_manifest(media_assets),
        GateCheckResult(
            name="audio", passed=audio_validation_passed, reasons=audio_validation_problems
        ),
        _check_rss_and_url_consistency(episode, site_base_url=site_base_url),
    )
    return PublishGateResult(
        episode_id=episode.episode_id,
        rule_version=RULE_VERSION,
        publish_ready=all(c.passed for c in checks),
        checks=checks,
    )
