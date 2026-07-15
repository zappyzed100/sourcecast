/** AuditEvent.ts — 生成物。手編集しない（正本: services/pipeline/src/history_radio/domain、生成: scripts/generate_contracts.py + packages/contracts/scripts/generate-types.ts） */

export type Action = string;
export type Actor = string;
export type Detail = string;
export type EntityId = string;
export type EntityType = string;
export type EventId = string;
export type OccurredAt = string;
export type SchemaVersion = 1;

/**
 * 追記型監査ログ（仕様書§15: 公開・訂正・削除・権利判定変更を必ず記録する）。
 */
export interface AuditEvent {
  action: Action;
  actor: Actor;
  detail?: Detail;
  entity_id: EntityId;
  entity_type: EntityType;
  event_id: EventId;
  occurred_at: OccurredAt;
  schema_version?: SchemaVersion;
}
