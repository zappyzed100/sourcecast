# development-plan.md — history-radio 開発計画（フェーズ別タスク・検証コマンドの正本）

全体像・アーキテクチャ・技術選定の要約は [PLAN.md](../../PLAN.md) を参照。本書は
仕様書 [history_radio_spec_v0_4.md](../../history_radio_spec_v0_4.md)（以下「仕様書」）を
実装可能な単位へ分解し、採用言語、構成、品質基準、検証方法まで確定する。

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

進捗の一覧・機械可読タスクは [PLAN.md](../../PLAN.md) を参照。

### Phase 0 — モノレポと開発基盤 ✅

* [x] `bindings/catalog.md` のPython/uv列とTypeScript/Node/pnpm列を採用し、実在する列IDを記録する。
  検証: `scripts/repo_scan.py` が未刻印・未配線をHARDで検出できる。
* [x] Python 3.14、Node 24 LTS、pnpm workspace、`uv.lock`、`pnpm-lock.yaml` を初期化する。
  検証: `uv run python --version`、`node --version`、`pnpm --version` が固定範囲内。
* [x] `apps/site`、`apps/admin`、`services/pipeline`、`packages/contracts` を上記構成で作る。
  検証: 各パッケージの空ビルドとimportが通る。
* [x] `scripts/dev.py` に `check`、`test`、`build`、`up`/`reset`/`db` を配線する。
  検証: WindowsとCIの両方で同じコマンドが動く。
* [x] Ruff、basedpyright、pytest、Biome、`tsc -b`、Vitest、PlaywrightをCIへ登録する。
  検証: 意図的なlint違反と型違反をPython/TypeScript各1件ずつ入れ、CIが失敗する
  （`tsc --noEmit`単体だとproject-references構成で何も検査しない実測バグを発見・`tsc -b`へ修正）。

### Phase 1 — ドメイン契約・状態機械・保存基盤 ✅

* [x] `SourceRecord`、`RightsDecision`、`Candidate`、`Claim`、`Episode`、`Job`、`AuditEvent` を
  Pydanticで定義し、JSON SchemaとTypeScript型を生成する。
  検証: 必須項目欠落・未知のschema_versionをPythonが拒否する（56テスト）。TypeScript側は
  型生成まで(json-schema-to-typescript)——ランタイム検証(ajv等)はTS側で実際にJSONを
  受け取る消費者ができてから追加する(Phase 8以降のAPI層)。
* [x] 状態遷移をpure functionで定義し、不正な逆行と段階飛ばしを拒否する。
  検証: 全9前進辺・代表的な失敗遷移・8つの禁止遷移を表駆動テストで固定。
* [x] SQLite、Alembic、WAL、`busy_timeout`、単一writerを実装する。
  検証: 2つの読取中にwriterが更新でき、競合更新がrevision不一致(EpisodeConflictError)で拒否される。
* [x] `config/source_registry.yaml`、`license_rules.yaml`、`model_registry.yaml` をSchema検証する。
  検証: 未知キー、重複ID、不正URL、期限切れ・有料モデル設定を起動時に拒否する(8テスト)。

### Phase 2 — Webの土台を先に作る ✅（年代・地域・人物フィルタは未実装 — 下記参照）

* [x] `apps/site` にエピソード一覧、詳細、出典、訂正履歴、404をfixtureで実装する。
  検証: ビルド後のHTMLから直接fixture文言を検索し、JavaScript無しで内容が読めることを確認。
* [x] Pagefindをbuild後処理へ組み込み、日本語全文検索を実装する。
  検証: fixtureの固有語(「アペール」)で検索し、該当エピソードが返る(Playwright 2件)。
  **未実装**: 年代・地域・人物の絞り込みフィルタ——現時点でfixtureのメタデータに
  年代/地域/人物の構造化フィールドが無く、Pagefindのfilter機能を使う対象が無い。
  Phase 5(出典独立性・題材選出)でtopicsに年代/人物等の構造化データが載ったら追加する。
* [x] 音声プレイヤー、章移動、再生速度、再生位置保存を遅延読み込み部品として実装する。
  検証: Playwrightでキーボードのみの再生・停止・章移動・前後10秒送りが通る(3件)。
* [x] `apps/admin` とlocalhost FastAPIをfixtureで接続し、ダッシュボード、候補、ジョブ画面を作る。
  検証: API停止・タイムアウト・空データ・壊れた応答の6ケースをvitestで固定。
* [x] CSP、セキュリティヘッダー、axe、性能予算をCIへ追加する。
  検証: axe(wcag2a/aa)で4ページとも重大違反0件。gzip後60KB予算をビルドの一部として
  検査(`pnpm --filter apps-site run build`に組み込み済みでCI/pre-pushが自動網羅)。
  **Lighthouseではなく数値予算(§3.3のgzip 60KB)を直接測る方式を採用**——LighthouseのCI上の
  性能スコアはCPU割当でばらつきやすく決定的でないため(判断ごと記録)。

### Phase 3 — 権利判定エンジン（仕様書 §5A・§5.2）

事実収集より先に判定器を完成させる。権利不明資料を本文保存や公開処理へ流さない。

* [x] 権利表示文字列を `normalized_license_id` へ正規化する。
  検証: `cc0`、`cc-by`、`cc-by-sa`、`gov-jp-2.0`、`unknown` のnamedテスト
  （`services/pipeline/src/history_radio/rights/license_normalization.py`）。
* [x] §5Aの判定項目（没年計算、映画1953年、写真1957年、戦時加算等）をpure functionで実装する。
  **年数は資料取得ごとに現在日付で再計算する**。
  検証: 各規則の許可最小ケース、境界、拒否ケースをnamedテストで固定する
  （`services/pipeline/src/history_radio/rights/screening.py`）。年代計算だけで満了と
  分かった資料も、専門家レビューで個別に解禁されるまでは `rights/engine.py` 側で
  `manual_review` に留める（§5A冒頭の方針どおり、Phase 3時点では解禁経路は未実装）。
* [x] 判定不能、入力不足、規約取得失敗を `manual_review` または `deny` へ倒す。
  検証: 欠損値を組み合わせても `allow_public_use` にならない
  （`services/pipeline/src/history_radio/rights/engine.py`）。
* [x] 判定入力、規則バージョン、結果、理由を追記型の監査ログへ残す。
  検証: 同じ資料を新ルールで再判定しても旧判定が消えない
  （`services/pipeline/src/history_radio/store/rights.py` — `rights_records` は
  `decision_id` を主キーとする追記のみのテーブルとし、更新・削除関数を持たせない
  ことで構造的に保証する。保存のたびに `audit_events` へも記録する）。

### Phase 4 — 収集（仕様書 §7・§5.3）

MVP対象はWikipedia、Wikimedia Commons、NDLデジタルコレクションの利用可能区分、ColBase、
および明示的に許可したCC0資料とする。

* [x] 共通取得結果スキーマとアダプターProtocolを実装する。
  検証: 必須フィールド欠落を型検査と実行時検証で拒否する
  （`ingest/schema.py`・`ingest/adapter.py`。storage/publication権限の分離と
  保存許可なしfull_textの実行時拒否を含む）。
* [x] ソースごとに独立アダプターを実装する。APIを優先し、robots.txt、規約、レート制限に従う。
  検証: 記録済みfixtureを用いた統合テストを実ネットワークなしで通す
  （`ingest/adapters/` — Wikipedia・Wikimedia Commons（ファイル単位ライセンスの
  資料単位判定）・NDLデジタルコレクション（「インターネット公開（保護期間満了）」
  区分のみ収集し他区分は例外で拒否）・ColBase（規約ベースCC BY相当）。
  実APIの応答形は2026-07時点の記録fixtureが正——形が変わればパース例外で
  fail closedに止まる。ライセンス正規化へ `ndl-internet-pd` を追加し、
  §5A冒頭の明示列挙に基づき自動採用対象へ組み入れた — config/license_rules.yaml）。
* [x] ドメイン別セマフォ、接続プール、タイムアウト、条件付きGET、指数バックオフを実装する。
  検証: 429、5xx、タイムアウト、途中切断を注入し、上限後に安全に停止する
  （`ingest/crawl_control.py`。Retry-After遵守・過大レスポンス拒否・Clock注入込み）。
* [x] `status: approved` のソースだけを収集し、権利判定を通過しない本文を保存しない。
  検証: `candidate` と `internal_research_only` の全文が永続化されない
  （`ingest/collector.py` — candidateは取得自体を行わず、判定はPhase 3エンジンで
  取得のたびに再計算して追記保存。`store/documents.py` は store_full_text=False で
  受け取った本文を捨てるfail-closed経路）。
