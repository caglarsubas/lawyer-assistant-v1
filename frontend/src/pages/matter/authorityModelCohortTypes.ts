import type { ComparisonArm } from './comparisonTypes';
import type { AuthorityCohortDimension, AuthorityCohortReport } from './authorityCohortTypes';
import type { ModelTrialCapture, ModelTrialEvidence } from './authorityModelTypes';

export interface ModelCohortCandidate { trial_id: string; analysis_id: string; registered_at: string; admission_complete: boolean }
export interface ModelCohortArm {
  status: string; retained_passes: number; elapsed_seconds: number | null; provider_round_trip_seconds: number | null;
  semantic: AuthorityCohortDimension[]; findings: AuthorityCohortDimension[];
  semantic_observation_slots: number; finding_observation_slots: number; unknown_semantic_observations: number; unknown_finding_observations: number;
  outcome_difference_count: number | null; active_effort: { preparation_seconds: number | null; verification_seconds: number | null; correction_seconds: number | null } | null;
  active_effort_accounted: boolean; assessment_times: { reviewer_id: string; review_seconds: number | null }[];
  adverse_scopes: { reviewer_id: string; scope: { status: string; limitations: string; inspected_source_indices: number[] } }[];
}
export interface ModelCohortRow {
  trial_id: string; title: string; profile_sha256: string; capture_present: boolean; capture_complete: boolean;
  current_reviewer_count: number; effort_accounted: boolean; arms: Record<ComparisonArm, ModelCohortArm>;
  source_freshness: ModelTrialCapture['freshness']; execution_sha256: string; unknown_semantic_observations: number; unknown_finding_observations: number;
}
export interface ModelCohortReport extends Pick<AuthorityCohortReport, 'counts' | 'families' | 'duplicate_inputs' | 'repeated_versions' | 'cross_family_private_sources' | 'repeated_public_passages' | 'reserved_overlaps'> {
  profiles: { profile_sha256: string; trial_ids: string[]; profile: { sample_kind: 'real' | 'synthetic'; input_kind: 'original_review' | 'admitted_renewal'; provider_pin: { model: string }; rubric_sha256: string } }[];
  rows: ModelCohortRow[];
}
export interface ModelCohortManifest {
  title: string; purpose: string; selections: { trial_id: string }[]; reserved_family_sha256: string[];
  reconciliation: ModelCohortReport; entries: { trial_id: string; capture: ModelTrialEvidence }[];
}
export interface ModelCohortPreview { manifest: ModelCohortManifest; preview_sha256: string }
export interface ModelCohortView { id: string; registered_at: string; manifest: ModelCohortManifest | null; manifest_sha256: string; public_source_access: boolean; freshness: { status: 'current' | 'stale' | 'withheld'; reasons: { trial_id: string | null; code: string }[] } }
export function pendingModelCohort(data: unknown) {
  if (!data || typeof data !== 'object') return false;
  const value = data as Record<string, unknown>;
  return value.outcome === 'committed_needs_revalidation' && value.needs_revalidation === true && typeof value.id === 'string' && /^amc-[a-f0-9]{20}-[a-f0-9]{32}$/.test(value.id);
}
