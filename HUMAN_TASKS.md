<!-- HUMAN_TASKS.md — 実装を進める上でユーザー本人の判断・操作が必要な作業の一覧 -->
# HUMAN_TASKS.md — 人間側の作業手順

このリポジトリの実装（コード・テスト・plan更新）はエージェントが進められるが、
以下は **人間本人のアカウント・鍵・リポジトリ設定の操作** が必要で、エージェントが
代行すべきではない（資格情報の取り扱い・外部サービス契約・GitHub設定変更にあたるため）。
2026-07-16時点、Phase 0〜3実装済み・Phase 4「収集」着手前の整理。

## 今すぐ（ブロッキング — Step 3・Step 9④が未完了）

現状 `.git/hooks/pre-commit` が存在せず、`uv run scripts/dev.py check` の
`SOFT:hooks-not-installed` 警告が出続けている。これは「まだ誰もこのマシンで
`pre-commit install` していない」ことを機械的に示している——コミット時の秘密検出・
構造検査・push時のlint/testが**このマシン上では**まだ強制されていない
（CIが最終防衛線として同じ検査を再実行するので致命的ではないが、手戻りが遅く気づく）。

1. **pre-commitシムを導入する**（`.guardrails/GUARDRAILS.md` Step 3）
   ```bash
   uv tool install pre-commit
   pre-commit install
   ```
   確認: `uv run scripts/dev.py check` から `SOFT:hooks-not-installed` が消える。

2. **GitHubリポジトリのブランチ保護（ruleset）に3つの必須チェックを登録する**
   （`.guardrails/GUARDRAILS.md` Step 9④。CIワークフロー自体は導入済みだが、
   「PRをブロックする必須チェック」としての登録はGitHub側のリポジトリ設定でしか
   できず、`gh api repos/zappyzed100/sourcecast/rulesets` で確認した限り現状 `[]`
   ＝未登録）。
   - GitHub の Settings → Rules → Rulesets（またはBranches→Branch protection rules）で
     `main` を対象に以下3ジョブを必須ステータスチェックとして登録する:
     - `checks`
     - `red-first`
     - `commit-msg-history`
   - rulesets側での登録を推奨（`.guardrails/GUARDRAILS.md` Step 9の注記: CIの
     `GITHUB_TOKEN` で照会できるのはrulesetsのみのため、`check-bootstrap`が
     `gh api`で自動検証できるのはrulesets登録のみ）。
   - 登録手順の参考: [GitHub Docs — Managing rulesets](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets)

これら2点が終わると `.guardrails/BOOTSTRAP.md` のStep 3・Step 9の実測条件が揃う
（Stepを`✅`化するコミット自体は実装側でやるので、人間側はここまでで良い）。

## Phase 4〜5（収集・題材選出）は追加の外部アカウント不要

Wikipedia・Wikimedia Commons・Wikidata・NDLデジタルコレクション・NDL次世代
デジタルライブラリー・ColBase・e-Gov法令検索などはAPIキー不要の公開APIのみで、
現状のfixture/mock方針のまま進められる。**このフェーズだけを見るなら、上の2点を
終えれば人間側の作業は無い。**

## Phase 6（LLM処理）までに準備するもの

- **OpenRouterアカウント作成**（`docs/plans/development-plan.md` §1・§4 Phase 6）。
  - 無料モデルのみ使用する方針（`config/model_registry.yaml`に登録する各モデルの
    `price_prompt`/`price_completion`が0であることを起動時に検証——`config_loader.py`
    の`load_model_registry`が有料エントリを拒否する)。**API利用規約・データポリシー
    （学習利用の有無等）を確認**した上でAPIキーを発行する。
  - APIキーはGit・SQLite・ログに保存しない方針（development-plan.md §2・仕様書）。
    実装側で環境変数経由の読み込みに対応するので、キー自体はローカルの安全な場所
    （OS環境変数・パスワードマネージャ等）に控えておく。

## Phase 7（音声・スライド動画）までに準備するもの

- **VOICEVOXエンジンのローカル導入**（ずんだもん等、使用するキャラクターのクレジット
  表記条件を確認 — development-plan.md §4 Phase 7）。VOICEVOX本体はPython依存に
  混ぜず外部実行ファイルとして扱う方針のため、導入時にバージョン・取得元URL・
  SHA-256を控えておく（実装側でこの記録をどこに残すか——configかREADMEか——は
  Phase 7着手時に相談する）。
- **FFmpegのローカル導入**（同上、バージョン・取得元・SHA-256を控える）。
- 読み辞書（development-plan.md §8）で使う **JMnedict・NDL「ヨミガナ辞書」PDF等の
  再頒布条件**は既に調査済み（§8.1）。追加のアカウント登録は不要だが、
  「国語研 歴史UniDic」だけは営利目的利用に事前相談が必要——**許可を得るまで
  使わない**方針なので、相談したい場合は早めに動くとよい。

## Phase 8（公開ページ統合・Cloudflare）までに決めること

- **独自ドメイン名の確定とCloudflareアカウント**。
- **Cloudflare R2バケット名・公開URLの方針**（例: 音声・画像を`/media/`配下で
  独自ドメイン配信するか、R2の既定公開URLを使うか）。
- CI/CDからCloudflare Pages・R2へデプロイする段になったら、Cloudflare API
  トークン・アカウントIDをGitHub Actionsのrepository secretsとして登録する
  （このタイミングでよく、今は不要）。

## Phase 9（RSS・配信先）までに決めること

- **YouTube・Podcast配信先（RSSホスティング）・Amazon Music/Audibleのアカウント**。
  審査や登録に時間がかかるものがあれば早めに申請しておくと待ち時間を短縮できる。

## Phase 12（バックアップ・障害対応）までに決めること

- **Google DriveまたはNASのバックアップ保存先**（development-plan.md §7・運用節）。

## 継続して守ってほしいこと

- OpenRouter・R2・Google Driveなどの資格情報は、発行後も**Git・SQLite・ログへ
  絶対に保存しない**（development-plan.md §2・§7ログ規則）。実装側が環境変数や
  シークレットマネージャ経由の読み込みを用意するので、それ以外の経路（設定ファイル
  への直書き等）で渡さないでほしい。
- 上記以外の判断（技術選定・アーキテクチャ・ドメインルールの解釈）は
  plan.md／development-plan.md／仕様書に基づいて実装側で進められるので、
  ここに列挙した「アカウント・鍵・GitHubリポジトリ設定」だけが人間側の作業。
