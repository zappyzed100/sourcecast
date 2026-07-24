# youtube_test_upload.py — YouTube Data API経由で動画を1本アップロードする動作確認用CLI
"""
使い方:
  uv run --with google-auth-oauthlib --with google-api-python-client \
    python scripts/youtube_test_upload.py <動画ファイルパス> --title "タイトル" [--privacy unlisted]

.envのGOOGLE_OAUTH_CLIENT_ID/SECRET/GOOGLE_OAUTH_REFRESH_TOKENを使ってリフレッシュ
トークンからアクセストークンを取得し、videos.insertで1本アップロードする。Google
OAuth本番審査のデモ動画撮影（scope実使用の証跡）、および実装前の疎通確認を兼ねる
使い捨てツール——本番の自動投稿パイプライン本体ではない。

既定の公開設定はunlisted（限定公開）。誤って一般公開しないための安全策。
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
TOKEN_URI = "https://oauth2.googleapis.com/token"


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


def build_credentials(env: dict[str, str]) -> Credentials:
    required = [
        "GOOGLE_OAUTH_CLIENT_ID",
        "GOOGLE_OAUTH_CLIENT_SECRET",
        "GOOGLE_OAUTH_REFRESH_TOKEN",
    ]
    missing = [key for key in required if not env.get(key, "").strip()]
    if missing:
        print(f"エラー: .envに{', '.join(missing)}が無い", file=sys.stderr)
        sys.exit(1)

    credentials = Credentials(
        token=None,
        refresh_token=env["GOOGLE_OAUTH_REFRESH_TOKEN"],
        token_uri=TOKEN_URI,
        client_id=env["GOOGLE_OAUTH_CLIENT_ID"],
        client_secret=env["GOOGLE_OAUTH_CLIENT_SECRET"],
        scopes=SCOPES,
    )
    credentials.refresh(Request())
    return credentials


def main() -> None:
    parser = argparse.ArgumentParser(description="YouTube動画アップロード動作確認")
    parser.add_argument("video_path", type=Path, help="アップロードする動画ファイル")
    parser.add_argument("--title", required=True, help="動画タイトル")
    parser.add_argument("--description", default="", help="動画の説明")
    parser.add_argument(
        "--privacy",
        choices=["private", "unlisted", "public"],
        default="unlisted",
        help="公開設定（既定: unlisted）",
    )
    args = parser.parse_args()

    if not args.video_path.is_file():
        print(f"エラー: 動画ファイルが無い: {args.video_path}", file=sys.stderr)
        sys.exit(1)

    repo_root = Path(__file__).resolve().parents[1]
    env = {**load_env(repo_root / ".env"), **os.environ}

    credentials = build_credentials(env)
    youtube = build("youtube", "v3", credentials=credentials)

    body = {
        "snippet": {"title": args.title, "description": args.description},
        "status": {"privacyStatus": args.privacy},
    }
    media = MediaFileUpload(str(args.video_path), chunksize=-1, resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    print(f"アップロード開始: {args.video_path.name} (privacy={args.privacy})")
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"  進捗: {int(status.progress() * 100)}%")

    video_id = response["id"]
    print()
    print("アップロード完了:")
    print(f"  https://www.youtube.com/watch?v={video_id}")


if __name__ == "__main__":
    main()
