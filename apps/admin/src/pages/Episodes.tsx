// Episodes.tsx — エピソード一覧・承認・限定公開(仕様書§12.4「公開承認／差し戻し」)。
// API停止・タイムアウト・空データ・壊れた応答を安全に表示する(plan.md Phase 2 DoD)。
// 承認はpublish_ready状態かつ自動検査ゲート合格が前提、限定公開はapproved状態が前提
// ——それ以外はAPIがfail closedで拒否する(development-plan.md Phase 11タスク1)。
import { useState } from "react";
import {
	ApiError,
	approveEpisode,
	type Episode,
	getEpisodes,
	publishEpisode,
} from "../lib/api";
import { useAsync } from "../lib/useAsync";

const STATE_LABELS: Record<Episode["state"], string> = {
	collected: "収集済み",
	rights_passed: "権利確認済み",
	topic_selected: "題材選出済み",
	facts_verified: "事実確認済み",
	script_generated: "台本生成済み",
	script_verified: "台本検査済み",
	media_generated: "media生成済み",
	publish_ready: "公開準備完了",
	approved: "承認済み",
	published: "公開済み(限定公開)",
	rejected: "却下",
	blocked: "障害停止",
};

export function Episodes() {
	const state = useAsync<Episode[]>(getEpisodes);
	// 承認・限定公開成功後の行を上書き表示する(一覧の再取得はしない——Candidates.tsxと同じ方針)。
	const [overrides, setOverrides] = useState<Record<string, Episode>>({});
	const [pendingId, setPendingId] = useState<string | null>(null);
	const [rowError, setRowError] = useState<Record<string, string>>({});

	async function handleApprove(episodeId: string) {
		await runAction(episodeId, () => approveEpisode(episodeId));
	}

	async function handlePublish(episodeId: string) {
		await runAction(episodeId, () => publishEpisode(episodeId));
	}

	async function runAction(episodeId: string, action: () => Promise<Episode>) {
		setPendingId(episodeId);
		setRowError((prev) => ({ ...prev, [episodeId]: "" }));
		try {
			const updated = await action();
			setOverrides((prev) => ({ ...prev, [episodeId]: updated }));
		} catch (error) {
			setRowError((prev) => ({
				...prev,
				[episodeId]: error instanceof ApiError ? error.message : "不明なエラー",
			}));
		} finally {
			setPendingId(null);
		}
	}

	if (state.status === "loading") {
		return (
			<p role="status" data-testid="episodes-loading">
				読み込み中…
			</p>
		);
	}

	if (state.status === "error") {
		const message =
			state.error instanceof ApiError ? state.error.message : "不明なエラー";
		return (
			<p role="alert" data-testid="episodes-error">
				エピソード一覧を取得できませんでした: {message}
			</p>
		);
	}

	const { data } = state;
	if (data.length === 0) {
		return <p data-testid="episodes-empty">エピソードはまだありません。</p>;
	}

	return (
		<table data-testid="episodes-table">
			<thead>
				<tr>
					<th scope="col">題名</th>
					<th scope="col">状態</th>
					<th scope="col">操作</th>
				</tr>
			</thead>
			<tbody>
				{data.map((fetched) => {
					const episode = overrides[fetched.episode_id] ?? fetched;
					const isPending = pendingId === episode.episode_id;
					const error = rowError[episode.episode_id];
					return (
						<tr key={episode.episode_id}>
							<td>{episode.title}</td>
							<td data-testid={`episode-state-${episode.episode_id}`}>
								{STATE_LABELS[episode.state]}
							</td>
							<td>
								{episode.state === "publish_ready" && (
									<button
										type="button"
										disabled={isPending}
										data-testid={`approve-${episode.episode_id}`}
										onClick={() => handleApprove(episode.episode_id)}
									>
										承認
									</button>
								)}
								{episode.state === "approved" && (
									<button
										type="button"
										disabled={isPending}
										data-testid={`publish-${episode.episode_id}`}
										onClick={() => handlePublish(episode.episode_id)}
									>
										限定公開
									</button>
								)}
								{episode.state !== "publish_ready" &&
									episode.state !== "approved" && (
										<span data-testid={`no-action-${episode.episode_id}`}>
											—
										</span>
									)}
								{error && (
									<p
										role="alert"
										data-testid={`episode-error-${episode.episode_id}`}
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
