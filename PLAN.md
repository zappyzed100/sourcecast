<!-- PLAN.md — history-radio（歴史スライド動画・自動生成ツール）の全体計画・アーキテクチャ・技術選定理由の正本 -->
# PLAN.md — history-radio 全体計画

## 目的

著作権上利用可能な歴史資料を自動収集し、面白い題材を選定して、出典付きの日本語台本・
VOICEVOX音声・簡易スライド動画をほぼ無管理で生成する。「大量転載」ではなく、複数資料から
事実を抽出し、独自構成の短い歴史番組へ変換する。公開物には必ず出典と素材ライセンスを表示する。
詳細仕様の正本は [history_radio_spec_v0_4.md](history_radio_spec_v0_4.md)。

## アーキテクチャ

```text
apps/admin/                  管理画面（React + TypeScript）
  ↓ localhost APIのみを呼ぶ
services/pipeline/.../api/   ローカル管理API（FastAPI・127.0.0.1限定）
  ↓
services/pipeline/.../{rights,ingest,select,llm,script,media,books,gate}/
                              生成パイプライン（権利判定→収集→選出→LLM→台本→音声/動画→公開ゲート）
  ↓
services/pipeline/.../{store,publish,distribute}/
                              永続化・公開データ生成・配信
  ↓
SQLite（運用状態） / Git上のJSON・Markdown（公開データ） / R2（音声・画像）
  ↓
apps/site/                   公開サイト（Astro静的出力・Cloudflare Pages）
```

依存方向は `domain ← rights/select ← use-cases ← adapters` の一方向のみ。禁止依存と機械強制は
AGENTS.md §5 と `.guardrails/GUARDRAILS.md` が正本。

## 技術選定理由

- **Python 3.14 / uv**: 生成パイプライン全体（収集・権利判定・LLM・VOICEVOX・FFmpeg呼び出し）。
  HTTP・外部CLI連携の実装が速く、ライブラリが成熟している。
- **FastAPI（127.0.0.1限定）**: ローカル管理API。パイプラインの型をそのまま共有できる。
- **Astro 7（静的出力）**: 公開サイト。JavaScriptなしでも本文・出典・訂正履歴を読める。
- **React 19 + Vite 8**: 管理画面。状態の多いUIを型安全に組み立てやすい。
- **Pagefind**: 公開済みページの全文検索。検索サーバー・DBが不要。
- **SQLite（WAL）+ Git + R2**: 運用状態・公開データ・メディアを責務ごとに分離し、単一障害点を作らない。
- **Cloudflare Pages/R2**: 静的サイト＋メディア配信。Workers/D1はMVPでは使わない
  （障害時に既存ページが読めなくなる設計を避ける）。

技術選定の詳細な比較・バージョン固定・標準構成は
[docs/plans/development-plan.md](docs/plans/development-plan.md) §1 を正本とする。

## 方針（公開判断の原則）

1. 権利不明素材と未裏付け事実を公開しない（fail closed）。
2. 誤りが判明した回を迅速に訂正・告知できる。恒久URLは変更せず、旧版を不変保存する。
3. 出典と生成過程を第三者が追跡できる。
4. LLMの自己申告confidenceを採用可否に使わない——判断は明示ルールと独立出典系統数で行う。
5. MVPでは完全自動公開をしない。公開は必ず人手承認を経る。

毎日投稿は成功条件に含めない。安全な候補がない日は公開しない。

## 運用

- 日次バックアップ: SQLite・設定・公開データ・必要なartifactsをGoogle Drive/NASへ（Phase 12）。月次で復元試験。
- タイムゾーンは Asia/Tokyo を前提に日付境界を扱う。
- 公開は「検証済み成果物への参照切替」とし、途中状態を見せない（development-plan.md §3.4）。
- LLM API費は原則0円。OpenRouterの無料モデルのみを使い、価格・有効期限を起動時に検証する。

## ロードマップ

1. **Phase 0〜2（完了）**: モノレポ基盤、ドメイン契約・状態機械・保存基盤、Webの土台
   （公開サイト・管理画面・CSP/axe/性能予算）。
2. **Phase 3〜7**: 権利判定エンジン → 収集 → 題材選出 → LLM/主張台帳/台本 → 音声・動画・関連書籍。
3. **Phase 8〜10**: 公開ページ統合・Cloudflare、RSS・配信先、自動検査ゲート。
4. **Phase 11〜13**: 管理画面の実運用化、バックアップ・障害対応、受入検証（仕様書§17 段階0〜3）。

フェーズごとの詳細タスクと検証コマンドは
[docs/plans/development-plan.md](docs/plans/development-plan.md) が正本（AGENTS.md §4 — feat⇔plan対）。

## タスク（機械可読）

書式:
- `- [ ] タイトル` … 未完了。行末に `` `状態タグ` `` が無ければ `backlog` 扱い
- `- [x] タイトル` … 完了。行末にタグが無ければ `done` 扱い
- 状態を明示したい時だけ行末にタグを付ける: `` `next` `` / `` `in_progress` `` / `` `blocked` ``
- 各タスクの詳細・検証コマンドは [docs/plans/development-plan.md](docs/plans/development-plan.md) の同名フェーズを参照

- [x] Phase 0 — モノレポと開発基盤
- [x] Phase 1 — ドメイン契約・状態機械・保存基盤
- [x] Phase 2 — Webの土台（公開サイト・管理画面・CSP/axe/性能予算）
- [ ] Pagefindの年代・地域・人物フィルタ（Phase 5でtopicsに構造化データが載ってから） `backlog`
- [x] Phase 3 — 権利判定エンジン
- [x] Phase 4 — 収集
- [x] Phase 5 — 出典独立性・題材選出
- [x] Phase 6 — LLM処理・主張台帳・台本
- [x] OpenRouter実接続の配線と品質実測（caller実装・Napoleon検証・レジストリ実測反映）
- [x] 読み辞書の構築（人名・地名・元号・官職 — development-plan.md §8。7ソース・解決器・
  手動修正辞書まで完了。VOICEVOXへの読み注入はPhase 7で同時着手）
- [x] Phase 7 — 音声・スライド動画・関連書籍
- [x] Phase 8 — 公開ページ統合・Cloudflare（タスク5・6のCloudflareダッシュボード側の
  仕上げ〔独自ドメイン接続・Pagesプロジェクト作成・実クレデンシャルでの動作確認〕は
  HUMAN_TASKS.mdで依頼中——実装・テストは完了）
- [ ] Phase 9 — RSS・配信先 `in_progress`
- [ ] Phase 10 — 自動検査ゲート `backlog`
- [ ] Phase 11 — 管理画面の実運用化 `backlog`
- [ ] Phase 12 — バックアップ・障害対応 `backlog`
- [ ] Phase 13 — 受入検証 `backlog`
