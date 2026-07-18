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
- **解消済み: `e2e`ジョブのCI限定失敗**（`e2e/audio-player.spec.ts`の
  10秒送り・戻しテスト）。原因はフィクスチャ音声が3秒しかないのに+10秒シークして
  いたことで、シーク先が末尾を越えて`ended`が発火していた（ローカルで通っていたのは
  Chromiumのduration推定がOS間で異なるため）。フィクスチャを120秒の無音MP3へ
  再生成して修正（PR #2でCIの`e2e`ジョブが緑になることを確認済み）。
  人間側の作業は無い。

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

## キット更新（Phase 50→53・2026-07-16）で増えたGitHub側の設定作業

ガードレールキットv2.51相当への更新で、required checksの期待構成が変わった
（`.guardrails/GUARDRAILS.md` Phase 51〜53）。既存rulesetの編集は
`https://github.com/zappyzed100/sourcecast/settings/rules` → 作成済みの
`main-required-checks` をクリック → 該当欄を変更 → **Save changes**。

1. **必須ステータスチェックに `workflow-integrity` を追加する**（Phase 52:
   required contextsは4コア＝`checks`・`red-first`・`commit-msg-history`・
   `workflow-integrity`）。rulesetの「Require status checks to pass」の
   チェック一覧に、検索欄から `workflow-integrity` を足すだけ。
   ※このコンテキストは今回のPRで初めてCIに現れるため、検索候補に出ない場合は
   PRのチェックが一度走った後に再度試す。
2. **言語別ジョブも必須チェックへ追加する**（Phase 52「採用した全言語別job」）:
   `python-test`・`ts-test`・`contracts`・`e2e`。
   ※`e2e`はフィクスチャ修正済みで現在安定して緑（PR #2）。
3. **「Require a pull request before merging」を有効化する**（Phase 51:
   全トピック1コミット=1ブランチ=1PRへ統一。現rulesetはstatus checksのみで、
   PR自体の必須化が入っていない——直接pushはstrict checksで実質防がれているが、
   Phase 51の監査はPR必須設定そのものを確認する）。
4. **CODEOWNERSのplaceholder（判断が必要）**: 新設の `.github/CODEOWNERS` は
   workflow信頼境界のため `@GUARDRAILS-HUMAN-REVIEWER` というplaceholderを
   PR作成者とは別の実在の人間へ置き換える設計（Phase 53）。**個人運用で
   別の人間ownerを用意できない場合、この置換とcode owner review必須化は
   スキップしてよい**——その場合の帰結はGUARDRAILS.md Phase 53の境界どおり
   「workflow自己改変の封鎖が不完全なままStep 9を✅にしない」だけで、
   他の門は全て機能する。どうするか決めたら実装側に伝えてほしい
   （placeholderのままでも検査はbase/headバイト一致のみなので日常作業は通る）。

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

   **調査結果（2026-07-19）——ずんだもんの権利関係は2層に分かれる**:
   - **東北ずん子・ずんだもんプロジェクト（SSS合同会社）**: キャラクター
     概念そのもの、および音声（VOICEVOX）の権利元。
   - **坂本アヒル氏**: 一般に「ずんだもん」として認識されている立ち絵
     イラストの作者——プロジェクト本家とは別人。2021年8月、公式が公開した
     参考画像をもとに自身の画風で立ち絵を制作・公開したもので、公式
     フィギュア（POP UP PARADEずんだもん等）にも採用されるほど代表的
     ビジュアルとして定着している。**声とキャラクターデザイン（本家）・
     一般に見慣れた立ち絵（坂本アヒル氏）は別々の権利者**という認識が必要。

   **収益化について**: 個人のYouTube広告収益・スーパーチャットは
   東北6県（青森・秋田・岩手・山形・宮城・福島）の企業/個人事業主以外でも
   「非商用」の範囲として事前申請不要で明示的に許可されている。禁止は
   「営利目的の大規模販売」（グッズの本格製造販売等）——個人が動画に
   広告を付けて収益を得る程度は問題ない。

   **イラスト利用について**: 坂本アヒル氏の立ち絵素材は東北ずん子プロジェクト
   公式ガイドラインに準拠する形で提供されており、改変・加工・商用利用
   （非商用の範囲内）が許可されている。クレジット表記は必須ではないが
   慣習として付ける人が多い。

   **禁止事項・注意点**:
   - 政治・宗教関連での利用、公序良俗に反する表現
   - キャラクターと分からなくなるレベルの改変
   - 素材自体の転売（NFT化・スタンプ販売等）
   - 情報商材の宣伝への利用、フェイク情報拡散目的の利用
   - 反社勢力の利用、商標・意匠の独占登録
   - 過去に「坂本アヒル氏の画風を別の絵師に模倣させて描かせる」行為が
     炎上した事例がある——素材をそのまま/軽微な加工で使う分には問題ないが、
     画風を真似て別人に描き直させるようなことはしない（「常識的な範囲内」
     という制約が当然にある、というのが公式ガイドラインの前提）。

   本プロジェクトの計画（個人運営・YouTube広告での収益化・立ち絵をそのまま
   または軽微な加工で使用）は、上記のいずれの許可範囲にも収まる。
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

