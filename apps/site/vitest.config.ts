/// <reference types="vitest/config" />
// vitest.config.ts — src/lib配下の純粋関数(diffLines等)の単体テスト用(Astroページ本体はe2eで検証)
import { defineConfig } from "vitest/config";

export default defineConfig({
	test: {
		environment: "node",
		include: ["src/**/*.test.ts"],
	},
});
