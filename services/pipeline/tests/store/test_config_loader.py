"""test_config_loader.py — Phase 1 DoD: 未知キー・重複ID・不正URL・期限切れ設定の拒否を固定する"""

from datetime import date
from pathlib import Path

import pytest

from history_radio.store.config_loader import (
    ConfigValidationError,
    load_license_rules,
    load_model_registry,
    load_source_registry,
)

REPO_ROOT = Path(__file__).resolve().parents[4]
CONFIG_DIR = REPO_ROOT / "config"

VALID_SOURCE_ENTRY = """
source_id: wikimedia_commons
status: approved
use_class: A
normalized_license_id: cc0
commercial_use: conditional
modification: conditional
redistribution: conditional
attribution: required_if_not_cc0
share_alike: preserve_per_asset
third_party_exception: deny
territory: global
terms_url: "https://commons.wikimedia.org/wiki/Commons:Reusing_content_outside_Wikimedia"
terms_checked_at: 2026-07-16
recheck_days: 90
"""


def test_real_source_registry_loads() -> None:
    sources = load_source_registry(CONFIG_DIR / "source_registry.yaml")
    assert len(sources) >= 4
    assert all(s.status == "approved" for s in sources)


def test_real_license_rules_loads() -> None:
    licenses = load_license_rules(CONFIG_DIR / "license_rules.yaml")
    ids = {lic.license_id for lic in licenses}
    assert {"cc0", "cc-by-sa", "gov-jp-2.0"} <= ids


def test_real_model_registry_loads() -> None:
    models = load_model_registry(CONFIG_DIR / "model_registry.yaml", today=date(2026, 7, 16))
    assert len(models) >= 1
    assert all(m.price_prompt == 0 and m.price_completion == 0 for m in models)


def test_unknown_key_rejected(tmp_path: Path) -> None:
    path = tmp_path / "source_registry.yaml"
    path.write_text(
        "sources:\n  - "
        + VALID_SOURCE_ENTRY.strip().replace("\n", "\n    ")
        + "\n    unexpected_field: oops\n"
    )
    with pytest.raises(ConfigValidationError):
        load_source_registry(path)


def test_duplicate_source_id_rejected(tmp_path: Path) -> None:
    entry = "  - " + VALID_SOURCE_ENTRY.strip().replace("\n", "\n    ")
    path = tmp_path / "source_registry.yaml"
    path.write_text(f"sources:\n{entry}\n{entry}\n")
    with pytest.raises(ConfigValidationError, match="重複"):
        load_source_registry(path)


def test_invalid_url_rejected(tmp_path: Path) -> None:
    broken = VALID_SOURCE_ENTRY.replace(
        'terms_url: "https://commons.wikimedia.org/wiki/Commons:Reusing_content_outside_Wikimedia"',
        'terms_url: "not-a-url"',
    )
    path = tmp_path / "source_registry.yaml"
    path.write_text("sources:\n  - " + broken.strip().replace("\n", "\n    ") + "\n")
    with pytest.raises(ConfigValidationError):
        load_source_registry(path)


def test_expired_model_rejected(tmp_path: Path) -> None:
    path = tmp_path / "model_registry.yaml"
    path.write_text(
        """
models:
  - model_id: "some/expired-model:free"
    provider: openrouter
    endpoint: "https://openrouter.ai/api/v1/chat/completions"
    price_prompt: 0
    price_completion: 0
    context_length: 8000
    expires_at: 2020-01-01
    data_policy: "no_training_no_retention"
    supports_structured_output: true
    japanese_regression_passed: true
"""
    )
    with pytest.raises(ConfigValidationError, match="期限切れ"):
        load_model_registry(path, today=date(2026, 7, 16))


def test_paid_model_rejected(tmp_path: Path) -> None:
    path = tmp_path / "model_registry.yaml"
    path.write_text(
        """
models:
  - model_id: "some/paid-model"
    provider: openrouter
    endpoint: "https://openrouter.ai/api/v1/chat/completions"
    price_prompt: 0.001
    price_completion: 0.002
    context_length: 8000
    expires_at: 2099-01-01
    data_policy: "no_training_no_retention"
    supports_structured_output: true
    japanese_regression_passed: true
"""
    )
    with pytest.raises(ConfigValidationError, match="無料枠外"):
        load_model_registry(path, today=date(2026, 7, 16))


def _model_yaml(**overrides: object) -> str:
    """Phase 6検査（ルーター・構造化出力・日本語回帰）用の1エントリYAML。"""
    values: dict[str, object] = {
        "model_id": "vendor/fixed-model:free",
        "supports_structured_output": "true",
        "japanese_regression_passed": "true",
    }
    values.update(overrides)
    return f"""
models:
  - model_id: "{values["model_id"]}"
    provider: openrouter
    endpoint: "https://openrouter.ai/api/v1/chat/completions"
    price_prompt: 0
    price_completion: 0
    context_length: 8000
    expires_at: 2099-01-01
    data_policy: "no_training_no_retention"
    supports_structured_output: {values["supports_structured_output"]}
    japanese_regression_passed: {values["japanese_regression_passed"]}
"""


@pytest.mark.parametrize("router_id", ["openrouter/free", "openrouter/auto", "some-vendor/auto"])
def test_random_router_models_are_rejected(tmp_path: Path, router_id: str) -> None:
    """§8.1: 実モデルがランダムに変わるルーターは本番で使用しない。"""
    path = tmp_path / "model_registry.yaml"
    path.write_text(_model_yaml(model_id=router_id))
    with pytest.raises(ConfigValidationError, match="ランダムルーター"):
        load_model_registry(path, today=date(2026, 7, 16))


def test_model_without_structured_output_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "model_registry.yaml"
    path.write_text(_model_yaml(supports_structured_output="false"))
    with pytest.raises(ConfigValidationError, match="構造化出力"):
        load_model_registry(path, today=date(2026, 7, 16))


def test_regression_failed_model_is_rejected(tmp_path: Path) -> None:
    """§8.1: 日本語回帰テストに合格するまで自動公開に使用しない。"""
    path = tmp_path / "model_registry.yaml"
    path.write_text(_model_yaml(japanese_regression_passed="false"))
    with pytest.raises(ConfigValidationError, match="日本語回帰"):
        load_model_registry(path, today=date(2026, 7, 16))
