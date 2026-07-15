/** RightsDecision.ts — 生成物。手編集しない（正本: services/pipeline/src/history_radio/domain、生成: scripts/generate_contracts.py + packages/contracts/scripts/generate-types.ts） */

export type ComputedAt = string;
export type Decision = "allow_public_use" | "internal_research_only" | "manual_review" | "deny";
export type DecisionId = string;
export type DocumentId = string;
/**
 * @minItems 1
 */
export type Reasons = [string, ...string[]];
export type RuleVersion = string;
export type SchemaVersion = 1;

/**
 * `rights_records`（仕様書§5A）: 資料単位の機械スクリーニング結果。
 *
 * 年数計算は資料取得のたびに現在日付で再計算する契約（§5A冒頭）——computed_at が
 * その再計算時点を記録し、判定結果を使い回さないことを保証する。
 */
export interface RightsDecision {
  computed_at: ComputedAt;
  decision: Decision;
  decision_id: DecisionId;
  document_id: DocumentId;
  reasons: Reasons;
  rule_version: RuleVersion;
  schema_version?: SchemaVersion;
}
