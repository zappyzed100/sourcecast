// Jobs.tsx — ジョブ管理(仕様書§12.1・§14)。API停止・タイムアウト・空データ・壊れた応答を安全に表示する。
import { ApiError, getJobs, type Job } from "../lib/api";
import { useAsync } from "../lib/useAsync";

export function Jobs() {
	const state = useAsync<Job[]>(getJobs);

	if (state.status === "loading") {
		return (
			<p role="status" data-testid="jobs-loading">
				読み込み中…
			</p>
		);
	}

	if (state.status === "error") {
		const message =
			state.error instanceof ApiError ? state.error.message : "不明なエラー";
		return (
			<p role="alert" data-testid="jobs-error">
				ジョブ一覧を取得できませんでした: {message}
			</p>
		);
	}

	const { data } = state;
	if (data.length === 0) {
		return <p data-testid="jobs-empty">ジョブはまだありません。</p>;
	}

	return (
		<table data-testid="jobs-table">
			<thead>
				<tr>
					<th scope="col">エピソード</th>
					<th scope="col">工程</th>
					<th scope="col">状態</th>
					<th scope="col">エラー</th>
				</tr>
			</thead>
			<tbody>
				{data.map((job) => (
					<tr key={job.job_id}>
						<td>{job.episode_id ?? "—"}</td>
						<td>{job.kind}</td>
						<td>{job.status}</td>
						<td>{job.error ?? ""}</td>
					</tr>
				))}
			</tbody>
		</table>
	);
}
