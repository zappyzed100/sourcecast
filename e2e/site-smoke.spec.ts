// site-smoke.spec.ts — Phase 0のブラウザsmoke test: 公開サイトのホームページが読み込めることだけを確認する
import { expect, test } from "@playwright/test";

test("ホームページが表示され、タイトルを持つ", async ({ page }) => {
	await page.goto("/");
	await expect(page).toHaveTitle(/.+/);
});
