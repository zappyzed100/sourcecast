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

const candidateDecisionSchema = z.object({
	schema_version: z.literal(1),
	decision_id: z.string(),
	candidate_id: z.string(),
	decision: z.enum(["adopted", "excluded"]),
	reason: z.string(),
	decided_at: z.string(),
});
export type CandidateDecision = z.infer<typeof candidateDecisionSchema>;
export type CandidateDecisionValue = CandidateDecision["decision"];

const episodeStateSchema = z.enum([
	"collected",
	"rights_passed",
	"topic_selected",
	"facts_verified",
	"script_generated",
	"script_verified",
	"media_generated",
	"publish_ready",
	"approved",
	"published",
	"rejected",
	"blocked",
]);
export type EpisodeState = z.infer<typeof episodeStateSchema>;

const episodeSchema = z.object({
	schema_version: z.literal(1),
	episode_id: z.string(),
	state: episodeStateSchema,
	revision: z.number().int().positive(),
	title: z.string(),
	created_at: z.string(),
	updated_at: z.string(),
});
export type Episode = z.infer<typeof episodeSchema>;

const jobStatusSchema = z.enum([
	"queued",
	"running",
	"succeeded",
	"failed",
	"blocked",
	"cancelled",
]);
export type JobStatus = z.infer<typeof jobStatusSchema>;

// SSE再接続時にクライアント側で購読を止める判断に使う(サーバー側の
// jobs/events.pyのTERMINAL_JOB_STATUSESと同じ集合——値が食い違うとブラウザが
// 終了済みジョブへ無駄な再接続を続けてしまう)。
export const TERMINAL_JOB_STATUSES: ReadonlySet<JobStatus> = new Set([
	"succeeded",
	"failed",
	"blocked",
	"cancelled",
]);

const jobSchema = z.object({
	schema_version: z.literal(1),
	job_id: z.string(),
	episode_id: z.string().nullable(),
	kind: z.string(),
	status: jobStatusSchema,
	progress: z.number().min(0).max(1),
	cancel_requested: z.boolean(),
	retry_of: z.string().nullable(),
	error: z.string().nullable(),
	created_at: z.string(),
	started_at: z.string().nullable(),
	finished_at: z.string().nullable(),
});
export type Job = z.infer<typeof jobSchema>;

const jobLogEntrySchema = z.object({
	schema_version: z.literal(1),
	job_id: z.string(),
	seq: z.number().int().positive(),
	level: z.enum(["info", "warning", "error"]),
	message: z.string(),
	occurred_at: z.string(),
});
export type JobLogEntry = z.infer<typeof jobLogEntrySchema>;

const jobEventSchema = z.object({
	job: jobSchema,
	logs: z.array(jobLogEntrySchema),
});
export type JobEvent = z.infer<typeof jobEventSchema>;

