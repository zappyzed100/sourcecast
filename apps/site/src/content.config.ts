// content.config.ts — 公開エピソードのコンテンツコレクション定義（Astro Content Layer API）
//
// Phase 2時点ではPythonの公開データ生成(Phase 8)がまだ無いため、src/content/episodes/*.md の
// フィクスチャで土台を作る。フィールドは仕様書§10Bの表示要件（出典・訂正履歴・主張対応）と
// plan.md §2.3の契約（schema_version・episode_id・revision・generated_at）に合わせてある。

import { defineCollection, z } from "astro:content";
import { glob } from "astro/loaders";

const sourceSchema = z.object({
	name: z.string(),
	url: z.string().url(),
	license: z.string(),
	credit: z.string(),
	accessedAt: z.coerce.date(),
});

const claimSchema = z.object({
	text: z.string(),
	sourceIndexes: z.array(z.number().int().nonnegative()),
});

const correctionSchema = z.object({
	date: z.coerce.date(),
	description: z.string(),
});

const relatedBookSchema = z.object({
	title: z.string(),
	author: z.string(),
	isbn: z.string().optional(),
	url: z.string().url(),
});

const episodes = defineCollection({
	loader: glob({ pattern: "**/*.md", base: "./src/content/episodes" }),
	schema: z.object({
		schemaVersion: z.literal(1),
		episodeId: z.string(),
		revision: z.number().int().positive(),
		title: z.string(),
		summary: z.string(),
		publishedAt: z.coerce.date(),
		updatedAt: z.coerce.date(),
		sources: z.array(sourceSchema).min(1),
		claims: z.array(claimSchema),
		corrections: z.array(correctionSchema),
		relatedBooks: z.array(relatedBookSchema),
		audioUrl: z.string().optional(),
		// RSS 2.0のenclosure要素が要求する実バイト数（development-plan.md Phase 9タスク1・
		// 仕様書§10D）。audioUrlと対で必須（feed.xml.ts側でも両方揃っているかを検証する）。
		audioLengthBytes: z.number().int().positive().optional(),
		chapters: z
			.array(
				z.object({ title: z.string(), startSeconds: z.number().nonnegative() }),
			)
			.optional(),
	}),
});

export const collections = { episodes };
