# plan.md — 歴史スライド動画・自動生成ツール 実装計画 v0.2

設計根拠の正本は [history_radio_spec_v0_4.md](history_radio_spec_v0_4.md)（以下「仕様書」）とする。
本書は仕様書を実装可能な単位へ分解し、採用言語、構成、品質基準、検証方法まで確定する。

> 基本方針: 見た目は簡素でよい。ただし、公開サイトと管理画面は機能を削らず、
> 「静的配信」「強い型」「小さな実行時依存」「失敗時に安全側へ倒れる設計」で、堅牢性と速度を優先する。

AGENTS.md §4 の方針（小タスク＋各タスクの検証コマンド）に従う。フェーズを跨ぐ大きな
`feat:` コミットには、本書の該当タスクへの差分を同一コミットに含める
（`feat-without-plan` hard 検査 — `.guardrails/GUARDRAILS.md` §3.4）。

---

## 1. 技術選定（確定）

### 1.1 言語と責務

| 領域              | 採用技術                                     | 用途                                                 | 採用理由                                  |
| --------------- | ---------------------------------------- | -------------------------------------------------- | ------------------------------------- |
| 生成パイプライン        | **Python 3.14.x**                        | 収集、権利判定、選出、OpenRouter、VOICEVOX、FFmpeg、関連書籍検索、公開ゲート | HTTP・データ処理・外部CLI連携の実装が速く、ライブラリが成熟している |
| ローカル管理API       | **Python / FastAPI**                     | ジョブ操作、レビュー、承認、設定、監査ログ、SSE進捗通知                      | パイプラインの型と処理を共有でき、別サービス間の重複を減らせる       |
| 公開サイト           | **TypeScript 7.0.x / Astro 7**           | エピソード、出典、訂正履歴、検索、RSS案内                             | HTMLを静的生成し、通常ページはJavaScriptなしでも表示できる  |
| 管理画面            | **TypeScript 7.0.x / React 19 + Vite 8** | 候補審査、主張‐出典対応、台本差分、音声・スライド確認、再実行                    | 状態の多いUIを型安全に組み立てやすく、テスト資産が豊富          |
| Cloudflare上の小処理 | **TypeScript / Workers**                 | 将来のリダイレクト、非公開プレビュー、Webhookのみ                       | Cloudflareで第一級にサポートされる。MVPの通常配信には使わない |
| 検索              | **Pagefind**                             | 公開済みページの全文検索                                       | 静的HTMLから検索索引を作るため、検索サーバーとDBが不要        |
| 永続化             | **SQLite（WAL）+ Git + R2**                | ローカル運用状態、公開データ、音声・画像                               | 用途ごとに責務を分離し、単一障害点を作らない                |

Pythonだけで管理画面まで作らない。逆に、クローラーやメディア生成をNode.jsへ寄せない。
この2言語構成は役割の境界が明確で、どちらか一方へ無理に統一するより実装量と障害範囲を抑えられる。

Rustは初期採用しない。処理時間の大半はネットワーク待ち、LLM待ち、VOICEVOX、FFmpegであり、
まず計測してPython自体がボトルネックと確認できた箇所だけ、後から置換を検討する。

参考:

