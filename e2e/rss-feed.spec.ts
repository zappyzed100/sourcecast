// rss-feed.spec.ts — Phase 9タスク1 DoD: RSS 2.0の標準バリデーターでエラー0件、
// 過去GUIDの変化0件であることを検証する(development-plan.md Phase 9タスク1・仕様書§10D)。
//
// 「標準バリデーター」としてブラウザのDOMParser(text/xml)によるwell-formedness検証に加え、
// RSS 2.0・Podcast enclosureの必須要素チェックリストを実装している(外部の検証サービスへの
// ネットワークアクセスはtest-network違反になるため、構造チェックとして自前実装する)。
import { expect, test } from "@playwright/test";

interface ParsedItem {
	title: string;
	link: string;
	guid: string;
	guidIsPermaLink: string | null;
	pubDate: string;
	description: string;
	enclosureUrl: string;
	enclosureLength: string;
	enclosureType: string;
	itunesAuthor: string;
}

interface ParsedFeed {
	rssVersion: string;
	xmlnsItunes: string | null;
	channelTitle: string;
	channelLink: string;
	channelDescription: string;
	parseError: string | null;
	items: ParsedItem[];
}

// GUIDは過去に生成された値のまま固定する(development-plan.md Phase 9タスク1 DoD:
// 過去GUIDの変化0件)。link生成ロジックが変わってこの値とずれたら、このテストで検出する。
// ドメインはastro.config.mjsのsite設定に追従する(2026-07-20: siteが未設定で
// https://example.invalid/のまま本番公開されていた不具合を修正——このテストの
// 期待値もその誤ったドメインを固定してしまっていたため、実際の本番ドメインへ直す)。
const EXPECTED_GUIDS = [
	"https://itsuwawa.com/episodes/2026-07-16-can-opener/",
	"https://itsuwawa.com/episodes/2026-07-15-first-railway/",
];

const RFC822_PUBDATE_PATTERN =
	/^(Mon|Tue|Wed|Thu|Fri|Sat|Sun), \d{2} (Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) \d{4} \d{2}:\d{2}:\d{2} (GMT|[+-]\d{4})$/;

test("feed.xmlはRSS 2.0の必須要素を全て備え、標準バリデーターでエラー0件になる", async ({ page, request }) => {
	const response = await request.get("/feed.xml");
	expect(response.status()).toBe(200);
	expect(response.headers()["content-type"]).toContain("xml");
	const xmlText = await response.text();

	await page.goto("/");
	const feed: ParsedFeed = await page.evaluate((xml) => {
		const doc = new DOMParser().parseFromString(xml, "text/xml");
		const parseErrorEl = doc.querySelector("parsererror");
		const rss = doc.documentElement;
		const channel = rss.querySelector("channel");
		const text = (el: Element | null, selector: string) => el?.querySelector(selector)?.textContent ?? "";

		const items = Array.from(channel?.querySelectorAll("item") ?? []).map((item) => {
			const guidEl = item.querySelector("guid");
			const enclosureEl = item.querySelector("enclosure");
			const itunesAuthorEl = item.getElementsByTagNameNS(
				"http://www.itunes.com/dtds/podcast-1.0.dtd",
				"author",
			)[0];
			return {
				title: text(item, "title"),
				link: text(item, "link"),
				guid: guidEl?.textContent ?? "",
				guidIsPermaLink: guidEl?.getAttribute("isPermaLink"),
				pubDate: text(item, "pubDate"),
				description: text(item, "description"),
				enclosureUrl: enclosureEl?.getAttribute("url") ?? "",
				enclosureLength: enclosureEl?.getAttribute("length") ?? "",
				enclosureType: enclosureEl?.getAttribute("type") ?? "",
				itunesAuthor: itunesAuthorEl?.textContent ?? "",
			};
		});

		return {
			rssVersion: rss.getAttribute("version") ?? "",
			xmlnsItunes: rss.getAttribute("xmlns:itunes"),
			channelTitle: text(channel, "title"),
			channelLink: text(channel, "link"),
			channelDescription: text(channel, "description"),
			parseError: parseErrorEl ? (parseErrorEl.textContent ?? "parse error") : null,
			items,
		};
	}, xmlText);

	// well-formedness
	expect(feed.parseError, `XML parse error: ${feed.parseError}`).toBeNull();

	// channel必須要素
	expect(feed.rssVersion).toBe("2.0");
	expect(feed.xmlnsItunes).toBe("http://www.itunes.com/dtds/podcast-1.0.dtd");
	expect(feed.channelTitle).not.toBe("");
	expect(feed.channelLink).not.toBe("");
	expect(feed.channelDescription).not.toBe("");
	expect(feed.items.length).toBeGreaterThan(0);

	for (const item of feed.items) {
		expect(item.title, `title missing: ${JSON.stringify(item)}`).not.toBe("");
		expect(item.link, `link missing: ${JSON.stringify(item)}`).not.toBe("");
		expect(item.description, `description missing: ${JSON.stringify(item)}`).not.toBe("");

		// GUID: linkと一致し、isPermaLink=true(既定)であること(development-plan.md Phase 9タスク1)
		expect(item.guid, `guid missing: ${JSON.stringify(item)}`).not.toBe("");
		expect(item.guid).toBe(item.link);
		expect(item.guidIsPermaLink).toBe("true");

		// pubDate: RFC822形式
		expect(item.pubDate, `pubDate malformed: ${item.pubDate}`).toMatch(RFC822_PUBDATE_PATTERN);

		// enclosure: url・length(正の整数)・MIME typeが揃っていること
		expect(item.enclosureUrl, `enclosure url missing: ${JSON.stringify(item)}`).toMatch(/^https:\/\//);
		expect(Number(item.enclosureLength), `enclosure length invalid: ${item.enclosureLength}`).toBeGreaterThan(0);
		expect(item.enclosureType).toBe("audio/mpeg");

		// クレジット(development-plan.md Phase 9タスク1「クレジットを固定する」)
		expect(item.itunesAuthor, `itunes:author missing: ${JSON.stringify(item)}`).toContain("VOICEVOX");
	}
});

test("既知エピソードのGUIDが過去の値から変化していない", async ({ request }) => {
	const response = await request.get("/feed.xml");
	const xmlText = await response.text();
	for (const expectedGuid of EXPECTED_GUIDS) {
		expect(xmlText, `GUIDが見つからない: ${expectedGuid}`).toContain(`<guid isPermaLink="true">${expectedGuid}</guid>`);
	}
});
