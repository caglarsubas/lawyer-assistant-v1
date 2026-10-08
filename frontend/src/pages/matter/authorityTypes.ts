import type { AnalysisContent, AnalysisFreshness } from './analysisTypes';
import type { ValidityEvidence } from '../../types';

export interface AuthorityIdentity { assertion_id: string; passage_id: string; authority_id: string }
export interface AuthorityPin { status: 'verified'; release_id: string; serving_sha256: string; activation_sequence: number }
export interface AuthoritySource extends AuthorityIdentity {
  document_id: string; source_version_id: string; source_sha256: string; release_id: string;
  text: string; locator: string; start_offset: number; end_offset: number; quote_sha256: string;
  text_sha256: string; locator_map_sha256: string; graph_family: string;
  subject_id: string; predicate: string; object_id: string; review_status: string; recorded_at: string; reviewed_at: string;
  valid_from: string | null; valid_to: string | null; validity_end_status: 'closed' | 'open_ended';
  validity_checked_through: string | null;
  validity_evidence?: ValidityEvidence[];
  target_provision_version: null | { id: string; version_of: string | null; resolution: string | null;
    validity: { kind: string; start: string | null; end: string | null; checked_through: string | null; evidence: string[] } };
  candidate_only: true; matter_applicability: 'not_assessed'; binding_effect: 'not_assessed';
}
export const AUTHORITY_ROLES = {
  support_candidate: 'Destek adayı', adverse_candidate: 'Karşı dayanak adayı',
  material_distinction: 'Olay veya kural farkı', background: 'Arka plan', unresolved: 'Bağlantı belirsiz',
} as const;
export type AuthorityRole = keyof typeof AUTHORITY_ROLES;
export interface AuthoritySelection extends AuthorityIdentity { target_ids: string[]; relationship: AuthorityRole; note: string }
export interface AuthoritySpec { version_id: string; product_id: string; title: string; purpose: string; selections: AuthoritySelection[] }
export interface AuthorityCandidates {
  sources: AuthoritySource[]; graph_release_pin: AuthorityPin; research_as_of: string; analysis_event_date: string | null;
  targets: Record<string, unknown>; private_freshness: AnalysisFreshness; current_version: boolean;
}
export interface LinkedAuthority {
  selection: AuthoritySelection; evidence: AuthoritySource; target_snapshots: Record<string, unknown>;
  temporal_alignment: { research_as_of: string; analysis_event_date: string | null; dates_equal: boolean | null;
    within_assertion_interval: boolean | null; target_version_within_interval: boolean | null; applicability: 'not_assessed' };
}
export interface AuthorityManifest extends AuthoritySpec {
  recipe: string; analysis_content: AnalysisContent; graph_release_pin: AuthorityPin; sources: LinkedAuthority[];
  analysis_content_sha256: string; analysis_review_id: string | null; product_sha256: string;
  legal_approval: 'not_granted'; matter_applicability: 'not_assessed'; binding_effect: 'not_assessed'; model_use: 'none';
}
export interface AuthorityPreview { manifest: AuthorityManifest; preview_sha256: string }
export interface AuthoritySummary { id: string; title: string; version_id: string }
export interface AuthorityContext extends AuthoritySummary {
  registered_at: string; manifest_sha256: string; packet_sha256: string; manifest: AuthorityManifest | null;
  public_source_access: boolean; freshness: { status: 'current' | 'stale' | 'withheld'; reasons: string[] };
  qualification_granted: false; production_qualified: false; runtime_authorization: 'none';
}
export function occurrenceKey(source: AuthorityIdentity): string { return JSON.stringify([source.assertion_id, source.passage_id, source.authority_id]); }
export function occurrence(source: AuthorityIdentity): AuthorityIdentity {
  return { assertion_id: source.assertion_id, passage_id: source.passage_id, authority_id: source.authority_id };
}
export function committedAuthorityReceipt(data: unknown): string | null {
  if (!data || typeof data !== 'object') return null;
  const value = data as Record<string, unknown>;
  return value.outcome === 'committed_needs_revalidation' && value.needs_revalidation === true
    && typeof value.id === 'string' && /^aac-[a-f0-9]{20}-[a-f0-9]{32}$/.test(value.id) ? value.id : null;
}
