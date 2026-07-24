# youtube_oauth_setup.py — YouTube Data APIのOAuth認可を1回だけ実行しリフレッシュトークンを取得する
"""
使い方:
  uv run --with google-auth-oauthlib --with google-auth-httplib2 --with google-api-python-client \
    python scripts/youtube_oauth_setup.py

.envのGOOGLE_OAUTH_CLIENT_ID / GOOGLE_OAUTH_CLIENT_SECRETを読み込み、ブラウザでの
認可フロー(ローカルサーバー方式)を実行する。取得したリフレッシュトークンは
標準出力に表示するのみで、.envへの書き込みは行わない——人間が確認した上で
自分で追記する（development-plan.md §2・§7ログ規則: 秘密情報を勝手にファイルへ
書き込まない）。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]


def load_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        env[key.strip()] = value.strip()
    return env


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    env = {**load_env(repo_root / ".env"), **os.environ}

    client_id = env.get("GOOGLE_OAUTH_CLIENT_ID", "").strip()
    client_secret = env.get("GOOGLE_OAUTH_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        print(
            "エラー: .envにGOOGLE_OAUTH_CLIENT_ID / GOOGLE_OAUTH_CLIENT_SECRETが無い",
            file=sys.stderr,
        )
        sys.exit(1)

    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }

    flow = InstalledAppFlow.from_client_config(client_config, scopes=SCOPES)
    print(
        "ブラウザが開きます。YouTubeチャンネル「いつわわ」を所有するアカウントで認可してください。"
    )
    credentials = flow.run_local_server(port=0)

    print()
    print("認可が完了しました。次の行を.envへ追記してください:")
    print()
    print(f"GOOGLE_OAUTH_REFRESH_TOKEN={credentials.refresh_token}")
    print()


if __name__ == "__main__":
    main()
