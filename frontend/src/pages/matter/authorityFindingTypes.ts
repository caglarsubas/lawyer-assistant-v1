import type { AuthorityContext, AuthorityIdentity } from './authorityTypes';

export const FINDING_DIMENSIONS = ['applicability', 'history', 'conditions', 'relationship', 'adverse', 'certainty'] as const;
export type FindingDimension = typeof FINDING_DIMENSIONS[number];
export const FINDING_OUTCOMES = { supported: 'Destekleniyor · Avukat değerlendirmesi', needs_change: 'Değişiklik gerekli', unresolved: 'Çözümlenmedi', not_assessed: 'Değerlendirilmedi' } as const;
export type FindingOutcome = keyof typeof FINDING_OUTCOMES;
export interface AuthorityObservation { dimension: FindingDimension; outcome: FindingOutcome; note: string }
export interface SourceAssessment extends AuthorityIdentity { target_ids: string[]; observations: AuthorityObservation[] }
export interface AuthorityAssessment { sources: SourceAssessment[]; note: string; review_seconds: number | null }
export interface FindingInputs { authority_context: AuthorityContext; basis_sha256: string; expected_review_id: string | null; dimensions: Record<FindingDimension, string>; recipe: string; scope: string; can_record: boolean; qualification_granted: false }
export interface FindingSummary { id: string; sequence: number; reviewer_name: string; recorded_at: string }
export interface FindingSnapshot { context_id: string; context_manifest_sha256: string; context_snapshot: AuthorityContext; basis_sha256: string; assessment: AuthorityAssessment; dimensions: Record<FindingDimension, string>; previous_review_id: string | null; recipe: string; scope: string; reviewer_id: string; reviewer_name: string; recorded_at: string; sequence: number; legal_approval: 'not_granted'; model_use: 'none'; qualification_granted: false }
export interface FindingView extends FindingSummary { review_sha256: string; snapshot: FindingSnapshot | null; public_source_access: boolean; is_latest_review: boolean; freshness: { status: 'current' | 'stale' | 'withheld'; reasons: string[] }; qualification_granted: false; legal_approval: 'not_granted'; runtime_authorization: 'none' }
export interface EditableObservation { dimension: FindingDimension; outcome: FindingOutcome | ''; note: string }
export interface EditableAssessment extends AuthorityIdentity { target_ids: string[]; observations: EditableObservation[] }

export function assessmentPayload(sources: EditableAssessment[], note: string, seconds: string): AuthorityAssessment | null {
  const time = seconds.trim() === '' ? null : Number(seconds);
  if (note.trim().length < 3 || note.length > 2000 || (time !== null && (!Number.isInteger(time) || time < 1 || time > 28800))
    || !sources.length || sources.length > 8 || new Set(sources.map(item => JSON.stringify([item.assertion_id, item.passage_id, item.authority_id]))).size !== sources.length
    || sources.some(source => !source.target_ids.length || source.target_ids.length > 12 || new Set(source.target_ids).size !== source.target_ids.length
      || source.observations.length !== 6 || new Set(source.observations.map(item => item.dimension)).size !== 6
      || source.observations.some(item => !FINDING_DIMENSIONS.includes(item.dimension) || !item.outcome || !Object.hasOwn(FINDING_OUTCOMES, item.outcome) || item.note.trim().length < 3 || item.note.length > 2000))) return null;
  const value: AuthorityAssessment = { note, review_seconds: time, sources: sources.map(source => ({ assertion_id: source.assertion_id, passage_id: source.passage_id, authority_id: source.authority_id, target_ids: [...source.target_ids], observations: source.observations.map(item => ({ dimension: item.dimension, outcome: item.outcome as FindingOutcome, note: item.note })) })) };
  return new TextEncoder().encode(JSON.stringify(value)).length > 128 * 1024 ? null : value;
}

export function committedFindingReceipt(data: unknown): string | null {
  if (!data || typeof data !== 'object') return null;
  const value = data as Record<string, unknown>;
  return value.outcome === 'committed_needs_revalidation' && value.needs_revalidation === true && typeof value.id === 'string' && /^aaf-[a-f0-9]{24}-[a-f0-9]{32}$/.test(value.id) ? value.id : null;
}
