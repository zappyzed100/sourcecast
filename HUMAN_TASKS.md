<!-- HUMAN_TASKS.md — 実装を進める上でユーザー本人の判断・操作が必要な作業の一覧 -->
# HUMAN_TASKS.md — 人間側の作業手順

このリポジトリの実装（コード・テスト・plan更新）はエージェントが進められるが、
以下は **人間本人のアカウント・鍵・リポジトリ設定の操作** が必要で、エージェントが
代行すべきではない（資格情報の取り扱い・外部サービス契約・GitHub設定変更にあたるため）。
2026-07-16時点、Phase 0〜3実装済み・Phase 4「収集」着手前の整理。各項目はできる限り
クリック単位まで具体化してある——迷ったらこのファイルの手順どおりに進めれば良い。

## 状況更新（この整理の過程で分かったこと）

- **pre-commitのローカル導入（旧Step 3）はこのマシンで完了済み**。当初
  `.git/hooks/pre-commit` が存在せず`SOFT:hooks-not-installed`警告が出ていたが、
  作業の過程で `uv tool install pre-commit` 相当のインストールと
  `pre-commit install` が実行され、`.git/hooks/pre-commit`・`commit-msg`・
  `pre-push` の3本が実在し、直近のコミット・pushで実際に発火することを確認した
  （`trim trailing whitespace`等のフック出力がコミット時に表示され、
  `SOFT:hooks-not-installed`警告も消えた）。**このマシンでは何もする必要が無い。**
  もし将来これを**別のマシン**（別PC、CI以外の環境）でクローンして作業する場合は、
  そちらで改めて次を実行する:
  ```bash
  uv tool install pre-commit
  pre-commit install
  ```
  確認方法: `uv run scripts/dev.py check` の出力に`SOFT:hooks-not-installed`が
  含まれないこと。
- **CIが全pushで赤くなり続けていた原因を特定・修正済み**（`checks`ジョブ =
  `pre-commit run --all-files`）。原因は、ベンダーコピーの`.claude/skills/`配下の
  ファイル（CSV・JSON・Python）に末尾空白・ファイル末尾改行なしがあり、
  `trailing-whitespace`/`end-of-file-fixer`フックがそれを「直そうとして」
  exit 1していたこと。ベンダーコピーは手で編集しない方針（AGENTS.md §6）のため、
  該当2フックから`.claude/skills/`を除外し、ついでに実ファイル側の不備
  （`apps/admin/public/favicon.svg`・`migrations/README`の末尾改行なし）も直した
  （コミット`52993a4`）。**この修正後、実際にGitHub Actions上で`checks`ジョブが
  緑になることを確認済み**（run 29455705044）。
- **既知の未解決問題（今回は対応していない・優先度低）**: `e2e`ジョブの
  `e2e/audio-player.spec.ts`（10秒送り・戻し操作後に再生状態表示が「再生中」に
  ならない）が、GitHub Actions上でのみ3回中3回失敗する（ローカルでの
  `pnpm exec playwright test`実行では再現せず、CI環境（ヘッドレスChromiumの
  タイミング差）依存の疑い）。`e2e`は下記の必須チェック3つには含まれないため
  ブランチ保護の設定はブロックしないが、**そのうち直すか原因調査が必要**。
  実装側のタスクとして着手するタイミングであらためて相談する。

## 今すぐやること: GitHubブランチ保護（ruleset）に3つの必須チェックを登録する

`.guardrails/GUARDRAILS.md` Step 9④の要求（CIワークフロー自体は導入済みだが、
「PRをマージ不可にする必須チェック」としての登録はGitHub側のリポジトリ設定でしか
できない）。`gh api repos/zappyzed100/sourcecast/rulesets` で確認した限り現状 `[]`
（未登録）。このリポジトリは public（`gh api repos/.../--jq .private` → `false`）
なので、rulesets機能は無料プランでそのまま使える。

