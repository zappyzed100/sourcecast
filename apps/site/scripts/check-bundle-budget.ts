// check-bundle-budget.ts — 初期JavaScript予算(gzip後60KB以下 — plan.md §3.3)をビルド済みdistで検査する。
//
// Lighthouseの性能スコアはCIコンテナのCPU割り当てでばらつきやすく決定的でないため、
// plan.md §3.3が明示する数値予算(gzip後60KB)を直接測る形でゲート化する
// （Lighthouse自体の性能スコア測定はこのビルドでは代替しない——判断ごと記録）。

import { readdir, readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { gzipSync } from "node:zlib";

const BUDGET_BYTES = 60 * 1024;
const here = path.dirname(fileURLToPath(import.meta.url));
const distDir = path.resolve(here, "..", "dist");

async function findHtmlFiles(dir: string): Promise<string[]> {
	const entries = await readdir(dir, { withFileTypes: true });
	const files: string[] = [];
	for (const entry of entries) {
		const full = path.join(dir, entry.name);
		if (entry.isDirectory()) {
			if (entry.name === "pagefind") continue; // 検索は使用時にのみ遅延読み込みされる別予算
			files.push(...(await findHtmlFiles(full)));
		} else if (entry.name.endsWith(".html")) {
			files.push(full);
		}
	}
	return files;
}

function extractScripts(html: string): { inline: string[]; srcs: string[] } {
	const inline: string[] = [];
	const srcs: string[] = [];
	const scriptTagPattern = /<script\b([^>]*)>([\s\S]*?)<\/script>/gi;
	let match: RegExpExecArray | null = scriptTagPattern.exec(html);
	while (match !== null) {
		const [, attrs, body] = match;
		const srcMatch = /\bsrc="([^"]+)"/.exec(attrs ?? "");
		if (srcMatch) {
			srcs.push(srcMatch[1]);
		} else if (body && body.trim().length > 0) {
			inline.push(body);
		}
		match = scriptTagPattern.exec(html);
	}
	return { inline, srcs };
}

async function main(): Promise<void> {
	const htmlFiles = await findHtmlFiles(distDir);
	let hasFailure = false;

	for (const htmlFile of htmlFiles) {
		const html = await readFile(htmlFile, "utf-8");
		const { inline, srcs } = extractScripts(html);

		const externalContents = await Promise.all(
			srcs
				.filter(
					(src) => !src.startsWith("http://") && !src.startsWith("https://"),
				)
				.map((src) =>
					readFile(path.join(distDir, src.replace(/^\//, "")), "utf-8"),
				),
		);

		const totalSource = [...inline, ...externalContents].join("\n");
		const gzippedSize = gzipSync(Buffer.from(totalSource, "utf-8")).length;
		const relPath = path.relative(distDir, htmlFile);

		if (gzippedSize > BUDGET_BYTES) {
			console.error(
				`[bundle-budget] NG ${relPath}: 初期JS ${gzippedSize}B (gzip) > 予算 ${BUDGET_BYTES}B`,
			);
			hasFailure = true;
		} else {
			console.log(
				`[bundle-budget] OK ${relPath}: 初期JS ${gzippedSize}B (gzip) <= 予算 ${BUDGET_BYTES}B`,
			);
		}
	}

	if (hasFailure) {
		process.exitCode = 1;
	}
}

main().catch((err: unknown) => {
	console.error(err);
	process.exitCode = 1;
});