async function fetchJson(path: string, init?: RequestInit): Promise<unknown> {
	const controller = new AbortController();
	const timeoutId = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
	let response: Response;
	try {
		response = await fetch(`${API_BASE_URL}${path}`, {
			...init,
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
		// エラー応答のdetailを拾えれば理由をそのままユーザーへ見せる
		// (例: 除外の理由未入力 — 除外理由が空でAPIに拒否された旨をUIに伝える)。
		const detail = await response
			.json()
			.then((body: unknown) =>
				typeof body === "object" && body !== null && "detail" in body
					? String((body as { detail: unknown }).detail)
					: null,
			)
			.catch(() => null);
		throw new ApiError(
			detail ?? `APIがエラーを返しました(${response.status}): ${path}`,
		);
	}
	try {
		return await response.json();
	} catch (error) {
		throw new ApiError(`APIの応答がJSONとして解釈できません: ${path}`, error);
	}
}

async function postJson(path: string, body: unknown): Promise<unknown> {
	return fetchJson(path, {
		method: "POST",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify(body),
	});
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

export async function reviewCandidate(
	candidateId: string,
	decision: CandidateDecisionValue,
	reason?: string,
): Promise<CandidateDecision> {
	const json = await postJson(`/api/v1/candidates/${candidateId}/review`, {
		decision,
		reason: reason ?? null,
	});
	const result = candidateDecisionSchema.safeParse(json);
	if (!result.success) {
		throw new ApiError("審査結果応答の形式が不正です", result.error);
	}
	return result.data;
}

export async function getCandidateDecisions(
	candidateId: string,
): Promise<CandidateDecision[]> {
	const json = await fetchJson(`/api/v1/candidates/${candidateId}/decisions`);
	const result = z.array(candidateDecisionSchema).safeParse(json);
	if (!result.success) {
		throw new ApiError("審査履歴応答の形式が不正です", result.error);
	}
	return result.data;
}

export async function getEpisodes(): Promise<Episode[]> {
	const json = await fetchJson("/api/v1/episodes");
	const result = z.array(episodeSchema).safeParse(json);
	if (!result.success) {
		throw new ApiError("エピソード一覧応答の形式が不正です", result.error);
	}
	return result.data;
}

export async function approveEpisode(episodeId: string): Promise<Episode> {
	const json = await postJson(`/api/v1/episodes/${episodeId}/approve`, {});
	const result = episodeSchema.safeParse(json);
	if (!result.success) {
		throw new ApiError("承認結果応答の形式が不正です", result.error);
	}
	return result.data;
}

export async function publishEpisode(episodeId: string): Promise<Episode> {
	const json = await postJson(`/api/v1/episodes/${episodeId}/publish`, {});
	const result = episodeSchema.safeParse(json);
	if (!result.success) {
		throw new ApiError("限定公開結果応答の形式が不正です", result.error);
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

export async function startEpisodeGeneration(episodeId: string): Promise<Job> {
	const json = await postJson(`/api/v1/episodes/${episodeId}/generate`, {});
	const result = jobSchema.safeParse(json);
	if (!result.success) {
		throw new ApiError("生成ジョブ開始応答の形式が不正です", result.error);
	}
	return result.data;
}

export async function getJobLogs(jobId: string): Promise<JobLogEntry[]> {
	const json = await fetchJson(`/api/v1/jobs/${jobId}/logs`);
	const result = z.array(jobLogEntrySchema).safeParse(json);
	if (!result.success) {
		throw new ApiError("ジョブログ応答の形式が不正です", result.error);
	}
	return result.data;
}

export async function cancelJob(jobId: string): Promise<Job> {
	const json = await postJson(`/api/v1/jobs/${jobId}/cancel`, {});
	const result = jobSchema.safeParse(json);
	if (!result.success) {
		throw new ApiError("キャンセル結果応答の形式が不正です", result.error);
	}
	return result.data;
}

export async function retryJob(jobId: string): Promise<Job> {
	const json = await postJson(`/api/v1/jobs/${jobId}/retry`, {});
	const result = jobSchema.safeParse(json);
	if (!result.success) {
		throw new ApiError("再実行結果応答の形式が不正です", result.error);
	}
	return result.data;
}

// subscribeToJobEvents — GET /api/v1/jobs/{id}/eventsをEventSourceで購読する
// (仕様書§14・Phase 11タスク2「SSE進捗」)。ジョブが終端状態(succeeded/failed/
// blocked/cancelled)へ達したイベントを受け取ったら、サーバー側がストリームを
// 閉じた後もブラウザのEventSourceが自動再接続を試み続けてしまう既定動作を
// 避けるため、ここで明示的にclose()する。戻り値の関数を呼べば購読を中断できる
// (ReactのuseEffectクリーンアップから呼ぶ想定)。
export function subscribeToJobEvents(
	jobId: string,
	onUpdate: (event: JobEvent) => void,
): () => void {
	const source = new EventSource(`${API_BASE_URL}/api/v1/jobs/${jobId}/events`);
	source.onmessage = (message) => {
		let parsed: unknown;
		try {
			parsed = JSON.parse(message.data as string);
		} catch {
			return; // 壊れたイベントは無視し、次のイベントで復帰を待つ
		}
		const result = jobEventSchema.safeParse(parsed);
		if (!result.success) return;
		onUpdate(result.data);
		if (TERMINAL_JOB_STATUSES.has(result.data.job.status)) {
			source.close();
		}
	};
	return () => source.close();
}
