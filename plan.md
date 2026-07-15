# plan.md — 歴史スライド動画・自動生成ツール 実装計画

設計根拠の正本は [history_radio_spec_v0_4.md](history_radio_spec_v0_4.md)(以下「仕様書」)。
本書は仕様書を実装可能な単位へ分解したもので、AGENTS.md §4 の方針(小タスク＋各タスクの
検証コマンド)に従う。フェーズを跨ぐ大きな`feat:`コミットは、本書の該当タスクへの差分を
同一コミットに含める(`feat-without-plan` hard 検査 — .guardrails/GUARDRAILS.md §3.4)。

## 前提として決めること(Step 0 — AGENTS.md §0/§5 の「未定」を確定する)

実装コードがまだ無いため、着手前に以下を確定する。**未確認のまま Phase 1 へ進まない**。

- **提案**: 生成パイプライン(クローラー・権利判定・OpenRouter呼び出し・VOICEVOX・FFmpeg・
  関連書籍検索)は `bindings/catalog.md` の `python-uv` 列を採用する(uv 前提が
  kit 既定で導入済み・スクリプト連携がしやすい)。
- **提案**: 公開基盤(§10C)は MVP では **Cloudflare Pages(静的HTML)＋R2** のみを実装し、
  Workers／D1 は導入しない(§12 管理画面・RSS動的応答は静的生成＋ローカル管理CLIで代替し、
  仕様の「D1は管理用メタデータに限定・唯一の保存先にしない」という制約とも整合する)。
  Workers/D1 が必要になった時点(管理画面のWeb化等)で列を追加する。
- 上記2点をユーザー承認後、`bindings/catalog.md` の採用列を刻印し(§12.7)、
  `scripts/repo_scan.py` / `scripts/dev.py` / `.pre-commit-config.yaml` / CI へ
  paste-block を充填する(ガードレールキットの Step 0/2、本計画の対象外)。

## フェーズ構成

仕様書 §6(処理フロー7工程)・§16(MVP範囲)・§17(受入条件の段階制)にそのまま対応させる。
各フェーズは「公開しない状態で単体検証できる」単位に区切ってあり、フェーズ順は
§6.1 の状態機械(`collected → … → published`)の順序と一致する。

---

### Phase 0 — プロジェクト骨格

- [ ] `pyproject.toml` 作成(`uv init` 相当)。依存追加は空でよい
      (`依存追加:` 行は §10 の undeclared-dependency 検査対象——最初のコミットから記録する)。
      検証: `uv run python -c "print('ok')"` が通る。
- [ ] `config/source_registry.yaml`・`config/license_rules.yaml`・`config/model_registry.yaml`
      を仕様書 付録B の最小例1件(`wikimedia_commons`)だけ入れて作成。
      検証: `uv run python -c "import yaml,sys; yaml.safe_load(open('config/source_registry.yaml'))"`
      がエラーなく1件を読める。
- [ ] `src/` 配下にレイヤー骨格を作る: `src/ingest/`(収集)・`src/rights/`(§5A判定)・
      `src/select/`(§6A選出)・`src/llm/`(§8)・`src/script/`(§9)・`src/media/`(§10)・
      `src/books/`(§10A)・`src/publish/`(§10B/§10C)・`src/distribute/`(§10D)・
      `src/gate/`(§11自動検査)・`src/store/`(§13エンティティ)。
      レイヤー依存方向を AGENTS.md §5 へ転記し、`layer-violation` を有効化する。
      検証: `uv run scripts/dev.py check` が `layer-violation` 系の HARD を出さない。
- [ ] Step 0 の決定を `bindings/catalog.md` へ刻印し、`scripts/dev.py` の `up`/`test`/`fmt`
      を python-uv 列の値で配線する。
      検証: `uv run scripts/dev.py test` が「テストなし」で exit 0(空でも通る状態)。

### Phase 1 — 権利判定エンジン(§5A・§5.2)— 収集より先に作る

事実収集より先に判定器を作る理由: §11 の公開ゲートは「権利判定を通らない資料は
そもそも保存・使用しない」前提のため、収集モジュールが依存する。

- [ ] `src/rights/normalize.py`: 権利表示文字列 → `normalized_license_id`(§5.2表)への
      マッピング関数。
      検証: `cc0`/`cc-by`/`cc-by-sa`/`gov-jp-2.0`/`unknown` 等の入力→期待IDをアサートする
      単体テスト(pytest)を同梱し green。
