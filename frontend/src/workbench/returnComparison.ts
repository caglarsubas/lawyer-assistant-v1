import { sourceContextHref, verifyNavigation, type NavigationMetadata, type SourceTarget } from '../pages/sourceContextNavigationTypes';
import { verifyReviewLineage, type ReviewLineage } from '../pages/sourceReviewLineageTypes';
import type { ReturnIntent, ReturnReconciliation } from './portfolioReturn';
import { canonicalJson } from '../pages/matter/sourceReviewTypes';

export type IdentityRelation = 'same' | 'different' | 'unknown';
type Head = NavigationMetadata['historical_review'];
export type ReturnComparison = {
  fixed: { matter_id: string; analysis_id: string; context_id: string; version_id: string; manifest_sha256: string };
  before: { head_id: string | null; head_state: Head['state']; head_observed_at: string; version_id: string | null; version_observed_at: string | null };
  current: { head_id: string | null; head_state: Head['state']; version_id: string | null; observed_at: string; frozen_version_relation: IdentityRelation };
  selected: { id: string; packet_sha256: string | null; integrity: 'verified' | 'unavailable' } | null;
  head_relation: IdentityRelation; version_relation: IdentityRelation; selected_head_relation: IdentityRelation;
};

/** Follow-up links select identities; metadata must still match the original evidence. */
export function verifyReturnSelection(intent: ReturnIntent, meta: NavigationMetadata, lineage: ReviewLineage | null, reviewId?: string) {
  const t = intent.target;
  const target: SourceTarget = { kind: 'selected', matter_id: t.matter_id, analysis_id: t.analysis_id, context_id: t.context_id, ...(reviewId ? { review_id: reviewId } : {}) };
  verifyNavigation(meta, target);
  if (meta.integrity !== 'verified' || t.version_id === null || t.manifest_sha256 === null || t.version_id !== meta.context.version_id || t.manifest_sha256 !== meta.context.manifest_sha256)
    throw new Error('Sabit portföy seçimi değişti veya doğrulanamadı; başka kanıt sürümü kullanılmaz.');
  if (t.head_state !== 'unknown' && meta.historical_review.state !== 'unknown' && t.head_id === meta.historical_review.id && t.head_state !== meta.historical_review.state)
    throw new Error('Aynı değiştirilemez kararın gözlenen durumu çelişiyor; yeniden gözlemleyin.');
  if (lineage) {
    verifyReviewLineage(lineage, target);
    if (canonicalJson(lineage.context_navigation) !== canonicalJson(meta))
      throw new Error('Seçilen kararın kimlik gözlemi eşleşmiyor.');
    if (reviewId === t.review_id && t.review_packet_sha256 !== null && lineage.selected_review.packet_sha256 !== t.review_packet_sha256)
      throw new Error('Seçilen tarihsel inceleme değişti; başka karar kullanılmaz.');
  } else if (reviewId) throw new Error('Seçilen tarihsel inceleme gözlenmedi.');
}
export function compareReturnIdentities(intent: ReturnIntent, meta: NavigationMetadata, lineage: ReviewLineage | null): ReturnComparison {
  const t = intent.target; verifyReturnSelection(intent, meta, lineage, t.review_id || undefined);
  const head = meta.historical_review;
  const headKnown = t.head_state !== 'unknown' && head.state !== 'unknown';
  const selected = lineage?.selected_review;
  return {
    fixed: { matter_id: t.matter_id, analysis_id: t.analysis_id, context_id: t.context_id, version_id: t.version_id!, manifest_sha256: t.manifest_sha256! },
    before: { head_id: t.head_id, head_state: t.head_state, head_observed_at: t.observed_at, version_id: t.current_version_id, version_observed_at: t.version_observed_at },
    current: { head_id: head.id, head_state: head.state, version_id: meta.analysis.current_version_id, observed_at: meta.observed_at, frozen_version_relation: meta.version_relation },
    selected: selected ? { id: selected.id, packet_sha256: selected.packet_sha256, integrity: selected.integrity } : null,
    head_relation: headKnown ? (t.head_id === head.id ? 'same' : 'different') : 'unknown',
    version_relation: t.version_observed_at !== null && t.current_version_id !== null && meta.analysis.current_version_id !== null ? (t.current_version_id === meta.analysis.current_version_id ? 'same' : 'different') : 'unknown',
    selected_head_relation: selected?.integrity === 'verified' && head.state !== 'unknown' && head.id !== null ? (selected.id === head.id ? 'same' : 'different') : 'unknown',
  };
}
export function returnComparisonLinks(intent: ReturnIntent, value: ReturnReconciliation, token: string) {
  const closed = { selected: null, head: null, context: null };
  if (value.state !== 'observed') return closed;
  const t = intent.target, c = value.comparison;
  if (c.fixed.matter_id !== t.matter_id || c.fixed.analysis_id !== t.analysis_id || c.fixed.context_id !== t.context_id || c.fixed.version_id !== t.version_id || c.fixed.manifest_sha256 !== t.manifest_sha256
    || c.selected?.id !== (t.review_id || undefined) || t.review_packet_sha256 !== null && c.selected?.packet_sha256 !== t.review_packet_sha256) return closed;
  const href = (review?: string) => sourceContextHref(t.matter_id, t.analysis_id, t.context_id, review, token);
  return { selected: t.review_id ? c.selected?.integrity === 'verified' ? href(t.review_id) : null : href(),
    head: c.current.head_id && ['changes_requested', 'reviewed_conditional'].includes(c.current.head_state) && ['complete', 'pending'].includes(value.review_state) ? href(c.current.head_id) : null,
    context: href() };
}
