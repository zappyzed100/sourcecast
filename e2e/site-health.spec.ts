// site-health.spec.ts — Phase 8タスク5 DoD: プレビューと本番でリンク切れ、mixed content、
// ヘッダー欠落が0件であることを検証する(development-plan.md Phase 8タスク5)。
//
// ヘッダー欠落チェックは`_headers`ファイル自体をパースして検証する——astro previewは
// Cloudflare Pages固有の_headers適用を行わないため、ライブHTTP応答では検証できない。
// ライブ応答でのヘッダー検証(「プレビューと本番」の実物)は、Cloudflare Pagesプロジェクトが
// 実在してから別途スモークテストとして追加する(HUMAN_TASKS.md参照)。
import path from "node:path";
import { expect, request as playwrightRequest, test } from "@playwright/test";
import { KNOWN_PAGES } from "./known-pages";
import { parseHeadersFile } from "./parse-headers-file";

const REQUIRED_HEADERS = [
	"x-content-type-options",
	"referrer-policy",
	"permissions-policy",
	"x-frame-options",
	"cache-control",
];

// mixed content判定の対象: ブラウザが能動的に読み込む(=警告/ブロック対象になる)要素だけを見る。
// 単なる<a href>のナビゲーションリンクはmixed content扱いにならないので対象外。
const ACTIVE_RESOURCE_SELECTOR =
	"script[src], link[rel='stylesheet'][href], img[src], audio[src], source[src], iframe[src]";

function isInternalLink(href: string): boolean {
	return href.startsWith("/") && !href.startsWith("//");
}

test("_headersファイルに全ページ共通の必須セキュリティ/キャッシュヘッダーが宣言されている", () => {
	// playwright.config.tsのtestDir("./e2e")はリポジトリルートからの相対パス指定であり、
	// 実行時cwdは常にリポジトリルート(uv run scripts/dev.py e2e / pnpm exec playwright test)。
	const headersPath = path.join(process.cwd(), "apps", "site", "public", "_headers");
	const blocks = parseHeadersFile(headersPath);
	const wildcard = blocks.find((b) => b.pattern === "/*");
	expect(wildcard, "/* ブロックが_headersに存在しない").toBeDefined();

	const missing = REQUIRED_HEADERS.filter((name) => !(name in (wildcard?.headers ?? {})));
	expect(missing, `欠落ヘッダー: ${missing.join(", ")}`).toEqual([]);
});

for (const pagePath of KNOWN_PAGES) {
	test(`${pagePath} はmixed content(http://の能動的な資源読み込み)を含まない`, async ({ page }) => {
		await page.goto(pagePath);
		const httpResources = await page.locator(ACTIVE_RESOURCE_SELECTOR).evaluateAll((elements) =>
			elements
				.map((el) => el.getAttribute("src") ?? el.getAttribute("href") ?? "")
				.filter((url) => url.toLowerCase().startsWith("http://")),
		);
		expect(httpResources, JSON.stringify(httpResources)).toEqual([]);
	});
}

test("全既知ページの内部リンクにリンク切れが無い", async ({ page, baseURL }) => {
	const apiRequest = await playwrightRequest.newContext({ baseURL });
	const internalHrefs = new Set<string>();

	for (const pagePath of KNOWN_PAGES) {
		await page.goto(pagePath);
		const hrefs = await page
			.locator("a[href]")
			.evaluateAll((els) => els.map((el) => el.getAttribute("href") ?? ""));
		for (const href of hrefs) {
			if (isInternalLink(href)) {
				internalHrefs.add(href);
			}
		}
	}

	expect(
		internalHrefs.size,
		"内部リンクが1件も見つからない場合はテスト自体が機能していない",
	).toBeGreaterThan(0);

	const broken: { href: string; status: number }[] = [];
	for (const href of internalHrefs) {
		const response = await apiRequest.get(href);
		if (!response.ok()) {
			broken.push({ href, status: response.status() });
		}
	}
	await apiRequest.dispose();

	expect(broken, JSON.stringify(broken, null, 2)).toEqual([]);
});
