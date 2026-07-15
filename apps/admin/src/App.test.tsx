// App.test.tsx — Phase 0のvitestスモークテスト: レンダリングとカウンターの基本動作だけを確認する
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import App from "./App";

describe("App", () => {
	it("カウンターボタンを押すと表示が増える", () => {
		render(<App />);
		const button = screen.getByTestId("scaffold-counter-button");
		expect(button).toHaveTextContent("Count is 0");

		fireEvent.click(button);

		expect(button).toHaveTextContent("Count is 1");
	});
});
