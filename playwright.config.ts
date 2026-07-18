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
			use: { baseURL: "http://localhost:5173" },
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
			// apps/adminからのCORSはapi/main.pyでlocalhost:5173限定で許可しているため、
			// viteの既定devポート(5173)のまま起動する(明示指定しない)。
			command: "pnpm --filter apps-admin run dev",
			url: "http://localhost:5173",
			reuseExistingServer: !process.env.CI,
			timeout: 60_000,
		},
		{
			// e2e専用DBを使う(開発用の既定パスdata/history_radio.sqlite3を汚さない)。
			command:
				"uv run uvicorn history_radio.api.main:app --host 127.0.0.1 --port 8000",
			url: "http://127.0.0.1:8000/api/v1/dashboard",
			env: { HISTORY_RADIO_DB_PATH: "data/e2e-admin.sqlite3" },
			reuseExistingServer: !process.env.CI,
			timeout: 60_000,
		},
	],
});
