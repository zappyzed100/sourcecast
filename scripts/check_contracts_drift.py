"""check_contracts_drift.py — 契約生成物の鮮度検査（plan.md §2.3「Schemaを再生成して差分0」）。

Pydanticモデル→JSON Schema→TypeScript型の生成を再実行し、コミット済みの生成物との
差分が0であることを確認する。差分があれば「正本（domain/models.py）を変えたのに
生成物を再生成し忘れた」ことを意味する——exit 1 でCIを落とす。
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import repo_scan as rs  # noqa: E402

TRACKED_PATHS = (
    "packages/contracts/schema",
    "packages/contracts/src/generated",
    "packages/contracts/src/index.ts",
)


def _resolved(argv: list[str]) -> list[str]:
    """PATH上のコマンド名をフルパスへ解決する（Windows: shell=Falseだと.cmd/.batの
    直呼びが失敗するため、dev.pyと同じくshutil.whichで実パスを渡す — §7.2）。"""
    exe = shutil.which(argv[0])
    if exe is None:
        raise FileNotFoundError(f"コマンドが見つからない: {argv[0]!r}")
    return [exe, *argv[1:]]


def main() -> int:
    rs.reconfigure_stdio()
    root = rs.repo_root()

    gen_py = subprocess.run(
        _resolved(["uv", "run", "python", "scripts/generate_contracts.py"]), cwd=root
    )
    if gen_py.returncode != 0:
        print("[check-contracts-drift] generate_contracts.py が失敗", file=sys.stderr)
        return gen_py.returncode

    gen_ts = subprocess.run(
        _resolved(["pnpm", "--filter", "@history-radio/contracts", "run", "generate"]), cwd=root
    )
    if gen_ts.returncode != 0:
        print("[check-contracts-drift] generate-types.ts が失敗", file=sys.stderr)
        return gen_ts.returncode

    diff = subprocess.run(
        ["git", "diff", "--exit-code", "--stat", "--", *TRACKED_PATHS],
        cwd=root,
        capture_output=True,
        text=True,
    )
    if diff.returncode != 0:
        print(
            "[check-contracts-drift] 生成物に差分あり——domain/models.py 変更後に "
            "`uv run python scripts/generate_contracts.py && "
            "pnpm --filter @history-radio/contracts run generate` を実行してコミットする:",
            file=sys.stderr,
        )
        print(diff.stdout, file=sys.stderr)
        return 1

    print("[check-contracts-drift] 生成物は最新（差分0）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
