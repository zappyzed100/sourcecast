// Episodes.test.tsx — Phase 11タスク1 DoD: publish_ready状態だけ承認でき、
// approved状態だけ限定公開できる。Phase 11タスク2: 生成対象の状態には生成開始ボタンが出る
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import * as api from "../lib/api";
import { Episodes } from "./Episodes";

function renderEpisodes() {
	return render(
		<MemoryRouter>
			<Episodes />
		</MemoryRouter>,
	);
}

const READY_EPISODE = {
	schema_version: 1 as const,
	episode_id: "ep-001",
	state: "publish_ready" as const,
	revision: 1,
	title: "缶切りより缶詰",
	created_at: "2026-07-19T00:00:00Z",
	updated_at: "2026-07-19T00:00:00Z",
};

const COLLECTED_EPISODE = {
	...READY_EPISODE,
	episode_id: "ep-002",
	state: "collected" as const,
	title: "収集直後のエピソード",
};

const APPROVED_EPISODE = {
	...READY_EPISODE,
	episode_id: "ep-003",
	state: "approved" as const,
	title: "承認済みのエピソード",
};

const PUBLISHED_EPISODE = {
	...READY_EPISODE,
	episode_id: "ep-004",
	state: "published" as const,
	title: "公開済みのエピソード",
};

