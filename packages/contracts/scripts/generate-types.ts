// generate-types.ts — packages/contracts/schema/*.schema.json からTypeScript型を生成する
//
// 正本はPython側のPydanticモデル（services/pipeline/src/history_radio/domain）。
// JSON Schemaはそこから scripts/generate_contracts.py が生成し、本スクリプトはその
// Schemaから型を生成するだけ——手書きで二重管理しない（plan.md §2.3）。
import { readdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { compile } from "json-schema-to-typescript";

const here = path.dirname(fileURLToPath(import.meta.url));
const contractsRoot = path.resolve(here, "..");
const schemaDir = path.join(contractsRoot, "schema");
const generatedDir = path.join(contractsRoot, "src", "generated");

async function main(): Promise<void> {
	const entries = (await readdir(schemaDir))
		.filter((name) => name.endsWith(".schema.json"))
		.sort();

	const exportLines: string[] = [];
	for (const entry of entries) {
		const schemaText = await readFile(path.join(schemaDir, entry), "utf-8");
		const schema = JSON.parse(schemaText);
		const modelName = entry.replace(/\.schema\.json$/, "");
		const ts = await compile(schema, modelName, {
			bannerComment: `/** ${modelName}.ts — 生成物。手編集しない（正本: services/pipeline/src/history_radio/domain、生成: scripts/generate_contracts.py + packages/contracts/scripts/generate-types.ts） */`,
			style: { semi: true },
		});
		const outPath = path.join(generatedDir, `${modelName}.ts`);
		await writeFile(outPath, ts, "utf-8");
		exportLines.push(
			`export type { ${modelName} } from "./generated/${modelName}.ts";`,
		);
		console.log(`[generate-types] src/generated/${modelName}.ts`);
	}

	const indexPath = path.join(contractsRoot, "src", "index.ts");
	const indexBody = [
		"// index.ts — 生成された型の再輸出エントリポイント（手編集しない部分は generated/ 側）",
		"// 手編集してよいのはこのヘッダーコメントと CONTRACTS_SCHEMA_VERSION の値のみ。",
		"",
		...exportLines,
		"",
		"export const CONTRACTS_SCHEMA_VERSION = 1 as const;",
		"",
	].join("\n");
	await writeFile(indexPath, indexBody, "utf-8");
	console.log("[generate-types] src/index.ts");
}

main().catch((err: unknown) => {
	console.error(err);
	process.exitCode = 1;
});
