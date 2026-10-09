import type { AnalysisSuggestion } from './analysisTypes';
import type { AuthorityAssessment, FindingDimension } from './authorityFindingTypes';
import type { AuthorityManifest } from './authorityTypes';
import type { AdjudicationLinks, AdverseScope, FindingJudgment, SemanticDimension, SemanticObservation } from './authorityAdjudicationTypes';
import type { ComparisonArm, ComparisonEffortEvent, RegistrationContext } from './comparisonTypes';

export interface ModelInputSelection {
  kind: 'original_review' | 'admitted_renewal'; context_id: string; review_id: string; review_sha256: string;
  renewal_id?: string; renewal_sha256?: string; findings: { source_index: number; dimension: FindingDimension }[];
}
export interface TrialSourceInput { selection: Omit<ModelInputSelection, 'findings'>; assessment: AuthorityAssessment; dimensions: Record<FindingDimension, string> }
export interface ModelTrialContext extends RegistrationContext { selection: ModelInputSelection; feedback: AnalysisSuggestion['authority_feedback']; basis: ModelBasis }
export interface ModelBasis { input_ref: { kind: ModelInputSelection['kind']; id: string; sha256: string }; manifest: AuthorityManifest; assessment: AuthorityAssessment; authority_dimensions: Record<FindingDimension, string> }
export interface ModelComparison { comparison_sha256: string; before_targets: Record<string, unknown>; after_targets: Record<string, unknown>;
  changes: { target_id: string; before: unknown; after: unknown }[];
  private_sources: { source_ref: string; name: string; locator: string; text: string; quote_sha256: string; start: number; end: number }[] }
export interface TrialAssessment { comparison_sha256: string; observations: SemanticObservation[]; judgments: FindingJudgment[]; adverse_scope: AdverseScope; note: string; review_seconds: number | null }
export interface ModelTrialCapture {
  id: string; protocol: null | { title: string; question: string; rubric_text: string; protocol_sha256: string; registered_at: string;
    source_version_id: string; task_input_sha256: string; dimensions: Record<SemanticDimension, string>; authority_basis: ModelBasis;
    provider_pin: { model: string; transport: { uses_public_network: boolean } }; arms: Record<ComparisonArm, { max_passes: number; budget_seconds: number }> };
  execution_sha256: string; public_source_access: boolean; freshness: { status: 'current' | 'stale' | 'withheld'; reasons: string[] };
  arms: Record<ComparisonArm, { status: string; job: AnalysisSuggestion | null; comparison: ModelComparison | null; elapsed_seconds: number | null; provider_round_trip_seconds: number | null; gpu_compute_seconds: null }>;
  observations: { id: string; reviewer_name: string; sequence: number; note: string; arms: { arm: ComparisonArm; assessment: TrialAssessment }[] }[];
  effort_history: (ComparisonEffortEvent & { active_phases_nonoverlapping: boolean })[];
  disagreement: { arm: ComparisonArm; kind: string; item: string; outcomes: string[] }[] | null;
  current_reviewer_count: number; effort_accounted: boolean; capture_complete: boolean; can_run: boolean; can_observe: boolean; can_record_effort: boolean;
  previous_observation_id: string | null; previous_effort_id: string | null;
}
export const blankTrialLinks = (): AdjudicationLinks => ({ note: '', target_refs: [], private_source_refs: [], public_source_indices: [] });
export function renewedTrialSelection(dependency: Pick<ModelInputSelection, 'context_id' | 'review_id' | 'review_sha256'>,
  renewal: { id: string; sha256: string }): Omit<ModelInputSelection, 'findings'> {
  return { kind: 'admitted_renewal', context_id: dependency.context_id, review_id: dependency.review_id,
    review_sha256: dependency.review_sha256, renewal_id: renewal.id, renewal_sha256: renewal.sha256 };
}