### これは「ブランチ」のrulesetか「タグ」のrulesetか

**ブランチのruleset**（*New branch ruleset*）を選ぶ。保護したいのは`main`という
**ブランチ**へのマージ条件であり、Gitタグ（リリースタグ等）の作成・削除を制御する
「タグruleset」ではない。GitHubの新規作成メニューには両方の選択肢が並んでいるので
間違えないこと——迷ったら「対象がブランチ名か、タグ名か」で判断する。

### 手順（クリック単位）

1. ブラウザで `https://github.com/zappyzed100/sourcecast/settings/rules` を開く
   （もしくは Settings タブ → 左サイドバーの **Code and automation** セクション内
   **Rules** → **Rulesets**）。
2. 右上の緑ボタン **New ruleset** をクリックすると、次の2択が出る:
   - **New branch ruleset** ← こちらを選ぶ
   - New tag ruleset（今回は使わない）
   - Import a ruleset（今回は使わない）
3. 開いた設定画面で上から順に埋める:
   - **Ruleset Name**: 分かりやすい名前を入力する（例: `main-required-checks`）。
   - **Enforcement status**: `Active` を選ぶ（`Disabled`や`Evaluate`のままだと
     実際には強制されない——`Evaluate`は「違反を記録だけして許可する」お試しモード
     なので、今回は最初から`Active`で良い）。
   - **Bypass list**: 何も追加せずそのままで良い（個人開発でバイパス経路を
     増やす理由が無い。リポジトリ管理者は設定変更自体でいつでも調整できる）。
   - **Target branches**（対象ブランチ）: **Add target** ボタン →
     **Include default branch** を選ぶ（現在のデフォルトブランチ`main`に
     自動追従する。ブランチ名を直接指定したい場合は**Add branch name pattern**で
     `main`と入力しても同じ結果になる）。
   - 下にスクロールし **Rules** セクションで **Require status checks to pass**
     のトグルをONにする。
     - トグルON後に現れる **Add checks** ボタン（または検索ボックス）をクリックし、
       検索欄に `checks` と入力 → 候補に出てきた `checks` を選んでリストに追加する。
     - 同様に検索欄で `red-first` と入力 → 追加する。
     - 同様に検索欄で `commit-msg-history` と入力 → 追加する。
     - 3つとも「Required checks」のリストに並んでいることを確認する
       （表示名の横に緑チェックの実行履歴が出ることもある——これは直近の
       CI実行結果が反映されているだけで、設定操作としては3つ追加されていれば良い）。
     - **Require branches to be up to date before merging** は任意
       （個人開発でPRを溜めない運用なら付けなくても実害は小さいが、
       付けておくと「古いブランチのままマージ」を防げる。お好みで）。
   - その他のルール（**Restrict deletions**＝mainブランチの削除禁止、
     **Block force pushes**＝force push禁止）は`.guardrails/GUARDRAILS.md`の
     必須要件ではないが、`main`を直接消されたり強制上書きされたりする事故を防ぐ
     一般的な安全策として有効化を推奨する（任意）。
4. 画面下部の緑ボタン **Create** をクリックして保存する。
5. 保存後、確認コマンド:
   ```bash
   gh api repos/zappyzed100/sourcecast/rulesets --jq '.[].name'
   ```
   作成したruleset名が1件表示されれば登録完了。

### 補足: 必須チェックに登録すると何が変わるか

- 今後`main`へ直接pushしてマージする流れ（このセッションでずっと行ってきた
  「コミット→直接push」）を続けると、rulesetの**Restrict deletions/force push**は
  効くが、**status checksの必須化はPRのマージにしか効かない**（GitHubの仕様——
  直接pushには「必須ステータスチェック」ルールは基本的に適用されない）。
  つまり、この登録の効果を実際に活かすには、AGENTS.md §10の方針どおり
  **「1トピック=1ブランチ=1PR」**でPR経由のマージに切り替える必要がある
  （現状は毎回`git push origin main`で直接反映してきたため、実質的には
  ここまでのワークフローとズレがある——今後PRベースに切り替えるかどうかは
  相談したい）。

