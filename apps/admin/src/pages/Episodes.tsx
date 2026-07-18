// Episodes.tsx — エピソード一覧・生成開始・承認・限定公開(仕様書§12.4「公開承認／差し戻し」・
// Phase 11タスク2「エピソード生成ジョブ」)。API停止・タイムアウト・空データ・壊れた応答を
// 安全に表示する(plan.md Phase 2 DoD)。承認はpublish_ready状態かつ自動検査ゲート合格が前提、
// 限定公開はapproved状態が前提——それ以外はAPIがfail closedで拒否する(Phase 11タスク1)。
import { useState } from "react";
import { Link } from "react-router-dom";
import {
	ApiError,
	approveEpisode,
	deleteEpisode,
	type Episode,
	getEpisodes,
	publishEpisode,
	revokeEpisodePublication,
	startEpisodeGeneration,
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

// publish_readyへ向けて生成ジョブを開始できる状態(Phase 11タスク2:
// jobs/runner.pyのrun_episode_generation_job()が現在の状態から続きを行うため、
// どの段階からでも開始してよい——publish_ready以降・終端失敗状態は対象外)。
const GENERATABLE_STATES: ReadonlySet<Episode["state"]> = new Set([
	"collected",
	"rights_passed",
	"topic_selected",
	"facts_verified",
	"script_generated",
	"script_verified",
	"media_generated",
]);

export function Episodes() {
	const state = useAsync<Episode[]>(getEpisodes);
	// 承認・限定公開成功後の行を上書き表示する(一覧の再取得はしない——Candidates.tsxと同じ方針)。
	const [overrides, setOverrides] = useState<Record<string, Episode>>({});
	const [pendingId, setPendingId] = useState<string | null>(null);
	const [rowError, setRowError] = useState<Record<string, string>>({});
	// 生成ジョブはEpisodeでなくJobを返すため、成功後は「開始済み」フラグだけ持つ
	// (実際の進捗はJobs.tsx側でSSE購読する——このコンポーネントの責務は開始だけ)。
	const [startedJobIds, setStartedJobIds] = useState<Record<string, string>>(
		{},
	);
	// 削除・公開取消(Phase 11タスク3「破壊的操作は確認、理由入力、監査ログを必須にする」)
	// ——Candidates.tsxの除外フローと同じ「クリックで理由入力欄を開き、確定で送信する」
	// 2段階UXにする。削除成功後の行は一覧から消す(APIが実際に行を削除するため)。
	// 公開取消はEpisode自体を変更しない(監査ログのみ)ため、成功をローカルの
	// フラグだけで示す(GET /episodesの応答には反映されない)。
	const [deletingId, setDeletingId] = useState<string | null>(null);
	const [deleteReason, setDeleteReason] = useState("");
	const [deletedIds, setDeletedIds] = useState<ReadonlySet<string>>(new Set());
	const [revokingId, setRevokingId] = useState<string | null>(null);
	const [revokeReason, setRevokeReason] = useState("");
	const [revokedIds, setRevokedIds] = useState<ReadonlySet<string>>(new Set());

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

	async function handleStartGeneration(episodeId: string) {
		setPendingId(episodeId);
		setRowError((prev) => ({ ...prev, [episodeId]: "" }));
		try {
			const job = await startEpisodeGeneration(episodeId);
			setStartedJobIds((prev) => ({ ...prev, [episodeId]: job.job_id }));
		} catch (error) {
			setRowError((prev) => ({
				...prev,
				[episodeId]: error instanceof ApiError ? error.message : "不明なエラー",
			}));
		} finally {
			setPendingId(null);
		}
	}

	async function handleDelete(episodeId: string) {
		setPendingId(episodeId);
		setRowError((prev) => ({ ...prev, [episodeId]: "" }));
		try {
			await deleteEpisode(episodeId, deleteReason);
			setDeletedIds((prev) => new Set(prev).add(episodeId));
			setDeletingId(null);
			setDeleteReason("");
		} catch (error) {
			setRowError((prev) => ({
				...prev,
				[episodeId]: error instanceof ApiError ? error.message : "不明なエラー",
			}));
		} finally {
			setPendingId(null);
		}
	}

	async function handleRevoke(episodeId: string) {
		setPendingId(episodeId);
		setRowError((prev) => ({ ...prev, [episodeId]: "" }));
		try {
			await revokeEpisodePublication(episodeId, revokeReason);
			setRevokedIds((prev) => new Set(prev).add(episodeId));
			setRevokingId(null);
			setRevokeReason("");
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

	// 削除成功後の行は一覧から消す(APIが実際に行を削除するため)。
	const data = state.data.filter(
		(episode) => !deletedIds.has(episode.episode_id),
	);
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
					const startedJobId = startedJobIds[episode.episode_id];
					return (
						<tr key={episode.episode_id}>
							<td>{episode.title}</td>
							<td data-testid={`episode-state-${episode.episode_id}`}>
								{STATE_LABELS[episode.state]}
							</td>
							<td>
								{GENERATABLE_STATES.has(episode.state) &&
									(startedJobId ? (
										<Link
											to="/jobs"
											data-testid={`generation-started-${episode.episode_id}`}
										>
											ジョブ一覧で進捗を確認
										</Link>
									) : (
										<button
											type="button"
											disabled={isPending}
											data-testid={`generate-${episode.episode_id}`}
											onClick={() => handleStartGeneration(episode.episode_id)}
										>
											生成開始
										</button>
									))}
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
								{episode.state === "published" ? (
									revokedIds.has(episode.episode_id) ? (
										<span data-testid={`revoked-${episode.episode_id}`}>
											取消済み
										</span>
									) : revokingId === episode.episode_id ? (
										<>
											<label>
												取消理由
												<input
													type="text"
													value={revokeReason}
													data-testid={`revoke-reason-${episode.episode_id}`}
													onChange={(e) => setRevokeReason(e.target.value)}
												/>
											</label>
											<button
												type="button"
												disabled={isPending}
												data-testid={`confirm-revoke-${episode.episode_id}`}
												onClick={() => handleRevoke(episode.episode_id)}
											>
												取消を確定
											</button>
											<button
												type="button"
												disabled={isPending}
												data-testid={`cancel-revoke-${episode.episode_id}`}
												onClick={() => {
													setRevokingId(null);
													setRevokeReason("");
												}}
											>
												キャンセル
											</button>
										</>
									) : (
										<button
											type="button"
											disabled={isPending}
											data-testid={`revoke-${episode.episode_id}`}
											onClick={() => {
												setRevokingId(episode.episode_id);
												setRevokeReason("");
											}}
										>
											公開取消
										</button>
									)
								) : deletingId === episode.episode_id ? (
									<>
										<label>
											削除理由
											<input
												type="text"
												value={deleteReason}
												data-testid={`delete-reason-${episode.episode_id}`}
												onChange={(e) => setDeleteReason(e.target.value)}
											/>
										</label>
										<button
											type="button"
											disabled={isPending}
											data-testid={`confirm-delete-${episode.episode_id}`}
											onClick={() => handleDelete(episode.episode_id)}
										>
											削除を確定
										</button>
										<button
											type="button"
											disabled={isPending}
											data-testid={`cancel-delete-${episode.episode_id}`}
											onClick={() => {
												setDeletingId(null);
												setDeleteReason("");
											}}
										>
											キャンセル
										</button>
									</>
								) : (
									<button
										type="button"
										disabled={isPending}
										data-testid={`delete-${episode.episode_id}`}
										onClick={() => {
											setDeletingId(episode.episode_id);
											setDeleteReason("");
										}}
									>
										削除
									</button>
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