* [Python公式ダウンロード](https://www.python.org/downloads/)
* [Astro 7の公式案内](https://astro.build/blog/whats-new-june-2026/)
* [Cloudflare PagesのAstroガイド](https://developers.cloudflare.com/pages/framework-guides/deploy-an-astro-site/)
* [Cloudflare WorkersのTypeScript対応](https://developers.cloudflare.com/workers/languages/typescript/)
* [TypeScript公式サイト](https://www.typescriptlang.org/)
* [Reactの公式バージョン情報](https://react.dev/versions)
* [Pagefind公式ドキュメント](https://pagefind.app/docs/)

### 1.2 バージョン固定

* Pythonは `requires-python = ">=3.14,<3.15"` とし、`uv.lock` をコミットする。
* Node.jsは **24 LTS** を `.node-version` とCIで固定する。
* TypeScriptは7.0.x、Astroは7.x、Reactは19.2.x、Viteは8.xを採用し、正確なpatch版を
  `package.json` と `pnpm-lock.yaml` で固定する。`latest` 指定を本番ビルドへ持ち込まない。
* pnpmは11系を使い、`packageManager` フィールドで正確なバージョンを固定する。
* VOICEVOX、FFmpegはPython依存へ混ぜず、外部実行ファイルとしてバージョン、取得元、SHA-256を記録する。
* 依存更新は自動マージしない。週1回の更新PRで、全テストとプレビューを通してから取り込む。

### 1.3 Pythonの標準構成

* パッケージ管理・実行: `uv`
* モデルと入力検証: Pydantic v2
* HTTP: HTTPX。`AsyncClient` を再利用し、接続プール、ドメイン別同時実行数、タイムアウトを明示する
* DB: SQLAlchemy 2 + Alembic。SQLiteはWAL、`busy_timeout`、単一writer、短いトランザクションを原則とする
* CLI: Typer
* ローカルAPI: FastAPI。`127.0.0.1` のみにbindし、外部公開しない
* ログ: JSON構造化ログ。`job_id`、`episode_id`、`source_id` を必須コンテキストにする
* 品質: Ruff（lint/format）、basedpyright（strict）、pytest、coverage

業務ロジックで `Any`、無検査の `dict[str, object]`、巨大な例外握りつぶしを常用しない。
FastAPIのroute関数へ権利判定や公開判定を書かず、domain/use-case層を呼ぶだけにする。

`asyncio` はクロールなどI/O待ちにだけ使う。CPU処理を無条件に非同期化しない。
FFmpeg、VOICEVOXのプロセスには必ずタイムアウト、終了コード検査、キャンセル時の子プロセス終了を実装する。

### 1.4 TypeScriptの標準構成

* パッケージ管理: pnpm workspace
* 型検査: TypeScript `strict` に加え、`noUncheckedIndexedAccess`、
  `exactOptionalPropertyTypes`、`useUnknownInCatchVariables` を有効化する
* lint/format: Biome。型検査は `tsc --noEmit` を別実行する
* 単体テスト: Vitest
* ブラウザテスト: Playwright
* アクセシビリティ検査: axe-core
* 公開サイト: Astroの静的出力。クライアントJavaScriptは検索、音声プレイヤー、絞り込みなど
  操作が必要な部品だけ遅延読み込みする
* 管理画面: React。コンポーネントライブラリを丸ごと導入せず、ネイティブHTMLと小さな共通部品を優先する
* CSS: 通常CSS + CSS Custom Properties。見た目の都合だけで重いCSSフレームワークを導入しない

アプリケーションコードは `.ts` / `.tsx` を原則とし、手書きの `.js` はビルド設定など
必要最小限に限定する。`as any`、型検査を迂回する二重cast、API応答の無検証利用をCIで禁止する。

公開サイトでReact Server Components、SSR、常時稼働APIを使わない。公開ページの表示に
Workers、D1、ローカルPCのいずれも必要としない構成にする。

---

## 2. システム構成

```mermaid
flowchart TD
    A["管理画面<br/>React + TypeScript"] --> B["ローカルAPI<br/>FastAPI"]
    B --> C["生成パイプライン<br/>Python"]
    C --> D["運用状態<br/>SQLite + artifacts"]
    C --> E["公開データ<br/>Git管理 JSON/Markdown"]
    E --> F["Astro build<br/>Cloudflare Pages"]
    C --> G["音声・画像<br/>Cloudflare R2"]
    F --> G
```

### 2.1 保存先の責務

| データ                | 正本                    | 備考                                 |
| ------------------ | --------------------- | ---------------------------------- |
| ソース登録・権利規則・モデル設定   | Git                   | 人がレビューでき、変更履歴が残る形式にする              |
| 取得本文・スナップショット      | ローカル `artifacts/`     | 保存許可がある資料だけ。公開リポジトリへ入れない           |
| ジョブ、候補、レビュー状態、監査ログ | SQLite                | 日次バックアップ対象。公開サイトの表示には使わない          |
| 公開エピソード、主張、出典、訂正履歴 | Git上の版管理JSON/Markdown | Astroのビルド入力。GitHubから再構築できる         |
| MP3、スライド画像、MP4     | R2                    | SHA-256付きの不変キー。公開データ側から参照する        |
| 公開HTML、検索索引、RSS    | Cloudflare Pages      | GitHub ActionsまたはPages buildで再生成可能 |

公開済み情報をすべてローカルだけに保持する必要はない。ただし、公開前の取得本文、審査情報、
トークン、未公開原稿をGitHubへ置かない。Gitには公開に必要な最小データと設定だけを入れる。

### 2.2 リポジトリ構成

```text
.
├─ apps/
│  ├─ site/                 # Astro公開サイト
│  └─ admin/                # Reactローカル管理画面
├─ services/
│  └─ pipeline/
│     ├─ src/history_radio/
│     │  ├─ domain/         # 副作用のない型・規則
│     │  ├─ rights/         # 権利判定
│     │  ├─ ingest/         # 収集アダプター
│     │  ├─ select/         # 機械選出
│     │  ├─ llm/            # OpenRouter境界
│     │  ├─ script/         # 台本
│     │  ├─ media/          # VOICEVOX・FFmpeg
│     │  ├─ books/          # 関連書籍
│     │  ├─ publish/        # 公開データ生成
│     │  ├─ distribute/     # RSS・配信先
│     │  ├─ gate/           # 公開検査
│     │  ├─ store/          # DB・ファイル実装
│     │  └─ api/            # localhost FastAPI
│     └─ tests/
├─ packages/
│  ├─ contracts/            # JSON Schemaと生成済みTypeScript型
│  └─ ui/                   # 最小限の共通UI部品・デザイントークン
├─ content/episodes/        # 公開エピソードの版管理データ
├─ config/                  # ソース・権利・モデル設定
├─ migrations/              # Alembic
├─ scripts/                 # dev、検証、バックアップ
├─ artifacts/               # ローカル生成物。Git対象外
└─ .github/workflows/
```

依存方向は `domain ← rights/select ← use-cases ← adapters` とし、`domain` からHTTP、DB、
OpenRouter、Cloudflareを参照しない。ソースごとの差はアダプターへ閉じ込める。

### 2.3 PythonとTypeScriptの契約

* Pydanticモデルからバージョン付きJSON Schemaを生成し、`packages/contracts/schema/` へコミットする。
* TypeScript型はSchemaから自動生成し、手書きで二重管理しない。
* CIで「Schemaを再生成して差分0」を検査する。
* すべての公開データに `schema_version`、`episode_id`、`revision`、`generated_at` を持たせる。
* 破壊的変更は新しい `schema_version` と移行コードを必要とする。
* APIは `/api/v1/` を使い、更新時は `revision` またはETagによる楽観ロックで上書き競合を防ぐ。

---

## 3. Web要件

### 3.1 公開サイト（簡素な見た目、豊富な機能）

必須機能:

* エピソード一覧、年代・地域・人物・テーマによる絞り込み
* Pagefindによる日本語全文検索。検索UIと索引は検索開始時に遅延読み込み
* 音声プレイヤー（再生速度、10秒送り/戻し、章移動、キーボード操作、再生位置の端末内保存）
* 台本の表示、章単位コピー、全文コピー、Markdown/プレーンテキストのダウンロード
* 各主張から、その根拠となる出典へ展開できる「主張‐出典対応表」
* 出典名、原URL、取得日、ライセンス、権利判定、クレジットの表示
* 訂正履歴と過去版の閲覧。現行版と旧版の差分表示
* 関連書籍、Podcast RSS、YouTubeへの導線
* 共有用OGP、canonical URL、構造化データ、サイトマップ
* 404でも検索、一覧、RSSへ戻れる導線

公開ページには保存した根拠抜粋を無条件に掲載しない。公開許可のある引用だけを表示し、
それ以外は主張、出典メタデータ、原URLの表示に留める。

### 3.2 ローカル管理画面

必須画面:

1. **ダッシュボード**: 今日のジョブ、失敗、待機、API使用量、R2/Git同期状態
2. **候補一覧**: 点数内訳、除外理由、ニュース連想リスク、重複、採否の一括操作
3. **出典・権利審査**: 利用規約スナップショット、ライセンス根拠、判定履歴、手動保留
4. **主張台帳**: 主張と独立した出典系統の対応、根拠位置、不足出典の警告
5. **台本レビュー**: 版差分、claim_id、禁止表現、転載類似箇所、承認/差戻し
6. **メディア確認**: 音声、字幕、スライド、クレジット、動画の同期プレビュー
7. **ジョブ管理**: 実行、停止、安全な再実行、失敗地点からの再開、ログ表示
8. **設定**: ソース、ライセンス、モデル、禁止語の編集。変更前後の差分と監査記録
9. **公開確認**: URL、RSS、R2、ハッシュ、過去版、公開ゲートの最終一覧

ジョブ進捗はWebSocketではなくSSEを基本とする。操作は通常のHTTP APIとし、再接続しやすくする。
一覧APIは件数が増えても全件返さず、カーソルページング、絞り込み、並べ替えを備える。
MVPは単一運用者を想定し、管理APIをインターネットへ公開しない。

### 3.3 速度・アクセシビリティ予算

* 公開エピソードページは静的HTMLを返し、JavaScript無効でも本文、出典、訂正履歴を読めること
* 初回表示に不要な音声、検索索引、差分表示コードを読み込まないこと
* エピソードページの初期JavaScriptはgzip後 **60 KB以下**を目標とし、超過時はCIで警告する
* Lighthouse目標: Performance 90以上、Accessibility 95以上、Best Practices 95以上
* Core Web Vitals目標: LCP 2.5秒未満、CLS 0.1未満、INP 200ms未満
* 画像は表示寸法を明示し、AVIF/WebPを生成する。OGP等で必要な場合だけPNG/JPEGを残す
* キーボード操作、フォーカス表示、十分なコントラスト、`prefers-reduced-motion` を必須にする
* 大きな台本、出典一覧、検索結果は仮想化または段階表示し、DOMを無制限に増やさない

### 3.4 堅牢性・セキュリティ

* Cloudflare Pagesの静的配信を通常経路とし、Workers/D1障害で既存ページが読めなくなる設計を禁止する
* メディアを先にR2へ配置・ハッシュ検証し、その後に公開データをGitへ反映する
* 公開は「検証済み成果物への参照切替」とし、途中状態を見せない。直前版へロールバック可能にする
* Markdown/HTMLは許可リストでsanitizeし、ソース由来のHTMLをそのまま描画しない
* CSP、`X-Content-Type-Options`、`Referrer-Policy`、`Permissions-Policy` をPagesのヘッダーに設定する
* 管理APIはlocalhost限定。将来外部公開する場合はCloudflare Access、CSRF対策、権限分離を別フェーズで設計する
* OpenRouter、R2、Google Driveの資格情報をGit、SQLite、ログへ保存しない
* すべての外部HTTPに接続・読み取り・全体タイムアウト、再試行上限、指数バックオフを設定する
* 書き込み処理には冪等キーを使い、二重実行で二重公開・二重アップロードしない
* 失敗時の既定動作は `blocked` または `manual_review`。不明状態を公開可へ倒さない

---

## 4. フェーズ構成

仕様書 §6（処理フロー7工程）、§16（MVP範囲）、§17（受入条件の段階制）に対応させる。
各フェーズは公開しない状態で単体検証できる単位とし、状態機械
`collected → screened → selected → scripted → rendered → approved → published` と整合させる。

### Phase 0 — モノレポと開発基盤

* [ ] `bindings/catalog.md` のPython/uv列とTypeScript/Node/pnpm列を採用し、実在する列IDを記録する。
  検証: `scripts/repo_scan.py` が未刻印・未配線をHARDで検出できる。
* [ ] Python 3.14、Node 24 LTS、pnpm workspace、`uv.lock`、`pnpm-lock.yaml` を初期化する。
  検証: `uv run python --version`、`node --version`、`pnpm --version` が固定範囲内。
* [ ] `apps/site`、`apps/admin`、`services/pipeline`、`packages/contracts` を上記構成で作る。
  検証: 各パッケージの空ビルドとimportが通る。
* [ ] `scripts/dev.py` に `check`、`test`、`build`、`dev`、`pipeline` を配線する。
  検証: WindowsとCIの両方で同じコマンドが動く。
* [ ] Ruff、basedpyright、pytest、Biome、`tsc --noEmit`、Vitest、PlaywrightをCIへ登録する。
  検証: 意図的なlint違反と型違反をPython/TypeScript各1件ずつ入れ、CIが失敗する。

### Phase 1 — ドメイン契約・状態機械・保存基盤

* [ ] `SourceRecord`、`RightsDecision`、`Candidate`、`Claim`、`Episode`、`Job`、`AuditEvent` を
  Pydanticで定義し、JSON SchemaとTypeScript型を生成する。
  検証: 必須項目欠落・未知のschema_versionをPythonとTypeScript双方で拒否する。
* [ ] 状態遷移をpure functionで定義し、不正な逆行と段階飛ばしを拒否する。
  検証: 全許可遷移と代表的な禁止遷移を表駆動テストで固定する。
* [ ] SQLite、Alembic、WAL、`busy_timeout`、単一writerを実装する。
  検証: 2つの読取中にwriterが更新でき、競合更新がrevision不一致で拒否される。
* [ ] `config/source_registry.yaml`、`license_rules.yaml`、`model_registry.yaml` をSchema検証する。
  検証: 未知キー、重複ID、不正URL、期限切れ設定を起動時に拒否する。

### Phase 2 — Webの土台を先に作る

* [ ] `apps/site` にエピソード一覧、詳細、出典、訂正履歴、404をfixtureで実装する。
  検証: `pnpm build` 後のHTMLをJavaScript無効で閲覧できる。
* [ ] Pagefindをbuild後処理へ組み込み、日本語検索、年代・地域・人物フィルタを実装する。
  検証: fixtureの固有語を検索し、該当エピソードが返る。
* [ ] 音声プレイヤー、章移動、再生速度、再生位置保存を遅延読み込み部品として実装する。
  検証: Playwrightでキーボードのみの再生・停止・章移動が通る。
* [ ] `apps/admin` とlocalhost FastAPIをfixtureで接続し、ダッシュボード、候補、ジョブ画面を作る。
  検証: API停止、タイムアウト、空データ、壊れた応答を各画面が安全に表示する。
* [ ] CSP、セキュリティヘッダー、axe、Lighthouse予算をCIへ追加する。
  検証: 重大なaxe違反と性能予算超過でCIが失敗する。

### Phase 3 — 権利判定エンジン（仕様書 §5A・§5.2）

事実収集より先に判定器を完成させる。権利不明資料を本文保存や公開処理へ流さない。

* [ ] 権利表示文字列を `normalized_license_id` へ正規化する。
  検証: `cc0`、`cc-by`、`cc-by-sa`、`gov-jp-2.0`、`unknown` のnamedテスト。
* [ ] §5Aの判定項目（没年計算、映画1953年、写真1957年、戦時加算等）をpure functionで実装する。
  **年数は資料取得ごとに現在日付で再計算する**。
  検証: 各規則の許可最小ケース、境界、拒否ケースをnamedテストで固定する。
* [ ] 判定不能、入力不足、規約取得失敗を `manual_review` または `deny` へ倒す。
  検証: 欠損値を組み合わせても `allow_public_use` にならない。
* [ ] 判定入力、規則バージョン、結果、理由を追記型の監査ログへ残す。
  検証: 同じ資料を新ルールで再判定しても旧判定が消えない。

### Phase 4 — 収集（仕様書 §7・§5.3）

MVP対象はWikipedia、Wikimedia Commons、NDLデジタルコレクションの利用可能区分、ColBase、
および明示的に許可したCC0資料とする。

* [ ] 共通取得結果スキーマとアダプターProtocolを実装する。
  検証: 必須フィールド欠落を型検査と実行時検証で拒否する。
* [ ] ソースごとに独立アダプターを実装する。APIを優先し、robots.txt、規約、レート制限に従う。
  検証: 記録済みfixtureを用いた統合テストを実ネットワークなしで通す。
* [ ] ドメイン別セマフォ、接続プール、タイムアウト、条件付きGET、指数バックオフを実装する。
  検証: 429、5xx、タイムアウト、途中切断を注入し、上限後に安全に停止する。
* [ ] `status: approved` のソースだけを収集し、権利判定を通過しない本文を保存しない。
  検証: `candidate` と `internal_research_only` の全文が永続化されない。
* [ ] 取得URL、取得日時、レスポンスハッシュ、規約スナップショット、出典関係を保存する。
  検証: 同じ内容の再取得で重複スナップショットを作らない。

### Phase 5 — 出典独立性・題材選出（仕様書 §6.2・§6A）

* [ ] 出典の系統判定（転載、同一一次資料由来、同一組織系列等）を実装する。
  検証: 仕様書の独立性パターンをnamedテストで固定する。
* [ ] §6A.1の候補点計算式をLLM不使用で実装し、点数内訳を保存する。
  検証: 各特徴量を固定した入力から期待点数が得られる。
* [ ] ニュースから使う語は題材選出用に限定し、本文・要約を歴史エピソードの出典にしない。
  検証: ニュースURLが公開出典一覧へ混入しない。
* [ ] 悪感情を呼ぶニュースとの便乗連想を避けるため、死傷、災害、戦争、事件、差別、疾病、
  性犯罪等のカテゴリと禁止語で候補を隔離する。曖昧な場合は採用せず手動確認へ送る。
  検証: 代表的な不適切連想ケースが自動採用されない。
* [ ] 類似題材、同一人物、同一事件のクールダウン期間を実装する。
  検証: 期間内の重複候補が順位から除外される。

### Phase 6 — LLM処理・主張台帳・台本（仕様書 §8・§9）

* [ ] OpenRouterの固定モデルをレジストリで管理し、価格、利用可否、構造化出力、日本語回帰を検査する。
  ランダムルーターを本番へ使わない。
  検証: 無料枠外、期限切れ、回帰失敗モデルを採用しない。
* [ ] 要約、facts、根拠位置をJSON Schemaで受け取る。URL、取得日、ライセンスはプログラムから注入する。
  検証: JSON不正、余分なキー、存在しない根拠位置を拒否する。
* [ ] 根拠抜粋が保存本文と完全一致することをプログラムで検証する。
  検証: 1文字改変した抜粋が拒否される。
* [ ] `claim_ledger` を作り、独立系統2件未満の主張を台本へ入れない。
  検証: 1系統だけの主張が `allowed_in_script: false` になる。
* [ ] §9.1の7段構成で台本を生成し、各外部検証可能文を `claim_id` へ結びつける。
  検証: claim_idのない事実文、台帳にない事実、禁止表現を含む台本を拒否する。
* [ ] 生成結果、プロンプト版、モデルID、入力ハッシュ、出力ハッシュ、使用量を保存する。
  検証: 同じ入力と版ではキャッシュが使われ、二重課金呼び出しをしない。

### Phase 7 — 音声・スライド動画・関連書籍（仕様書 §10・§10A）

* [ ] VOICEVOX（ずんだもん）の起動確認、音声生成、クレジット自動付与を実装する。
  検証: エンジン停止、タイムアウト、途中失敗で不完全MP3を公開対象にしない。
* [ ] FFmpegで音量正規化、無音、破損、長さ、codecを検査する。
  検証: 基準外音量と破損音声を公開ゲートが拒否する。
* [ ] 静止画、地図、年表、字幕からスライド動画を生成する。素材不足時は自作図形へフォールバックする。
  検証: 画像0件でも権利上安全な動画を生成できる。
* [ ] 画像の権利、クレジット、使用箇所を `media_manifest` に記録する。
  検証: クレジット欠落素材をレンダリング前に拒否する。
* [ ] ISBN、著者、件名標目による関連書籍検索と機械ランキングを実装する。LLMは使わない。
  検証: 書誌系統1件だけの候補を非表示にする。

### Phase 8 — 公開ページ統合・Cloudflare（仕様書 §10B・§10C）

* [ ] Pythonからバージョン付き公開JSON/Markdownを生成し、Astroのcontent collectionで検証する。
  検証: 不正Schema、欠落出典、未知ライセンスでbuildを失敗させる。
* [ ] `/episodes/<ID>/` と `/episodes/<ID>/versions/<revision>/` を生成する。
  検証: 再生成が旧版を上書きせず、新版と訂正履歴を追加する。
* [ ] 主張‐出典対応、コピー、ダウンロード、過去版差分を実データへ接続する。
  検証: 全公開主張から1件以上の有効な出典URLへ到達できる。
* [ ] R2へハッシュ付きキーでmediaをアップロードし、存在・サイズ・ハッシュを確認する。
  検証: 同じ入力の再実行が重複オブジェクトを作らない。
* [ ] Cloudflare Pagesへ独自ドメイン、HTTPS、キャッシュ、セキュリティヘッダー、404を設定する。
  検証: プレビューと本番でリンク切れ、mixed content、ヘッダー欠落が0件。
* [ ] Pages/R2からGit上の直前版へ戻す手順を自動化する。
  検証: ステージングで1回ロールバックし、URLとRSS GUIDが変わらない。

### Phase 9 — RSS・配信先（仕様書 §10D）

* [ ] RSS 2.0を静的生成し、GUID、公開日時、enclosure、長さ、MIME、クレジットを固定する。
  検証: 標準バリデーターでエラー0件、過去GUIDの変化0件。
* [ ] YouTube、Podcast、Amazon Music/Audible向けメタデータを同じEpisodeから生成する。
  検証: 全配信先で同じ `episode_id` を冪等キーとして使う。
* [ ] 自動アップロードはMVPでは限定公開までとし、公開ボタンは最終ゲート通過後だけ有効化する。
  検証: `approved` 未満の状態から公開操作できない。
* [ ] 外部配信の成功・失敗・外部IDを記録し、同じ配信先への二重投稿を防ぐ。
  検証: タイムアウト後の再実行でも二重投稿しない。

### Phase 10 — 自動検査ゲート（仕様書 §11）

* [ ] 権利、独立出典数、claim_id、転載類似度、禁止語、クレジット、media、RSS、URLをAND評価する。
  検証: 各項目を1つずつ失敗させたケースがすべて `publish_ready=false` になる。
* [ ] 和文25文字以上、欧文8語以上の連続一致を転載候補として検出する。
  検証: 出典原文の25文字コピーを拒否する。
* [ ] ゲート結果に規則版と全チェックの根拠を保存し、管理画面から追跡できるようにする。
  検証: 公開済み版から当時の検査結果を再表示できる。
* [ ] ゲート通過後の成果物ハッシュを固定し、公開直前の差替えを拒否する。
  検証: 承認後に台本やmediaを変更すると再承認が必要になる。

### Phase 11 — 管理画面の実運用化（仕様書 §12）

* [ ] Phase 2の画面を実DBと実ジョブへ接続し、候補→審査→承認→限定公開を一画面ずつ完成させる。
  検証: 1件を最初から限定公開まで操作するPlaywright E2Eが通る。
* [ ] 長時間ジョブのSSE進捗、キャンセル、再実行、ログ追跡を実装する。
  検証: ブラウザ再読込後も正しいジョブ状態へ復帰する。
* [ ] 破壊的操作は確認、理由入力、監査ログを必須にする。
  検証: 理由なしの却下、削除、公開取消をAPIが拒否する。
* [ ] CLIは残し、管理画面障害時にも状態確認、停止、再開、バックアップを実行できるようにする。
  検証: Reactを起動せず主要な復旧操作ができる。

### Phase 12 — バックアップ・障害対応（仕様書 §13〜§15）

* [ ] SQLite、設定、公開データ、必要なartifactsをGoogle Drive/NASへ日次バックアップする。
  R2とGitの内容は参照情報と復元手順を保存する。
  検証: 空の環境へ復元し、恒久ページとRSSを同一ハッシュで再構築できる。
* [ ] 月次復元試験をジョブ化し、結果と所要時間を監査ログへ残す。
  検証: 失敗をダッシュボードと終了コードで通知する。
* [ ] 429、LLM JSON不正、クロール失敗、VOICEVOX停止、FFmpeg失敗、Git/R2失敗を状態遷移へ反映する。
  検証: 各障害が `blocked`、`rejected`、または上限付きretryへ遷移する。
* [ ] PC再起動後に中断ジョブを検出し、二重実行せず再開または手動確認へ送る。
  検証: 各工程で強制終了して再起動するfault injectionテスト。

### Phase 13 — 受入検証（仕様書 §17 段階0〜3）

* [ ] 段階0: Python/TypeScriptの単体、契約、統合、E2E、公開ゲート試験を全通過させる。
  検証: `uv run scripts/dev.py check && uv run scripts/dev.py test && uv run scripts/dev.py build`。
* [ ] 段階1: 30候補ドライラン（非公開）。採否、権利、面白さ、誤情報、画面操作を人手確認する。
  検証: 30件のレビュー記録と改善チケットを残す。
* [ ] 段階2: 限定公開10本。1本あたりの確認時間、失敗率、再実行回数、ページ性能を記録する。
  検証: 確認時間15分以内、重大アクセシビリティ違反0、壊れた出典リンク0。
* [ ] 段階3: 公開運用30日。権利不明混入0、重複公開0、復旧不能0を確認する。
  検証: 仕様書§17末尾の全指標を運用ログから集計する。

---

## 5. CI/CDの必須ゲート

Pull Requestごとに以下を並列実行する。

```text
Python:    ruff → basedpyright → pytest → migration check
Contracts: JSON Schema再生成 → 差分検査 → fixture互換性
Web:       biome → tsc --noEmit → vitest → astro build → pagefind
Browser:   Playwright smoke → axe → link check → performance budget
Security:  secret scan → dependency audit → generated HTML/CSP check
```

production deployは、PRの同一commit SHAで作った検証済みartifactだけを使う。
deploy時に依存を再解決したり、LLMを再実行したりしない。

---

## 6. 対象外

MVPでは以下を実装しない。

* 完全自動の一般公開
* 年代計算だけによるパブリックドメイン自動許可
* 一般ニュースRSS本文の保存・要約・出典利用
* 有料素材
* 歴史音源（SP盤等）の実演・原盤を含む3層権利判定
* 動画生成AI、高度なキャラクターアニメーション
* 多言語配信
* 広告・アフィリエイトの自動挿入
* 公開サイトのSSR、常時稼働API、D1必須化
* 管理画面のインターネット公開、複数ユーザー・権限管理

---

## 7. 実装前に必要な外部設定

技術選定は本書で確定済みとし、実装着手のために残る確認事項はアカウントと公開範囲に限定する。

* 独自ドメイン名とCloudflareアカウント
* GitHubリポジトリの公開/非公開
* R2バケット名と公開URL方針
* Google Driveバックアップ先
* YouTube、Podcast、Amazon Music/Audibleの配信アカウント

これらが未確定でもPhase 0〜7はローカルfixtureとモックで進められる。Phase 8以降の実接続だけを保留する。
