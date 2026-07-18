/** Job.ts — 生成物。手編集しない（正本: services/pipeline/src/history_radio/domain、生成: scripts/generate_contracts.py + packages/contracts/scripts/generate-types.ts） */

export type CancelRequested = boolean;
export type CreatedAt = string;
export type EpisodeId = string | null;
export type Error = string | null;
export type FinishedAt = string | null;
export type JobId = string;
export type Kind = string;
export type Progress = number;
export type RetryOf = string | null;
export type SchemaVersion = 1;
export type StartedAt = string | null;
export type Status = "queued" | "running" | "succeeded" | "failed" | "blocked" | "cancelled";

/**
 * `jobs`（仕様書§13・§14・Phase 11タスク2）: 処理工程単位の実行状態とエラー。
 *
 * `retry_of`は再実行元のjob_id（仕様書§14「工程単位で再実行」——失敗したジョブの行は
 * 書き換えず、新しいjob_idで再実行することで実行履歴を保つ。エピソードの状態遷移自体は
 * domain/episode_state.pyのtransition()が保証するため、再実行は現在の状態から続きを
 * 行うだけでよい）。
 */
export interface Job {
  cancel_requested?: CancelRequested;
  created_at: CreatedAt;
  episode_id?: EpisodeId;
  error?: Error;
  finished_at?: FinishedAt;
  job_id: JobId;
  kind: Kind;
  progress?: Progress;
  retry_of?: RetryOf;
  schema_version?: SchemaVersion;
  started_at?: StartedAt;
  status: Status;
}
