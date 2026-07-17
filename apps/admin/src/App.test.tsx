// App.test.tsx — ナビゲーションでダッシュボード/候補一覧/ジョブ画面を切り替えられることを確認する
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import App from "./App";
import * as api from "./lib/api";

describe("App", () => {
	it("既定でダッシュボードが表示される", () => {
		vi.spyOn(api, "getDashboardSummary").mockReturnValue(new Promise(() => {}));
		render(
			<MemoryRouter initialEntries={["/"]}>
				<App />
			</MemoryRouter>,
		);
		expect(
			screen.getByRole("heading", { name: "history-radio 管理画面" }),
		).toBeInTheDocument();
		expect(screen.getByTestId("dashboard-loading")).toBeInTheDocument();
	});

	it("候補一覧へのリンクで画面が切り替わる", () => {
		vi.spyOn(api, "getCandidates").mockReturnValue(new Promise(() => {}));
		render(
			<MemoryRouter initialEntries={["/candidates"]}>
				<App />
			</MemoryRouter>,
		);
		expect(screen.getByTestId("candidates-loading")).toBeInTheDocument();
	});

	it("ジョブ画面へのリンクで画面が切り替わる", () => {
		vi.spyOn(api, "getJobs").mockReturnValue(new Promise(() => {}));
		render(
			<MemoryRouter initialEntries={["/jobs"]}>
				<App />
			</MemoryRouter>,
		);
		expect(screen.getByTestId("jobs-loading")).toBeInTheDocument();
	});

	it("エピソード画面へのリンクで画面が切り替わる", () => {
		vi.spyOn(api, "getEpisodes").mockReturnValue(new Promise(() => {}));
		render(
			<MemoryRouter initialEntries={["/episodes"]}>
				<App />
			</MemoryRouter>,
		);
		expect(screen.getByTestId("episodes-loading")).toBeInTheDocument();
	});
});
