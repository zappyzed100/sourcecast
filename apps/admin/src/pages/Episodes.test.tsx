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

	it("published状態には生成・承認・限定公開ボタンが表示されず公開取消ボタンが出る", async () => {
		vi.spyOn(api, "getEpisodes").mockResolvedValue([PUBLISHED_EPISODE]);
		renderEpisodes();
		await screen.findByTestId("episodes-table");
		expect(screen.queryByTestId("generate-ep-004")).not.toBeInTheDocument();
		expect(screen.queryByTestId("approve-ep-004")).not.toBeInTheDocument();
		expect(screen.queryByTestId("publish-ep-004")).not.toBeInTheDocument();
		expect(screen.queryByTestId("delete-ep-004")).not.toBeInTheDocument();
		expect(screen.getByTestId("revoke-ep-004")).toBeInTheDocument();
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

	it("公開済みでない状態には削除ボタンが表示される(Phase 11タスク3)", async () => {
		vi.spyOn(api, "getEpisodes").mockResolvedValue([COLLECTED_EPISODE]);
		renderEpisodes();
		await screen.findByTestId("episodes-table");
		expect(screen.getByTestId("delete-ep-002")).toBeInTheDocument();
	});

	it("削除ボタンをクリックすると理由入力欄が現れ、理由付きで削除される", async () => {
		vi.spyOn(api, "getEpisodes").mockResolvedValue([COLLECTED_EPISODE]);
		vi.spyOn(api, "deleteEpisode").mockResolvedValue(undefined);

		renderEpisodes();
		await screen.findByTestId("episodes-table");

		fireEvent.click(screen.getByTestId("delete-ep-002"));
		expect(screen.getByTestId("delete-reason-ep-002")).toBeInTheDocument();

		fireEvent.change(screen.getByTestId("delete-reason-ep-002"), {
			target: { value: "重複作成のため" },
		});
		fireEvent.click(screen.getByTestId("confirm-delete-ep-002"));

		await waitFor(() => {
			expect(screen.getByTestId("episodes-empty")).toBeInTheDocument();
		});
		expect(api.deleteEpisode).toHaveBeenCalledWith("ep-002", "重複作成のため");
	});

	it("削除キャンセルボタンで理由入力欄が閉じ、行はそのまま残る", async () => {
		vi.spyOn(api, "getEpisodes").mockResolvedValue([COLLECTED_EPISODE]);
		renderEpisodes();
		await screen.findByTestId("episodes-table");

		fireEvent.click(screen.getByTestId("delete-ep-002"));
		fireEvent.click(screen.getByTestId("cancel-delete-ep-002"));

		expect(
			screen.queryByTestId("delete-reason-ep-002"),
		).not.toBeInTheDocument();
		expect(screen.getByTestId("delete-ep-002")).toBeInTheDocument();
	});

	it("削除失敗時はエラーメッセージが行内に表示され行は残る", async () => {
		vi.spyOn(api, "getEpisodes").mockResolvedValue([COLLECTED_EPISODE]);
		vi.spyOn(api, "deleteEpisode").mockRejectedValue(
			new api.ApiError("削除には理由の入力が必須"),
		);

		renderEpisodes();
		await screen.findByTestId("episodes-table");

		fireEvent.click(screen.getByTestId("delete-ep-002"));
		fireEvent.click(screen.getByTestId("confirm-delete-ep-002"));

		await waitFor(() => {
			expect(screen.getByTestId("episode-error-ep-002")).toHaveTextContent(
				"削除には理由の入力が必須",
			);
		});
		expect(screen.getByTestId("episodes-table")).toBeInTheDocument();
	});

	it("公開取消ボタンをクリックすると理由入力欄が現れ、理由付きで取消される", async () => {
		vi.spyOn(api, "getEpisodes").mockResolvedValue([PUBLISHED_EPISODE]);
		vi.spyOn(api, "revokeEpisodePublication").mockResolvedValue({
			schema_version: 1,
			event_id: "audit-episode-revoke-ep-004-abc123",
			entity_type: "episode",
			entity_id: "ep-004",
			action: "publish_revoked",
			actor: "admin_review",
			occurred_at: "2026-07-19T00:00:00Z",
			detail: "reason='権利者からの削除要請'",
		});

		renderEpisodes();
		await screen.findByTestId("episodes-table");

		fireEvent.click(screen.getByTestId("revoke-ep-004"));
		fireEvent.change(screen.getByTestId("revoke-reason-ep-004"), {
			target: { value: "権利者からの削除要請" },
		});
		fireEvent.click(screen.getByTestId("confirm-revoke-ep-004"));

		await waitFor(() => {
			expect(screen.getByTestId("revoked-ep-004")).toBeInTheDocument();
		});
		expect(api.revokeEpisodePublication).toHaveBeenCalledWith(
			"ep-004",
			"権利者からの削除要請",
		);
		expect(screen.queryByTestId("revoke-ep-004")).not.toBeInTheDocument();
		// 公開取消はEpisode自体を変更しない(仕様書§10B)——行は一覧に残る。
		expect(screen.getByTestId("episode-state-ep-004")).toHaveTextContent(
			"公開済み(限定公開)",
		);
	});

	it("公開取消失敗時はエラーメッセージが行内に表示される", async () => {
		vi.spyOn(api, "getEpisodes").mockResolvedValue([PUBLISHED_EPISODE]);
		vi.spyOn(api, "revokeEpisodePublication").mockRejectedValue(
			new api.ApiError("公開取消には理由の入力が必須"),
		);

		renderEpisodes();
		await screen.findByTestId("episodes-table");

		fireEvent.click(screen.getByTestId("revoke-ep-004"));
		fireEvent.click(screen.getByTestId("confirm-revoke-ep-004"));

		await waitFor(() => {
			expect(screen.getByTestId("episode-error-ep-004")).toHaveTextContent(
				"公開取消には理由の入力が必須",
			);
		});
		expect(screen.getByTestId("revoke-reason-ep-004")).toBeInTheDocument();
	});
});
