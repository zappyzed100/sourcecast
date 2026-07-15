/** Episode.ts — 生成物。手編集しない（正本: services/pipeline/src/history_radio/domain、生成: scripts/generate_contracts.py + packages/contracts/scripts/generate-types.ts） */

export type CreatedAt = string;
export type EpisodeId = string;
export type Revision = number;
export type SchemaVersion = 1;
export type State =
  | "collected"
  | "rights_passed"
  | "topic_selected"
  | "facts_verified"
  | "script_generated"
  | "script_verified"
  | "media_generated"
  | "publish_ready"
  | "approved"
  | "published"
  | "rejected"
  | "blocked";
export type Title = string;
export type UpdatedAt = string;

/**
 * `episodes`（仕様書§13・§6.1）: エピソード単位の状態と識別子。
 */
export interface Episode {
  created_at: CreatedAt;
  episode_id: EpisodeId;
  revision: Revision;
  schema_version?: SchemaVersion;
  state: State;
  title: Title;
  updated_at: UpdatedAt;
}
