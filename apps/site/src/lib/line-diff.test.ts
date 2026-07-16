// line-diff.test.ts — diffLines()の行単位差分ロジックを固定する(Phase 8タスク3)
import { describe, expect, it } from "vitest";
import { diffLines } from "./line-diff";

describe("diffLines", () => {
	it("完全一致する本文は全行unchangedになる", () => {
		const result = diffLines("a\nb\nc", "a\nb\nc");
		expect(result).toEqual([
			{ op: "unchanged", text: "a" },
			{ op: "unchanged", text: "b" },
			{ op: "unchanged", text: "c" },
		]);
	});

	it("末尾に行を追加すると追加行だけがaddedになる", () => {
		const result = diffLines("a\nb", "a\nb\nc");
		expect(result).toEqual([
			{ op: "unchanged", text: "a" },
			{ op: "unchanged", text: "b" },
			{ op: "added", text: "c" },
		]);
	});

	it("行を削除すると削除行だけがremovedになる", () => {
		const result = diffLines("a\nb\nc", "a\nc");
		expect(result).toEqual([
			{ op: "unchanged", text: "a" },
			{ op: "removed", text: "b" },
			{ op: "unchanged", text: "c" },
		]);
	});

	it("行の書き換えはremoved+addedのペアとして表れる", () => {
		const result = diffLines("誤字がある行", "訂正した行");
		expect(result).toEqual([
			{ op: "removed", text: "誤字がある行" },
			{ op: "added", text: "訂正した行" },
		]);
	});

	it("空文字列同士は1つの空行としてunchangedになる", () => {
		expect(diffLines("", "")).toEqual([{ op: "unchanged", text: "" }]);
	});

	it("完全に入れ替わった本文は全行がremoved→addedの順で並ぶ", () => {
		const result = diffLines("旧版の本文", "新版の本文");
		expect(result.filter((l) => l.op === "removed").map((l) => l.text)).toEqual(
			["旧版の本文"],
		);
		expect(result.filter((l) => l.op === "added").map((l) => l.text)).toEqual([
			"新版の本文",
		]);
	});
});
