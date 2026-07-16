// line-diff.ts — 台本本文の行単位差分(過去版差分表示・development-plan.md Phase 8タスク3)
export type DiffOp = "added" | "removed" | "unchanged";

export interface DiffLine {
	op: DiffOp;
	text: string;
}

export function diffLines(before: string, after: string): DiffLine[] {
	const a = before.split("\n");
	const b = after.split("\n");
	const m = a.length;
	const n = b.length;

	const lcs: number[][] = Array.from({ length: m + 1 }, () =>
		new Array<number>(n + 1).fill(0),
	);
	for (let i = m - 1; i >= 0; i--) {
		for (let j = n - 1; j >= 0; j--) {
			lcs[i][j] =
				a[i] === b[j]
					? lcs[i + 1][j + 1] + 1
					: Math.max(lcs[i + 1][j], lcs[i][j + 1]);
		}
	}

	const result: DiffLine[] = [];
	let i = 0;
	let j = 0;
	while (i < m && j < n) {
		if (a[i] === b[j]) {
			result.push({ op: "unchanged", text: a[i] });
			i++;
			j++;
		} else if (lcs[i + 1][j] >= lcs[i][j + 1]) {
			result.push({ op: "removed", text: a[i] });
			i++;
		} else {
			result.push({ op: "added", text: b[j] });
			j++;
		}
	}
	while (i < m) {
		result.push({ op: "removed", text: a[i] });
		i++;
	}
	while (j < n) {
		result.push({ op: "added", text: b[j] });
		j++;
	}
	return result;
}
