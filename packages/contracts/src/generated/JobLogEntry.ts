/** JobLogEntry.ts — 生成物。手編集しない（正本: services/pipeline/src/history_radio/domain、生成: scripts/generate_contracts.py + packages/contracts/scripts/generate-types.ts） */

export type JobId = string;
export type Level = "info" | "warning" | "error";
export type Message = string;
export type OccurredAt = string;
export type SchemaVersion = 1;
export type Seq = number;

/**
 * ジョブ1件分の実行ログ1行（Phase 11タスク2「ログ追跡」）。`seq`はジョブ内で1始まりの
 * 連番——SSE配信時に「前回まで受信済みのseq以降だけ」を再接続後に取りこぼしなく送れる。
 */
export interface JobLogEntry {
  job_id: JobId;
  level: Level;
  message: Message;
  occurred_at: OccurredAt;
  schema_version?: SchemaVersion;
  seq: Seq;
}
