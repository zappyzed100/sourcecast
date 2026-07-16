// parse-headers-file.ts — Cloudflare Pagesの_headers構文をパースする(site-health.spec.tsで使用)。
// astro previewはCloudflare Pages固有の_headers適用を行わないため、ライブHTTP応答では
// 検証できない——設定ファイル自体をパースして必須ヘッダーの宣言漏れを検出する。
import { readFileSync } from "node:fs";

export interface HeaderBlock {
	pattern: string;
	headers: Record<string, string>;
}

export function parseHeadersFile(filePath: string): HeaderBlock[] {
	const text = readFileSync(filePath, "utf-8");
	const blocks: HeaderBlock[] = [];
	let current: HeaderBlock | null = null;

	for (const rawLine of text.split("\n")) {
		const line = rawLine.replace(/\r$/, "");
		if (line.trim() === "" || line.trim().startsWith("#")) {
			continue;
		}
		if (!line.startsWith(" ") && !line.startsWith("\t")) {
			current = { pattern: line.trim(), headers: {} };
			blocks.push(current);
			continue;
		}
		if (current) {
			const separatorIndex = line.indexOf(":");
			if (separatorIndex === -1) {
				continue;
			}
			const name = line.slice(0, separatorIndex).trim().toLowerCase();
			const value = line.slice(separatorIndex + 1).trim();
			current.headers[name] = value;
		}
	}
	return blocks;
}
