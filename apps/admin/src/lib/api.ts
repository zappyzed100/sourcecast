// api.ts — localhost管理APIのクライアント(plan.md Phase 2)。
//
// 3つの失敗モードを型で区別する(plan.md Phase 2 DoD「API停止・タイムアウト・空データ・
// 壊れた応答を各画面が安全に表示する」): ネットワーク層の失敗(down/timeout)はApiError、
// 形が違う応答はzodのParseErrorとして呼び出し側へ伝える。空データはエラーではなく
// 正常系の「結果が0件」として扱う(呼び出し側でUI分岐する)。
import { z } from "zod";

const API_BASE_URL =
	import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";
const REQUEST_TIMEOUT_MS = 5000;

export class ApiError extends Error {
	constructor(message: string, cause?: unknown) {
		super(message, { cause });
		this.name = "ApiError";
	}
}

const dashboardSummarySchema = z.object({
	schema_version: z.literal(1),
	jobs_running: z.number().int().nonnegative(),
	jobs_queued: z.number().int().nonnegative(),
	jobs_failed_today: z.number().int().nonnegative(),
	episodes_published_this_month: z.number().int().nonnegative(),
	openrouter_calls_today: z.number().int().nonnegative(),
	candidates_awaiting_review: z.number().int().nonnegative(),
});
export type DashboardSummary = z.infer<typeof dashboardSummarySchema>;

const candidateSchema = z.object({
	schema_version: z.literal(1),
	candidate_id: z.string(),
	topic_title: z.string(),
	score: z.number(),
	score_breakdown: z.record(z.string(), z.number()),
	independent_source_families: z.number().int().nonnegative(),
});
export type Candidate = z.infer<typeof candidateSchema>;

const jobSchema = z.object({
	schema_version: z.literal(1),
	job_id: z.string(),
	episode_id: z.string().nullable(),
	kind: z.string(),
	status: z.enum(["queued", "running", "succeeded", "failed", "blocked"]),
	error: z.string().nullable(),
	started_at: z.string().nullable(),
	finished_at: z.string().nullable(),
});
export type Job = z.infer<typeof jobSchema>;

async function fetchJson(path: string): Promise<unknown> {
	const controller = new AbortController();
	const timeoutId = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
	let response: Response;
	try {
		response = await fetch(`${API_BASE_URL}${path}`, {
			signal: controller.signal,
		});
	} catch (error) {
		if (error instanceof DOMException && error.name === "AbortError") {
			throw new ApiError(
				`APIがタイムアウトしました(${REQUEST_TIMEOUT_MS}ms): ${path}`,
				error,
			);
		}
		throw new ApiError(`APIに接続できません: ${path}`, error);
	} finally {
		clearTimeout(timeoutId);
	}
	if (!response.ok) {
		throw new ApiError(`APIがエラーを返しました(${response.status}): ${path}`);
	}
	try {
		return await response.json();
	} catch (error) {
		throw new ApiError(`APIの応答がJSONとして解釈できません: ${path}`, error);
	}
}

export async function getDashboardSummary(): Promise<DashboardSummary> {
	const json = await fetchJson("/api/v1/dashboard");
	const result = dashboardSummarySchema.safeParse(json);
	if (!result.success) {
		throw new ApiError("ダッシュボード応答の形式が不正です", result.error);
	}
	return result.data;
}

export async function getCandidates(): Promise<Candidate[]> {
	const json = await fetchJson("/api/v1/candidates");
	const result = z.array(candidateSchema).safeParse(json);
	if (!result.success) {
		throw new ApiError("候補一覧応答の形式が不正です", result.error);
	}
	return result.data;
}

export async function getJobs(): Promise<Job[]> {
	const json = await fetchJson("/api/v1/jobs");
	const result = z.array(jobSchema).safeParse(json);
	if (!result.success) {
		throw new ApiError("ジョブ一覧応答の形式が不正です", result.error);
	}
	return result.data;
}
