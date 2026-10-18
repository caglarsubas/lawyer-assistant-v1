import { hasExactKeys } from './privateObservationValidation';
import { canonicalJson } from '../pages/matter/sourceReviewTypes';
import type { NavigationMetadata, SourceTarget } from '../pages/sourceContextNavigationTypes';
import { verifyReviewLineage, type ReviewLineage } from '../pages/sourceReviewLineageTypes';
import { compareDestinationIdentities, validateComparisonObservation, type ComparisonQueueReconciliation, type ComparisonReturnReceipt, type ObservedComparison } from './comparisonReturn';
import type { ReturnIntent } from './portfolioReturn';
import { returnVerifiedEvent, verifyReturnedEventTarget } from './returnedReviewLineage';
import { compareReviewPathHandoff, verifyReviewPathDestination, type ReviewPathDestination } from './reviewPathHandoff';

export type ComparisonEventHandoff = { recipe: 'private-comparison-event-handoff-v1'; receipt: ComparisonReturnReceipt;
  queue: ObservedComparison; prepared: ReviewPathDestination; observed_at: [string, string] };
const equal = (a: unknown, b: unknown) => plainObservationDataEqual(a, b) ?? canonicalJson(a) === canonicalJson(b);
function fail(): never { throw new Error('Karşılaştırmadan tam karara geçiş doğrulanamadı. Yeni kuyruk gözlemi gerekli; başka kayıt veya önceki sonuç kullanılmadı.'); }
const stamp = (v: unknown): v is string => typeof v === 'string' && v.length <= 40 && Number.isFinite(Date.parse(v));
const stable = (v: ReviewPathDestination) => ({ ...v, metadata: { ...v.metadata, observed_at: null } });
const admitted = (v: ReviewPathDestination) => v.metadata.tools_available && v.metadata.analysis.current_version_id !== null
  && v.metadata.admission.context_state === 'complete' && v.metadata.admission.review_state === 'complete'
  && v.selected.integrity === 'verified' && v.selected.admission === 'complete' && v.head?.integrity === 'verified' && v.head.admission === 'complete';

export function comparisonEventAvailable(intent: ReturnIntent, receipt: ComparisonReturnReceipt, value: ComparisonQueueReconciliation) {
  if (value.state !== 'observed') return false;
  validateComparisonObservation(intent, receipt, value); return admitted(value.fresh);
}
export function validateComparisonEventHandoff(value: ComparisonEventHandoff, intent: ReturnIntent) {
  if (!value || !hasExactKeys(value, ['observed_at', 'prepared', 'queue', 'receipt', 'recipe']) || value.recipe !== 'private-comparison-event-handoff-v1') fail();
  validateComparisonObservation(intent, value.receipt, value.queue); verifyReviewPathDestination(intent, value.receipt.handoff, value.prepared);
  if (!admitted(value.queue.fresh) || !admitted(value.prepared) || !equal(stable(value.queue.fresh), stable(value.prepared))
    || !Array.isArray(value.observed_at) || value.observed_at.length !== 2 || value.observed_at.some(time => !stamp(time))
    || Date.parse(value.observed_at[0]) < Date.parse(value.queue.fresh.metadata.observed_at)
    || Date.parse(value.observed_at[1]) < Date.parse(value.observed_at[0]) || value.prepared.metadata.observed_at !== value.observed_at[1]) fail();
}

/** Two fresh exact-event GETs; a one-record window never asserts a path from the head. */
export async function prepareComparisonEvent(intent: ReturnIntent, receipt: ComparisonReturnReceipt, value: ComparisonQueueReconciliation,
  read: (url: string) => Promise<ReviewLineage>, current: () => boolean): Promise<ComparisonEventHandoff> {
  if (value.state !== 'observed' || !comparisonEventAvailable(intent, receipt, value)) fail();
  const queued = value;
  const t = intent.target, target: SourceTarget = { kind: 'selected', matter_id: t.matter_id, analysis_id: t.analysis_id, context_id: t.context_id, review_id: t.review_id! };
  verifyReturnedEventTarget(intent, target);
  const url = `/matters/${encodeURIComponent(t.matter_id)}/analyses/${encodeURIComponent(t.analysis_id)}/source-contexts/${encodeURIComponent(t.context_id)}/reviews/${encodeURIComponent(t.review_id!)}/navigation-context?window=1`;
  async function observe() {
    if (!current()) fail(); const h = await read(url); if (!current()) fail();
    verifyReviewLineage(h, target); compareReviewPathHandoff(intent, receipt.handoff, h);
    const fresh = { metadata: h.context_navigation, selected: h.selected_review, head: h.current_head };
    compareDestinationIdentities(receipt.destination, fresh);
    if (h.lineage.window !== 1 || !admitted(fresh) || !h.tools_available || !equal(stable(fresh), stable(queued.fresh))
      || Date.parse(h.observed_at) < Date.parse(queued.fresh.metadata.observed_at)) fail();
    return fresh;
  }
  const before = await observe(), after = await observe();
  const result: ComparisonEventHandoff = { recipe: 'private-comparison-event-handoff-v1', receipt: structuredClone(receipt), queue: structuredClone(value), prepared: after,
    observed_at: [before.metadata.observed_at, after.metadata.observed_at] };
  validateComparisonEventHandoff(result, intent); if (!current()) fail(); return structuredClone(result);
}

export function compareComparisonEventArrival(intent: ReturnIntent, handoff: ComparisonEventHandoff, target: SourceTarget, history: ReviewLineage) {
  validateComparisonEventHandoff(handoff, intent); verifyReturnedEventTarget(intent, target); verifyReviewLineage(history, target);
  compareReviewPathHandoff(intent, handoff.receipt.handoff, history);
  const fresh = { metadata: history.context_navigation, selected: history.selected_review, head: history.current_head };
  compareDestinationIdentities(handoff.receipt.destination, fresh);
  return structuredClone({ fresh, ...compareDestinationIdentities(handoff.prepared, fresh) });
}

/** A failed arrival can return its exact selection, but cannot invent a new receipt. */
export function returnComparisonEvent(intent: ReturnIntent, handoff: ComparisonEventHandoff, target: SourceTarget, meta: NavigationMetadata | null, history: ReviewLineage | null) {
  validateComparisonEventHandoff(handoff, intent); const next = returnVerifiedEvent(intent, target, meta, history);
  if (!meta && !history) return { intent: next, receipt: null };
  compareComparisonEventArrival(intent, handoff, target, history!);
  return { intent: next, receipt: structuredClone(handoff.receipt) };
}
import { plainObservationDataEqual } from './plainObservationDataEqual';
