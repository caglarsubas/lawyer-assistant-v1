import type { AuthorityComparisonView } from './authorityComparisonTypes';
import type { FindingDimension, FindingSummary } from './authorityFindingTypes';
export const SEMANTIC_DIMENSIONS = ['meaning', 'roles', 'logic', 'conditions', 'adverse', 'certainty'] as const;
export type SemanticDimension = typeof SEMANTIC_DIMENSIONS[number];
export const SEMANTIC_OUTCOMES = { supported: 'Destekleniyor · İnceleyen beyanı', needs_change: 'Değişiklik gerekli', unresolved: 'Çözümlenmedi', not_assessed: 'Değerlendirilmedi' } as const;
export const JUDGMENT_OUTCOMES = { agree: 'Beyana katılıyorum', disagree: 'Beyana katılmıyorum', unresolved: 'Çözümlenmedi', not_assessed: 'Değerlendirilmedi' } as const;
export interface AdjudicationLinks { note: string; target_refs: string[]; private_source_refs: string[]; public_source_indices: number[] }
export interface SemanticObservation extends AdjudicationLinks { dimension: SemanticDimension; outcome: keyof typeof SEMANTIC_OUTCOMES | '' }
export interface FindingJudgment extends AdjudicationLinks { source_index: number; dimension: FindingDimension; outcome: keyof typeof JUDGMENT_OUTCOMES | '' }
export interface AdverseScope { status: 'not_searched' | 'selected_sources_inspected' | ''; inspected_source_indices: number[]; limitations: string }
export interface AdjudicationInputs {
  basis_sha256: string; expected_adjudication_id: string | null; can_record: boolean; independent_account: boolean;
  freshness: { status: 'current' | 'stale'; reasons: string[] };
  basis: { comparison: NonNullable<AuthorityComparisonView['snapshot']>; dimensions: Record<SemanticDimension, string>; excluded_account_ids: string[]; account_separation_only: true };
}
export interface AdjudicationView extends FindingSummary {
  reviewer_id: string; adjudication_sha256: string; public_source_access: boolean; is_latest_for_reviewer: boolean;
  freshness: { status: 'current' | 'stale' | 'withheld'; reasons: string[] };
  snapshot: null | { basis: AdjudicationInputs['basis']; basis_sha256: string;
    assessment: { note: string; review_seconds: number | null; observations: SemanticObservation[]; judgments: FindingJudgment[]; adverse_scope: AdverseScope };
    coverage: { semantic: { assessed: number; total: number }; findings: { assessed: number; total: number }; corpus_completeness: 'unknown'; adverse_recall: null } };
}
export function adjudicationAssessment(inputs: AdjudicationInputs, observations: SemanticObservation[], judgments: FindingJudgment[], scope: AdverseScope, note: string, seconds: string) {
  const time = seconds.trim() === '' ? null : Number(seconds);
  const comp = inputs.basis.comparison.comparison_snapshot;
  const publicIndices = comp.authority_review_snapshot.assessment.sources.map((_, index) => index);
  const targets = new Set(['before', 'after'].flatMap(side => Object.keys(side === 'before' ? comp.before_targets : comp.after_targets).map(key => `${side}:${key}`)));
  const refs = new Set(comp.private_sources.map(item => item.source_ref));
  const keys = inputs.basis.comparison.assessment.dispositions.map(item => `${item.source_index}:${item.dimension}`);
  const validLinks = (item: AdjudicationLinks) => item.note.trim().length >= 3 && item.note.length <= 2000
    && item.target_refs.length <= 24 && item.private_source_refs.length <= 20 && item.public_source_indices.length <= 8
    && [item.target_refs, item.private_source_refs, item.public_source_indices].every(items => new Set<string | number>(items).size === items.length)
    && item.target_refs.every(key => targets.has(key)) && item.private_source_refs.every(key => refs.has(key)) && item.public_source_indices.every(key => Number.isInteger(key) && publicIndices.includes(key));
  if (!inputs.can_record || note.trim().length < 3 || note.length > 2000 || (time !== null && (!Number.isInteger(time) || time < 1 || time > 28800))
    || observations.length !== 6 || new Set(observations.map(item => item.dimension)).size !== 6 || SEMANTIC_DIMENSIONS.some(dim => !observations.some(item => item.dimension === dim))
    || judgments.length !== keys.length || new Set(judgments.map(item => `${item.source_index}:${item.dimension}`)).size !== keys.length || keys.some(key => !judgments.some(item => `${item.source_index}:${item.dimension}` === key))
    || !scope.status || scope.limitations.trim().length < 3 || scope.limitations.length > 2000 || scope.inspected_source_indices.length > 8
    || new Set(scope.inspected_source_indices).size !== scope.inspected_source_indices.length || scope.inspected_source_indices.some(key => !Number.isInteger(key) || !publicIndices.includes(key))
    || (scope.status === 'not_searched' && scope.inspected_source_indices.length > 0) || (scope.status === 'selected_sources_inspected' && !scope.inspected_source_indices.length)
    || observations.some(item => !Object.hasOwn(SEMANTIC_OUTCOMES, item.outcome)) || judgments.some(item => !Object.hasOwn(JUDGMENT_OUTCOMES, item.outcome))) return null;
  for (const item of [...observations, ...judgments]) {
    if (!validLinks(item)) return null;
    if (['supported', 'needs_change', 'agree', 'disagree'].includes(item.outcome) && (!item.target_refs.length || !item.private_source_refs.length || !item.public_source_indices.length)) return null;
    if ('source_index' in item && ['agree', 'disagree'].includes(item.outcome) && !item.public_source_indices.includes(item.source_index)) return null;
    if (item.outcome === 'supported' && (!item.target_refs.some(key => key.startsWith('after:')) || !item.private_source_refs.some(key => key.startsWith('after:')))) return null;
    if (item.dimension === 'adverse' && ['supported', 'agree'].includes(item.outcome) && (scope.status !== 'selected_sources_inspected' || item.public_source_indices.some(key => !scope.inspected_source_indices.includes(key)))) return null;
  }
  const result = { observations, judgments, adverse_scope: scope, note, review_seconds: time };
  return new TextEncoder().encode(JSON.stringify(result)).length > 128 * 1024 ? null : result;
}
export function committedAdjudicationReceipt(data: unknown): string | null {
  if (!data || typeof data !== 'object') return null;
  const value = data as Record<string, unknown>;
  return value.outcome === 'committed_needs_revalidation' && value.needs_revalidation === true && typeof value.id === 'string' && /^aij-[a-f0-9]{24}-[a-f0-9]{32}$/.test(value.id) ? value.id : null;
}
