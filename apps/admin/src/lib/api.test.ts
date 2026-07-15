// api.test.ts — Phase 2 DoD: API停止・タイムアウト・空データ・壊れた応答の4パターンを固定する
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, getCandidates, getDashboardSummary, getJobs } from "./api";

function jsonResponse(body: unknown, ok = true): Response {
	return {
		ok,
		status: ok ? 200 : 500,
		json: () => Promise.resolve(body),
	} as Response;
}

describe("api client", () => {
	afterEach(() => {
		vi.restoreAllMocks();
	});

	it("APIが停止している場合はApiErrorになる(down)", async () => {
		vi.stubGlobal(
			"fetch",
			vi.fn().mockRejectedValue(new TypeError("Failed to fetch")),
		);
		await expect(getDashboardSummary()).rejects.toBeInstanceOf(ApiError);
	});

	it("タイムアウトした場合はApiErrorになる(timeout)", async () => {
		vi.stubGlobal(
			"fetch",
			vi
				.fn()
				.mockImplementation((_url: string, init?: { signal?: AbortSignal }) => {
					return new Promise((_resolve, reject) => {
						init?.signal?.addEventListener("abort", () => {
							reject(
								new DOMException("The operation was aborted.", "AbortError"),
							);
						});
					});
				}),
		);
		vi.useFakeTimers();
		const promise = getDashboardSummary();
		const assertion = expect(promise).rejects.toBeInstanceOf(ApiError);
		await vi.advanceTimersByTimeAsync(6000);
		await assertion;
		vi.useRealTimers();
	});

	it("空配列は正常系として扱う(empty)", async () => {
		vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse([])));
		await expect(getCandidates()).resolves.toEqual([]);
		await expect(getJobs()).resolves.toEqual([]);
	});

	it("形の壊れた応答はApiErrorになる(malformed)", async () => {
		vi.stubGlobal(
			"fetch",
			vi
				.fn()
				.mockResolvedValue(jsonResponse({ totally: "not what we expect" })),
		);
		await expect(getDashboardSummary()).rejects.toBeInstanceOf(ApiError);
	});

	it("JSONとして解釈できない応答もApiErrorになる(malformed)", async () => {
		vi.stubGlobal(
			"fetch",
			vi.fn().mockResolvedValue({
				ok: true,
				status: 200,
				json: () => Promise.reject(new SyntaxError("Unexpected token")),
			} as unknown as Response),
		);
		await expect(getCandidates()).rejects.toBeInstanceOf(ApiError);
	});

	it("HTTPエラーステータスはApiErrorになる", async () => {
		vi.stubGlobal(
			"fetch",
			vi.fn().mockResolvedValue(jsonResponse({ detail: "boom" }, false)),
		);
		await expect(getJobs()).rejects.toBeInstanceOf(ApiError);
	});
});
