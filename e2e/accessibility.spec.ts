// accessibility.spec.ts — Phase 2 DoD: 重大なaxe違反はCIを落とす(plan.md §3.3・§5)
import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { KNOWN_PAGES } from "./known-pages";

for (const path of KNOWN_PAGES) {
	test(`${path} に重大なアクセシビリティ違反が無い`, async ({ page }) => {
		await page.goto(path);
		const results = await new AxeBuilder({ page })
			.withTags(["wcag2a", "wcag2aa"])
			.analyze();

		const serious = results.violations.filter(
			(v) => v.impact === "serious" || v.impact === "critical",
		);
		expect(serious, JSON.stringify(serious, null, 2)).toEqual([]);
	});
}
