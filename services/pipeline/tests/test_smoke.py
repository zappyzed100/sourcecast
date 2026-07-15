"""test_smoke.py — Phase 0 DoD: パッケージが import できることを確認する"""

import history_radio


def test_package_imports() -> None:
    assert history_radio is not None
