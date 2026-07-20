// feed.xml.ts — Podcast RSS 2.0フィード生成(仕様書§10D・development-plan.md Phase 9タスク1)。
//
// GUIDは各エピソードの恒久ページURL(link)をそのまま使う——@astrojs/rssの既定動作
// (link未指定時のguid = link, isPermaLink=true)。恒久URLは仕様書§10Bで
// 「公開済みページの削除・URL変更を原則禁止」「不変IDは公開前に確定し、再利用しない」と
// されているため、GUIDの安定性は既にepisode_idの設計そのものが保証している
// (このファイルが独自にGUIDを算出するのではなく、既に不変な値へ乗るだけ)。

import { getCollection } from "astro:content";
import rss from "@astrojs/rss";
import type { APIRoute } from "astro";

export const GET: APIRoute = async (context) => {
	const episodes = await getCollection(
		"episodes",
		(entry) => !entry.id.includes("/versions/"),
	);
	const withAudio = episodes.filter(
		(episode) =>
			episode.data.audioUrl !== undefined &&
			episode.data.audioLengthBytes !== undefined,
	);

	const podcastCoverUrl = new URL(
		"/podcast-cover.png",
		context.site ?? "https://example.invalid",
	).toString();

	return rss({
		title: "いつわわ",
		description: "史実の意外な一面を、出典明記で毎回お届けするPodcast。",
		site: context.site ?? "https://example.invalid",
		xmlns: { itunes: "http://www.itunes.com/dtds/podcast-1.0.dtd" },
		items: withAudio
			.sort(
				(a, b) => b.data.publishedAt.valueOf() - a.data.publishedAt.valueOf(),
			)
			.map((episode) => ({
				title: episode.data.title,
				description: episode.data.summary,
				pubDate: episode.data.publishedAt,
				link: `/episodes/${episode.data.episodeId}/`,
				enclosure: {
					url: new URL(
						episode.data.audioUrl as string,
						context.site ?? "https://example.invalid",
					).toString(),
					type: "audio/mpeg",
					length: episode.data.audioLengthBytes as number,
				},
				customData: `<itunes:author>VOICEVOX:ずんだもん</itunes:author>`,
			})),
		customData: `<language>ja</language>
			<itunes:author>いつわわ</itunes:author>
			<itunes:owner>
				<itunes:name>いつわわ</itunes:name>
				<itunes:email>itsuwawa.admin@gmail.com</itunes:email>
			</itunes:owner>
			<itunes:image href="${podcastCoverUrl}" />
			<itunes:category text="Society &amp; Culture" />
			<itunes:explicit>false</itunes:explicit>`,
	});
};
