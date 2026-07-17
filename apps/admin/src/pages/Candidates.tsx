// Candidates.tsx — 候補一覧・審査(仕様書§12.3「採用／除外／再生成」のうち採用・除外)。
// API停止・タイムアウト・空データ・壊れた応答を安全に表示する(plan.md Phase 2 DoD)。
// 除外には理由の入力を必須にする(development-plan.md Phase 11タスク1・3)。
import { useState } from "react";
import {
	ApiError,
	type Candidate,
	type CandidateDecision,
	getCandidates,
	reviewCandidate,
} from "../lib/api";
import { useAsync } from "../lib/useAsync";

export function Candidates() {
	const state = useAsync<Candidate[]>(getCandidates);
	const [decisions, setDecisions] = useState<Record<string, CandidateDecision>>(
		{},
	);
	const [excludingId, setExcludingId] = useState<string | null>(null);
	const [excludeReason, setExcludeReason] = useState("");
	const [pendingId, setPendingId] = useState<string | null>(null);
	const [rowError, setRowError] = useState<Record<string, string>>({});

	async function submitDecision(
		candidateId: string,
		decision: "adopted" | "excluded",
		reason?: string,
	) {
		setPendingId(candidateId);
		setRowError((prev) => ({ ...prev, [candidateId]: "" }));
		try {
			const result = await reviewCandidate(candidateId, decision, reason);
			setDecisions((prev) => ({ ...prev, [candidateId]: result }));
			setExcludingId(null);
			setExcludeReason("");
		} catch (error) {
			setRowError((prev) => ({
				...prev,
				[candidateId]:
					error instanceof ApiError ? error.message : "不明なエラー",
			}));
		} finally {
			setPendingId(null);
		}
	}

	if (state.status === "loading") {
		return (
			<p role="status" data-testid="candidates-loading">
				読み込み中…
			</p>
		);
	}

	if (state.status === "error") {
		const message =
			state.error instanceof ApiError ? state.error.message : "不明なエラー";
		return (
			<p role="alert" data-testid="candidates-error">
				候補一覧を取得できませんでした: {message}
			</p>
		);
	}

	const { data } = state;
	if (data.length === 0) {
		return <p data-testid="candidates-empty">候補はまだありません。</p>;
	}

	return (
		<table data-testid="candidates-table">
			<thead>
				<tr>
					<th scope="col">題材</th>
					<th scope="col">総合点</th>
					<th scope="col">独立出典系統数</th>
					<th scope="col">審査</th>
				</tr>
			</thead>
			<tbody>
				{data.map((candidate) => {
					const decision = decisions[candidate.candidate_id];
					const isPending = pendingId === candidate.candidate_id;
					const error = rowError[candidate.candidate_id];
					return (
						<tr key={candidate.candidate_id}>
							<td>{candidate.topic_title}</td>
							<td>{candidate.score.toFixed(1)}</td>
							<td>{candidate.independent_source_families}</td>
							<td data-testid={`candidate-review-${candidate.candidate_id}`}>
								{decision ? (
									<span data-testid="candidate-decision-status">
										{decision.decision === "adopted" ? "採用済み" : "除外済み"}
									</span>
								) : excludingId === candidate.candidate_id ? (
									<>
										<label>
											除外理由
											<input
												type="text"
												value={excludeReason}
												data-testid={`exclude-reason-${candidate.candidate_id}`}
												onChange={(e) => setExcludeReason(e.target.value)}
											/>
										</label>
										<button
											type="button"
											disabled={isPending}
											data-testid={`confirm-exclude-${candidate.candidate_id}`}
											onClick={() =>
												submitDecision(
													candidate.candidate_id,
													"excluded",
													excludeReason,
												)
											}
										>
											除外を確定
										</button>
										<button
											type="button"
											disabled={isPending}
											data-testid={`cancel-exclude-${candidate.candidate_id}`}
											onClick={() => {
												setExcludingId(null);
												setExcludeReason("");
											}}
										>
											キャンセル
										</button>
									</>
								) : (
									<>
										<button
											type="button"
											disabled={isPending}
											data-testid={`adopt-${candidate.candidate_id}`}
											onClick={() =>
												submitDecision(candidate.candidate_id, "adopted")
											}
										>
											採用
										</button>
										<button
											type="button"
											disabled={isPending}
											data-testid={`exclude-${candidate.candidate_id}`}
											onClick={() => {
												setExcludingId(candidate.candidate_id);
												setExcludeReason("");
											}}
										>
											除外
										</button>
									</>
								)}
								{error && (
									<p
										role="alert"
										data-testid={`candidate-error-${candidate.candidate_id}`}
									>
										{error}
									</p>
								)}
							</td>
						</tr>
					);
				})}
			</tbody>
		</table>
	);
}