* [x] 取得URL、取得日時、レスポンスハッシュ、規約スナップショット、出典関係を保存する。
  検証: 同じ内容の再取得で重複スナップショットを作らない
  （`store/documents.py` — fetch_snapshots/terms_snapshotsともcontent_hashで重複抑制）。

### Phase 5 — 出典独立性・題材選出（仕様書 §6.2・§6A）

* [x] 出典の系統判定（転載、同一一次資料由来、同一組織系列等）を実装する。
  検証: 仕様書の独立性パターンをnamedテストで固定する
  （`select/lineage.py` — §6.2の4パターンをunion-findの併合規則に写した純粋関数。
  一次＋独自二次が2系統を保つケースも固定）。
* [x] §6A.1の候補点計算式をLLM不使用で実装し、点数内訳を保存する。
  検証: 各特徴量を固定した入力から期待点数が得られる
  （`select/scoring.py` — 全特徴量1で45点の初期式・重み注入・範囲外は例外で拒否。
  内訳合計＝候補点の性質も固定）。
* [x] ニュースから使う語は題材選出用に限定し、本文・要約を歴史エピソードの出典にしない。
  検証: ニュースURLが公開出典一覧へ混入しない
  （`select/news_filter.py` — 採用結果 `NewsDerivedTerms` はURLフィールド自体を
  持たないfrozenモデル。混入経路が型レベルで存在しない）。
* [x] 悪感情を呼ぶニュースとの便乗連想を避けるため、死傷、災害、戦争、事件、差別、疾病、
  性犯罪等のカテゴリと禁止語で候補を隔離する。曖昧な場合は採用せず手動確認へ送る。
  検証: 代表的な不適切連想ケースが自動採用されない
  （災害×交通の連想・禁止語1件での全語不採用・カテゴリ/イベント型不明のfail closed・
  個人名の不採用をnamedテストで固定。禁止語辞書はPhase 11で管理画面と併せてconfig化）。
* [x] 類似題材、同一人物、同一事件のクールダウン期間を実装する。
  検証: 期間内の重複候補が順位から除外される
  （`select/cooldown.py` — 境界日込みの除外・期間経過後の解除・順序維持フィルタ）。

### Phase 6 — LLM処理・主張台帳・台本（仕様書 §8・§9）

* [x] OpenRouterの固定モデルをレジストリで管理し、価格、利用可否、構造化出力、日本語回帰を検査する。
  ランダムルーターを本番へ使わない。
  検証: 無料枠外、期限切れ、回帰失敗モデルを採用しない
  （`store/config_loader.load_model_registry` — openrouter/free・/auto等の
  ランダムルーター拒否・構造化出力非対応拒否・日本語回帰未合格拒否をnamedテストで固定。
  実OpenRouter接続の配線はAPIキー到着後 — HUMAN_TASKS.md）。
* [x] 要約、facts、根拠位置をJSON Schemaで受け取る。URL、取得日、ライセンスはプログラムから注入する。
  検証: JSON不正、余分なキー、存在しない根拠位置を拒否する
  （`llm/extraction.py` — §8.2スキーマはextra=forbidで、URL等のフィールド自体を
  持たない。出所は `attach_provenance` が資料レコードから注入する）。
* [x] 根拠抜粋が保存本文と完全一致することをプログラムで検証する。
  検証: 1文字改変した抜粋が拒否される
  （`verify_evidence_quote` — locator位置の部分文字列と完全一致のみ許可。
  保存本文の無い資料の引用も拒否）。
* [x] `claim_ledger` を作り、独立系統2件未満の主張を台本へ入れない。
  検証: 1系統だけの主張が `allowed_in_script: false` になる
  （`llm/ledger.py` — 系統IDの重複は集合で数え、単一系統は qualification=資料帰属を
  強制する — §6.2）。
* [x] §9.1の7段構成で台本を生成し、各外部検証可能文を `claim_id` へ結びつける。
  検証: claim_idのない事実文、台帳にない事実、禁止表現を含む台本を拒否する
  （`script/schema.py`＋`script/validator.py` — 7段の欠落・順序違反も拒否し、
  問題は全件列挙で報告。**生成側のLLM呼び出し配線はOpenRouterクライアント実装時**
  ——検証器が先にあることで、生成が繋がった日から公開検査が効く）。
* [x] 生成結果、プロンプト版、モデルID、入力ハッシュ、出力ハッシュ、使用量を保存する。
  検証: 同じ入力と版ではキャッシュが使われ、二重課金呼び出しをしない
  （`llm/cache.py` — キャッシュキーは (model_id, prompt_version, input_hash)。
  版またはモデルが変われば再実行。実呼び出しはcaller注入でフェイク検証済み）。

### Phase 7 — 音声・スライド動画・関連書籍（仕様書 §10・§10A）

読み辞書（人名・地名・元号・官職）の設計・出典・ライセンス方針、および実装タスクの
詳細な分解は本書 §8（特に §8.4）が正本。VOICEVOXのナレーション品質は読み仮名の
正確さに直結する（仕様書§9.2「読み上げ困難な固有名詞には読み仮名を付ける」）ため、
**§8.4の全タスクを本フェーズの音声生成タスクより前に完了させる**（7ソースの取得
アダプタ・手動修正辞書・解決器・VOICEVOXへの読み適用までを含み、想定より工数が
大きい——1タスクとして見積もらない）。

* [x] VOICEVOX（ずんだもん）の起動確認、音声生成、クレジット自動付与を実装する。
  検証: エンジン停止、タイムアウト、途中失敗で不完全MP3を公開対象にしない
  （`media/voicevox.py` — `VoicevoxClient`。speaker=3〔ずんだもん・ノーマル〕。
  `check_version`でエンジン起動確認、`synthesize`はaudio_query→synthesisの
  2段階すべてで例外を握りつぶさず、非200・空応答・タイムアウトを`VoicevoxError`
  へ。`CREDIT_TEXT="VOICEVOX:ずんだもん"`定数を公開ページ・概要欄・音声末尾で
  共通利用する契約——実際の埋め込み先〔publish/gate層〕はPhase 8以降）。
* [x] FFmpegで音量正規化、無音、破損、長さ、codecを検査する。
  検証: 基準外音量と破損音声を公開ゲートが拒否する
  （`media/ffmpeg_audio.py` — ローカル導入済みのffmpeg/ffprobeへ実際に問い合わせる
  統合テスト。`validate_audio`は問題を全件列挙し、無音・基準外音量・破損・
  長さ不足・非許可codecをすべて検査する。子プロセスは全てタイムアウト付き）。
* [x] 静止画、地図、年表、字幕からスライド動画を生成する。素材不足時は自作図形へフォールバックする。
  検証: 画像0件でも権利上安全な動画を生成できる
  （`media/slides.py` — 台本の7段構成から1スライドずつ決定する純粋関数
  〔題名・60字以内の本文行・8〜20秒の表示秒数・出典番号〕。使える素材が無い
  セクションは`uses_self_drawn_fallback=True`のスライドを必ず生成し、
  スライドが0件になったり生成が止まったりしない。`media/slide_render.py`が
  Pillowで実際にPNGを描画〔自作フォールバックは単色背景のテキストカード〕し、
  FFmpegで静止画列＋音声をMP4へ結合する。日本語フォントが1つも見つからない
  環境ではフォールバックせず`SlideRenderError`で止める（文字化けを黙って
  許容しない）。地図・年表・比較図の高度な自動生成〔Natural Earth・地理院タイル
  連携〕は将来の拡張として残し、本タスクは「画像0件でも安全に動画化できる」
  ことの充足を優先した——テストは実際のffmpeg/ffprobe/Pillow/日本語フォントに
  対する統合テスト）。
* [x] 画像の権利、クレジット、使用箇所を `media_manifest` に記録する。
  検証: クレジット欠落素材をレンダリング前に拒否する
  （`media/media_manifest.py` — `MediaAsset`〔licensed/self_drawn〕。クレジット
  空文字・licensed素材の出典URL/正規化ライセンスID欠落・asset_id重複を全件
  列挙して拒否。自作図形も著作権が発生しないだけでクレジット自体は必須のまま）。
* [x] ISBN、著者、件名標目による関連書籍検索と機械ランキングを実装する。LLMは使わない。
  検証: 書誌系統1件だけの候補を非表示にする
  （`books/search.py` — §10Aの初期式（題名35+件名25+人物20+時代10+新しさ5+
  音声版5）。独立した書誌システムが2件未満の候補・題名だけの曖昧一致・
  閾値未満の候補を除外〔埋め合わせをせず空リストで「関連書籍なし」を表す〕。
  ISBN/Amazon商品識別子の確認可否でアフィリエイトリンク可否を分離）。

### Phase 8 — 公開ページ統合・Cloudflare（仕様書 §10B・§10C）