## Phase 4〜5（収集・題材選出）は追加の外部アカウント不要

Wikipedia・Wikimedia Commons・Wikidata・NDLデジタルコレクション・NDL次世代
デジタルライブラリー・ColBase・e-Gov法令検索などはAPIキー不要の公開APIのみで、
現状のfixture/mock方針のまま進められる。**このフェーズだけを見るなら、上の
ruleset登録を終えれば人間側の作業は無い。**

## Phase 6（LLM処理）までに準備するもの

1. **OpenRouterアカウントを作成する**: `https://openrouter.ai/` にアクセスし、
   GitHubまたはGoogleアカウントでサインアップする。
2. **利用規約・データポリシーを確認する**: 特に「入力データがモデル学習に
   再利用されるか」を確認する無料モデルは学習利用ポリシーがモデルごとに異なる
   ため、`config/model_registry.yaml`へ登録する前に該当モデルのポリシーページで
   確認する（development-plan.md §1・§4 Phase 6の「無料モデルのみ使用」方針）。
3. **APIキーを発行する**: OpenRouterダッシュボードの **Keys** ページで新規キーを
   作成する。利用上限（credit limit）を明示的に0または低額に設定できる場合は
   設定しておくと、誤設定時の課金事故を防げる（無料モデルのみを使う方針だが、
   保険として）。
4. **キーの保管**: このリポジトリの方針として、APIキーは**Git・SQLite・ログへ
   絶対に保存しない**（development-plan.md §2・§7ログ規則）。実装側が
   環境変数経由の読み込みに対応する予定なので、それまではOSのパスワード
   マネージャ等、リポジトリの外で保管しておく。
5. `config/model_registry.yaml`へモデルを登録する作業自体（`price_prompt`/
   `price_completion`が0であることの検証は`config_loader.py`が起動時に行う）は
   実装側のタスク——キー発行とポリシー確認だけが人間側の作業。

## Phase 7（音声・スライド動画）までに準備するもの

1. **VOICEVOXエンジンをローカル導入する**: `https://voicevox.hiroshiba.jp/` から
   OS（Windows/macOS/Linux）に合ったエンジンをダウンロードする。GPU版/CPU版の
   選択肢があるので、使用するマシンのGPU有無に応じて選ぶ。
2. **使用する話者のクレジット表記条件を確認する**: 使う予定の話者（例:
   ずんだもん）のキャラクター利用規約ページで、クレジット表記の必須文言・
   禁止事項（政治的発言への使用禁止等）を確認し、控えておく（実装側が
   音声生成時にクレジットを自動付与する処理を作るための入力になる）。
3. **バージョン・取得元URL・SHA-256を控えておく**: ダウンロードしたインストーラー
   のファイルに対して次を実行し、結果を控える（記録先は実装側と相談——
   `config/`か`README`かはPhase 7着手時に決める）。
   ```bash
   # Windowsの場合(PowerShell)
   Get-FileHash .\VOICEVOX-Installer.exe -Algorithm SHA256
   ```
4. **FFmpegをローカル導入する**: `https://ffmpeg.org/download.html` から
   ビルド済みバイナリを取得する（Windowsは`gyan.dev`や`BtbN`のビルドが一般的）。
   同様にバージョン・取得元URL・SHA-256を控える。
5. 読み辞書（development-plan.md §8・§8.4）で使う外部データソースのうち、
   **アカウント登録が要るものは無い**（SudachiDict/JMnedict/Wikidata/Web NDL
   Authorities/デジタル庁アドレス・ベース・レジストリはいずれも登録不要の
   公開配布・公開API)。ただし2点だけ人間側のフォローが要る:
   - **国語研 歴史UniDicの営利利用許可**: 統合を保留中（§8.1）。営利目的での
     利用には事前相談が必要な旨が明記されているため、使いたくなった時点で
     国立国語研究所へ問い合わせる。許可が取れるまでは実装側でも統合しない。
   - **NDL「ヨミガナ辞書」(PDF)の扱い**: 辞書全体の再配布はしない方針
     （§8.1・§8.4）。手動修正辞書へ個別の読みを追加する際の**確認資料**として
     参照するだけなので、追加のライセンス手続きは不要。