## Phase 8着手中（2026-07-16〜）: R2アップロード・Pages公開/ロールバックで今すぐ必要になったもの

タスク4「R2へハッシュ付きキーでmediaをアップロード」のクライアント
（`services/pipeline/src/history_radio/media/r2_upload.py`）と、タスク6
「Pages/R2からGit上の直前版へ戻す手順」のクライアント
（`services/pipeline/src/history_radio/publish/cloudflare_pages.py`）は
実装・単体テスト済みだが、**どちらも実クレデンシャルでの動作確認はまだ行っていない**
（Cloudflare API v4のR2オブジェクト/Pagesデプロイ関連エンドポイントの存在・認証
ヘッダ形式は`api.cloudflare.com`への実プローブで確認済みだが、成功応答の形は未確認）。
下記の項目がまだなら、このタイミングで進めてもらえると実クレデンシャルでの検証ができる:

1. 上記「Phase 8までに決めること」の1〜4（ドメイン・Cloudflareアカウント・
   R2バケット作成・公開URL方針）が未了なら先に進める。
2. **Cloudflare Workers（静的サイト配信）プロジェクトを作成する**（2026-07時点、
   Cloudflareダッシュボードの新規Git連携作成フローは旧来の「Pages」単独メニューでは
   なく「Workers & Pages」→ **Create application** → **Import a repository**
   経由の「Worker」作成に統合されている——挙動は旧Pagesと同等で、静的サイトの
   配信先としてそのまま使える）:
   - **Workers & Pages** → **Create application** → **Import a repository**（または
     **Connect to Git**）でこのGitHubリポジトリ（`zappyzed100/sourcecast`）を選ぶ。
   - 設定画面で **Advanced settings** を開き、**Root directory** に `apps/site`
     を入力する（モノレポのため——これを設定しないとリポジトリ直下を見てしまう）。
   - **Build command**: `pnpm run build`
   - **Deploy command**: デフォルトの `npx wrangler deploy` のままでよい
     （`apps/site/wrangler.jsonc`をコミット済みで、静的アセット配信先として
     `./dist`を指定してある——これがあることで初めて**Deploy**ボタンが押せる
     ようになる。この設定ファイルが無いとダッシュボードがデプロイ対象を検出できず
     ボタンがグレーアウトしたままになる、という既知の詰まりポイントだった）。
   - **Deploy** をクリックしてビルドを実行する。モノレポでのpnpm workspace解決が
     Root directory設定と噛み合わずビルドが失敗する可能性があるので、失敗したら
     ビルドログをそのまま実装側に共有してほしい（設定側で追加調整する）。
   - プロジェクト名（画面上部の入力欄、例: `sourcecast-site`。
     `apps/site/wrangler.jsonc`の`name`と揃えてある）——これは
     `CLOUDFLARE_PAGES_PROJECT`として教えてほしい（秘密情報ではない）。
