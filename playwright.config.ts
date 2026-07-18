// playwright.config.ts — Phase 0 のブラウザ smoke test 設定（plan.md §5 CI必須ゲート「Browser: Playwright smoke」）。
// Phase 11タスク1のPlaywright E2E（候補→審査→承認→限定公開）はapps/adminとlocalhost
// FastAPIの2サーバーを追加で必要とするため、projectsでbaseURLを切り替える
// （webServer配列は全プロジェクト共通で起動する——admin向けを追加しても既存のapps/site
// テストの通り方自体は変わらない。起動時間は数秒伸びる）。
import { defineConfig } from "@playwright/test";

export default defineConfig({
	testDir: "./e2e",
	fullyParallel: true,
	forbidOnly: !!process.env.CI,
	retries: process.env.CI ? 2 : 0,
	reporter: "list",
	use: {
		trace: "on-first-retry",
	},
	projects: [
		{
			name: "site",
			testDir: "./e2e",
			testIgnore: "**/admin/**",
			// url/baseURLは127.0.0.1ではなくlocalhostを使うこと: このWindows環境では
			// Node/astroのlistenがIPv6(::1)側に紐づき、127.0.0.1（IPv4）へは接続できなかった
			// （実測で確認済み）。
			use: { baseURL: "http://localhost:4321" },
		},
		{
			name: "admin",
			testDir: "./e2e/admin",
			use: { baseURL: "http://localhost:5183" },
		},
	],
	webServer: [
		{
			// astro previewの既定ポートは4321——追加引数を挟むとpnpm run経由の引数区切り
			// （--）がそのままastroへ渡ってしまい起動に失敗するため、既定のまま呼ぶ。
			command: "pnpm --filter apps-site run preview",
			url: "http://localhost:4321",
			reuseExistingServer: !process.env.CI,
			timeout: 60_000,
		},
		{
			// viteの既定devポート(5173)は開発機で別プロジェクトのdevサーバーと衝突し得る
			// （実機で発生済み: 別ポートの何かがreuseExistingServerに拾われ、admin一式が
			// 全滅した）。E2E専用ポート5183へ--strictPortで固定する
			// （ポートが埋まっていたら黙って次のポートへ逃げず即失敗させる——
			// 「別アプリを誤って読み込む」事故を起動時点で検出する）。
			// api/main.pyのCORS許可オリジンにも5183を追加済み。
			command: "pnpm --filter apps-admin exec vite --port 5183 --strictPort",
			url: "http://localhost:5183",
			reuseExistingServer: !process.env.CI,
			timeout: 60_000,
		},
		{
			// e2e専用DBを使う(開発用の既定パスdata/history_radio.sqlite3を汚さない)。
			// ジョブのstep delay/SSEポーリング間隔は既定値(1秒/0.2秒)だとE2E一式が
			// 数十秒がかりになるため短縮する——0にはしない(job-progress-reload.spec.tsが
			// 「実行中の途中」を実際に観測する必要があるため、0だと一瞬で完了してしまう)。
			command:
				"uv run uvicorn history_radio.api.main:app --host 127.0.0.1 --port 8000",
			url: "http://127.0.0.1:8000/api/v1/dashboard",
			env: {
				HISTORY_RADIO_DB_PATH: "data/e2e-admin.sqlite3",
				HISTORY_RADIO_JOB_STEP_DELAY_SECONDS: "0.3",
				HISTORY_RADIO_JOB_SSE_POLL_SECONDS: "0.1",
			},
			reuseExistingServer: !process.env.CI,
			timeout: 60_000,
		},
	],
});