## Phase 8（公開ページ統合・Cloudflare）までに決めること

1. **独自ドメイン名を決める**: 使いたいドメインを決め、未取得なら取得する
   （Cloudflare Registrar経由でもよいし、他のレジストラで取得して
   Cloudflareへネームサーバーを向けてもよい）。
2. **Cloudflareアカウントを作成する**: `https://dash.cloudflare.com/sign-up`。
   ドメインをアカウントに追加し、ネームサーバーの向き先を確認する。
3. **Cloudflare R2バケットを作成する**: Cloudflareダッシュボード →
   **R2 Object Storage** → **Create bucket**。バケット名を決める
   （例: `history-radio-media`）。
4. **公開URLの方針を決める**: 次のどちらかを選ぶ。
   - R2バケットの**Public Development URL**（`*.r2.dev`）をそのまま使う
     （手軽だが本番運用には非推奨とCloudflareが案内している）。
   - 独自ドメインのサブドメイン（例: `media.example.com`）をR2バケットに
     カスタムドメインとして紐づける（Cloudflareダッシュボードの
     バケット設定 → **Custom Domains** → **Connect Domain**）。
5. **CI/CDからのデプロイに使う認証情報は今は不要**——Phase 8着手時に
   Cloudflare API トークン（Pages編集権限・R2編集権限）とアカウントIDを
   発行し、`https://github.com/zappyzed100/sourcecast/settings/secrets/actions`
   でGitHub Actionsのrepository secretsとして登録する（このタイミングで
   実装側から声をかける）。

## Phase 9（RSS・配信先）までに決めること

1. **YouTubeチャンネルを作成する**（未作成なら）。Google アカウントで
   `https://www.youtube.com/` → 右上のアカウントアイコン →
   **チャンネルを作成**。
2. **Podcast配信先（RSSホスティング）を決める**: Spotify for
   Podcasters・Apple Podcasts Connect等、RSSフィードを受け付ける配信先を選ぶ。
   審査に数日かかることがあるので、Phase 9着手前でも早めにアカウント作成・
   審査申請だけ進めておくと待ち時間を短縮できる。
3. **Amazon Music/Audibleの配信アカウント**: Amazon Music for
   Podcasters等、該当するプログラムに登録する（同様に審査待ちがあり得る）。

## Phase 12（バックアップ・障害対応）までに決めること

1. **バックアップ保存先を決める**: Google DriveかNAS（自宅サーバー等）かを
   決める。Google Driveの場合はバックアップ専用のフォルダとアカウントを
   用意しておくと、他の個人データと混ざらない。
2. **容量の見積もり**: SQLite・設定・公開データ・必要なartifactsの合計サイズを
   Phase 12着手時に実測してから、無料枠で足りるか判断する
   （development-plan.md §7・運用節）。

## 継続して守ってほしいこと

- OpenRouter・Cloudflare・Google Driveなどの資格情報は、発行後も**Git・SQLite・
  ログへ絶対に保存しない**（development-plan.md §2・§7ログ規則）。実装側が
  環境変数やシークレットマネージャ経由の読み込みを用意するので、それ以外の経路
  （設定ファイルへの直書き等）で渡さないでほしい。
- 上記以外の判断（技術選定・アーキテクチャ・ドメインルールの解釈）は
  PLAN.md／development-plan.md／仕様書に基づいて実装側で進められるので、
  ここに列挙した「アカウント・鍵・GitHubリポジトリ設定」だけが人間側の作業。
