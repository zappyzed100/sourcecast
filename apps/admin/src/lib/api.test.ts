// api.test.ts — Phase 2 DoD: API停止・タイムアウト・空データ・壊れた応答の4パターンを固定する
// (Phase 11タスク1: 候補審査・エピソード承認APIクライアントのテストも本ファイルに追加)
import { afterEach, describe, expect, it, vi } from "vitest";
import {
	ApiError,
	approveEpisode,
	getCandidateDecisions,
	getCandidates,
	getDashboardSummary,
	getEpisodes,
	getJobs,
	reviewCandidate,
} from "./api";

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

describe("candidate review", () => {
	afterEach(() => {
		vi.restoreAllMocks();
	});

	function decisionResponse(overrides: Record<string, unknown> = {}) {
		return jsonResponse({
			schema_version: 1,
			decision_id: "decision-cand-1-abcd1234",
			candidate_id: "cand-1",
			decision: "adopted",
			reason: "",
			decided_at: "2026-07-19T00:00:00Z",
			...overrides,
		});
	}

	it("採用はPOSTでdecisionを送りCandidateDecisionを返す", async () => {
		const fetchMock = vi.fn().mockResolvedValue(decisionResponse());
		vi.stubGlobal("fetch", fetchMock);

		const result = await reviewCandidate("cand-1", "adopted");

		expect(result.decision).toBe("adopted");
		const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
		expect(init.method).toBe("POST");
		expect(JSON.parse(init.body as string)).toEqual({
			decision: "adopted",
			reason: null,
		});
	});

	it("除外理由をbodyへ含めて送る", async () => {
		const fetchMock = vi.fn().mockResolvedValue(
			decisionResponse({
				decision: "excluded",
				reason: "出典が信頼できない",
			}),
		);
		vi.stubGlobal("fetch", fetchMock);

		const result = await reviewCandidate(
			"cand-1",
			"excluded",
			"出典が信頼できない",
		);

		expect(result.decision).toBe("excluded");
		expect(result.reason).toBe("出典が信頼できない");
		const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
		expect(JSON.parse(init.body as string)).toEqual({
			decision: "excluded",
			reason: "出典が信頼できない",
		});
	});

	it("除外理由なしでAPIが400を返すとdetailメッセージ付きのApiErrorになる", async () => {
		vi.stubGlobal(
			"fetch",
			vi
				.fn()
				.mockResolvedValue(
					jsonResponse({ detail: "除外には理由の入力が必須" }, false),
				),
		);

		await expect(reviewCandidate("cand-1", "excluded")).rejects.toMatchObject({
			message: "除外には理由の入力が必須",
		});
	});

	it("審査履歴は空配列を正常系として扱う", async () => {
		vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse([])));
		await expect(getCandidateDecisions("cand-1")).resolves.toEqual([]);
	});

	it("形の壊れた審査結果応答はApiErrorになる", async () => {
		vi.stubGlobal(
			"fetch",
			vi.fn().mockResolvedValue(jsonResponse({ totally: "wrong shape" })),
		);
		await expect(reviewCandidate("cand-1", "adopted")).rejects.toBeInstanceOf(
			ApiError,
		);
	});
});

describe("episode approval", () => {
	afterEach(() => {
		vi.restoreAllMocks();
	});

	function episodeResponse(overrides: Record<string, unknown> = {}) {
		return jsonResponse({
			schema_version: 1,
			episode_id: "ep-001",
			state: "publish_ready",
			revision: 1,
			title: "缶切りより缶詰",
			created_at: "2026-07-19T00:00:00Z",
			updated_at: "2026-07-19T00:00:00Z",
			...overrides,
		});
	}

	it("空配列は正常系として扱う", async () => {
		vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse([])));
		await expect(getEpisodes()).resolves.toEqual([]);
	});

	it("承認はPOSTしstateがapprovedのEpisodeを返す", async () => {
		const fetchMock = vi
			.fn()
			.mockResolvedValue(episodeResponse({ state: "approved" }));
		vi.stubGlobal("fetch", fetchMock);

		const result = await approveEpisode("ep-001");

		expect(result.state).toBe("approved");
		const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
		expect(url).toContain("/api/v1/episodes/ep-001/approve");
		expect(init.method).toBe("POST");
	});

	it("ゲート不合格でAPIが400を返すとdetailメッセージ付きのApiErrorになる", async () => {
		vi.stubGlobal(
			"fetch",
			vi
				.fn()
				.mockResolvedValue(
					jsonResponse({ detail: "自動検査ゲートが不合格" }, false),
				),
		);

		await expect(approveEpisode("ep-001")).rejects.toMatchObject({
			message: "自動検査ゲートが不合格",
		});
	});

	it("形の壊れたエピソード応答はApiErrorになる", async () => {
		vi.stubGlobal(
			"fetch",
			vi.fn().mockResolvedValue(jsonResponse({ totally: "wrong shape" })),
		);
		await expect(getEpisodes()).rejects.toBeInstanceOf(ApiError);
	});
});
