// candidate-to-published.spec.ts — Phase 11タスク1 DoD: 1件を最初から限定公開まで
// 操作するPlaywright E2E(候補→審査→承認→限定公開)。
//
// 実際の収集・選出・台本生成・音声合成・自動検査ゲート実行(Phase 4〜10)は
// まだ管理API・管理画面へ接続されていない(Phase 11タスク2「実ジョブ接続」以降の仕事)
// ——このE2Eは「候補が既にある」ところから始め、審査(採用)後にpublish_readyへ
// 進める部分だけpythonの直接シードで代替する。候補→審査(採用)によるEpisode自動作成、
// 承認、限定公開の4操作はすべてブラウザ操作(実クリック)と実API呼び出しで検証する。
import { randomUUID } from "node:crypto";
import { execFileSync } from "node:child_process";
import path from "node:path";
import { expect, test } from "@playwright/test";

const DB_PATH = path.join(process.cwd(), "data", "e2e-admin.sqlite3");
// e2e-admin.sqlite3はローカル実行間で使い回される(playwright.config.tsの
// reuseExistingServer)ため、テストごとに一意なIDが必要(時刻依存の挙動を
// 検証しているわけではない)。
const CANDIDATE_ID = `e2e-candidate-${randomUUID()}`;

function runPythonSeed(script: string, ...args: string[]): void {
	execFileSync("uv", ["run", "python", script, DB_PATH, ...args], {
		cwd: process.cwd(),
		stdio: "inherit",
	});
}

test.beforeAll(() => {
	// 実際の収集・選出パイプラインが未接続のため、候補一覧の起点をテスト専用シードで作る。
	runPythonSeed(
		"scripts/e2e_seed_candidate.py",
		CANDIDATE_ID,
		"E2Eテスト用の題材(缶切りの歴史)",
	);
});

test("候補の採用から限定公開までを1件のエピソードとして操作できる", async ({ page }) => {
	// 1. 候補一覧 → 採用(審査)。episode_idにはcandidate_idがそのまま使われる
	//    (development-plan.md Phase 11タスク1「候補→審査→承認→限定公開を1件の
	//    エピソードとして繋げる連携」)。
	await page.goto("/candidates");
	await page.waitForSelector('[data-testid="candidates-table"]');
	await page.click(`[data-testid="adopt-${CANDIDATE_ID}"]`);
	await expect(
		page.locator(`[data-testid="candidate-review-${CANDIDATE_ID}"]`),
	).toContainText("採用済み");

	// 2. 実生成パイプライン(script/media生成・自動検査ゲート実行)がまだ無いため、
	//    テスト専用シードでpublish_readyへ進める(この1手順だけがブラウザ操作の代わり)。
	runPythonSeed("scripts/e2e_fast_forward_episode.py", CANDIDATE_ID);

	// 3. エピソード一覧 → 承認。
	await page.goto("/episodes");
	await page.waitForSelector('[data-testid="episodes-table"]');
	await expect(
		page.locator(`[data-testid="episode-state-${CANDIDATE_ID}"]`),
	).toHaveText("公開準備完了");
	await page.click(`[data-testid="approve-${CANDIDATE_ID}"]`);
	await expect(
		page.locator(`[data-testid="episode-state-${CANDIDATE_ID}"]`),
	).toHaveText("承認済み");

	// 4. 限定公開。
	await page.click(`[data-testid="publish-${CANDIDATE_ID}"]`);
	await expect(
		page.locator(`[data-testid="episode-state-${CANDIDATE_ID}"]`),
	).toHaveText("公開済み(限定公開)");

	// 限定公開後は操作ボタンが両方とも消える(publishedは終端状態)。
	await expect(
		page.locator(`[data-testid="approve-${CANDIDATE_ID}"]`),
	).toHaveCount(0);
	await expect(
		page.locator(`[data-testid="publish-${CANDIDATE_ID}"]`),
	).toHaveCount(0);
});
