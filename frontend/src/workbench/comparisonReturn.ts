import { hasExactKeys, scalarDataRecordsEqual } from './privateObservationValidation';
import { canonicalJson } from '../pages/matter/sourceReviewTypes';
import { verifyPortfolioQueue, type PortfolioQueuePage } from '../pages/portfolioSourceQueueTypes';
import type { NavigationMetadata, SourceTarget } from '../pages/sourceContextNavigationTypes';
import type { ReviewLineage, ReviewMetadata } from '../pages/sourceReviewLineageTypes';
import { reconcileReturn, validateReturn, type ReturnIntent } from './portfolioReturn';
import { returnVerifiedEvent } from './returnedReviewLineage';
import { compareReviewPathHandoff, verifyReviewPathDestination, type ReviewPathDestination, type ReviewPathHandoff } from './reviewPathHandoff';
import type { IdentityRelation } from './returnComparison';

export type ComparisonReturnReceipt = { recipe: 'private-comparison-return-receipt-v1'; intent: ReturnIntent; handoff: ReviewPathHandoff; destination: ReviewPathDestination };
const equal = (a: unknown, b: unknown) => canonicalJson(a) === canonicalJson(b);
function fail(): never { throw new Error('Korunan karşılaştırmanın dönüş veya yeni kuyruk bağı doğrulanamadı. Yeni gözlem gerekli; önceki sonuç kullanılmadı.'); }
const immutable = ({ admission: _admission, integrity: _integrity, ...value }: ReviewMetadata) => value;
function equalImmutable(left: ReviewMetadata, right: ReviewMetadata) {
  const a = immutable(left), b = immutable(right); return scalarDataRecordsEqual(a, b) ?? equal(a, b);
}
export function validateComparisonReturn(value: ComparisonReturnReceipt, intent: ReturnIntent) {
  validateReturn(intent);
  if (!value || !hasExactKeys(value, ['destination', 'handoff', 'intent', 'recipe'])
    || value.recipe !== 'private-comparison-return-receipt-v1' || !equal(value.intent, intent)) fail();
  verifyReviewPathDestination(intent, value.handoff, value.destination);
}

/** An explicit return records only the comparison actually observed, never an inferred receipt. */
export function captureComparisonReturn(intent: ReturnIntent, handoff: ReviewPathHandoff, target: SourceTarget,
  meta: NavigationMetadata | null, history: ReviewLineage | null): { intent: ReturnIntent; receipt: ComparisonReturnReceipt | null } {
  const next = returnVerifiedEvent(intent, target, meta, history);
  if (!meta && !history) return { intent: next, receipt: null };
  compareReviewPathHandoff(intent, handoff, history!);
  const receipt: ComparisonReturnReceipt = { recipe: 'private-comparison-return-receipt-v1', intent: structuredClone(next), handoff: structuredClone(handoff),
    destination: { metadata: structuredClone(meta!), selected: structuredClone(history!.selected_review), head: structuredClone(history!.current_head) } };
  validateComparisonReturn(receipt, next); return { intent: next, receipt };
}

export type ComparisonQueueReconciliation = { state: 'not_observed'; queue_observed_at: string } | {
  state: 'observed'; queue_observed_at: string; fresh: ReviewPathDestination;
  head_relation: IdentityRelation; version_relation: IdentityRelation; revision_relation: 'same' | 'different';
};
/** Existing bounded queue and exact-event GETs suffice; no scan, body read or repair. */
export function reconcileComparisonReturn(intent: ReturnIntent, receipt: ComparisonReturnReceipt, page: PortfolioQueuePage,
  meta: NavigationMetadata | null, history: ReviewLineage | null, offset = 0): ComparisonQueueReconciliation {
  validateComparisonReturn(receipt, intent); verifyPortfolioQueue(page, intent.filters, offset);
  const previous = receipt.destination, before = previous.metadata;
  if (!Number.isFinite(Date.parse(page.observed_at)) || Date.parse(page.observed_at) < Date.parse(before.observed_at)) fail();
  const result = reconcileReturn(intent, page, meta, history);
  if (result.state === 'not_observed') return { state: 'not_observed', queue_observed_at: page.observed_at };
  if (!meta || !history || Date.parse(meta.observed_at) < Date.parse(page.observed_at) || meta.analysis.revision < before.analysis.revision) fail();
  compareReviewPathHandoff(intent, receipt.handoff, history);
  const fresh = { metadata: meta, selected: history.selected_review, head: history.current_head };
  return structuredClone({ state: 'observed', queue_observed_at: page.observed_at, fresh, ...compareDestinationIdentities(previous, fresh) });
}

/** Both observations must already have passed their exact-context validators. */
export function compareDestinationIdentities(previous: ReviewPathDestination, fresh: ReviewPathDestination) {
  const before = previous.metadata, meta = fresh.metadata, head = fresh.head, oldHead = previous.head;
  if (Date.parse(meta.observed_at) < Date.parse(before.observed_at) || meta.analysis.revision < before.analysis.revision) fail();
  if (head?.integrity === 'verified' && oldHead?.integrity === 'verified' && head.id === oldHead.id && !equalImmutable(head, oldHead)) fail();
  const knownHeads = head?.integrity === 'verified' && meta.historical_review.state !== 'unknown' && oldHead?.integrity === 'verified' && before.historical_review.state !== 'unknown';
  return {
    head_relation: (knownHeads ? head.id === oldHead.id ? 'same' : 'different' : 'unknown') as IdentityRelation,
    version_relation: (before.analysis.current_version_id === null || meta.analysis.current_version_id === null ? 'unknown'
      : before.analysis.current_version_id === meta.analysis.current_version_id ? 'same' : 'different') as IdentityRelation,
    revision_relation: (before.analysis.revision === meta.analysis.revision ? 'same' : 'different') as 'same' | 'different' };
}

export type ObservedComparison = Extract<ComparisonQueueReconciliation, { state: 'observed' }>;
export function validateComparisonObservation(intent: ReturnIntent, receipt: ComparisonReturnReceipt, value: ObservedComparison) {
  validateComparisonReturn(receipt, intent);
  validateDestinationObservation(intent, receipt.handoff, receipt.destination, value);
}

/** Strict reduced queue observation, bound to its own historical comparison baseline. */
export function validateDestinationObservation(intent: ReturnIntent, handoff: ReviewPathHandoff, previous: ReviewPathDestination, value: ObservedComparison) {
  if (!value || !hasExactKeys(value, ['fresh', 'head_relation', 'queue_observed_at', 'revision_relation', 'state', 'version_relation']) || value.state !== 'observed'
    || typeof value.queue_observed_at !== 'string' || value.queue_observed_at.length > 40 || !Number.isFinite(Date.parse(value.queue_observed_at))) fail();
  verifyReviewPathDestination(intent, handoff, value.fresh);
  if (Date.parse(value.queue_observed_at) < Date.parse(previous.metadata.observed_at) || Date.parse(value.fresh.metadata.observed_at) < Date.parse(value.queue_observed_at)) fail();
  const expected = compareDestinationIdentities(previous, value.fresh);
  if (!equal(expected, { head_relation: value.head_relation, version_relation: value.version_relation, revision_relation: value.revision_relation })) fail();
}
