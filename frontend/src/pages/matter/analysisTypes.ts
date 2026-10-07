import type { Fact, Passage } from '../../types';

export interface AnalysisPremise { id: string; kind: 'fact' | 'assumption' | 'unknown'; fact_id: string | null; fact_revision: number | null; text: string }
export interface AnalysisCondition { id: string; text: string; kind: 'element' | 'exception' | 'jurisdiction' | 'burden'; required_status: 'met' | 'not_met' }
export interface AnalysisRule { id: string; kind: 'contract_clause' | 'legal_norm'; text: string; evidence_ids: string[]; conditions: AnalysisCondition[] }
export interface AnalysisAssessment { condition_id: string; status: 'met' | 'not_met' | 'unknown'; premise_ids: string[] }
export interface AnalysisApplication { id: string; rule_id: string; premise_ids: string[]; rationale: string; assessments: AnalysisAssessment[] }
export interface AnalysisAlternative { id: string; kind: 'adverse_argument' | 'alternative_classification' | 'material_distinction' | 'search_gap'; text: string; evidence_ids: string[] }
export interface AnalysisSelection { evidence_id: string; passage_sha256: string; document_revision: number; start: number; end: number }
export interface AnalysisForm {
  title: string; issue: string; posture: string; event_date: string | null;
  evidence: AnalysisSelection[]; premises: AnalysisPremise[]; rules: AnalysisRule[];
  applications: AnalysisApplication[]; alternatives: AnalysisAlternative[];
  conclusion: { text: string; requested_disposition: 'supported_candidate' | 'conditional' | 'withheld'; application_ids: string[]; alternative_ids: string[]; uncertainty: string[]; next_step: string };
}
export interface AnalysisChecks {
  recipe: string; scope: 'declared_structure_only'; legal_approval: 'not_granted';
  effective_disposition: 'conditional' | 'withheld'; critical_count: number;
  defects: { id: string; code: string; target_id: string; severity: 'critical' | 'major'; message: string }[];
  dependency_nodes: string[];
}
export interface AnalysisFreshness { status: 'current' | 'stale'; reasons: string[]; scope: string }
export interface AnalysisContent extends Omit<AnalysisForm, 'evidence'> {
  evidence: (AnalysisSelection & { document_id: string; document_revision: number; document_sha256: string | null; name: string; locator: Passage['locator']; passage_sha256: string; quote_sha256: string; text: string; full_passage_length: number })[];
  fact_snapshots: { id: string; revision: number; text: string; status: string; evidence_id: string | null }[];
  checks: AnalysisChecks; status: 'needs_review' | 'reviewed' | 'stale'; authorship: 'user' | 'user_with_ai_assistance' | 'model_proposal'; legal_authority: false;
  ai_assistance?: { job_id: string; source_version_id: string; passes: number; provider: { model: string }; review_notes?: { target_id: string; text: string; pass: number }[]; review_feedback?: AnalysisFeedback; feedback_responses?: FeedbackResponse[]; feedback_response_pass?: number | null };
  revision_comparison: { previous_version_id: string | null; changed_sections: string[]; changed_dependency_groups: string[]; checks_no_longer_triggered: string[]; new_check_ids: string[]; scope: string };
}
export interface AnalysisRecord extends AnalysisContent {
  id: string; revision: number; version: number; latest_version_id: string; created_at: string;
  freshness: AnalysisFreshness;
  review?: AnalysisReviewProjection;
}
export interface AnalysisVersion { id: string; version: number; content: AnalysisContent; change_note: string; created_at: string; freshness: AnalysisFreshness; review?: AnalysisReviewProjection }

export function analysisForm(record?: AnalysisContent, visibleFacts?: Fact[]): AnalysisForm {
  return record ? {
    title: record.title, issue: record.issue, posture: record.posture, event_date: record.event_date,
    evidence: record.evidence.map(({ evidence_id, passage_sha256, document_revision, start, end }) => ({ evidence_id, passage_sha256, document_revision, start, end })),
    premises: record.premises.map((premise) => ({ ...premise,
      fact_revision: premise.kind === 'fact' ? visibleFacts?.find((fact) => fact.id === premise.fact_id)?.revision ?? premise.fact_revision : null,
    })), rules: record.rules,
    applications: record.applications.map((app) => ({ ...app, assessments: [
      ...app.assessments,
      ...(record.rules.find((rule) => rule.id === app.rule_id)?.conditions || [])
        .filter((condition) => !app.assessments.some((assessment) => assessment.condition_id === condition.id))
        .map((condition) => ({ condition_id: condition.id, status: 'unknown' as const, premise_ids: [] })),
    ] })), alternatives: record.alternatives,
    conclusion: record.conclusion,
  } : {
    title: '', issue: '', posture: '', event_date: null, evidence: [], premises: [], rules: [], applications: [], alternatives: [],
    conclusion: { text: '', requested_disposition: 'conditional', application_ids: [], alternative_ids: [], uncertainty: [], next_step: '' },
  };
}

