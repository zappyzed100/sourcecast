// audio-player.spec.ts — Phase 2 DoD: キーボードのみで再生・停止・章移動が通ることを確認する
import { expect, test } from "@playwright/test";

test.describe("音声プレイヤー", () => {
	test("キーボードのみで再生・一時停止ができる", async ({ page }) => {
		await page.goto("/episodes/2026-07-16-can-opener/");

		const playButton = page.getByTestId("audio-play-pause");
		const status = page.getByTestId("audio-status");

		await playButton.focus();
		await expect(playButton).toBeFocused();

		await page.keyboard.press("Enter");
		await expect(status).toHaveText("再生中");
		await expect(playButton).toHaveAttribute("aria-pressed", "true");

		await page.keyboard.press("Enter");
		await expect(status).toHaveText("一時停止中");
		await expect(playButton).toHaveAttribute("aria-pressed", "false");
	});

	test("キーボードのみで章へ移動して再生できる", async ({ page }) => {
		await page.goto("/episodes/2026-07-16-can-opener/");

		const secondChapter = page.getByTestId("audio-chapter-1");
		await secondChapter.focus();
		await expect(secondChapter).toBeFocused();

		await page.keyboard.press("Enter");
		// 章ボタンは押すと該当秒数へシークしてから再生する実装——再生状態になることが
		// シークで例外にならなかったことの確認になる
		await expect(page.getByTestId("audio-status")).toHaveText("再生中");
	});

	test("キーボードのみで10秒送り・戻しをしても再生状態のままエラーにならない", async ({ page }) => {
		await page.goto("/episodes/2026-07-16-can-opener/");

		const playButton = page.getByTestId("audio-play-pause");
		const status = page.getByTestId("audio-status");
		await playButton.focus();
		await page.keyboard.press("Enter");
		await expect(status).toHaveText("再生中");

		const forwardButton = page.getByTestId("audio-seek-forward");
		await forwardButton.focus();
		await expect(forwardButton).toBeFocused();
		await page.keyboard.press("Enter");
		await expect(status).toHaveText("再生中");

		const backButton = page.getByTestId("audio-seek-back");
		await backButton.focus();
		await expect(backButton).toBeFocused();
		await page.keyboard.press("Enter");
		await expect(status).toHaveText("再生中");
	});
});
