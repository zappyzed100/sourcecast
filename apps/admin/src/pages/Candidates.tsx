// Candidates.tsx — 候補一覧(仕様書§12.3)。API停止・タイムアウト・空データ・壊れた応答を安全に表示する。
import { ApiError, type Candidate, getCandidates } from "../lib/api";
import { useAsync } from "../lib/useAsync";

export function Candidates() {
	const state = useAsync<Candidate[]>(getCandidates);

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
				</tr>
			</thead>
			<tbody>
				{data.map((candidate) => (
					<tr key={candidate.candidate_id}>
						<td>{candidate.topic_title}</td>
						<td>{candidate.score.toFixed(1)}</td>
						<td>{candidate.independent_source_families}</td>
					</tr>
				))}
			</tbody>
		</table>
	);
}
