import type { TrialView } from './authorityTrialTypes';

export interface AuthorityCohortCandidate { trial_id: string; title: string | null; registered_at: string; capture_id: string | null; capture_present: boolean; freshness: TrialView['freshness'] }
export interface AuthorityCohortOutcome { reviewer_id: string; reviewer_name: string; outcome: string; note: string; target_refs: string[]; private_source_refs: string[]; public_source_indices: number[] }
export interface AuthorityCohortDimension { dimension: string; label: string; source_index?: number; target_ids?: string[]; observations: AuthorityCohortOutcome[]; outcome_difference: boolean | null; unknown_observations: number }
export interface AuthorityCohortRow {
  trial_id: string; title: string; profile_sha256: string; entry_sha256: string; family_sha256: string;
  sample_kind: 'real' | 'synthetic'; source_freshness: TrialView['freshness']; capture_id: string | null; capture_present: boolean; capture_complete: boolean;
  current_reviewer_count: number; semantic: AuthorityCohortDimension[]; findings: AuthorityCohortDimension[];
  semantic_observation_slots: number; finding_observation_slots: number; unknown_semantic_observations: number; unknown_finding_observations: number;
  outcome_difference_count: number | null; recorded_effort: NonNullable<TrialView['snapshot']>['assessment'] | null; effort_accounted: boolean;
  assessment_times: { reviewer_id: string; review_seconds: number | null }[];
  adverse_scopes: { reviewer_id: string; scope: { status: string; limitations: string; inspected_source_indices: number[] } }[];
}
export interface AuthorityCohortReport {
  counts: Record<'selected_records' | 'profile_groups' | 'declared_families' | 'current_source_records' | 'captures_present' | 'complete_capture_records' | 'current_reviewer_pairs' | 'accounted_effort_records' | 'records_with_outcome_differences' | 'records_with_unknown_observations', number>;
  profiles: { profile_sha256: string; trial_ids: string[]; profile: { sample_kind: 'real' | 'synthetic'; semantic_dimensions_sha256: string; finding_dimensions_sha256: string; workflow: string; model_use: 'none' } }[];
  families: { family_sha256: string; trial_ids: string[]; reserved_overlap: boolean }[];
  duplicate_inputs: { input_sha256: string; trial_ids: string[] }[];
  repeated_versions: { version_id: string; sha256: string; trial_ids: string[] }[];
  cross_family_private_sources: { document_id: string; selections: { trial_id: string; family_sha256: string }[] }[];
  repeated_public_passages: { selection: Record<string, string>; selections: { trial_id: string; family_sha256: string }[] }[];
  reserved_overlaps: string[]; rows: AuthorityCohortRow[];
}
export interface AuthorityCohortManifest {
  title: string; purpose: string; selections: { trial_id: string }[]; reserved_family_sha256: string[];
  reconciliation: AuthorityCohortReport;
  entries: { trial_id: string; entry_sha256: string; capture: TrialView }[];
}
export interface AuthorityCohortPreview { manifest: AuthorityCohortManifest; preview_sha256: string }
export interface AuthorityCohortView { id: string; registered_at: string; owner_id: string; manifest: AuthorityCohortManifest | null; public_source_access: boolean; manifest_sha256: string; freshness: { status: 'current' | 'stale' | 'withheld'; reasons: { trial_id: string | null; code: string }[] } }
export function authorityReservedFamilies(text: string) {
  const labels = text.split('\n').map(label => label.trim()).filter(Boolean);
  if (labels.length > 60 || labels.some(label => label.length > 200) || new Set(labels).size !== labels.length) throw new Error('En fazla 60 farklı aile adı yazın; her ad 200 karakteri geçmemeli.');
  return labels;
}
export function pendingAuthorityCohort(data: unknown) {
  if (!data || typeof data !== 'object') return false;
  const value = data as Record<string, unknown>;
  return value.outcome === 'committed_needs_revalidation' && value.needs_revalidation === true && typeof value.id === 'string' && /^atc-[a-f0-9]{20}-[a-f0-9]{32}$/.test(value.id);
}
