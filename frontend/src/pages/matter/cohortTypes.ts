import type { ComparisonArm, ComparisonCapture, ComparisonEffort } from './comparisonTypes';

export interface CohortSelection { analysis_id: string; comparison_id: string }
export interface CohortCandidate extends CohortSelection {
  title: string; registered_at: string; family_sha256: string; sample_kind: 'real' | 'synthetic'; source_version: number;
}
export type FrozenCapture = Omit<ComparisonCapture, 'exported_at' | 'can_run' | 'can_observe' | 'can_record_effort' | 'previous_observation_id' | 'previous_effort_id'>;
export interface CohortOutcome {
  reviewer_id: string; reviewer_name: string; outcome: string; note: string; target_ids: string[]; source_refs: string[];
}
export interface CohortDimension {
  dimension: string; label: string; observations: CohortOutcome[]; outcome_difference: boolean; unknown_observations: number;
}
export interface CohortFinding {
  finding_index: number; target_id: string; observations: CohortOutcome[]; outcome_difference: boolean; unresolved_or_missing: boolean;
}
export interface CohortArm {
  status: string; retained_passes: number; elapsed_seconds: number | null; provider_round_trip_seconds: number | null;
  gpu_compute_seconds: null; dimensions: CohortDimension[]; findings: CohortFinding[];
  active_effort: ComparisonEffort | null; active_effort_accounted: boolean;
  assessment_times: { reviewer_id: string; review_seconds: number | null }[];
  unknown_assessment_observations: number; outcome_difference_count: number; unresolved_finding_count: number;
}
export interface CohortRow extends CohortSelection {
  title: string; capture_sha256: string; profile_sha256: string; family_sha256: string; sample_kind: 'real' | 'synthetic';
  source_freshness: ComparisonCapture['freshness']; capture_complete: boolean; current_reviewer_count: number;
  unknown_assessment_observations: number; outcome_difference_count: number; unresolved_finding_count: number;
  arms: Record<ComparisonArm, CohortArm>;
}
export interface CohortReport {
  counts: Record<'selected_records' | 'profile_groups' | 'declared_families' | 'current_source_records' | 'complete_capture_records' | 'current_reviewer_pairs' | 'accounted_effort_records' | 'records_with_outcome_differences' | 'records_with_unknown_assessments' | 'records_with_unresolved_findings', number>;
  profiles: { profile_sha256: string; comparison_ids: string[]; profile: {
    sample_kind: 'real' | 'synthetic'; rubric_sha256: string; provider_pin: { model: string };
    arms: Record<ComparisonArm, { max_passes: number; budget_seconds: number }>;
    feedback_policy: { selected: boolean; recipe: string | null };
  } }[];
  families: { family_sha256: string; comparison_ids: string[]; reserved_overlap: boolean }[];
  duplicate_inputs: { task_input_sha256: string; comparison_ids: string[] }[];
  repeated_versions: { version_id: string; content_sha256: string; comparison_ids: string[] }[];
  cross_family_sources: { document_id: string; selections: { comparison_id: string; family_sha256: string }[] }[];
  reserved_overlaps: string[]; rows: CohortRow[];
  selection_is_exhaustive: false; held_out_qualified: false; reviewer_expertise_verified: false;
  legal_verdict: null; preparation_time_gain: null; qualification_granted: false; production_qualified: false; benefit_established: false;
}
export interface CohortManifest {
  matter_id: string; title: string; purpose: string; reserved_family_sha256: string[]; selections: CohortSelection[];
  captures: (CohortSelection & { capture_sha256: string; capture: FrozenCapture })[];
  reconciliation: CohortReport;
}
export interface CohortPreview { manifest: CohortManifest; preview_sha256: string }
export interface CohortView {
  id: string; registered_at: string; manifest: CohortManifest; manifest_sha256: string; cohort_sha256: string;
  freshness: { status: 'current' | 'stale'; reasons: { comparison_id: string | null; code: string }[] };
  qualification_granted: false; production_qualified: false; benefit_established: false;
}
