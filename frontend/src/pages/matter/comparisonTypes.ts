import type { AnalysisContent, AnalysisSuggestion, RevisionAssessment, RevisionComparison } from './analysisTypes';

export type ComparisonArm = 'single_pass' | 'bounded_correction';
export const ARM_LABELS: Record<ComparisonArm, string> = { single_pass: 'Tek geçiş', bounded_correction: 'Koşullu yapısal ek geçiş' };
export interface RegistrationContext {
  context_sha256: string; version_id: string; expected_revision: number;
  eligible_reviewers: { id: string; name: string }[]; synthetic_only: boolean; can_register: boolean;
  provider_model: string; research_budget_seconds: number;
}
export interface ComparisonEffort {
  arm: ComparisonArm; preparation_seconds: number | null; verification_seconds: number | null; correction_seconds: number | null;
}
export interface ComparisonObservation {
  id: string; reviewer_id: string; reviewer_name: string; note: string; sequence: number; execution_sha256: string;
  arms: { arm: ComparisonArm; assessment: RevisionAssessment }[]; comparison_snapshots: Record<ComparisonArm, RevisionComparison>;
}
export interface ComparisonEffortEvent {
  id: string; reviewer_name: string; note: string; sequence: number; arms: ComparisonEffort[];
  shared_setup_included: boolean; verification_and_correction_included: boolean;
}
export interface ComparisonCapture {
  id: string; execution_sha256: string; sample_kind: 'real' | 'synthetic'; exported_at: string;
  protocol: {
    title: string; question: string; rubric_text: string; rubric_sha256: string; protocol_sha256: string;
    registered_at: string; registered_by: string; source_version: number; source_content: AnalysisContent;
    source_version_id: string; task_input_sha256: string; reviewer_ids: string[];
    provider_pin: { model: string; transport?: { mode: string; uses_public_network: boolean } };
    arms: Record<ComparisonArm, { max_passes: number; budget_seconds: number }>;
  };
  arms: Record<ComparisonArm, { status: string; job: Omit<AnalysisSuggestion, 'can_adopt' | 'freshness'> | null;
    comparison: RevisionComparison | null; elapsed_seconds: number | null; provider_round_trip_seconds: number | null; gpu_compute_seconds: null }>;
  freshness: { status: 'current' | 'stale'; reasons: string[] };
  observations: ComparisonObservation[]; effort_history: ComparisonEffortEvent[];
  current_reviewer_count: number; effort_accounted: boolean; capture_complete: boolean;
  can_run: boolean; can_observe: boolean; can_record_effort: boolean;
  previous_observation_id: string | null; previous_effort_id: string | null;
  qualification_granted: false; benefit_established: false;
}
