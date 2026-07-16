// script.md.ts — 原稿本文のMarkdownダウンロード用静的エンドポイント(仕様書§10B「原稿のMarkdownダウンロード」)

import { getCollection, getEntry } from "astro:content";
import type { APIRoute } from "astro";

export async function getStaticPaths() {
	const episodes = await getCollection(
		"episodes",
		(entry) => !entry.id.includes("/versions/"),
	);
	return episodes.map((episode) => ({
		params: { id: episode.data.episodeId },
		props: { slug: episode.id },
	}));
}

interface Props {
	slug: string;
}

export const GET: APIRoute = async ({ props }) => {
	const { slug } = props as Props;
	const episode = await getEntry("episodes", slug);
	if (!episode) {
		// getStaticPaths が返したslugのはずなので到達しない——ビルド決定性が壊れた合図として落とす。
		throw new Error(`episodes/[id]/script.md: エントリが見つからない: ${slug}`);
	}
	return new Response(episode.body ?? "", {
		headers: {
			"content-type": "text/markdown; charset=utf-8",
			"content-disposition": `attachment; filename="${episode.data.episodeId}.md"`,
		},
	});
};
