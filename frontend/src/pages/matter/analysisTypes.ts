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
  checks: AnalysisChecks; status: 'needs_review' | 'stale'; authorship: 'user'; legal_authority: false;
  revision_comparison: { previous_version_id: string | null; changed_sections: string[]; changed_dependency_groups: string[]; checks_no_longer_triggered: string[]; new_check_ids: string[]; scope: string };
}
export interface AnalysisRecord extends AnalysisContent {
  id: string; revision: number; version: number; latest_version_id: string; created_at: string;
  freshness: AnalysisFreshness;
}
export interface AnalysisVersion { id: string; version: number; content: AnalysisContent; change_note: string; created_at: string; freshness: AnalysisFreshness }

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