export const ANALYSIS_LABELS: Record<string, string> = {
  fact: 'Olgu defterinden', assumption: 'Varsayım', unknown: 'Bilinmeyen',
  contract_clause: 'Sözleşme maddesi adayı', legal_norm: 'Mevzuat kuralı adayı · otorite doğrulanmadı',
  element: 'Koşul', exception: 'İstisna', jurisdiction: 'Yetki', burden: 'İspat yükü',
  met: 'Karşılanıyor', not_met: 'Karşılanmıyor',
  adverse_argument: 'Karşı argüman', alternative_classification: 'Alternatif sınıflandırma',
  material_distinction: 'Maddi ayrım', search_gap: 'Araştırma boşluğu',
  supported_candidate: 'Daha güçlü sonuç talebi · doğrulanmadı', conditional: 'Koşullu taslak', withheld: 'Sonuç bekletiliyor',
};


export interface AnalysisSuggestion {
  id: string; status: string; phase: string; mode: 'single' | 'repair'; max_passes: number;
  source_version_id: string; created_at: string; finished_at?: string; deadline_at: string; budget_seconds: number;
  provider_pin: { model: string; recipe: string; transport: { mode: string; uses_public_network: boolean } };
  candidate?: AnalysisContent; candidate_sha256?: string; can_adopt: boolean; adopted_version_id?: string;
  freshness: AnalysisFreshness; error?: string;
  review_notes?: { target_id: string; text: string; evidence_ids: string[]; pass: number }[];
  review_feedback?: AnalysisFeedback; feedback_responses?: FeedbackResponse[]; feedback_response_pass?: number | null;
  iterations?: { pass: number; provider_seconds: number; prompt: { utf8_bytes: number; messages_sha256: string; completion_tokens: number }; outcome: string; new_critical_check_ids: string[]; checks: AnalysisChecks; patch?: { feedback_responses?: FeedbackResponse[] } }[];
}

export interface FeedbackResponse { finding_id: string; outcome: 'proposed_change' | 'requires_manual_work' | 'unresolved'; edited_targets: string[]; text: string; evidence_ids: string[] }
export interface AnalysisFeedback {
  review_id: string; source_version_id: string; content_sha256: string; review_recipe: string;
  findings: (AnalysisReviewFinding & { finding_id: string; index: number; editable_targets: string[] })[];
}

export type ReviewCriterionKey = 'sources' | 'reasoning' | 'fact_roles' | 'limits' | 'ai_contribution';
export type ReviewOutcome = 'confirmed' | 'needs_change' | 'not_applicable';
export interface AnalysisReviewCriterion { criterion: ReviewCriterionKey; outcome: ReviewOutcome; note: string }
export interface AnalysisReviewFinding { target_id: string; severity: 'critical' | 'major' | 'note'; text: string; suggested_change: string; evidence_ids: string[] }
export interface AnalysisReviewEvent {
  id: string; version_id: string; created_at: string; sequence: number; content_sha256: string;
  decision: 'reviewed_conditional' | 'changes_requested'; reviewer_id: string; reviewer_name: string;
  note: string; criteria: AnalysisReviewCriterion[]; findings: AnalysisReviewFinding[];
  scope: 'conditional_private_draft_only'; recipe: string;
}
export interface AnalysisReviewProjection {
  effective_state: 'unreviewed' | 'reviewed_conditional' | 'changes_requested' | 'stale';
  scope: 'conditional_private_draft_only'; latest: AnalysisReviewEvent | null; reasons: string[];
}
export interface AnalysisReviewContext {
  version_id: string; expected_revision: number; content_sha256: string; expected_review_id: string | null;
  recipe: string; criteria: Record<ReviewCriterionKey, string>; ai_contribution_required: boolean;
  current_version: boolean; can_record: boolean; can_accept: boolean; critical_count: number;
  freshness: AnalysisFreshness; review: AnalysisReviewProjection; targets: string[];
  sources: { evidence_id: string; document_id: string; name: string; locator: Passage['locator']; start: number; end: number; quote_sha256: string }[];
}
