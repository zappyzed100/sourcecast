"""generate_contracts.py — Pydanticドメインモデルからバージョン付きJSON Schemaを生成する。

正本はPython側の history_radio.domain の型。生成物は packages/contracts/schema/ へ
コミットし、TypeScript型はそこから json-schema-to-typescript で生成する（手書きで
二重管理しない — plan.md §2.3）。CIは本スクリプトを再実行して差分0であることを検査する
（scripts/check_contracts_drift.py）。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import repo_scan as rs  # noqa: E402

sys.path.insert(0, str(rs.repo_root() / "services" / "pipeline" / "src"))

from history_radio.domain import (  # noqa: E402
    AuditEvent,
    Candidate,
    Claim,
    Episode,
    Job,
    RightsDecision,
    SourceRecord,
)

MODELS = [
    SourceRecord,
    RightsDecision,
    Candidate,
    Claim,
    Episode,
    Job,
    AuditEvent,
]


def main() -> int:
    root = rs.repo_root()
    schema_dir = root / "packages" / "contracts" / "schema"
    schema_dir.mkdir(parents=True, exist_ok=True)

    for model in MODELS:
        schema = model.model_json_schema()
        schema = {"$schema": "http://json-schema.org/draft-07/schema#", **schema}
        out_path = schema_dir / f"{model.__name__}.schema.json"
        text = json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        out_path.write_text(text, encoding="utf-8", newline="\n")
        print(f"[generate-contracts] {out_path.relative_to(root)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
