/** Job.ts — 生成物。手編集しない（正本: services/pipeline/src/history_radio/domain、生成: scripts/generate_contracts.py + packages/contracts/scripts/generate-types.ts） */

export type EpisodeId = string | null;
export type Error = string | null;
export type FinishedAt = string | null;
export type JobId = string;
export type Kind = string;
export type SchemaVersion = 1;
export type StartedAt = string | null;
export type Status = "queued" | "running" | "succeeded" | "failed" | "blocked";

/**
 * `jobs`（仕様書§13・§14）: 処理工程単位の実行状態とエラー。
 */
export interface Job {
  episode_id?: EpisodeId;
  error?: Error;
  finished_at?: FinishedAt;
  job_id: JobId;
  kind: Kind;
  schema_version?: SchemaVersion;
  started_at?: StartedAt;
  status: Status;
}