* [x] Pythonからバージョン付き公開JSON/Markdownを生成し、Astroのcontent collectionで検証する。
  検証: 不正Schema、欠落出典、未知ライセンスでbuildを失敗させる。
  実装メモ: `services/pipeline/src/history_radio/publish/episode_page.py`。
  `EpisodePageData`（Pydantic）は`apps/site/src/content.config.ts`のzodスキーマと
  フィールド1対1対応（camelCaseへは`render_episode_frontmatter`が変換）。
  `validate_episode_page()`が生成時点で拒否する3点: episode_id形式、
  `normalized_license_id`が`rights.engine.AUTO_APPROVABLE_LICENSE_IDS`外の出典、
  claimsの`source_indexes`範囲外参照——全問題を一括報告するfail closed設計
  （script/validator.py等と同じ house style）。検証(validate)と描画(render)を
  分離（resolver.py/slides.pyと同じ「決定と実行の分離」）。
  Python生成→実際に`pnpm --filter apps-site run build`で受理されることを
  手動生成した検証用episodeで実地確認済み（二重の網の両層を実証、検証後は
  scratchとして削除）。単体テストは`tests/publish/test_episode_page.py`(22件)。
* [x] `/episodes/<ID>/` と `/episodes/<ID>/versions/<revision>/` を生成する。
  検証: 再生成が旧版を上書きせず、新版と訂正履歴を追加する。
  実装メモ: `services/pipeline/src/history_radio/publish/episode_publisher.py`の
  `publish_episode()`が2段書き込みを行う——`<episodeId>/versions/<revision>.md`へ
  不変の記録として追加し（既に同一内容で存在するなら冪等・異なる内容なら
  `EpisodePublishConflictError`でfail closed）、`<episodeId>.md`（現行版ポインタ）
  だけを新しい内容へ更新する。revisionの後退・据え置きも拒否する。
  Astro側は`content.config.ts`のスキーマ変更無しで対応: `episodes`コレクションの
  glob(`**/*.md`)がネストした`versions/`配下も自然に拾うため、
  `apps/site/src/pages/episodes/[id]/index.astro`のgetStaticPathsを
  `!entry.id.includes("/versions/")`で現行版ポインタだけに絞り、新設した
  `apps/site/src/pages/episodes/[id]/versions/[revision]/index.astro`が
  アーカイブ済みスナップショット側を担当する（同一episodeIdでの静的パス衝突を回避）。
  共通描画は`apps/site/src/components/EpisodeDetail.astro`に集約。
  実地検証: `publish_episode`で実際にrevision 1→2を生成し、
  `pnpm --filter apps-site run build`で両ページが期待どおり出力されることを確認
  （旧版ページの本文が新版で上書きされていない、現行ページに過去版一覧と
  今回の訂正履歴が追加される）。単体テストは`tests/publish/test_episode_publisher.py`(7件)。
* [x] 主張‐出典対応、コピー、ダウンロード、過去版差分を実データへ接続する。
  検証: 全公開主張から1件以上の有効な出典URLへ到達できる。
  実装メモ: `apps/site/src/components/EpisodeDetail.astro`に4機能を集約。
  (1) 主張‐出典対応: 主張ごとに出典番号リンク`[1][2]`を`#source-N`アンカーへ張り、
  出典リストの各`<li>`に`id="source-N"`を付与——名前の羅列でなく番号リンクで
  実データを指す。(2)(3) コピー・ダウンロード: `episode.body`（rawmarkdown）を
  `<textarea hidden>`へ埋め込み、Clipboard APIでコピー、`episodes/[id]/script.md.ts`
  静的エンドポイント（current・versions両方）でMarkdownダウンロードを提供。
  (4) 過去版差分: `apps/site/src/lib/line-diff.ts`（自前のLCS行差分・新規依存無し、
  vitest単体テスト6件）で直前revisionとの行差分を`versions/[revision]/`ページに表示。
  実フィクスチャ`2026-07-18-tokyo-tower-color`（revision 1→2、
  `publish_episode`で実生成・常時コミット）でPlaywright e2e 6件
  （`e2e/episode-publish.spec.ts`）と既存a11yスイートを実データに対して実行し、
  番号リンクのジャンプ・クリップボードへの実コピー・ダウンロードした
  Markdownの内容一致・追加行のdiff表示を確認済み。Python側は
  `test_every_claim_reaches_at_least_one_valid_source_url`
  （`tests/publish/test_episode_page.py`）でDoDのハッピーパスを明示的に固定。
* [x] R2へハッシュ付きキーでmediaをアップロードし、存在・サイズ・ハッシュを確認する。
  検証: 同じ入力の再実行が重複オブジェクトを作らない。
  実装メモ: `services/pipeline/src/history_radio/media/r2_upload.py`。
  Cloudflare API v4のR2オブジェクトエンドポイント（`Authorization: Bearer`認証）を
  使う——HUMAN_TASKS.mdで依頼している「Cloudflare API トークン（R2編集権限）＋
  アカウントID」がそのままこのクライアントの資格情報になる（S3互換APIのaccess
  key/secretとは別物）。エンドポイントの存在・認証ヘッダ形式・HEAD不可（405実測）は
  `api.cloudflare.com`への実プローブで確認済み（実クレデンシャルでの成功応答は
  HUMAN_TASKS.mdのトークン発行待ち）。`object_key()`がコンテンツのsha256から
  決定的にキーを導出するため、重複防止は事前チェックの有無に関わらずキー設計
  そのものへ構造的に埋め込まれている——アップロード前の存在確認はGETを
  ストリーミングモードで発行しヘッダだけ読んでbodyを読まずに閉じる方式
  （R2 API v4にはHEADもオブジェクト一覧APIも無いため）。既存オブジェクトの
  サイズが今回のバイト列と食い違う場合（キー設計の前提破壊）はfail closedで拒否する。
  単体テスト12件（`tests/media/test_r2_upload.py`、`httpx.MockTransport`で
  GET+PUT/GETのみ/エラー系を検証——同一内容の再アップロードでPUTが
  一切呼ばれないことを直接アサートしている）。
* [x] Cloudflare Pagesへ独自ドメイン、HTTPS、キャッシュ、セキュリティヘッダー、404を設定する。
  検証: プレビューと本番でリンク切れ、mixed content、ヘッダー欠落が0件。
  実装メモ: リポジトリ側で完結する部分を実装・e2eで固定した——独自ドメイン・HTTPS証明書
  発行・Pagesプロジェクトの作成自体はCloudflareダッシュボード操作が必須のため
  HUMAN_TASKS.mdへ依頼済み（未着手）。404は既存の`404.astro`がAstroの規約で
  `dist/404.html`としてビルドされ、Cloudflare Pagesは規約上これを自動でカスタム
  404として認識する（追加設定不要）。`apps/site/public/_headers`へキャッシュ方針
  （content-hashされた資産がまだ無いため`immutable`は使わず、HTML=no-cache、
  audio/pagefind/scripts=中期キャッシュに限定）を追記。`e2e/site-health.spec.ts`で
  3点を固定: (1) `_headers`ファイル自体をパースし必須ヘッダーの宣言漏れが無いこと
  （`astro preview`はCloudflare Pages固有の`_headers`適用を行わないため、ライブHTTP
  応答ではなく設定ファイルを検証——ライブ応答での検証はPagesプロジェクトが実在してから
  別途スモークテストとして追加する）、(2) 全既知ページでmixed content
  （`http://`の能動的な資源読み込み）が0件、(3) 全既知ページの内部リンクに
  リンク切れが0件（外部ドメインへの実アクセスはtest-network違反になるため対象外——
  同一オリジンのみ検証）。`e2e/known-pages.ts`へページ一覧を集約し
  `accessibility.spec.ts`と共有（重複管理によるドリフト防止）。
* [x] Pages/R2からGit上の直前版へ戻す手順を自動化する。
  検証: ステージングで1回ロールバックし、URLとRSS GUIDが変わらない。
  実装メモ: `services/pipeline/src/history_radio/publish/cloudflare_pages.py`の
  `PagesClient.rollback_to_previous()`。Cloudflare Pagesのrollbackは既存デプロイへ
  配信対象を差し替えるだけで新しいURLを発行しない（Cloudflare公式機能の性質——
  本番URL・各エピソードの恒久URLは変わらない）。R2上のmediaオブジェクトは
  ロールバックで一切変更されない（r2_upload.pyは削除APIを持たず、既存オブジェクトを
  不変に保つ設計）。デプロイ一覧を新しい順に取得し2番目（直前版）へロールバックする。
  ロールバック先が無い（デプロイ1件以下）場合はfail closedで拒否する。
  エンドポイントの存在・認証形式は`api.cloudflare.com`への実プローブで確認済み
  （`GET .../deployments`・`POST .../deployments/{id}/rollback`）が、実クレデンシャルでの
  成功応答の中身は未確認——HUMAN_TASKS.mdでPagesプロジェクト作成とトークン発行を依頼中。
  「URLとRSS GUIDが変わらない」というDoDのうち、RSS GUIDの部分はPhase 9でRSSが
  実装されてからでないと検証できない（現時点ではepisode_idから決定的にGUIDを
  導出する設計にする、という設計意図のみ）——**Phase 9完了後に本DoDを再検証すること**。
  単体テスト10件（`tests/publish/test_cloudflare_pages.py`）。

