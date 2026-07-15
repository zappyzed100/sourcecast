// Dashboard.tsx — 管理画面ホーム(仕様書§12.1)。API停止・タイムアウト・壊れた応答を安全に表示する。
import {
	ApiError,
	type DashboardSummary,
	getDashboardSummary,
} from "../lib/api";
import { useAsync } from "../lib/useAsync";

export function Dashboard() {
	const state = useAsync<DashboardSummary>(getDashboardSummary);

	if (state.status === "loading") {
		return (
			<p role="status" data-testid="dashboard-loading">
				読み込み中…
			</p>
		);
	}

	if (state.status === "error") {
		const message =
			state.error instanceof ApiError ? state.error.message : "不明なエラー";
		return (
			<p role="alert" data-testid="dashboard-error">
				ダッシュボードを取得できませんでした: {message}
			</p>
		);
	}

	const { data } = state;
	return (
		<dl data-testid="dashboard-summary">
			<div>
				<dt>実行中のジョブ</dt>
				<dd data-testid="dashboard-jobs-running">{data.jobs_running}</dd>
			</div>
			<div>
				<dt>待機中のジョブ</dt>
				<dd data-testid="dashboard-jobs-queued">{data.jobs_queued}</dd>
			</div>
			<div>
				<dt>本日失敗したジョブ</dt>
				<dd data-testid="dashboard-jobs-failed">{data.jobs_failed_today}</dd>
			</div>
			<div>
				<dt>今月の公開本数</dt>
				<dd data-testid="dashboard-published">
					{data.episodes_published_this_month}
				</dd>
			</div>
			<div>
				<dt>本日のOpenRouter呼び出し回数</dt>
				<dd data-testid="dashboard-openrouter-calls">
					{data.openrouter_calls_today}
				</dd>
			</div>
			<div>
				<dt>審査待ちの候補</dt>
				<dd data-testid="dashboard-candidates-awaiting">
					{data.candidates_awaiting_review}
				</dd>
			</div>
		</dl>
	);
}
