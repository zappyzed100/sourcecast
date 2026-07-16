// episode-publish.spec.ts — Phase 8タスク3 DoD: 主張‐出典対応・コピー・ダウンロード・過去版差分が
// 実データ(publish_episodeが生成した2世代フィクスチャ)で実際に機能することを検証する
import { expect, test } from "@playwright/test";

const EPISODE_ID = "2026-07-18-tokyo-tower-color";

test.describe("主張と出典の対応", () => {
	test("主張の出典番号リンクをクリックすると対応する出典へジャンプする", async ({ page }) => {
		await page.goto(`/episodes/${EPISODE_ID}/`);
		const links = page.locator('[data-testid="claim-source-link"]');
		await expect(links.first()).toHaveText("[1]");
		await expect(links.first()).toHaveAttribute("href", "#source-0");
		await page.locator('#source-0 a').first().waitFor();
		await expect(page.locator("#source-0")).toContainText("Wikipedia『東京タワー』");
	});

	test("全ての主張が最低1件の有効な出典URLへ到達できる", async ({ page }) => {
		await page.goto(`/episodes/${EPISODE_ID}/`);
		const rows = page.locator('[data-testid="claim-evidence-table"] tbody tr');
		const count = await rows.count();
		expect(count).toBeGreaterThan(0);
		for (let i = 0; i < count; i++) {
			const rowLinks = rows.nth(i).locator('[data-testid="claim-source-link"]');
			expect(await rowLinks.count()).toBeGreaterThanOrEqual(1);
			for (const href of await rowLinks.evaluateAll((els) => els.map((el) => el.getAttribute("href")))) {
				expect(href).toMatch(/^#source-\d+$/);
			}
		}
	});
});

test.describe("原稿のコピー・ダウンロード", () => {
	test.beforeEach(async ({ context }) => {
		await context.grantPermissions(["clipboard-read", "clipboard-write"]);
	});

	test("コピーボタンで原稿全文がクリップボードへコピーされる", async ({ page }) => {
		await page.goto(`/episodes/${EPISODE_ID}/`);
		const rawText = await page.locator('[data-testid="script-raw-text"]').inputValue();
		expect(rawText).toContain("東京タワー");

		await page.locator('[data-testid="copy-script-button"]').click();
		await expect(page.locator('[data-testid="copy-script-status"]')).toHaveText("コピーしました");

		const clipboardText = await page.evaluate(() => navigator.clipboard.readText());
		// OSクリップボード経由で\n→\r\nへ改行コードが正規化されることがある(Windows実測)。
		// コピー機能自体の検証が目的なので、比較前に改行コードをそろえる。
		expect(clipboardText.replace(/\r\n/g, "\n")).toBe(rawText);
	});

	test("ダウンロードリンクが実際の原稿Markdownを返す", async ({ page, request }) => {
		await page.goto(`/episodes/${EPISODE_ID}/`);
		const href = await page.locator('[data-testid="download-script-link"]').getAttribute("href");
		expect(href).toBe(`/episodes/${EPISODE_ID}/script.md`);

		const response = await request.get(href as string);
		expect(response.ok()).toBe(true);
		expect(response.headers()["content-type"]).toContain("text/markdown");
		const body = await response.text();
		expect(body).toContain("## 高さと義務");
	});
});

test.describe("過去版差分", () => {
	test("revision 2は前版(revision 1)との差分で追加行がaddedとして表示される", async ({ page }) => {
		await page.goto(`/episodes/${EPISODE_ID}/versions/2/`);
		const diff = page.locator('[data-testid="version-diff"]');
		await expect(diff).toBeVisible();
		await expect(diff).toContainText("revision 1 からの変更点");

		const addedLines = diff.locator('li[data-diff-op="added"]');
		expect(await addedLines.count()).toBeGreaterThan(0);
		await expect(addedLines.filter({ hasText: "高さと義務" })).toHaveCount(1);
	});

	test("revision 1は最初の公開版として差分無しと表示される", async ({ page }) => {
		await page.goto(`/episodes/${EPISODE_ID}/versions/1/`);
		await expect(page.locator('[data-testid="version-diff-none"]')).toBeVisible();
		await expect(page.locator('[data-testid="version-diff"]')).toHaveCount(0);
	});

	test("現行ページの過去バージョン一覧からrevision 1へ遷移できる", async ({ page }) => {
		await page.goto(`/episodes/${EPISODE_ID}/`);
		await page.locator('[data-testid="version-history"] a', { hasText: "revision 1" }).click();
		await expect(page).toHaveURL(`/episodes/${EPISODE_ID}/versions/1/`);
		await expect(page.locator('[data-testid="version-banner"]')).toContainText("最新版はこちら");
	});
});