### Phase 9 — RSS・配信先（仕様書 §10D）

* [x] RSS 2.0を静的生成し、GUID、公開日時、enclosure、長さ、MIME、クレジットを固定する。
  検証: 標準バリデーターでエラー0件、過去GUIDの変化0件。
  実装メモ: `apps/site/src/pages/feed.xml.ts`。Astro公式の`@astrojs/rss`
  （既存のXML生成・RFC822日時整形を自前実装せずに済む——依存追加:
  @astrojs/rss — RSS 2.0生成の実績あるAstro公式パッケージ）を使用。
  GUIDは各エピソードの恒久ページURL（link）をそのまま使う（`@astrojs/rss`の既定動作
  で`isPermaLink="true"`）——恒久URLは仕様書§10Bで「削除・URL変更を原則禁止」
  「不変IDは再利用しない」とされているため、GUIDの安定性はepisode_idの設計自体が
  既に保証しており、このファイル側で独自のGUID算出は行わない。enclosureの`length`
  （実バイト数）・`type`（MIME）を生成できるよう、`content.config.ts`の
  episodesスキーマと`episode_page.py`の`EpisodePageData`へ`audioLengthBytes`
  （`audio_length_bytes`）を追加し、`audioUrl`と対で必須というfail closedな検証を
  `validate_episode_page`へ追加した（RSSのenclosureはurlとlengthの両方が
  無いと生成できないため）。クレジットは`<itunes:author>`（`xmlns:itunes`を
  `xmlns`オプションで明示宣言——未宣言のまま名前空間付き要素を使うとXML
  well-formedness違反になる）。
  検証: `e2e/rss-feed.spec.ts`が「標準バリデーター」として
  ブラウザの`DOMParser`によるwell-formedness検証と、RSS 2.0・Podcast
  enclosureの必須要素チェックリスト（channel title/link/description、
  item title/link/guid/pubDate(RFC822)/description/enclosure(url・length・type)・
  itunes:author）をエラー0件で固定。過去GUIDの変化0件は、既存2フィクスチャの
  GUID文字列をハードコードした回帰テストで固定（外部の検証サービスへの
  ネットワークアクセスはtest-network違反になるため、標準バリデーターの
  代わりに構造チェックを自前実装している——実際の配信登録後は各配信先の
  バリデーション結果も確認すること）。単体テスト4件を`tests/publish/test_episode_page.py`
  へ追加（audio_url/audio_length_bytesの対必須検証）。
* [x] YouTube、Podcast、Amazon Music/Audible向けメタデータを同じEpisodeから生成する。
  検証: 全配信先で同じ `episode_id` を冪等キーとして使う。
  実装メモ: `services/pipeline/src/history_radio/publish/distribution_metadata.py`。
  `build_all_distribution_metadata()`が`EpisodePageData`という単一の正本から
  YouTube/Podcast/Amazon Music向けメタデータを導出し、全てのepisode_idが
  元データと一致することを構造的に検証する（決定と実行の分離——実際の
  アップロードAPI呼び出しはここでは行わない）。YouTube説明欄は仕様書§10D
  「説明欄の先頭付近に恒久エピソードページを掲載する」に合わせ先頭にpage_urlを置く。
  privacy_statusは既定`unlisted`（§10D「自動投稿開始前は非公開または限定公開」）。
  Podcastメタデータはaudio_url/audio_length_bytesが揃っていないとfail closedで
  拒否する（RSSのenclosureと同じ前提）。単体テスト7件。
* [x] 自動アップロードはMVPでは限定公開までとし、公開ボタンは最終ゲート通過後だけ有効化する。
  検証: `approved` 未満の状態から公開操作できない。
  実装メモ: `distribution_ledger.py`の`dispatch()`が`episode_state`を検査し、
  `approved`/`published`以外はfail closedで拒否する。`domain/episode_state.py`の
  既存状態機械（Phase 1実装）が既に「publish_readyの次にapprovedを経ないと
  publishedへ進めない」を保証しているため、ここでは配信操作自体を
  approved以降へゲートするだけでよい（状態機械を再実装しない）。
  全12状態（approved/published以外）に対してdispatchが拒否し、
  `publish_fn`自体が一切呼ばれないことをパラメータ化テストで固定。
* [x] 外部配信の成功・失敗・外部IDを記録し、同じ配信先への二重投稿を防ぐ。
  検証: タイムアウト後の再実行でも二重投稿しない。
  実装メモ: `DistributionLedger`が`(episode_id, target)`単位で直近の配信結果を
  保持し、既に`success`が記録済みの組み合わせへは`publish_fn`（実アップロード処理の
  差し替え可能な注入関数——実クレデンシャル取得後に各配信先のクライアントへ
  置き換える）を呼ばない。失敗（failed）は再送禁止の対象にせず次回`dispatch`で
  再試行できる。**スコープの明示**: これが防ぐのは「呼び出し側がタイムアウト等で
  再実行した場合に、こちらの記録に基づいて再送しない」という範囲であり、
  「配信先サーバー側では実際に届いていたが呼び出し側だけタイムアウトした」という
  真のat-least-once問題（配信先APIのidempotency key機能が必要）までは
  解決しない——それは各配信先の実アップロードクライアント実装時に配信先固有の
  冪等キー機構と組み合わせて対処する。単体テスト18件
  （`tests/publish/test_distribution_ledger.py`）。

### Phase 10 — 自動検査ゲート（仕様書 §11）

* [x] 権利、独立出典数、claim_id、転載類似度、禁止語、クレジット、media、RSS、URLをAND評価する。
  検証: 各項目を1つずつ失敗させたケースがすべて `publish_ready=false` になる。
  実装メモ: `services/pipeline/src/history_radio/publish/publish_gate.py`の
  `evaluate_publish_gate()`。**既存の検査ロジックを再実装しない**——
  `episode_page.validate_episode_page`（権利・episode_id形式・audio/RSS前提）、
  `script.validator.validate_script`（7段構成・claim_id・独立系統2件未満の主張の
  不使用）、`media_manifest.validate_media_manifest`（クレジット・出典URL・
  ライセンスID）、`distribution_metadata.build_all_distribution_metadata`
  （YouTube/Podcast/Amazon Music向けメタデータの episode_id 一致）という
  既存の`validate_*`/`build_*`関数をそのまま呼び出し、例外を`GateCheckResult`へ
  変換して束ねるだけにした（決定と実行の分離を保つ）。audioチェックは
  `ffmpeg_audio.validate_audio`が実ファイルへのI/Oを伴うため、ゲート関数自体は
  I/Oを行わず呼び出し側が事前実行した結果（bool + reasons）を受け取る設計にした。
  publish_readyは`all(c.passed for c in checks)`という素直なAND評価——7項目
  それぞれを単独で失敗させ、他の6項目は`passed=True`のまま残ることを
  9件のテストで直接証明した（`tests/publish/test_publish_gate.py`）。
  **スコープの明示**（モジュールdocstringに記載）: 仕様書§11の全17項目のうち
  本ゲートが検査するのは7系統（権利・claim・転載・禁止語・media・音声・
  RSS/URL整合性）。OpenRouterモデルレジストリとの整合性、前回動画との類似度、
  条件付き素材の§5A判定ログ添付、規約再確認期限は実クレデンシャル・実生成物が
  必要なため未対応（Phase 11以降で対応）。
* [x] 和文25文字以上、欧文8語以上の連続一致を転載候補として検出する。
  検証: 出典原文の25文字コピーを拒否する。
  実装メモ: `services/pipeline/src/history_radio/script/reproduction_detector.py`。
  標準ライブラリの`difflib.SequenceMatcher`（Ratcliff/Obershelp法）で2文字列間の
  連続一致ブロックを求める——新規依存を追加しない設計（全文検索エンジン水準の
  精度ではなく、規則ベースの自動ゲート用の実用的な実装であることをdocstringに
  明記）。一致した部分文字列自体にCJK文字が含まれれば和文（文字数閾値）、
  含まれなければ欧文（空白区切り語数閾値）と判定する。`ScriptSentence`へ
  `is_quoted: bool = False`を追加し、引用として明示・出所表示した文
  （仕様書§11「引用として明示・出所表示した箇所は除く」）を検査対象から
  除外できるようにした。単体テスト8件。