- [ ] `src/rights/screening.py`: §5A の13項目(没年計算・映画1953年・写真1957年・戦時加算等)
      を実装し、`allow_public_use / internal_research_only / manual_review / deny` を返す。
      **年数計算は資料取得ごとに現在日付で再計算**(仕様書§5A冒頭)。
      検証: 各項目につき「許可される最小ケース」「境界で拒否されるケース」をそれぞれ1件以上、
      pytest の pure function テストで固定(hypothesis 等の実例オラクルに頼らない——
      判定ルールは規則そのものなので named ケースで固定するのが適切)。
- [ ] 判定不能・入力不足・規約取得失敗は必ず `manual_review`/`deny` 側に倒れることを
      違反注入テストで確認(仕様書§5A末尾の既定)。
      検証: 意図的に欠損値を入れたケースが `allow_public_use` にならないことをテストで固定。

### Phase 2 — 収集(§7・§5.3の最小4〜5ソース)

MVP対象(§16): Wikipedia、Wikimedia Commons、NDLデジタルコレクション(保護期間満了区分)、
ColBase、CC0美術館(Smithsonian/Met等)。

- [ ] `src/ingest/base.py`: 共通の取得結果スキーマ(§7.2必須保存項目を dataclass 化)。
      検証: 必須フィールド欠落時に型/バリデーションエラーになる pytest。
- [ ] ソースごとに1アダプター(`src/ingest/wikipedia.py` 等)。API優先(§7.1)、
      同時接続1・待機2秒以上(§7.3)。
      検証: ソースごとに1本、記録済みフィクスチャ(実ネットワークなし——テスト内 外部I/O は
      hard 違反 `test-network`)を使った統合テストが green。
- [ ] 取得結果を Phase 1 の `screening()` に通し、`allow_public_use` 以外は
      本文を保存せず根拠抜粋・メタデータのみ保持する導線(§7.2 末尾の
      `storage_permission`/`publication_permission` 分離)。
      検証: `internal_research_only` 判定の資料が全文保存されないことをテストで固定。
- [ ] `source_registry.yaml` の `status: approved` 資料のみ収集対象にするフィルタ。
      検証: `status: candidate` のソースが収集されないことをテストで固定。

### Phase 3 — 出典独立性・題材選出(§6.2・§6A)

- [ ] `src/select/independence.py`: 出典の「系統」判定(§6.2の5規則: Wikipedia転載は
      同一系統、同一一次資料由来は1系統 等)。
      検証: 仕様書§6.2の5パターンをそれぞれ1テストケースとして固定。
- [ ] `src/select/score.py`: §6A.1 の候補点計算式をそのまま実装(LLM不使用)。
      検証: 各特徴量を0/1に固定した既知入力→期待点数をアサート。
- [ ] `src/select/news_filter.py`: §6A.2 の禁止語・カテゴリフィルタ(ニュースは題材選出の
      単語取得のみに使用・出典にしない)。
      検証: 禁止語を含む入力が候補から除外されることを固定ケースで確認。

### Phase 4 — 主張台帳と LLM 処理(§8)

- [ ] `src/llm/model_registry.py`: OpenRouter固定モデルの検証(価格0・有効期限・
      JSON Schema・日本語回帰テスト)。`openrouter/free` 等のランダムルーターは禁止。
      検証: 無料枠外・期限切れモデルを設定した場合に採用されないことをテストで固定。
- [ ] `src/llm/extract.py`: §8.2 の JSON 出力(要約・facts・根拠位置)。URLとライセンスは
      LLMに生成させず、プログラム側の値を注入する。
      検証: モック応答から `facts[].evidence_quote` が保存本文の該当位置と**完全一致**する
      ことを検査する関数のテスト(§8.2「自己申告confidenceを採用に使わない」の実装確認)。
- [ ] `src/llm/claim_ledger.py`: `claim_ledger.json` の生成・`allowed_in_script` 判定
      (独立系統2件未満は不採用)。
      検証: 独立系統1件の主張が `allowed_in_script: false` になることを固定ケースで確認。

### Phase 5 — 台本生成(§9)

- [ ] `src/script/build.py`: §9.1の7段構成テンプレート＋claim_ledgerにない外部事実を
      追加させないバリデーション(§8.2A末尾: 外部検証可能文なのに claim_id が無ければ
      公開検査を失敗させる)。
      検証: claim_id無しの外部検証可能文を含む台本が検査で reject されることを固定ケースで確認。

### Phase 6 — 音声・スライド動画(§10)

- [ ] `src/media/tts.py`: VOICEVOX(ずんだもん)呼び出し＋クレジット文言の自動付与。
      検証: 生成音声にクレジット文字列が(概要欄データとして)必ず同梱されることをテストで確認。
