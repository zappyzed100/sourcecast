// job-progress-reload.spec.ts — Phase 11タスク2 DoD: 長時間ジョブのSSE進捗・キャンセルが
// ブラウザ再読込後も正しいジョブ状態へ復帰することを検証する。
//
// ジョブのstep delay/SSEポーリング間隔はplaywright.config.tsのwebServer envで短縮している
// (HISTORY_RADIO_JOB_STEP_DELAY_SECONDS=0.3・HISTORY_RADIO_JOB_SSE_POLL_SECONDS=0.1)——
// 0にはしていない: このテストは「実行中の途中」を実際に観測してから再読込する必要があり、
// 即座に完了してしまうと再読込前後の状態比較にならない。
import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import path from "node:path";
import { expect, test } from "@playwright/test";

const DB_PATH = path.join(process.cwd(), "data", "e2e-admin.sqlite3");

function runPythonSeed(script: string, ...args: string[]): void {
	execFileSync("uv", ["run", "python", script, DB_PATH, ...args], {
		cwd: process.cwd(),
		stdio: "inherit",
	});
}

async function adoptCandidateAndStartGeneration(
	page: import("@playwright/test").Page,
	candidateId: string,
): Promise<void> {
	runPythonSeed(
		"scripts/e2e_seed_candidate.py",
		candidateId,
		"E2Eテスト用の題材(ジョブ進捗確認)",
	);

	await page.goto("/candidates");
	await page.waitForSelector('[data-testid="candidates-table"]');
	await page.click(`[data-testid="adopt-${candidateId}"]`);
	await expect(
		page.locator(`[data-testid="candidate-review-${candidateId}"]`),
	).toContainText("採用済み");

	await page.goto("/episodes");
	await page.waitForSelector('[data-testid="episodes-table"]');
	await page.click(`[data-testid="generate-${candidateId}"]`);
	await expect(
		page.locator(`[data-testid="generation-started-${candidateId}"]`),
	).toBeVisible();
}

test.describe("エピソード生成ジョブ(Phase 11タスク2)", () => {
	test("進捗はブラウザ再読込後もDBの正しい状態へ復帰し、成功まで進む", async ({
		page,
	}) => {
		const candidateId = `e2e-job-progress-${randomUUID()}`;
		await adoptCandidateAndStartGeneration(page, candidateId);

		await page.goto("/jobs");
		await page.waitForSelector('[data-testid="jobs-table"]');
		const jobRow = page.locator("tr", { hasText: candidateId });
		await expect(jobRow.locator('[data-testid^="job-status-"]')).toHaveText(
			/実行中|待機中/,
		);

		// 進捗が0より大きくなるまで待ってから再読込する(まだ実行中の途中であることを確かめてから)。
		await expect
			.poll(
				async () => {
					const value = await jobRow
						.locator('[data-testid^="job-progress-"]')
						.getAttribute("value");
					return value ? Number(value) : 0;
				},
				{ timeout: 10_000 },
			)
			.toBeGreaterThan(0);

		await page.reload();
		await page.waitForSelector('[data-testid="jobs-table"]');
		const reloadedJobRow = page.locator("tr", { hasText: candidateId });
		// 再読込直後もqueuedへ戻ったりせず、進行中か既に完了しているかのどちらか
		// ——DBが正本のGET /jobsを読むだけで正しい状態へ復帰する(Phase 11タスク2 DoD)。
		await expect(
			reloadedJobRow.locator('[data-testid^="job-status-"]'),
		).toHaveText(/実行中|成功/);

		// 最終的にpublish_readyまで到達し成功する。
		await expect(
			reloadedJobRow.locator('[data-testid^="job-status-"]'),
		).toHaveText("成功", { timeout: 15_000 });

		await page.goto("/episodes");
		await page.waitForSelector('[data-testid="episodes-table"]');
		await expect(
			page.locator(`[data-testid="episode-state-${candidateId}"]`),
		).toHaveText("公開準備完了");
	});

	test("キャンセルもブラウザ再読込後にキャンセル済みとして復帰する", async ({
		page,
	}) => {
		const candidateId = `e2e-job-cancel-${randomUUID()}`;
		await adoptCandidateAndStartGeneration(page, candidateId);

		await page.goto("/jobs");
		await page.waitForSelector('[data-testid="jobs-table"]');
		const jobRow = page.locator("tr", { hasText: candidateId });
		const cancelButton = jobRow.locator('[data-testid^="cancel-"]');
		await expect(cancelButton).toBeVisible();
		await cancelButton.click();

		await expect(jobRow.locator('[data-testid^="job-status-"]')).toHaveText(
			/キャンセル要求中|キャンセル済み/,
		);

		await page.reload();
		await page.waitForSelector('[data-testid="jobs-table"]');
		const reloadedJobRow = page.locator("tr", { hasText: candidateId });
		await expect(
			reloadedJobRow.locator('[data-testid^="job-status-"]'),
		).toHaveText("キャンセル済み", { timeout: 15_000 });
	});
});
