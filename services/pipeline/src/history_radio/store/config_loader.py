"""config_loader.py — config/*.yaml の読み込みと起動時検証（仕様書§5.14・§8.1）。

単一エントリの形は config_schemas.py（Pydantic）が検査する。ここではそれに加えて、
複数エントリを跨ぐ整合性——重複ID・期限切れ——を検査する。いずれも起動時に例外で
拒否する（fail closed。仕様書§2「公開処理は失敗時閉鎖とし…」と同じ方針をconfig読込にも適用）。
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import yaml
from pydantic import ValidationError

from history_radio.store.config_schemas import (
    LicenseRule,
    LicenseRulesFile,
    ModelRegistryEntry,
    ModelRegistryFile,
    SourceRegistryEntry,
    SourceRegistryFile,
)


class ConfigValidationError(ValueError):
    """config/*.yaml の検証失敗（未知キー・重複ID・不正URL・期限切れ等）。"""


def _read_yaml(path: Path) -> object:
    try:
        with path.open(encoding="utf-8") as f:
            return yaml.safe_load(f)
    except yaml.YAMLError as exc:
        raise ConfigValidationError(f"{path}: YAML構文エラー: {exc}") from exc
    except OSError as exc:
        raise ConfigValidationError(f"{path}: 読み込み失敗: {exc}") from exc


def _check_duplicates(ids: list[str], *, path: Path, field_name: str) -> None:
    seen: set[str] = set()
    dupes: set[str] = set()
    for i in ids:
        if i in seen:
            dupes.add(i)
        seen.add(i)
    if dupes:
        raise ConfigValidationError(
            f"{path}: 重複した {field_name}: {sorted(dupes)}（1エントリ1IDにする）"
        )


def load_source_registry(path: Path) -> list[SourceRegistryEntry]:
    raw = _read_yaml(path)
    try:
        parsed = SourceRegistryFile.model_validate(raw)
    except ValidationError as exc:
        raise ConfigValidationError(f"{path}: {exc}") from exc
    _check_duplicates([s.source_id for s in parsed.sources], path=path, field_name="source_id")
    return parsed.sources


def load_license_rules(path: Path) -> list[LicenseRule]:
    raw = _read_yaml(path)
    try:
        parsed = LicenseRulesFile.model_validate(raw)
    except ValidationError as exc:
        raise ConfigValidationError(f"{path}: {exc}") from exc
    _check_duplicates(
        [lic.license_id for lic in parsed.licenses], path=path, field_name="license_id"
    )
    return parsed.licenses


def load_model_registry(path: Path, *, today: date | None = None) -> list[ModelRegistryEntry]:
    """モデルレジストリを読み込む。期限切れ・有料エントリは起動時に拒否する。

    仕様書§8.1「毎日モデルAPIを確認」「pricing.prompt == 0」の前提を、
    config読込時点で担保する。
    """
    effective_today = today or date.today()
    raw = _read_yaml(path)
    try:
        parsed = ModelRegistryFile.model_validate(raw)
    except ValidationError as exc:
        raise ConfigValidationError(f"{path}: {exc}") from exc
    _check_duplicates([m.model_id for m in parsed.models], path=path, field_name="model_id")

    expired = [m.model_id for m in parsed.models if m.expires_at < effective_today]
    if expired:
        raise ConfigValidationError(
            f"{path}: 期限切れモデル: {expired}（expires_atを更新するか一覧から外す — §8.1）"
        )
    paid = [m.model_id for m in parsed.models if m.price_prompt != 0 or m.price_completion != 0]
    if paid:
        raise ConfigValidationError(
            f"{path}: 無料枠外のモデル: {paid}"
            "（本番は無料モデル限定 — §2「LLMはOpenRouterの無料モデルを使用する」）"
        )
    return parsed.models
