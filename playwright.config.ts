// playwright.config.ts — Phase 0 のブラウザ smoke test 設定（plan.md §5 CI必須ゲート「Browser: Playwright smoke」）
import { defineConfig } from "@playwright/test";

export default defineConfig({
	testDir: "./e2e",
	fullyParallel: true,
	forbidOnly: !!process.env.CI,
	retries: process.env.CI ? 2 : 0,
	reporter: "list",
	use: {
		baseURL: "http://localhost:4321",
		trace: "on-first-retry",
	},
	webServer: {
		// astro previewの既定ポートは4321——追加引数を挟むとpnpm run経由の引数区切り
		// （--）がそのままastroへ渡ってしまい起動に失敗するため、既定のまま呼ぶ。
		// url/baseURLは127.0.0.1ではなくlocalhostを使うこと: このWindows環境ではNode/astroの
		// listenがIPv6(::1)側に紐づき、127.0.0.1（IPv4）へは接続できなかった（実測で確認済み）。
		command: "pnpm --filter apps-site run preview",
		url: "http://localhost:4321",
		reuseExistingServer: !process.env.CI,
		timeout: 60_000,
	},
});
