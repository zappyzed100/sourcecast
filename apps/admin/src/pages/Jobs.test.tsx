// Jobs.test.tsx — Phase 11タスク2 DoD: 進捗・キャンセル・再実行・ログ追跡が
// 管理画面から操作できることを固定する。EventSourceはjsdomに実装が無いため、
// subscribeToJobEvents自体をAPI境界でモックし、SSEのonUpdateコールバックを
// テストから直接呼んで購読後の更新を再現する(他のテストと同じ「api.tsをモックする」方針)。
import {
	act,
	fireEvent,
	render,
	screen,
	waitFor,
} from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import * as api from "../lib/api";
import { Jobs } from "./Jobs";

const RUNNING_JOB: api.Job = {
	schema_version: 1,
	job_id: "job-001",
	episode_id: "ep-001",
	kind: "episode_generation",
	status: "running",
	progress: 0.3,
	cancel_requested: false,
	retry_of: null,
	error: null,
	created_at: "2026-07-19T00:00:00Z",
	started_at: "2026-07-19T00:00:01Z",
	finished_at: null,
};

const FAILED_JOB: api.Job = {
	...RUNNING_JOB,
	job_id: "job-002",
	status: "failed",
	progress: 0.1,
	error: "VOICEVOXエンジンへの接続タイムアウト",
	finished_at: "2026-07-19T00:00:02Z",
};

function mockSubscribe(): {
	trigger: (event: api.JobEvent) => void;
	unsubscribe: ReturnType<typeof vi.fn>;
} {
	let onUpdate: ((event: api.JobEvent) => void) | null = null;
	const unsubscribe = vi.fn();
	vi.spyOn(api, "subscribeToJobEvents").mockImplementation(
		(_jobId, callback) => {
			onUpdate = callback;
			return unsubscribe;
		},
	);
	return {
		trigger: (event) => {
			if (onUpdate) act(() => onUpdate?.(event));
		},
		unsubscribe,
	};
}

describe("Jobs", () => {
	it("ジョブが0件なら空メッセージを表示する", async () => {
		vi.spyOn(api, "getJobs").mockResolvedValue([]);
		render(<Jobs />);
		expect(await screen.findByTestId("jobs-empty")).toBeInTheDocument();
	});

	it("running状態のジョブには進捗バーとキャンセルボタンが表示される", async () => {
		vi.spyOn(api, "getJobs").mockResolvedValue([RUNNING_JOB]);
		mockSubscribe();
		render(<Jobs />);
		await screen.findByTestId("jobs-table");
		expect(screen.getByTestId("job-progress-job-001")).toHaveValue(0.3);
		expect(screen.getByTestId("cancel-job-001")).toBeInTheDocument();
		expect(screen.queryByTestId("retry-job-001")).not.toBeInTheDocument();
	});

	it("running状態のジョブはSSE購読を開始する", async () => {
		vi.spyOn(api, "getJobs").mockResolvedValue([RUNNING_JOB]);
		mockSubscribe();
		render(<Jobs />);
		await screen.findByTestId("jobs-table");
		expect(api.subscribeToJobEvents).toHaveBeenCalledWith(
			"job-001",
			expect.any(Function),
		);
	});

	it("SSEイベントを受け取ると進捗・状態がその場で更新される", async () => {
		vi.spyOn(api, "getJobs").mockResolvedValue([RUNNING_JOB]);
		const { trigger } = mockSubscribe();
		render(<Jobs />);
		await screen.findByTestId("jobs-table");

		trigger({
			job: { ...RUNNING_JOB, status: "succeeded", progress: 1 },
			logs: [],
		});

		await waitFor(() => {
			expect(screen.getByTestId("job-status-job-001")).toHaveTextContent(
				"成功",
			);
		});
		expect(screen.getByTestId("job-progress-job-001")).toHaveValue(1);
		// 終端状態になったのでキャンセルボタンは消える
		expect(screen.queryByTestId("cancel-job-001")).not.toBeInTheDocument();
	});

	it("キャンセルボタンをクリックするとcancel_requestedがtrueになる", async () => {
		vi.spyOn(api, "getJobs").mockResolvedValue([RUNNING_JOB]);
		mockSubscribe();
		vi.spyOn(api, "cancelJob").mockResolvedValue({
			...RUNNING_JOB,
			cancel_requested: true,
		});

		render(<Jobs />);
		await screen.findByTestId("jobs-table");

		fireEvent.click(screen.getByTestId("cancel-job-001"));

		await waitFor(() => {
			expect(screen.getByTestId("job-status-job-001")).toHaveTextContent(
				"キャンセル要求中",
			);
		});
		expect(api.cancelJob).toHaveBeenCalledWith("job-001");
	});

	it("終端の失敗状態のジョブには再実行ボタンが表示されキャンセルボタンは無い", async () => {
		vi.spyOn(api, "getJobs").mockResolvedValue([FAILED_JOB]);
		render(<Jobs />);
		await screen.findByTestId("jobs-table");
		expect(screen.getByTestId("retry-job-002")).toBeInTheDocument();
		expect(screen.queryByTestId("cancel-job-002")).not.toBeInTheDocument();
	});

	it("再実行ボタンをクリックすると新しいジョブが一覧の先頭に追加される", async () => {
		vi.spyOn(api, "getJobs").mockResolvedValue([FAILED_JOB]);
		mockSubscribe();
		vi.spyOn(api, "retryJob").mockResolvedValue({
			...FAILED_JOB,
			job_id: "job-003",
			status: "queued",
			progress: 0,
			error: null,
			retry_of: "job-002",
			finished_at: null,
		});

		render(<Jobs />);
		await screen.findByTestId("jobs-table");

		fireEvent.click(screen.getByTestId("retry-job-002"));

		await waitFor(() => {
			expect(screen.getByTestId("job-status-job-003")).toHaveTextContent(
				"待機中",
			);
		});
		expect(api.retryJob).toHaveBeenCalledWith("job-002");
	});

	it("ログを表示ボタンでログが取得され表示される", async () => {
		vi.spyOn(api, "getJobs").mockResolvedValue([FAILED_JOB]);
		vi.spyOn(api, "getJobLogs").mockResolvedValue([
			{
				schema_version: 1,
				job_id: "job-002",
				seq: 1,
				level: "error",
				message: "失敗: VOICEVOXエンジンへの接続タイムアウト",
				occurred_at: "2026-07-19T00:00:02Z",
			},
		]);

		render(<Jobs />);
		await screen.findByTestId("jobs-table");

		fireEvent.click(screen.getByTestId("toggle-logs-job-002"));

		await waitFor(() => {
			expect(screen.getByTestId("job-logs-job-002")).toHaveTextContent(
				"失敗: VOICEVOXエンジンへの接続タイムアウト",
			);
		});
		expect(api.getJobLogs).toHaveBeenCalledWith("job-002");
	});
});
