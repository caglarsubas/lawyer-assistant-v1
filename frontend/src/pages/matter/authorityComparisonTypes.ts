import type { FindingDimension, FindingSnapshot, FindingSummary } from './authorityFindingTypes';
export const DISPOSITIONS = { addressed: 'Ele alındı · Avukat beyanı', retained: 'Değişmeden korundu', removed: 'Bağlı adımlar çıkarıldı', unresolved: 'Çözümlenmedi', not_assessed: 'Değerlendirilmedi' } as const;
export type DispositionOutcome = keyof typeof DISPOSITIONS;
export interface AuthorityDisposition { source_index: number; dimension: FindingDimension; outcome: DispositionOutcome; note: string; after_target_ids: string[]; private_source_refs: string[] }
export interface EditableDisposition extends Omit<AuthorityDisposition, 'outcome'> { outcome: DispositionOutcome | '' }
export interface AuthorityComparisonSnapshot {
  review_id: string; authority_review_snapshot: FindingSnapshot; authority_review_sha256: string;
  base_version_id: string; base_version: number; base_content_sha256: string;
  candidate_version_id: string; candidate_version: number; candidate_content_sha256: string;
  before_targets: Record<string, unknown>; after_targets: Record<string, unknown>;
  changes: { target_id: string; before: unknown; after: unknown }[];
  private_sources: { source_ref: string; name: string; locator: string; text: string; quote_sha256: string; start: number; end: number }[];
  dimensions: Record<FindingDimension, string>; historical_context_changes: string[];
}
export interface AuthorityComparisonInputs { comparison: AuthorityComparisonSnapshot; basis_sha256: string; expected_comparison_id: string | null; freshness: { status: 'current' | 'stale'; reasons: string[] }; can_record: boolean }
export interface AuthorityComparisonView extends FindingSummary {
  comparison_sha256: string; public_source_access: boolean; is_latest_comparison: boolean;
  freshness: { status: 'current' | 'stale' | 'withheld'; reasons: string[] };
  snapshot: null | { comparison_snapshot: AuthorityComparisonSnapshot; assessment: { note: string; review_seconds: number | null; dispositions: AuthorityDisposition[] }; basis_sha256: string; previous_comparison_id: string | null };
}
export function comparisonAssessment(inputs: AuthorityComparisonInputs, rows: EditableDisposition[], note: string, seconds: string) {
  const time = seconds.trim() === '' ? null : Number(seconds);
  const sources = inputs.comparison.authority_review_snapshot.assessment.sources;
  const keys = sources.flatMap((source, index) => source.observations.map(item => `${index}:${item.dimension}`));
  const refs = new Set(inputs.comparison.private_sources.map(item => item.source_ref));
  const unique = new Set(rows.map(item => `${item.source_index}:${item.dimension}`));
  if (!inputs.can_record || note.trim().length < 3 || note.length > 2000 || (time !== null && (!Number.isInteger(time) || time < 1 || time > 28800))
    || rows.length !== keys.length || unique.size !== keys.length || keys.some(key => !unique.has(key))
    || rows.some(item => !item.outcome || !Object.hasOwn(DISPOSITIONS, item.outcome) || item.note.trim().length < 3 || item.note.length > 2000
      || item.after_target_ids.length > 12 || item.private_source_refs.length > 20
      || new Set(item.after_target_ids).size !== item.after_target_ids.length || new Set(item.private_source_refs).size !== item.private_source_refs.length
      || item.after_target_ids.some(key => !Object.hasOwn(inputs.comparison.after_targets, key)) || item.private_source_refs.some(key => !refs.has(key)))) return null;
  for (const item of rows) {
    const linked = sources[item.source_index].target_ids;
    const changed = item.after_target_ids.some(key => JSON.stringify(inputs.comparison.before_targets[key]) !== JSON.stringify(inputs.comparison.after_targets[key]));
    if (item.outcome === 'addressed' && (!changed || !item.private_source_refs.some(key => key.startsWith('after:')))) return null;
    if (item.outcome === 'retained' && linked.some(key => !item.after_target_ids.includes(key) || JSON.stringify(inputs.comparison.before_targets[key]) !== JSON.stringify(inputs.comparison.after_targets[key]))) return null;
    if (item.outcome === 'removed' && (item.after_target_ids.length || linked.some(key => Object.hasOwn(inputs.comparison.after_targets, key)))) return null;
  }
  const value = { dispositions: rows as AuthorityDisposition[], note, review_seconds: time };
  return new TextEncoder().encode(JSON.stringify(value)).length > 128 * 1024 ? null : value;
}
export function committedComparisonReceipt(data: unknown): string | null {
  if (!data || typeof data !== 'object') return null;
  const value = data as Record<string, unknown>;
  return value.outcome === 'committed_needs_revalidation' && value.needs_revalidation === true && typeof value.id === 'string' && /^acr-[a-f0-9]{24}-[a-f0-9]{32}$/.test(value.id) ? value.id : null;
}