3. **独自ドメインをPagesプロジェクトへ接続する**（上記1でドメインが決まっていれば）:
   Pagesプロジェクトの **Custom domains** タブ → **Set up a custom domain**。
   HTTPS証明書はCloudflareが自動発行する（追加操作は基本不要）。
4. **Cloudflare API トークンを発行する**: Cloudflareダッシュボード →
   右上のプロフィールアイコン → **My Profile** → **API Tokens** →
   **Create Token** → **Custom token**。権限は最低限
   「**Account** → **Workers R2 Storage** → **Edit**」（R2オブジェクトの
   読み書き）と「**Account** → **Cloudflare Pages** → **Edit**」
   （Pagesデプロイ一覧取得・ロールバック）の両方を付与する。発行された
   トークン文字列は**このチャットに貼らず**、環境変数
   `CLOUDFLARE_API_TOKEN`として渡してほしい（渡し方はOpenRouterのAPIキーの
   時と同じ——ローカルなら`.env`等、CIならGitHub Actions repository secrets）。
5. **アカウントIDを控える**: Cloudflareダッシュボードの右サイドバー
   （どのドメイン/サービスのページでも表示される）に「Account ID」という
   32文字の16進数文字列がある。これも環境変数
   `CLOUDFLARE_ACCOUNT_ID`として渡してほしい（秘密情報ではないので
   チャットに直接書いても問題ない）。
6. **R2バケット名を教えてほしい**（上記「決めること」3で決めた名前、
   例: `history-radio-media`）——これは`CLOUDFLARE_R2_BUCKET`として渡す
   か、チャットで直接教えてもらえればよい。

これらが揃うまでは、R2アップロード・Pagesロールバックの両機能はモック
（`httpx.MockTransport`）による単体テストのみで検証された状態で先へ進める
（OpenRouter・VOICEVOXの時と同じ「実クレデンシャルが無くてもテスト可能な
クライアント抽象を先に作る」方針）。Pagesプロジェクトが実在してから、
「プレビューと本番でリンク切れ・mixed content・ヘッダー欠落が0件」という
タスク5のDoDの後半（ライブHTTP応答での検証——現状は`_headers`ファイル自体の
静的検証のみ）にも着手できる。

## Phase 8（公開ページ統合・Cloudflare）までに決めること

1. **独自ドメイン名を決める**: 使いたいドメインを決め、未取得なら取得する
   （Cloudflare Registrar経由でもよいし、他のレジストラで取得して
   Cloudflareへネームサーバーを向けてもよい）。
   **決定（2026-07-19）**: `itsuwawa.com`。「逸話（itsuwa）」＋「〜のわ」
   （輪＝community/circleを表す語尾。`rekishinowa.com`等の既存サイトで
   見られる命名パターンと同型）——対象ジャンルを歴史に限定しないための
   意図的な選定（「歴史」という語を含めない）。取得はCloudflare Registrar
   （`.com`は上乗せ手数料なしの卸価格・年$10前後で購入可能——調査済み。
   `.jp`はCloudflare Registrar非対応のため今回は不採用）。
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

**現状（2026-07-19）**: タスク1（RSSフィード生成）・タスク2（配信先ごとの
メタデータ生成）・タスク3（approved以降だけ配信操作を許可するゲート）・
タスク4（配信結果の記録と二重投稿防止の台帳）は実装・単体テスト済み。
いずれも実際のYouTube/Podcast/Amazon Music APIへは接続していない
（`distribution_ledger.py`の`dispatch()`が受け取る`publish_fn`は、各配信先の
実アップロード処理を後から差し込むための差し替え可能な関数——現時点ではテストの
フェイク関数だけを渡している）。したがって下記1〜3のアカウント自体は
**まだ実装側では使っていない**——実クライアントを実装する段階（Phase 11の
管理画面実運用化、またはそれ以前に前倒しで着手する場合）になったら、
その時点で改めて必要な認証情報を具体的に依頼する。早めにアカウント作成・
審査申請だけ進めておくと、実クライアント実装時の待ち時間を短縮できる。

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