* [x] ゲート結果に規則版と全チェックの根拠を保存し、管理画面から追跡できるようにする。
  検証: 公開済み版から当時の検査結果を再表示できる。
  実装メモ: `services/pipeline/src/history_radio/store/gate_results.py`
  （`store/orm.py`の`PublishGateResultRow`・`publish_gate_results`テーブル）。
  `store/rights.py`と同じ「追記のみ（append-only）」方針——更新・削除関数を
  意図的に置かず、同じepisode_id・revisionを再評価しても過去の結果が消えない
  ことを構造的に保証する。保存と同時に`AuditEventRow`も追記する（仕様書§15）。
  `(episode_id, revision)`で検索する`latest_gate_result_for_revision()`が、
  DoDの「公開済み版から当時の検査結果を再表示できる」を満たす——`revision`は
  `PublishGateResult.revision`（評価対象の`EpisodePageData.revision`）から
  来るため、`episode_publisher.py`のバージョン管理と同じ粒度で当時の検査結果を
  特定できる。**「管理画面から追跡できる」というDoDの管理画面側UI配線は
  本タスクの対象外**——apps/adminの実DB接続はPhase 11「Phase 2の画面を
  実DBと実ジョブへ接続」で扱う。ここではその配線が使う永続化・参照関数
  （save/list/latest）を用意した。単体テスト7件。
* [x] ゲート通過後の成果物ハッシュを固定し、公開直前の差替えを拒否する。
  検証: 承認後に台本やmediaを変更すると再承認が必要になる。
  実装メモ: `publish_gate.py`に`PublishGateResult.artifact_hash`
  （episode/script/media_assets一式を正規化JSON化したsha256。`publish_ready`の
  真偽に関わらず常に計算——不合格時の監査にも使える）と、公開直前に呼ぶ
  `verify_artifact_unchanged()`を追加した。現在の成果物から計算したハッシュが
  承認時のハッシュと食い違えばfail closedで`ArtifactLockError`を送出する
  （=再承認が必要）。episode・script・media_assetsのどれか1つでも変更されれば
  ハッシュが変わることを単体テストで直接確認した（`tests/publish/test_artifact_lock.py`
  7件、うち3件は台本のみ/mediaのみ/episodeメタデータのみの変更をそれぞれ
  個別に拒否することを確認）。

### Phase 11 — 管理画面の実運用化（仕様書 §12）

* [x] Phase 2の画面を実DBと実ジョブへ接続し、候補→審査→承認→限定公開を一画面ずつ完成させる。
  検証: 1件を最初から限定公開まで操作するPlaywright E2Eが通る。
  進捗（DoD本体のPlaywright E2Eまで完了）:
  `topics`（候補）・
  候補審査結果の永続化を新設した——`store/candidates.py`・`store/candidate_decisions.py`
  （`store/rights.py`と同じ「追記のみ」方針。候補は選出パイプラインが1回生成した
  時点の点数を記録し更新しない、審査結果は再審査しても過去の判定が消えない）。
  ドメインへ`CandidateDecision`を追加しcontracts（JSON Schema・TypeScript型）を
  再生成した。`select/candidate_review.py`の`review_candidate()`が採用／除外を
  判定する純粋関数——除外には理由の入力を必須にする（タスク3の方針を審査
  アクションへ先取り適用）。`api/db.py`でDBセッションを遅延初期化する
  FastAPI依存性注入を新設（DBパスは`HISTORY_RADIO_DB_PATH`環境変数、既定は
  `data/history_radio.sqlite3`。import時点でファイルを作らない——テストは
  `app.dependency_overrides`で差し替える）。`GET /api/v1/candidates`を実DBへ
  接続し、`POST /api/v1/candidates/{id}/review`・
  `GET /api/v1/candidates/{id}/decisions`を新設。apps/adminの`Candidates.tsx`へ
  採用・除外ボタンを追加（除外は理由入力欄が必須で表示される）。

  承認: `publish/episode_approval.py`の`approve_episode()`が承認操作を担う——
  **ここでは検査を再実行しない**。Phase 10の`evaluate_publish_gate`が既に評価し
  `store/gate_results.py`へ保存済みの結果を参照するだけにする（決定と実行の分離）。
  fail closedの2条件: (1) エピソードの現在状態が`publish_ready`である
  （`domain/episode_state.py`の`transition()`をそのまま呼ぶ——段階飛ばし・逆行の
  防止を再実装しない）、(2) 直近のゲート評価結果が存在し`publish_ready=True`である。
  **重要な設計上の発見**: `Episode.revision`（`store/episodes.py`の楽観ロック用
  カウンタ・状態遷移のたびに増える）と`PublishGateResult.revision`
  （`EpisodePageData.revision` = 公開コンテンツの版）は同名だが別概念——
  承認フローがこれを混同してrevision不一致で常に失敗するバグを実装中に発見し、
  `store/gate_results.py`へ`latest_gate_result_for_episode()`
  （revisionを問わず直近の評価結果を返す）を追加して解消した。`store/episodes.py`へ
  `list_episodes()`を追加。`POST /api/v1/episodes/{id}/approve`・
  `GET /api/v1/episodes`を新設。apps/adminへ新規`Episodes.tsx`画面
  （一覧・`publish_ready`状態にだけ承認ボタンを表示）を追加。

  限定公開: `publish/episode_publishing.py`の`publish_episode_limited()`が
  `approved`状態のエピソードを`published`へ進め、配信台帳
  （Phase 9の`distribution_ledger.dispatch`）へYouTube限定公開の試行を記録する。
  YouTubeの「限定公開（unlisted）」が仕様書§10D「自動投稿開始前は非公開または
  限定公開でアップロードする」に対応する公開区分そのもの
  （`distribution_metadata.YouTubeMetadata.privacy_status`の既定値も`unlisted`）。
  **`distribution_ledger.DistributionLedger`はPhase 9時点ではインメモリ実装
  だったため、管理API経由での利用（プロセス再起動をまたぐ二重投稿防止）に耐えない
  ——`store/distribution_records.py`へ同じインターフェースをDB永続化で実装する
  `DbDistributionLedger`を追加し、`dispatch()`のロジック自体は再利用した**
  （新テーブル`distribution_records`は`(episode_id, target)`複合主キーで直近状態
  だけを保持——`DistributionLedger`と同じ意味論。全試行履歴は`audit_events`側に
  追記される）。実際のYouTube Data APIへはまだ接続していない
  （`publish_fn`はプレースホルダー識別子を返すだけ——HUMAN_TASKS.mdでYouTube連携の
  認証情報取得を依頼するまでの暫定実装）。`POST /api/v1/episodes/{id}/publish`を
  新設し、apps/adminの`Episodes.tsx`へ`approved`状態にだけ表示される限定公開
  ボタンを追加した。

  候補採用時にEpisodeを自動作成する連携を実装: `api/main.py`の
  `_ensure_episode_for_adopted_candidate()`が採用決定の直後に呼ばれ、
  `episode_id`には`candidate_id`をそのまま流用する
  （`Episode.episode_id`には公開ページ用`<公開日>-<英語スラグ>`形式のような
  制約が無い——スラグ変換は実際に公開する段になってから検討すればよいと判明し、
  当初懸念していた「topic_titleからの英語スラグ導出」問題は前提から外れた）。
  再審査での重複作成は既存エピソードの有無チェックで防ぐ。

  **DoD本体の「1件を最初から限定公開まで操作するPlaywright E2Eが通る」を実施・
  合格**: `playwright.config.ts`を`projects`（`site`/`admin`でbaseURLを分離）＋
  共通`webServer`配列（astro preview・`apps-admin`のvite dev・
  `uv run uvicorn`の3プロセス、admin用FastAPIは`HISTORY_RADIO_DB_PATH`で
  専用DB`data/e2e-admin.sqlite3`を使い開発用DBを汚さない）へ拡張した。
  実際の収集・選出・台本生成・音声合成・自動検査ゲート実行（Phase 4〜10）は
  まだ管理画面に接続されていないため、それらを飛ばす2本のテスト専用シード
  スクリプト（本番コードから呼ばれない）を追加: `scripts/e2e_seed_candidate.py`
  （候補を1件DBへ直接投入）、`scripts/e2e_fast_forward_episode.py`
  （エピソードを`publish_ready`まで状態遷移させ合格ゲート結果を記録）。
  `e2e/admin/candidate-to-published.spec.ts`が候補一覧での採用クリック→
  （シードでpublish_readyへ進める）→エピソード一覧での承認クリック→
  限定公開クリックまでを実ブラウザ操作・実API呼び出しで検証し合格した
  （`uv run scripts/dev.py e2e`で site 31件・admin 1件の計32件通過）。
  ダッシュボード・ジョブ一覧は引き続きfixture（実ジョブ接続はタスク2）。
  本コミットでの追加分: Python単体テスト4件
  （api/main.py 候補採用時のEpisode自動作成関連）、Playwright E2E 1件
  （admin project新設）。累計: Python 586件・TypeScript 31件（apps-admin）・
  Playwright 32件（site 31・admin 1）。