- [ ] `src/media/slides.py`: 静止画・地図・年表・字幕からのスライド動画生成
      (素材不足時は著作権の発生しない自作図形へフォールバック——§10末尾)。
      検証: 画像0件の入力でも自作図形にフォールバックして生成が失敗しないことを固定ケースで確認。

### Phase 7 — 関連書籍検索(§10A)

- [ ] `src/books/search.py`: LLM不使用、ISBN/著者/件名標目でのメタデータ検索＋機械ランキング式。
      検証: §10A関連度式を既知入力でアサート。書誌系統1件のみの候補が非表示になることを確認。

### Phase 8 — 恒久ページ・公開基盤(§10B・§10C)

- [ ] `src/publish/episode_page.py`: 静的HTML生成(不変URL・訂正履歴・版保存
      `/episodes/<ID>/versions/<version>/`)。
      検証: 同一IDへの再生成が既存版を上書きせず新版として追記されることをテストで確認。
- [ ] R2/Pagesへのアップロードスクリプト(冪等・ハッシュ一致確認 — §14障害時動作)。
      検証: 同一入力を2回実行しても重複アップロードにならないことを確認(モックS3互換API)。

### Phase 9 — 配信(§10D)

- [ ] `src/distribute/podcast_rss.py`: RSS 2.0生成(GUID固定・標準バリデーター通過)。
      検証: 生成RSSがバリデーターツール(feedgen等)でエラー0件。
- [ ] YouTube/Amazon Music向けメタデータ生成(自動アップロードはMVPで「限定公開」までに留める — §17段階2)。
      検証: エピソードIDが全配信先で同一の冪等キーとして使われることをテストで確認。

### Phase 10 — 自動検査ゲート(§11)

- [ ] `src/gate/publish_check.py`: §11の全項目(転載検知・クレジット・条件付き素材ログ・
      類似度・禁止語 等)をANDで評価し `publish_ready` を決定。
      検証: 各項目を個別に失敗させた15+ケースで、いずれも `publish_ready=False` になることを
      固定ケースで確認(§17段階0の「意図的混入→すべて公開拒否」に対応)。
- [ ] 転載検知(§11: 和文25文字以上/欧文8語以上の連続一致)。
      検証: 出典原文をそのまま25文字コピーした台本が reject されることを確認。

### Phase 11 — 管理画面(§12)

MVPはWeb UIを持たず、CLI/静的レポートで代替する(Step 0の簡素化方針)。

- [ ] `uv run scripts/dev.py <verb>` 経由で §12.1(ホーム相当のステータス表示)・
      §12.3(候補一覧)を出す最小CLIコマンドを追加。
      検証: 候補0件の状態でもエラーにならず「候補なし」を表示する。

### Phase 12 — バックアップ・障害対応(§13〜§15)

- [ ] Google Drive/NAS日次バックアップスクリプト＋月次復元試験の手順化。
      検証: バックアップからの復元で恒久ページ・RSS項目が同一内容で再構築できることを
      1回、実データで確認(§17全段階共通の受入条件)。
- [ ] §14の障害時動作(モデル429・JSON不正・クロール失敗 等)を`jobs`状態遷移として実装。
      検証: 各障害を注入し、想定される状態(`blocked`/`rejected`/リトライ)に遷移することを確認。

### Phase 13 — 受入検証(§17 段階0〜3)

- [ ] 段階0: ユニット・固定データ試験(Phase 1-10の単体テスト group が実質これに相当)。
      検証: `uv run scripts/dev.py test` 全体 green。
- [ ] 段階1: 30候補ドライラン(非公開)。
      検証: 人手で30件を確認したレビュー記録を残す(このタスク自体は自動検証不可——
      `RED-FIRST-EXEMPT` ではなく人手レビューそのものが受入条件)。
- [ ] 段階2: 限定公開10本。
      検証: 1本あたり確認時間を計測し15分以内であることを記録。
- [ ] 段階3: 公開運用30日。
      検証: §17末尾の全指標(権利不明混入0件・重複生成0件 等)を運用ログから集計しレビューする。

---

## 対象外(仕様書§16「含めない」— 本計画でも扱わない)

完全自動公開、年代計算のみのPD自動許可、一般ニュースRSS題材選出、ニュース本文の出典利用、
有料素材、歴史音源(SP盤等)の実演/原盤3層判定、動画生成AI、高度キャラアニメ、多言語配信、
広告/アフィリエイト自動挿入。

## 未決事項(仕様書§19をそのまま引き継ぐ)

実装着手前にユーザー確認が要る項目は仕様書§19を参照。特に「完全自動公開の可否」と
「独自ドメイン/GitHub公開範囲/Cloudflareアカウント構成」はPhase 8着手前に確定が要る。
