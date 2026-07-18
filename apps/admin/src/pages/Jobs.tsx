// Jobs.tsx — ジョブ管理(仕様書§12.1・§14・development-plan.md Phase 11タスク2)。
// API停止・タイムアウト・空データ・壊れた応答を安全に表示する(plan.md Phase 2 DoD)。
// 一覧はGET /jobs(常にDBの正本を返す——ブラウザ再読込後もここから正しい状態へ復帰する)、
// 進捗・ログのその後の更新はqueued/runningのジョブだけSSEで購読する。
import { useCallback, useEffect, useState } from "react";
import {
	ApiError,
	cancelJob,
	getJobLogs,
	getJobs,
	type Job,
	type JobLogEntry,
	retryJob,
	subscribeToJobEvents,
} from "../lib/api";
import { useAsync } from "../lib/useAsync";

const ACTIVE_STATUSES: ReadonlySet<Job["status"]> = new Set([
	"queued",
	"running",
]);
const RETRYABLE_STATUSES: ReadonlySet<Job["status"]> = new Set([
	"failed",
	"blocked",
	"cancelled",
]);

const STATUS_LABELS: Record<Job["status"], string> = {
	queued: "待機中",
	running: "実行中",
	succeeded: "成功",
	failed: "失敗",
	blocked: "障害停止",
	cancelled: "キャンセル済み",
};

export function Jobs() {
	const state = useAsync<Job[]>(getJobs);
	const [overrides, setOverrides] = useState<Record<string, Job>>({});
	const [extraJobs, setExtraJobs] = useState<Job[]>([]);
	const [logsByJob, setLogsByJob] = useState<Record<string, JobLogEntry[]>>({});
	const [expanded, setExpanded] = useState<Record<string, boolean>>({});
	const [pendingId, setPendingId] = useState<string | null>(null);
	const [rowError, setRowError] = useState<Record<string, string>>({});

	const subscribeToJobUpdates = useCallback((jobId: string): (() => void) => {
		return subscribeToJobEvents(jobId, ({ job, logs }) => {
			setOverrides((prev) => ({ ...prev, [job.job_id]: job }));
			if (logs.length > 0) {
				setLogsByJob((prev) => ({
					...prev,
					[job.job_id]: [...(prev[job.job_id] ?? []), ...logs],
				}));
			}
		});
	}, []);

	// 初回取得時点でqueued/runningのジョブはSSEで進捗・ログを購読し続ける——
	// GET /jobsで正本のDB値を読んで正しい状態へ復帰した後、実行中のものだけ
	// 購読を再開する(Phase 11タスク2 DoD「ブラウザ再読込後も正しいジョブ状態へ復帰する」)。
	useEffect(() => {
		if (state.status !== "success") return;
		const unsubscribers = state.data
			.filter((job) => ACTIVE_STATUSES.has(job.status))
			.map((job) => subscribeToJobUpdates(job.job_id));
		return () => {
			for (const unsubscribe of unsubscribers) unsubscribe();
		};
	}, [state, subscribeToJobUpdates]);

	async function handleCancel(jobId: string) {
		setPendingId(jobId);
		setRowError((prev) => ({ ...prev, [jobId]: "" }));
		try {
			const updated = await cancelJob(jobId);
			setOverrides((prev) => ({ ...prev, [jobId]: updated }));
		} catch (error) {
			setRowError((prev) => ({
				...prev,
				[jobId]: error instanceof ApiError ? error.message : "不明なエラー",
			}));
		} finally {
			setPendingId(null);
		}
	}

	async function handleRetry(jobId: string) {
		setPendingId(jobId);
		setRowError((prev) => ({ ...prev, [jobId]: "" }));
		try {
			const newJob = await retryJob(jobId);
			setExtraJobs((prev) => [newJob, ...prev]);
			subscribeToJobUpdates(newJob.job_id);
		} catch (error) {
			setRowError((prev) => ({
				...prev,
				[jobId]: error instanceof ApiError ? error.message : "不明なエラー",
			}));
		} finally {
			setPendingId(null);
		}
	}

	async function handleToggleLogs(jobId: string) {
		const willExpand = !expanded[jobId];
		setExpanded((prev) => ({ ...prev, [jobId]: willExpand }));
		if (willExpand && !logsByJob[jobId]) {
			try {
				const logs = await getJobLogs(jobId);
				setLogsByJob((prev) => ({ ...prev, [jobId]: logs }));
			} catch {
				// ログ取得の失敗は行の主要な状態表示を妨げない(黙って空のまま表示する)
			}
		}
	}

	if (state.status === "loading") {
		return (
			<p role="status" data-testid="jobs-loading">
				読み込み中…
			</p>
		);
	}

	if (state.status === "error") {
		const message =
			state.error instanceof ApiError ? state.error.message : "不明なエラー";
		return (
			<p role="alert" data-testid="jobs-error">
				ジョブ一覧を取得できませんでした: {message}
			</p>
		);
	}

	const rows = [...extraJobs, ...state.data].map(
		(fetched) => overrides[fetched.job_id] ?? fetched,
	);
	if (rows.length === 0) {
		return <p data-testid="jobs-empty">ジョブはまだありません。</p>;
	}

	return (
		<table data-testid="jobs-table">
			<thead>
				<tr>
					<th scope="col">エピソード</th>
					<th scope="col">工程</th>
					<th scope="col">状態</th>
					<th scope="col">進捗</th>
					<th scope="col">操作</th>
				</tr>
			</thead>
			<tbody>
				{rows.map((job) => {
					const isPending = pendingId === job.job_id;
					const error = rowError[job.job_id];
					const logs = logsByJob[job.job_id] ?? [];
					return (
						<tr key={job.job_id}>
							<td>{job.episode_id ?? "—"}</td>
							<td>{job.kind}</td>
							<td data-testid={`job-status-${job.job_id}`}>
								{STATUS_LABELS[job.status]}
								{job.cancel_requested &&
									job.status === "running" &&
									"(キャンセル要求中)"}
							</td>
							<td>
								<progress
									data-testid={`job-progress-${job.job_id}`}
									value={job.progress}
									max={1}
								/>{" "}
								{Math.round(job.progress * 100)}%
							</td>
							<td>
								{ACTIVE_STATUSES.has(job.status) && !job.cancel_requested && (
									<button
										type="button"
										disabled={isPending}
										data-testid={`cancel-${job.job_id}`}
										onClick={() => handleCancel(job.job_id)}
									>
										キャンセル
									</button>
								)}
								{RETRYABLE_STATUSES.has(job.status) && (
									<button
										type="button"
										disabled={isPending}
										data-testid={`retry-${job.job_id}`}
										onClick={() => handleRetry(job.job_id)}
									>
										再実行
									</button>
								)}
								<button
									type="button"
									data-testid={`toggle-logs-${job.job_id}`}
									onClick={() => handleToggleLogs(job.job_id)}
								>
									ログ{expanded[job.job_id] ? "を隠す" : "を表示"}
								</button>
								{job.error && <p role="alert">{job.error}</p>}
								{error && (
									<p role="alert" data-testid={`job-error-${job.job_id}`}>
										{error}
									</p>
								)}
								{expanded[job.job_id] && (
									<ul data-testid={`job-logs-${job.job_id}`}>
										{logs.map((log) => (
											<li key={log.seq}>{log.message}</li>
										))}
									</ul>
								)}
							</td>
						</tr>
					);
				})}
			</tbody>
		</table>
	);
}
