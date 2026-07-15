/** Candidate.ts — 生成物。手編集しない（正本: services/pipeline/src/history_radio/domain、生成: scripts/generate_contracts.py + packages/contracts/scripts/generate-types.ts） */

export type CandidateId = string;
export type IndependentSourceFamilies = number;
export type SchemaVersion = 1;
export type Score = number;
export type TopicTitle = string;

/**
 * `topics`（仕様書§6A）: 機械選出の候補点と内訳。LLM不使用。
 */
export interface Candidate {
  candidate_id: CandidateId;
  independent_source_families: IndependentSourceFamilies;
  schema_version?: SchemaVersion;
  score: Score;
  score_breakdown: ScoreBreakdown;
  topic_title: TopicTitle;
}
export interface ScoreBreakdown {
  [k: string]: number;
}
