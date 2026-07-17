/** CandidateDecision.ts — 生成物。手編集しない（正本: services/pipeline/src/history_radio/domain、生成: scripts/generate_contracts.py + packages/contracts/scripts/generate-types.ts） */

export type CandidateId = string;
export type DecidedAt = string;
export type Decision = "adopted" | "excluded";
export type DecisionId = string;
export type Reason = string;
export type SchemaVersion = 1;

/**
 * `topics`の審査結果（仕様書§12.3「採用／除外／再生成」のうち採用・除外・
 * Phase 11タスク1・3）。除外にはreasonの入力が必須（select/candidate_review.pyが強制する
 * ——破壊的操作に理由入力を必須にする仕様書§12.4の方針を審査アクションにも適用する）。
 */
export interface CandidateDecision {
  candidate_id: CandidateId;
  decided_at: DecidedAt;
  decision: Decision;
  decision_id: DecisionId;
  reason?: Reason;
  schema_version?: SchemaVersion;
}
