/** Claim.ts — 生成物。手編集しない（正本: services/pipeline/src/history_radio/domain、生成: scripts/generate_contracts.py + packages/contracts/scripts/generate-types.ts） */

export type AllowedInScript = boolean;
export type ClaimId = string;
/**
 * @minItems 1
 */
export type EvidenceIds = [string, ...string[]];
export type Qualification = "断定" | "資料帰属" | "伝承" | "推定";
export type ReliabilityScore = number;
export type SchemaVersion = 1;
/**
 * @minItems 1
 */
export type SourceFamilyIds = [string, ...string[]];
export type Text = string;

/**
 * `claim_ledger`（仕様書§8.2A）: 台本生成前に確定する公開可能な主張の台帳。
 */
export interface Claim {
  allowed_in_script: AllowedInScript;
  claim_id: ClaimId;
  evidence_ids: EvidenceIds;
  qualification: Qualification;
  reliability_score: ReliabilityScore;
  schema_version?: SchemaVersion;
  source_family_ids: SourceFamilyIds;
  text: Text;
}