* [x] 長時間ジョブのSSE進捗、キャンセル、再実行、ログ追跡を実装する。
  検証: ブラウザ再読込後も正しいジョブ状態へ復帰する。
  進捗（DoD本体のPlaywright E2Eまで完了）:
  `store/jobs.py`を新設し`jobs`テーブルを実際に読み書きするようにした
  （`GET /api/v1/jobs`はfixtureから実DBへ切替。Job行は`job_id`単位で1行を持ち
  status/progress/errorをその場で更新する——append-onlyではない。ログだけは
  別テーブル`job_log_entries`へ追記のみ）。`domain/models.py`の`Job`へ
  `progress`・`cancel_requested`・`retry_of`・`created_at`を追加し、
  新設`JobLogEntry`をcontractsへ追加した。`JobStatus`へ`cancelled`を追加。

  実行するジョブの中身は「エピソード生成ジョブ」1種類:
  `jobs/runner.py`の`run_episode_generation_job()`がエピソードを現在の状態から
  `publish_ready`まで工程単位で進める——`domain/episode_state.py`へ追加した
  `remaining_forward_states()`（`FORWARD_SEQUENCE`を公開化して導出）で
  「どこから再開すべきか」を1箇所に決め、各段階は`store/episodes.py`の
  `update_episode_state()`（本物の永続化・楽観ロック）を呼ぶ——段階飛ばし・逆行の
  防止を再実装しない。**実際のLLM台本生成・VOICEVOX音声合成・FFmpeg動画生成・
  自動検査ゲート評価（Phase 6〜10）はまだこのジョブへ接続していない**——
  各工程の重い生成処理そのものは各段階を実際に接続する後続フェーズの仕事で、
  本ジョブは状態遷移の実行とキャンセル・進捗・ログの枠組みを提供するだけ
  （publish_readyに達しても偽のゲート合格結果は作らない——e2e専用シード
  スクリプトとは違い、本物の管理APIが嘘の合格を記録しないようにする）。

  実行はFastAPIのイベントループと独立した`threading.Thread`（daemon）——
  `POST /api/v1/episodes/{id}/generate`がジョブ行を作りスレッドを起動して
  即座に返す（`202`・返すJobは常にスレッド起動前のqueuedスナップショット）。
  キャンセルは共有メモリのフラグではなく`jobs.cancel_requested`列で行う
  ——`POST /api/v1/jobs/{id}/cancel`がフラグを立てるだけで、実行側が各工程の
  直前に確認して自ら停止する（プロセス内状態を持ち回らない設計——ブラウザ
  再読込やサーバー内の別リクエストからでも同じ行を見て判定できる。DoD本体の
  「再読込後も正しい状態へ復帰する」を裏で支える）。再実行
  （`POST /api/v1/jobs/{id}/retry`）は失敗/blocked/cancelledのジョブに対してのみ
  新しいjob_idで別行を作り（`retry_of`で元のjob_idを辿れる）、エピソードの
  現在の状態から続きを行う（仕様書§14「工程単位で再実行」）。

  キャンセル中断のテスト（`tests/jobs/test_runner.py`）はtime.sleep等の実待機を
  使わず、`on_before_step`フック+`threading.Event`でジョブ実行スレッドと決定的に
  同期する。API層のテスト（`tests/api/test_main.py`）は`get_session_maker`も
  FastAPIの依存性注入にしてdependency_overridesで差し替え可能にし
  （バックグラウンドスレッドが本番既定DBへ触れないように）、
  `HISTORY_RADIO_JOB_STEP_DELAY_SECONDS=0`環境変数でテスト実行を高速化した
  （本番既定値は1秒/工程）。

  SSE配信エンドポイント`GET /api/v1/jobs/{id}/events`を実装した
  （`jobs/events.py`の`stream_job_events()`が`jobs`/`job_log_entries`を
  一定間隔でポーリングして`data: {...}\n\n`形式で配信するだけ——配信側は状態を
  持たない）。**実機で踏んだ罠**: 最初は同期`time.sleep()`ループとして書いていた
  ——FastAPIは同期`def`のパスオペレーションを限られたスレッドプールで実行するため、
  SSE接続1本がジョブの生存期間まるごとスレッドを1つ占有し続け、同時に複数の
  SSE接続が開くとスレッドプールが枯渇して`/dashboard`のようなDB無関係の
  エンドポイントまで応答不能になった（Playwright E2Eで実際に発生・再現）。
  `asyncio.sleep()`を使う非同期ジェネレータへ書き換え、`request.is_disconnected()`で
  クライアント切断も検出するようにして解消した。

  管理画面: `Episodes.tsx`の生成対象状態（publish_ready未満）に「生成開始」ボタンを
  追加し`POST /episodes/{id}/generate`を呼ぶ（返るのはJobでありEpisodeではないため、
  承認・限定公開とは別に「開始済み」フラグだけ持ち、ジョブ一覧への導線を示す）。
  `Jobs.tsx`はGET /jobs（DBの正本）を初回取得したうえで、その時点でqueued/running
  だったジョブだけEventSourceで購読し続け、進捗バー・状態・ログをその場で更新する
  ——ブラウザ再読込時はこの初回取得が常に正しい現在値を返すため、購読も
  そこから再開されるだけで状態が失われない（Phase 11タスク2 DoD本体）。
  キャンセル・再実行ボタンをジョブ行へ追加した。

  DoD本体を検証するPlaywright E2E（`e2e/admin/job-progress-reload.spec.ts`）を追加:
  候補採用→生成開始→実行中の進捗を確認→**ブラウザ再読込**→再読込後も
  queuedへ戻らず正しい状態(実行中/成功)であること→最終的にpublish_readyまで
  到達することを検証する1件と、キャンセル→再読込後もキャンセル済みとして
  復帰することを検証する1件の計2件。実行時間を現実的にするため
  `playwright.config.ts`のuvicorn起動envで`HISTORY_RADIO_JOB_STEP_DELAY_SECONDS=0.3`・
  `HISTORY_RADIO_JOB_SSE_POLL_SECONDS=0.1`を設定した（0にすると一瞬で完了し
  「実行中の途中」を観測できないため）。

  **実機で踏んだもう1つの罠**: このE2E追加中、開発機のポート5173が別プロジェクトの
  devサーバーと衝突し、Playwrightの`reuseExistingServer`がそれを「起動済み」と
  誤認してadmin E2Eが全滅する事故が発生した——admin用vite devサーバーを
  `--port 5183 --strictPort`でE2E専用ポートに固定し（ポートが埋まっていたら
  黙って次のポートへ逃げず即失敗させる）、`api/main.py`のCORS許可オリジンへ
  5183を追加して解消した。

  実際のLLM台本生成・VOICEVOX音声合成・FFmpeg動画生成・自動検査ゲート評価
  （Phase 6〜10）は依然としてこのジョブへ未接続——本タスクが提供したのは
  状態遷移の実行とSSE進捗・キャンセル・再実行・ログの枠組みであり、各段階の
  実処理を接続するのは各段階を実際に統合する後続フェーズの仕事。
  本コミットでの追加分: Python単体テスト3件
  （jobs/events 3件・test_main.pyのSSEエンドポイント関連2件は既存カウントに含む）、
  TypeScript単体テスト8件（Jobs.test.tsx新規）・既存Episodes.test.tsx4件追加、
  Playwright E2E 2件。累計: Python 625件・TypeScript 42件（apps-admin）・
  Playwright 34件（site 31・admin 3）。
