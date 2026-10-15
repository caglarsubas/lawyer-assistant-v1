import { canonicalJson } from '../pages/matter/sourceReviewTypes';
import { sourceContextHref, type NavigationMetadata } from '../pages/sourceContextNavigationTypes';
import { verifyReviewLineage, type ReviewLineage } from '../pages/sourceReviewLineageTypes';
import { validateReturn, type ReturnIntent } from './portfolioReturn';
import { verifyReturnSelection } from './returnComparison';
import { verifyRenewalObservation, type RenewalObservation } from './renewalReconciliation';

export type ReviewCommitPin = { id: string; packet_sha256: string; state: 'changes_requested' | 'reviewed_conditional' };
export function completeRenewalAdmissions(value: RenewalObservation) {
  return value.outcome === 'verified' && value.admission?.successor === 'complete' && value.admission.parent === 'complete' && ['complete', 'not_recorded'].includes(value.admission.parent_review);
}
export function verifySameRenewalLink(before: RenewalObservation, after: RenewalObservation) {
  verifyRenewalObservation(before, before.receipt, before.matter_id, before.analysis_id);
  verifyRenewalObservation(after, before.receipt, before.matter_id, before.analysis_id);
  if (!completeRenewalAdmissions(before) || !completeRenewalAdmissions(after)
    || canonicalJson({ s: before.successor, l: before.lineage, a: before.admission }) !== canonicalJson({ s: after.successor, l: after.lineage, a: after.admission })) throw new Error('Yenileme bağı veya kabul durumu değişti; sonucu yeniden gözlemleyin.');
}
function freshIntent(intent: ReturnIntent, meta: NavigationMetadata): ReturnIntent {
  return { recipe: 'private-portfolio-return-intent-v2', filters: structuredClone(intent.filters), target: {
    matter_id: meta.matter_id, analysis_id: meta.analysis_id, context_id: meta.context_id, version_id: meta.context.version_id, manifest_sha256: meta.context.manifest_sha256,
    head_id: meta.historical_review.id, head_state: meta.historical_review.state, observed_at: meta.observed_at, current_version_id: meta.analysis.current_version_id,
    version_observed_at: meta.observed_at, review_id: null, review_packet_sha256: null } };
}
export function parentLineageIntent(intent: ReturnIntent, link: RenewalObservation, meta: NavigationMetadata, history: ReviewLineage | null): ReturnIntent {
  validateReturn(intent); verifySameRenewalLink(link, link);
  const p = link.lineage!, r = link.receipt;
  if (link.matter_id !== intent.target.matter_id || link.analysis_id !== intent.target.analysis_id || p.parent_context_id !== intent.target.context_id
    || p.parent_version_id !== intent.target.version_id || p.parent_manifest_sha256 !== intent.target.manifest_sha256 || meta.admission.context_state !== 'complete') throw new Error('Özgün yenileme bağının özel kapsamı değişti.');
  verifyReturnSelection(intent, meta, null);
  if (p.parent_review_id) {
    if (!history) throw new Error('Yakalanan tarihsel karar ayrıca doğrulanmalı.');
    verifyReviewLineage(history, { kind: 'selected', matter_id: link.matter_id, analysis_id: link.analysis_id, context_id: r.parent_context_id, review_id: p.parent_review_id });
    if (canonicalJson(history.context_navigation) !== canonicalJson(meta) || history.selected_review.integrity !== 'verified' || history.selected_review.admission !== 'complete'
      || history.selected_review.packet_sha256 !== p.parent_review_packet_sha256) throw new Error('Yakalanan tarihsel karar özeti değişti; son karar yerine kullanılamaz.');
  } else if (history) throw new Error('Yakalanmamış bir tarihsel karar eklenemez.');
  const next = freshIntent(intent, meta); next.target.review_id = p.parent_review_id; next.target.review_packet_sha256 = p.parent_review_packet_sha256;
  validateReturn(next); return next;
}
export function verifyReviewPreparation(intent: ReturnIntent, meta: NavigationMetadata, before?: NavigationMetadata, committed?: ReviewCommitPin) {
  validateReturn(intent); verifyReturnSelection(intent, meta, null);
  if (intent.target.review_id !== null || meta.version_relation !== 'same' || !meta.tools_available || meta.admission.context_state !== 'complete'
    || !['complete', 'not_recorded'].includes(meta.admission.review_state) || meta.historical_review.state === 'unknown') throw new Error('Yeni bağımsız inceleme için güncel tam bağlam ve tamamlanmış kabul gerekir.');
  if (before && (meta.analysis.revision !== before.analysis.revision || meta.analysis.current_version_id !== before.analysis.current_version_id
    || (committed ? meta.historical_review.id !== committed.id || meta.historical_review.state !== committed.state || meta.admission.review_state !== 'complete'
      : canonicalJson(meta.historical_review) !== canonicalJson(before.historical_review)))) throw new Error('Bağımsız incelemenin sürümü veya karar başı değişti; yeniden gözlemleyin.');
}
export function independentReviewIntent(intent: ReturnIntent, meta: NavigationMetadata): ReturnIntent {
  verifyReturnSelection(intent, meta, null); const next = freshIntent(intent, meta); verifyReviewPreparation(next, meta); return next;
}
export function verifyCommittedReview(intent: ReturnIntent, before: NavigationMetadata, committed: ReviewCommitPin, history: ReviewLineage) {
  verifyReviewLineage(history, { kind: 'selected', matter_id: intent.target.matter_id, analysis_id: intent.target.analysis_id, context_id: intent.target.context_id, review_id: committed.id });
  if (history.selected_review.integrity !== 'verified' || history.selected_review.admission !== 'complete' || history.selected_review.packet_sha256 !== committed.packet_sha256
    || history.selected_review.previous_review_id !== before.historical_review.id) throw new Error('Yeni bağımsız kararın tam kayıt veya önceki baş bağı doğrulanamadı.');
  verifyReviewPreparation(intent, history.context_navigation, before, committed);
}
export function reviewPreparationHref(intent: ReturnIntent, token: string) {
  validateReturn(intent);
  if (intent.target.review_id !== null || !intent.target.version_id || !intent.target.manifest_sha256) throw new Error('Tarihsel karar yeni incelemeye aktarılamaz.');
  const t = intent.target, href = sourceContextHref(t.matter_id, t.analysis_id, t.context_id, undefined, token);
  return href ? `${href}&prepare=review` : null;
}
