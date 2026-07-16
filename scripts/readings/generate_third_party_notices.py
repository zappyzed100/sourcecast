# generate_third_party_notices.py — sources.yaml から THIRD_PARTY_NOTICES.md を再生成する
"""使い方: uv run scripts/readings/generate_third_party_notices.py

config/readings/sources.yaml を正本として THIRD_PARTY_NOTICES.md を書き直す。
ドリフト（yamlだけ変えて再生成し忘れ）は tests/readings/test_notices.py が検出する。
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "services" / "pipeline" / "src"))

from history_radio.readings.notices import build_notices  # noqa: E402
from history_radio.readings.sources_config import load_reading_sources  # noqa: E402


def main() -> int:
    sources = load_reading_sources(REPO_ROOT / "config" / "readings" / "sources.yaml")
    target = REPO_ROOT / "THIRD_PARTY_NOTICES.md"
    target.write_text(build_notices(sources), encoding="utf-8", newline="\n")
    print(f"generated: {target} ({len(sources)} sources)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
