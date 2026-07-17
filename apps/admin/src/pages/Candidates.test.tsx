// Candidates.test.tsx — Phase 11タスク1・3 DoD: 採用・除外(理由必須)の審査UIを固定する
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import * as api from "../lib/api";
import { Candidates } from "./Candidates";

const CANDIDATE = {
	schema_version: 1 as const,
	candidate_id: "cand-1",
	topic_title: "缶切りより缶詰の方が50年も先に生まれていた",
	score: 78.5,
	score_breakdown: { date_match: 0.2, source_richness: 0.9 },
	independent_source_families: 2,
};

describe("Candidates", () => {
	it("候補一覧を表示し、採用ボタンで審査結果が表示される", async () => {
		vi.spyOn(api, "getCandidates").mockResolvedValue([CANDIDATE]);
		vi.spyOn(api, "reviewCandidate").mockResolvedValue({
			schema_version: 1,
			decision_id: "decision-cand-1-abcd1234",
			candidate_id: "cand-1",
			decision: "adopted",
			reason: "",
			decided_at: "2026-07-19T00:00:00Z",
		});

		render(<Candidates />);
		await screen.findByTestId("candidates-table");

		fireEvent.click(screen.getByTestId("adopt-cand-1"));

		await waitFor(() => {
			expect(screen.getByTestId("candidate-decision-status")).toHaveTextContent(
				"採用済み",
			);
		});
		expect(api.reviewCandidate).toHaveBeenCalledWith(
			"cand-1",
			"adopted",
			undefined,
		);
	});

	it("除外ボタンは理由入力欄を表示し、理由を添えて送信する", async () => {
		vi.spyOn(api, "getCandidates").mockResolvedValue([CANDIDATE]);
		const reviewSpy = vi.spyOn(api, "reviewCandidate").mockResolvedValue({
			schema_version: 1,
			decision_id: "decision-cand-1-abcd1234",
			candidate_id: "cand-1",
			decision: "excluded",
			reason: "出典が信頼できない",
			decided_at: "2026-07-19T00:00:00Z",
		});

		render(<Candidates />);
		await screen.findByTestId("candidates-table");

		fireEvent.click(screen.getByTestId("exclude-cand-1"));
		const reasonInput = screen.getByTestId("exclude-reason-cand-1");
		fireEvent.change(reasonInput, { target: { value: "出典が信頼できない" } });
		fireEvent.click(screen.getByTestId("confirm-exclude-cand-1"));

		await waitFor(() => {
			expect(screen.getByTestId("candidate-decision-status")).toHaveTextContent(
				"除外済み",
			);
		});
		expect(reviewSpy).toHaveBeenCalledWith(
			"cand-1",
			"excluded",
			"出典が信頼できない",
		);
	});

	it("除外理由なしで送信するとAPIエラーが行内に表示される", async () => {
		vi.spyOn(api, "getCandidates").mockResolvedValue([CANDIDATE]);
		vi.spyOn(api, "reviewCandidate").mockRejectedValue(
			new api.ApiError("除外には理由の入力が必須"),
		);

		render(<Candidates />);
		await screen.findByTestId("candidates-table");

		fireEvent.click(screen.getByTestId("exclude-cand-1"));
		fireEvent.click(screen.getByTestId("confirm-exclude-cand-1"));

		await waitFor(() => {
			expect(screen.getByTestId("candidate-error-cand-1")).toHaveTextContent(
				"除外には理由の入力が必須",
			);
		});
		// 失敗時は理由入力欄に留まり、審査未了のまま再入力してやり直せる
		expect(screen.getByTestId("exclude-reason-cand-1")).toBeInTheDocument();
		expect(screen.getByTestId("confirm-exclude-cand-1")).toBeInTheDocument();
	});

	it("候補が0件なら空メッセージを表示する", async () => {
		vi.spyOn(api, "getCandidates").mockResolvedValue([]);
		render(<Candidates />);
		expect(await screen.findByTestId("candidates-empty")).toBeInTheDocument();
	});
});