describe("Episodes", () => {
	it("publish_ready状態のエピソードには承認ボタンが表示される", async () => {
		vi.spyOn(api, "getEpisodes").mockResolvedValue([READY_EPISODE]);
		renderEpisodes();
		await screen.findByTestId("episodes-table");
		expect(screen.getByTestId("approve-ep-001")).toBeInTheDocument();
		expect(screen.queryByTestId("publish-ep-001")).not.toBeInTheDocument();
	});

	it("生成対象でも承認対象でもない状態(publishedなど)には操作ボタンが表示されない", async () => {
		vi.spyOn(api, "getEpisodes").mockResolvedValue([PUBLISHED_EPISODE]);
		renderEpisodes();
		await screen.findByTestId("episodes-table");
		expect(screen.queryByTestId("generate-ep-004")).not.toBeInTheDocument();
		expect(screen.queryByTestId("approve-ep-004")).not.toBeInTheDocument();
		expect(screen.queryByTestId("publish-ep-004")).not.toBeInTheDocument();
		expect(screen.getByTestId("no-action-ep-004")).toBeInTheDocument();
	});

	it("collected状態のエピソードには生成開始ボタンが表示される(Phase 11タスク2)", async () => {
		vi.spyOn(api, "getEpisodes").mockResolvedValue([COLLECTED_EPISODE]);
		renderEpisodes();
		await screen.findByTestId("episodes-table");
		expect(screen.getByTestId("generate-ep-002")).toBeInTheDocument();
		expect(screen.queryByTestId("no-action-ep-002")).not.toBeInTheDocument();
	});

	it("生成開始ボタンをクリックするとジョブ一覧へのリンクに切り替わる", async () => {
		vi.spyOn(api, "getEpisodes").mockResolvedValue([COLLECTED_EPISODE]);
		vi.spyOn(api, "startEpisodeGeneration").mockResolvedValue({
			schema_version: 1,
			job_id: "job-001",
			episode_id: "ep-002",
			kind: "episode_generation",
			status: "queued",
			progress: 0,
			cancel_requested: false,
			retry_of: null,
			error: null,
			created_at: "2026-07-19T00:00:00Z",
			started_at: null,
			finished_at: null,
		});

		renderEpisodes();
		await screen.findByTestId("episodes-table");

		fireEvent.click(screen.getByTestId("generate-ep-002"));

		await waitFor(() => {
			expect(
				screen.getByTestId("generation-started-ep-002"),
			).toBeInTheDocument();
		});
		expect(api.startEpisodeGeneration).toHaveBeenCalledWith("ep-002");
		expect(screen.queryByTestId("generate-ep-002")).not.toBeInTheDocument();
	});

	it("生成開始失敗時はエラーメッセージが行内に表示される", async () => {
		vi.spyOn(api, "getEpisodes").mockResolvedValue([COLLECTED_EPISODE]);
		vi.spyOn(api, "startEpisodeGeneration").mockRejectedValue(
			new api.ApiError(
				"エピソードは終端の失敗状態にあるため生成を開始できない",
			),
		);

		renderEpisodes();
		await screen.findByTestId("episodes-table");

		fireEvent.click(screen.getByTestId("generate-ep-002"));

		await waitFor(() => {
			expect(screen.getByTestId("episode-error-ep-002")).toHaveTextContent(
				"エピソードは終端の失敗状態にあるため生成を開始できない",
			);
		});
		expect(screen.getByTestId("generate-ep-002")).toBeInTheDocument();
	});

	it("承認ボタンで状態がapprovedに更新される", async () => {
		vi.spyOn(api, "getEpisodes").mockResolvedValue([READY_EPISODE]);
		vi.spyOn(api, "approveEpisode").mockResolvedValue({
			...READY_EPISODE,
			state: "approved",
			revision: 2,
		});

		renderEpisodes();
		await screen.findByTestId("episodes-table");

		fireEvent.click(screen.getByTestId("approve-ep-001"));

		await waitFor(() => {
			expect(screen.getByTestId("episode-state-ep-001")).toHaveTextContent(
				"承認済み",
			);
		});
		expect(api.approveEpisode).toHaveBeenCalledWith("ep-001");
		expect(screen.queryByTestId("approve-ep-001")).not.toBeInTheDocument();
	});

	it("承認失敗時はエラーメッセージが行内に表示される", async () => {
		vi.spyOn(api, "getEpisodes").mockResolvedValue([READY_EPISODE]);
		vi.spyOn(api, "approveEpisode").mockRejectedValue(
			new api.ApiError("自動検査ゲートが不合格"),
		);

		renderEpisodes();
		await screen.findByTestId("episodes-table");

		fireEvent.click(screen.getByTestId("approve-ep-001"));

		await waitFor(() => {
			expect(screen.getByTestId("episode-error-ep-001")).toHaveTextContent(
				"自動検査ゲートが不合格",
			);
		});
		// 失敗時は承認前の状態のまま、ボタンから再試行できる
		expect(screen.getByTestId("approve-ep-001")).toBeInTheDocument();
	});

	it("approved状態のエピソードには限定公開ボタンが表示される", async () => {
		vi.spyOn(api, "getEpisodes").mockResolvedValue([APPROVED_EPISODE]);
		renderEpisodes();
		await screen.findByTestId("episodes-table");
		expect(screen.getByTestId("publish-ep-003")).toBeInTheDocument();
		expect(screen.queryByTestId("approve-ep-003")).not.toBeInTheDocument();
	});

	it("限定公開ボタンで状態がpublishedに更新される", async () => {
		vi.spyOn(api, "getEpisodes").mockResolvedValue([APPROVED_EPISODE]);
		vi.spyOn(api, "publishEpisode").mockResolvedValue({
			...APPROVED_EPISODE,
			state: "published",
			revision: 3,
		});

		renderEpisodes();
		await screen.findByTestId("episodes-table");

		fireEvent.click(screen.getByTestId("publish-ep-003"));

		await waitFor(() => {
			expect(screen.getByTestId("episode-state-ep-003")).toHaveTextContent(
				"公開済み(限定公開)",
			);
		});
		expect(api.publishEpisode).toHaveBeenCalledWith("ep-003");
		expect(screen.queryByTestId("publish-ep-003")).not.toBeInTheDocument();
	});

	it("限定公開失敗時はエラーメッセージが行内に表示される", async () => {
		vi.spyOn(api, "getEpisodes").mockResolvedValue([APPROVED_EPISODE]);
		vi.spyOn(api, "publishEpisode").mockRejectedValue(
			new api.ApiError("限定公開できない"),
		);

		renderEpisodes();
		await screen.findByTestId("episodes-table");

		fireEvent.click(screen.getByTestId("publish-ep-003"));

		await waitFor(() => {
			expect(screen.getByTestId("episode-error-ep-003")).toHaveTextContent(
				"限定公開できない",
			);
		});
		expect(screen.getByTestId("publish-ep-003")).toBeInTheDocument();
	});

	it("エピソードが0件なら空メッセージを表示する", async () => {
		vi.spyOn(api, "getEpisodes").mockResolvedValue([]);
		renderEpisodes();
		expect(await screen.findByTestId("episodes-empty")).toBeInTheDocument();
	});
});
