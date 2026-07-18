// Episodes.test.tsx — Phase 11タスク1 DoD: publish_ready状態だけ承認でき、
// approved状態だけ限定公開できる
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import * as api from "../lib/api";
import { Episodes } from "./Episodes";

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

describe("Episodes", () => {
	it("publish_ready状態のエピソードには承認ボタンが表示される", async () => {
		vi.spyOn(api, "getEpisodes").mockResolvedValue([READY_EPISODE]);
		render(<Episodes />);
		await screen.findByTestId("episodes-table");
		expect(screen.getByTestId("approve-ep-001")).toBeInTheDocument();
		expect(screen.queryByTestId("publish-ep-001")).not.toBeInTheDocument();
	});

	it("publish_ready/approved以外の状態には操作ボタンが表示されない", async () => {
		vi.spyOn(api, "getEpisodes").mockResolvedValue([COLLECTED_EPISODE]);
		render(<Episodes />);
		await screen.findByTestId("episodes-table");
		expect(screen.queryByTestId("approve-ep-002")).not.toBeInTheDocument();
		expect(screen.queryByTestId("publish-ep-002")).not.toBeInTheDocument();
		expect(screen.getByTestId("no-action-ep-002")).toBeInTheDocument();
	});

	it("承認ボタンで状態がapprovedに更新される", async () => {
		vi.spyOn(api, "getEpisodes").mockResolvedValue([READY_EPISODE]);
		vi.spyOn(api, "approveEpisode").mockResolvedValue({
			...READY_EPISODE,
			state: "approved",
			revision: 2,
		});

		render(<Episodes />);
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

		render(<Episodes />);
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
		render(<Episodes />);
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

		render(<Episodes />);
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

		render(<Episodes />);
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
		render(<Episodes />);
		expect(await screen.findByTestId("episodes-empty")).toBeInTheDocument();
	});
});
