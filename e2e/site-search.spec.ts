// site-search.spec.ts — Phase 2 DoD: fixtureの固有語を検索し、該当エピソードが返ることを確認する
import { expect, test } from "@playwright/test";

test("固有語で検索するとフィクスチャの該当エピソードが返る", async ({ page }) => {
	await page.goto("/");

	const searchInput = page.getByTestId("site-search-input");
	await searchInput.focus();
	await searchInput.fill("アペール");

	const results = page.locator("#site-search-results");
	await expect(results.getByRole("link", { name: /缶切り/ })).toBeVisible();
});

test("該当が無い検索語では結果が空になる", async ({ page }) => {
	await page.goto("/");

	const searchInput = page.getByTestId("site-search-input");
	await searchInput.focus();
	await searchInput.fill("ザザザザザ存在しない単語ザザザザザ");

	const results = page.locator("#site-search-results");
	await expect(results.getByRole("link")).toHaveCount(0);
});