* [x] 破壊的操作は確認、理由入力、監査ログを必須にする。
  検証: 理由なしの却下、削除、公開取消をAPIが拒否する。
  候補の除外（却下）は`select/candidate_review.py`が理由なしをfail closedで
  拒否し、`store/candidate_decisions.py`が判定と同一トランザクションで
  `AuditEventRow`を追記する（仕様書§15・Phase 11タスク1で実装済み）。

  削除・公開取消は仕様書に具体的なUI操作としての定義が無い
  （§15は「公開・訂正・削除・権利判定変更を追記型監査ログへ記録する」という
  一般原則のみ）ため、本タスクで対象・意味論を決めた。§10B「公開済みページの
  削除・URL変更を原則禁止する」「法的削除要請や重大な権利問題では本文・
  メディアを非公開化できるが、可能な範囲でURLに理由と履歴を残す」から、
  削除と公開取消を対照的な操作として設計した:
  - **削除**（`publish/episode_deletion.py`）: `published`でないエピソードの行を
    実際に削除する（`store/episode_deletion.py`）。理由なし・公開済みは
    fail closedで拒否する。関連するjob・ゲート結果の行はカスケード削除しない
    （実行履歴として独立に価値を持つため）。削除の事実と理由は行の削除と
    同一トランザクションで`AuditEventRow`へ記録する——行が消えた後も
    「いつ・誰が・なぜ削除したか」だけは監査ログに残る。
  - **公開取消**（`publish/episode_revocation.py`）: `published`状態のエピソードに
    対してのみ許可し、理由なし・未公開・二重取消はfail closedで拒否する
    （`store/episode_revocations.py`）。**episodeの行・状態は変更しない**
    ——公開済みページのURL変更を原則禁止する仕様書の方針に従い、取消の事実は
    `audit_events`への追記だけで表現する（`action="publish_revoked"`）。
    実際のYouTube動画取り下げ・サイトページの非公開化はまだ接続していない
    （限定公開のYouTube Data API連携と同じくプレースホルダー段階——
    HUMAN_TASKS.md参照）。

  新設エンドポイント: `POST /episodes/{id}/delete`（`reason`必須・成功時204、
  行が実際に消えるため`response_model`なし）・`POST /episodes/{id}/revoke`
  （`reason`必須・成功時200でAuditEventを返す）。管理画面`Episodes.tsx`へ
  `published`以外の行に削除ボタン、`published`の行に公開取消ボタンを追加
  ——どちらもCandidates.tsxの除外フローと同じ「クリックで理由入力欄を開き、
  確定ボタンで送信する」2段階UXにした（`破壊的操作は確認、理由入力…を必須に
  する」の「確認」に相当）。削除成功後の行は一覧から消え、公開取消成功後は
  「取消済み」表示に変わる。
  本コミットでの追加分: Python単体テスト17件
  （publish/episode_deletion 4件・publish/episode_revocation 5件・
  api/main(削除・取消関連) 8件）、TypeScript単体テスト7件
  （Episodes.test.tsx追加）。累計: Python 642件・TypeScript 48件（apps-admin）。
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
Web:       biome → tsc -b → vitest → astro build → pagefind → bundle-budget
Browser:   Playwright smoke → axe → link check
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

---

## 8. 読み辞書計画（人名・地名・元号・官職）

VOICEVOXナレーションの読み仮名付与（仕様書§9.2）に使う辞書の設計。
「全部入りで高精度な単一辞書」は存在しないため、**複数辞書＋プロジェクト専用の
手動修正辞書を重ねる**構成にする（2026-07-16 調査・決定）。

### 8.1 採用データソースと商用利用条件

| 分類 | データ | 商用利用 | 条件・注意 |
|---|---|---|---|
| 一般語・基本固有名詞 | SudachiDict（full） | OK | Apache-2.0。ライセンス文・著作権表示を保持 |
| 人名・地名の読み補完 | JMnedict | OK | CC BY-SA 4.0。出典表示必須。**由来データは別テーブルで分離管理**（派生辞書を公開するとSA継承が及ぶ） |
| 歴史人物・歴史地名・官職 | Wikidata（P1814 name in kana） | OK | CC0。読み未登録の項目も多い——補完用 |
| 重要人物の読み・別名・生没年 | Web NDL Authorities | OK | 「Web NDL Authoritiesから取得」と出典明示。無料APIあり |
| 現代地名 | デジタル庁 アドレス・ベース・レジストリ | OK | PDL1.0。出典と加工した旨を表示 |
| 元号 | 独自小型辞書（約250件） | — | Wikidata・国会図書館資料を基に手作業で一度検証して自作 |
| 明治期の官職・行政用語 | NDL「ヨミガナ辞書」（PDF） | 慎重 | 読みの**確認資料**として使う。PDFから抽出した辞書全体の再配布はしない |
| 古語 | 国語研 歴史UniDic | 保留 | 営利目的は事前相談と明記——**許可確認まで使わない** |
| 現代地名（補助） | 日本郵便 郵便番号CSV | 慎重 | 無料公開と商用再配布許可は別。主辞書にしない |

### 8.2 解決順序（LLMに読みを推測させない）

```text
1. 手動修正辞書（config/readings/manual.yaml — 人間が検証した正）
2. 元号・官職専用辞書（自作・検証済み）
3. Wikidata / Web NDL Authorities（歴史人物・歴史地名）
4. 地名辞書（アドレス・ベース・レジストリ）
5. JMnedict（人名・地名の読み候補）
6. SudachiDict（一般語）
7. どの層でも未解決 → `unresolved` として公開前レビューへ（公開ゲートで停止）
```

歴史人名・官職は同じ表記でも時代・人物・用法で読みが変わる（例: 判官=ほうがん/はんがん）
ため、手動修正辞書は文脈依存の複数読みを表現できる形式にする。

### 8.3 リポジトリ上の扱い（ライセンス安全策）

- 大容量の外部辞書本体は**コミットしない**——セットアップ時に公式配布元から
  ダウンロードするスクリプトを用意し、取得日・件数・ハッシュを記録する。
- データソースごとに別テーブルで保持し、各レコードに `source_url` と `license` を残す
  （単一辞書に混ぜて再配布しない——特にJMnedict由来はCC BY-SAの継承対象になり得る）。
- `THIRD_PARTY_NOTICES.md` に出典・ライセンス・取得日を一覧し、必要なライセンス原文を
  `licenses/` に置く。公開サイトには使用データ・ライセンスのページを設ける。
- **手動修正辞書（完全自作分）はこのツールの資産**——外部由来と混ざらないよう
  独立ファイルで管理する。

### 8.4 実装タスク（詳細 — Phase 7着手前に完了させる）

「辞書を1個読み込むだけ」ではない——ソースが7種、ライセンスが7通り、かつ
VOICEVOXへの実際の読み適用まで含むため、Phase 4〜6と同等の粒度で分解する。
各タスクはPhase 7の音声生成タスクより**前に**完了させる（§9.2「読み上げ困難な
固有名詞には読み仮名を付ける」の前提を先に満たす）。

**基盤**

* [x] 置き場を確定する: `config/readings/`（手動修正辞書・元号辞書・ソースメタデータ）、
  `scripts/readings/`（外部取得スクリプト）、`licenses/`（ライセンス原文）、
  `THIRD_PARTY_NOTICES.md`。取得済み辞書本体の生成先は `artifacts/readings/`
  （`.gitignore`済みの`artifacts/`配下——GENERATED_PATTERNSより強く、
  コミット自体が構造的に不可能。当初案のGENERATED_PATTERNS登録は
  `THIRD_PARTY_NOTICES.md`（生成物だがコミットする側）にのみ適用した）。
  検証: `STRUCTURE.md`に各置き場が現れる。
* [x] 全ソース共通の`ReadingEntry`型（surface/reading/kind/context/confidence/
  source_id/source_url/license/fetched_at）をPydanticで定義する
  （`readings/entry.py` — `domain.base.SchemaModel`継承・frozen。読みはカタカナ統一
  〔VOICEVOX注入形式〕を実行時検証）。
  検証: 未知フィールド・必須項目欠落・非カタカナ読みを拒否するnamedテスト。
* [x] `config/readings/sources.yaml`にソースごとのメタデータ（id・license・
  attribution_text・redistribution_allowed）を登録し、`config_loader.py`と同じ
  パターン（Pydantic検証＋重複ID検査）で読み込む（`readings/sources_config.py`。
  §8.1の7ソースを初期登録済み）。
  検証: 未登録の`source_id`を持つ`ReadingEntry`を拒否する。
* [x] `THIRD_PARTY_NOTICES.md`を`sources.yaml`から機械生成するスクリプトを実装する
  （手書きにするとソース追加時に更新し忘れる——ドリフトを構造的に防ぐ。
  `readings/notices.py`＋`scripts/readings/generate_third_party_notices.py`。
  再生成==コミット済みのドリフト検査テスト・自作/外部の分離出力も固定）。
  検証: `sources.yaml`にソースを1件追加すると、生成物に出典行が1行増えるnamedテスト。

**ソース別アダプタ（§8.1の7ソース）**

* [x] SudachiDict（full）を導入し、形態素解析結果から読み（カナ）を取得するアダプタを
  実装する。
  検証: 既知語の読みが引ける固定テスト。Apache-2.0のライセンス文が
  `THIRD_PARTY_NOTICES.md`に含まれることを検査
  （`readings/sudachi.py` — 解決順序§8.2の最下層としてconfidence 0.5固定。
  品詞タプルから人名/地名/一般を判定し、名詞以外・カタカナ化不能語は除外。
  `sudachipy`/`sudachidict-full`を依存追加——型スタブ非配布のため
  `TokenLike` Protocolで受け渡しを自前保証しbasedpyright設定で対処）。
* [x] JMnedict（XML/JMdict形式）をパースし、人名・地名の読み候補テーブルへ変換する
  取得スクリプトを実装する。**JMnedict由来レコードは専用テーブルで分離管理**し、
  他ソースと混在させない（CC BY-SAのSA継承を派生辞書全体へ広げない — §8.3）。
  検証: サンプルXMLからのパース結果を固定テストで検証。他ソース由来テーブルに
  JMnedict由来行が1件も紛れ込んでいないことを検査するnamedテスト
  （`readings/jmnedict.py`＋`readings/store_jsonl.py` — ソース別JSONLへの書き込みは
  source_id不一致を1件でも拒否、読み込み時も混入検出。企業名等の非対象name_typeと
  かな見出しのみのエントリは対象外。**XML全体の取得スクリプト（~100MBのダウンロード）
  はSudachiDict導入と同じ回で実装**——パース・分離の契約が先）。
* [x] Wikidata SPARQL（P1814: name in kana）で歴史人物・歴史地名の読みを取得する
  アダプタを実装する。レート制限・タイムアウト・リトライを実装する。
  検証: 記録済みfixtureレスポンスでの統合テスト（実ネットワーク不要）。
  クエリ失敗時は当該語が例外を投げず`unresolved`候補へ落ちることを固定
  （`readings/wikidata_kana.py` — 取得はPoliteFetcher経由〔レート制限・リトライは
  crawl_control層〕。HTTPエラー・応答不正・カタカナ化不能値はすべて空リストへ）。
* [x] Web NDL Authorities APIで人名・地名の読み・別名・生没年を取得するアダプタを
  実装する。
  検証: fixtureベースの統合テスト。「Web NDL Authoritiesから取得」の出典表示が
  結果へ必ず付与される
  （`readings/ndl_authorities.py` — 実測で確認したSPARQLエンドポイント
  `id.ndl.go.jp/auth/ndla/sparql`＋エンティティJSON-LD`<uri>.json`の2段階取得。
  「姓, 名, 生没年」形式の見出し語・読みから日付部分を除いて姓名を連結。
  別名〔altLabel〕の読みも取得。fail-closed: 通信・解析失敗は例外でなく空リスト）。
* [x] デジタル庁アドレス・ベース・レジストリから現代地名の読みを変換するスクリプトを
  実装する（PDL1.0が求める出典表示・加工した旨の注記を満たす）。
  検証: 変換後の各レコードに出典表示と加工注記が欠けていないことを検査
  （`readings/address_registry.py` — **本session環境から`catalog.registries.digital.go.jp`
  へ接続できず**〔DNS解決不可。Wikipedia/Wikidata/NDL等の既知ドメインは到達可能なため
  環境固有の到達性の問題と判断〕実CSVヘッダーを確認できていない。そのため列名を
  `AddressColumns`パラメータで受け取るheader駆動の変換器として実装——ポジション
  依存にせず、実ヘッダー名は実CSV取得時に確認・指定する。出典表示＋「加工して作成」の
  文言を`ReadingEntry.license`へレコード単位で複製し欠落を構造的に防ぐ。
  一括ダウンロードスクリプト自体はJMnedict同様、実データ確認後の別タスクとして残す）。
* [x] 元号（和暦）の読み辞書 `config/readings/eras.yaml`（約250件）を、Wikidata・
  国会図書館資料を基に人手で一度検証して自作する。
  検証: 全件が一意な元号名を持ち、年代の重複・欠落がないことを
  `config_loader.py`と同じパターンで検査する
  （248件を生成——年代・QIDはWikidata実データ〔P31=Q24706、2026-07-17取得〕、
  読みは歴史年表の通行読みで自作。全件`verified: false`で**人手検証は未了**
  ——検証したらtrueへ〔confidence 0.9→1.0〕。`readings/era_dictionary.py`が
  一意性・start≤end・大宝701年以降の連続性〔2年超の空白拒否・南北朝並立は許容〕・
  無期限元号1件のみを機械検査）。
* [x] NDL「ヨミガナ辞書」（PDF）を**確認資料**として使うワークフローを
  `config/readings/README.md`等にドキュメント化する（辞書全体は再配布しない——
  `manual.yaml`へ個別エントリを追加する際の裏取りにのみ使う）。
  検証: `manual.yaml`の該当エントリに出典コメント（例:「NDLヨミガナ辞書で確認」）が
  ある行だけがこの資料由来と扱われることをレビュー観点として明記する（機械検査は
  対象外——目視レビューの手順を残すだけで良い。`config/readings/README.md`に記載）。
* [x] 国語研 歴史UniDicは統合しない（営利利用の事前相談が必要——許可確認までは
  §8.1どおり保留）。統合を保留している旨と相談状況を`HUMAN_TASKS.md`に反映する。
  検証: なし（実装タスクではなく状態記録。HUMAN_TASKS.md「読み辞書」節に記録済み）。

**手動修正辞書・解決器・VOICEVOXへの適用**

* [x] `config/readings/manual.yaml`のSchema（surface/reading/kind/context/confidence）
  を確定し、Pydanticで検証する。同一表記の文脈依存複数読み（例: 判官=ほうがん
  〔源平合戦文脈〕/はんがん〔現代文脈〕）を表現できる形にする。
  検証: 不正エントリを起動時に拒否するnamedテスト＋同一表記・複数読みが
  contextキーで正しく引き分けられるnamedテスト
  （`readings/manual_dictionary.py` — `context=None`〔既定読み〕はsurfaceごとに
  1件しか登録できず、2件目は必ず(surface, context)の重複検出に掛かる構造。
  `config/readings/manual.yaml`に判官の実例を収録）。
* [x] エピソードの時代・地域タグと`manual.yaml`の`context`を突き合わせる規則を
  実装する。
  検証: context不一致時はどちらの読みも採用せず`unresolved`へ倒すfail-closedな
  namedテスト（LLMに読みを推測させない — §8.2）
  （`readings/context_matching.py` — 複数文脈が同時一致する曖昧なケースも
  不採用。文脈非依存の既定エントリが別途あれば、それは明示的なフォールバックとして
  採用する〔推測ではなく人間が明示登録した既定値のため〕）。
* [x] §8.2の優先順位（手動修正辞書→元号・官職辞書→Wikidata/NDL→地名辞書→
  JMnedict→Sudachi→unresolved）でレイヤーを合成する解決器を純粋関数で実装する。
  検証: 各層単独のnamedテスト＋上位層が下位層の結果を上書きする優先順位テスト
  （`readings/resolver.py` — 手動辞書は候補があるのに決められない場合、下位層へ
  フォールバックせずその場でunresolvedにする〔曖昧さを下位層の機械読みで
  誤魔化さない〕。手動辞書以外の層も、層内で読みが割れたら次層へは進まず
  即unresolved——上位層飛ばしで下位層に妥協しない）。
* [x] どの層でも解決できない語を`unresolved`として記録し、公開ゲート
  （Phase 10）で当該台本の公開を止める。
  検証: 全層で該当なしの語が`allow`側の経路へ紛れ込まないfail-closedテスト
  （resolver.pyの`UnresolvedReading`型。**Phase 10公開ゲートへの実配線は
  Phase 10自体が未実装のため後続**——本タスクでは「unresolvedが
  resolved側と型レベルで混同されない」ことまでを固定する）。
* [x] 解決済みの読みをVOICEVOXのAudioQuery（アクセント句）へ注入する変換層を
  実装する（対象表記をカナ読みへ置換する、またはVOICEVOXのユーザー辞書API経由で
  登録する）。
  検証: 既知語を含む台本からのAudioQuery生成結果に注入した読みが反映されている
  ことを固定テスト（VOICEVOXは起動せずモック）
  （`media/voicevox.inject_readings` — アクセント句APIではなくテキスト置換方式を
  採用。文字数の多い表記から置換し部分一致誤爆を防ぐ。`synthesize()`へ渡す前段の
  純粋関数として分離し、audio_query呼び出し自体は注入済みテキストをそのまま
  送る形で合成される）。
* [x] `unresolved`語を1件でも含む台本は音声生成ジョブに進めない。
  検証: `unresolved`語1件でもジョブが`blocked`へ遷移するnamedテスト
  （`readings/media_gate.py` — `decide_media_job_status`。VOICEVOX本体との
  配線は上記タスクと同時に行う）。
* [x] 外部辞書取得スクリプトの実行結果（取得日・件数・ハッシュ）を記録し、
  再実行時の差分検出を可能にする。
  検証: 同一入力での再取得が同一ハッシュになる決定性テスト
  （`readings/fetch_manifest.py` — エントリ集合を安定ソートしてからハッシュ化
  するため、取得順序が変わっても同一内容なら同一ハッシュ）。
