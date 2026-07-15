/** SourceRecord.ts — 生成物。手編集しない（正本: services/pipeline/src/history_radio/domain、生成: scripts/generate_contracts.py + packages/contracts/scripts/generate-types.ts） */

export type Attribution = "required" | "not_required" | "required_if_not_cc0";
export type CommercialUse = "allow" | "deny" | "conditional";
export type Modification = "allow" | "deny" | "conditional";
export type NormalizedLicenseId = string;
export type RecheckDays = number;
export type Redistribution = "allow" | "deny" | "conditional";
export type SchemaVersion = 1;
export type ShareAlike = "none" | "preserve_per_asset";
export type SourceId = string;
export type Status = "candidate" | "approved" | "suspended" | "rejected";
export type TermsCheckedAt = string;
export type TermsUrl = string;
export type Territory = string;
export type ThirdPartyException = "allow" | "deny";
export type UseClass = "A" | "B" | "C" | "D";

/**
 * `sources`/`source_registry`（仕様書§5.14・§5.2）: ソース単位の利用区分・権利条件。
 */
export interface SourceRecord {
  attribution: Attribution;
  commercial_use: CommercialUse;
  modification: Modification;
  normalized_license_id: NormalizedLicenseId;
  recheck_days: RecheckDays;
  redistribution: Redistribution;
  schema_version?: SchemaVersion;
  share_alike: ShareAlike;
  source_id: SourceId;
  status: Status;
  terms_checked_at: TermsCheckedAt;
  terms_url: TermsUrl;
  territory: Territory;
  third_party_exception: ThirdPartyException;
  use_class: UseClass;
}
