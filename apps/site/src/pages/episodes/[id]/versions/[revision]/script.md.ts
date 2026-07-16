// script.md.ts — 過去バージョンの原稿本文Markdownダウンロード用静的エンドポイント(仕様書§10B)

import { getCollection, getEntry } from "astro:content";
import type { APIRoute } from "astro";

export async function getStaticPaths() {
	const versions = await getCollection("episodes", (entry) =>
		entry.id.includes("/versions/"),
	);
	return versions.map((version) => ({
		params: {
			id: version.data.episodeId,
			revision: String(version.data.revision),
		},
		props: { slug: version.id },
	}));
}

interface Props {
	slug: string;
}

export const GET: APIRoute = async ({ props }) => {
	const { slug } = props as Props;
	const version = await getEntry("episodes", slug);
	if (!version) {
		// getStaticPaths が返したslugのはずなので到達しない——ビルド決定性が壊れた合図として落とす。
		throw new Error(
			`episodes/[id]/versions/[revision]/script.md: エントリが見つからない: ${slug}`,
		);
	}
	return new Response(version.body ?? "", {
		headers: {
			"content-type": "text/markdown; charset=utf-8",
			"content-disposition": `attachment; filename="${version.data.episodeId}-r${version.data.revision}.md"`,
		},
	});
};
