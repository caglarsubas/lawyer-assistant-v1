import { canonicalJson } from '../pages/matter/sourceReviewTypes';
import type { PortfolioQueuePage } from '../pages/portfolioSourceQueueTypes';
import type { NavigationMetadata, SourceTarget } from '../pages/sourceContextNavigationTypes';
import { verifyReviewLineage, type ReviewLineage } from '../pages/sourceReviewLineageTypes';
import { reconcileArrivalHandoffDestinationReturn, validateArrivalHandoffDestinationReturn, type ArrivalHandoffDestinationReturn } from './arrivalHandoffDestinationReturn';
import { compareDestinationIdentities, validateDestinationObservation, type ComparisonQueueReconciliation, type ObservedComparison } from './comparisonReturn';
import type { ReturnIntent } from './portfolioReturn';
import { returnVerifiedEvent, verifyReturnedEventTarget } from './returnedReviewLineage';
import { verifyReviewPathDestination, type ReviewPathDestination } from './reviewPathHandoff';

/** Fixed-depth purpose. The separately saved destination and all prior observations stay unchanged. */
export type HandoffDestinationEvent = { recipe: 'private-handoff-destination-event-v1'; observation: ArrivalHandoffDestinationReturn;
  queue: ObservedComparison; prepared: ReviewPathDestination; observed_at: [string, string] };
const equal = (a: unknown, b: unknown) => canonicalJson(a) === canonicalJson(b);
const stable = (v: ReviewPathDestination) => ({ ...v, metadata: { ...v.metadata, observed_at: null } });
const admitted = (v: ReviewPathDestination) => v.metadata.tools_available && v.metadata.analysis.current_version_id !== null
  && v.metadata.admission.context_state === 'complete' && v.metadata.admission.review_state === 'complete'
  && v.selected.integrity === 'verified' && v.selected.admission === 'complete' && v.head?.integrity === 'verified' && v.head.admission === 'complete';
function fail(): never { throw new Error('Geçiş hedefini koruyan tam karar geçişi doğrulanamadı. Yeni kuyruk gözlemi gerekli; başka kayıt veya önceki sonuç kullanılmadı.'); }
const stamp = (v: unknown): v is string => typeof v === 'string' && v.length <= 40 && Number.isFinite(Date.parse(v));
/** Every public operation validates the complete history afresh. Checks never escape this module. */
function retainedChecks(intent: ReturnIntent, observation: ArrivalHandoffDestinationReturn) {
  const purpose = observation.handoff, arrival = purpose.observation, latest = arrival.handoff, d = latest.observation;
  const h = d.handoff, c = h.observation, o = c.handoff.observation, old = o.handoff.observation, r = old.handoff.receipt;
  const snapshots = [r.destination, old.arrival, o.handoff.queue.fresh, o.handoff.prepared, o.destination,
    c.handoff.queue.fresh, c.handoff.prepared, c.arrival, h.queue.fresh, h.prepared, d.destination,
    latest.queue.fresh, latest.prepared, arrival.arrival, purpose.queue.fresh, purpose.prepared, observation.destination];
  return {
    destination(fresh: ReviewPathDestination) {
      verifyReviewPathDestination(intent, r.handoff, fresh);
      for (const previous of snapshots) compareDestinationIdentities(previous, fresh);
    },
    queue(value: ObservedComparison) {
      validateDestinationObservation(intent, r.handoff, observation.destination, value);
      for (const previous of snapshots) compareDestinationIdentities(previous, value.fresh);
    },
  };
}
function historyChecks(intent: ReturnIntent, observation: ArrivalHandoffDestinationReturn) {
  validateArrivalHandoffDestinationReturn(observation, intent); return retainedChecks(intent, observation);
}
type HistoryChecks = ReturnType<typeof historyChecks>;
function fields(value: HandoffDestinationEvent, checks: HistoryChecks) {
  checks.queue(value.queue); checks.destination(value.prepared);
  if (!admitted(value.queue.fresh) || !admitted(value.prepared) || !equal(stable(value.queue.fresh), stable(value.prepared))
    || !Array.isArray(value.observed_at) || value.observed_at.length !== 2 || value.observed_at.some(time => !stamp(time))
    || Date.parse(value.observed_at[0]) < Date.parse(value.queue.fresh.metadata.observed_at)
    || Date.parse(value.observed_at[1]) < Date.parse(value.observed_at[0]) || value.prepared.metadata.observed_at !== value.observed_at[1]) fail();
}
function shape(value: HandoffDestinationEvent) {
  if (!value || !equal(Object.keys(value).sort(), ['observation', 'observed_at', 'prepared', 'queue', 'recipe']) || value.recipe !== 'private-handoff-destination-event-v1') fail();
}
function verified(value: HandoffDestinationEvent, intent: ReturnIntent) {
  shape(value); const checks = historyChecks(intent, value.observation); fields(value, checks); return checks;
}
export function handoffDestinationEventAvailable(intent: ReturnIntent, observation: ArrivalHandoffDestinationReturn, value: ComparisonQueueReconciliation) {
  if (value.state !== 'observed') return false;
  historyChecks(intent, observation).queue(value); return admitted(value.fresh);
}
export function validateHandoffDestinationEvent(value: HandoffDestinationEvent, intent: ReturnIntent) { verified(value, intent); }
export async function prepareHandoffDestinationEvent(intent: ReturnIntent, observation: ArrivalHandoffDestinationReturn, value: ComparisonQueueReconciliation,
  read: (url: string) => Promise<ReviewLineage>, current: () => boolean): Promise<HandoffDestinationEvent> {
  const anchored = structuredClone(intent), retained = structuredClone(observation), queued = structuredClone(value);
  if (queued.state !== 'observed') fail();
  const checks = historyChecks(anchored, retained); checks.queue(queued); const initial = queued.fresh; if (!admitted(initial)) fail();
  const t = anchored.target, target: SourceTarget = { kind: 'selected', matter_id: t.matter_id, analysis_id: t.analysis_id, context_id: t.context_id, review_id: t.review_id! };
  verifyReturnedEventTarget(anchored, target);
  const url = `/matters/${encodeURIComponent(t.matter_id)}/analyses/${encodeURIComponent(t.analysis_id)}/source-contexts/${encodeURIComponent(t.context_id)}/reviews/${encodeURIComponent(t.review_id!)}/navigation-context?window=1`;
  async function observe() {
    if (!current()) fail(); const h = structuredClone(await read(url)); if (!current()) fail();
    verifyReviewLineage(h, target);
    const fresh = { metadata: h.context_navigation, selected: h.selected_review, head: h.current_head }; checks.destination(fresh);
    if (h.lineage.window !== 1 || !h.tools_available || !admitted(fresh) || !equal(stable(initial), stable(fresh))
      || Date.parse(h.observed_at) < Date.parse(initial.metadata.observed_at)) fail();
    return fresh;
  }
  const before = await observe(), after = await observe();
  const result: HandoffDestinationEvent = { recipe: 'private-handoff-destination-event-v1', observation: retained, queue: queued, prepared: after,
    observed_at: [before.metadata.observed_at, after.metadata.observed_at] };
  fields(result, checks); if (!current()) fail(); return structuredClone(result);
}
function destinationFields(handoff: HandoffDestinationEvent, fresh: ReviewPathDestination, checks: HistoryChecks) {
  checks.destination(fresh); compareDestinationIdentities(handoff.queue.fresh, fresh);
  return compareDestinationIdentities(handoff.prepared, fresh);
}
/** Complete validation afresh; no unchecked checker is exported. */
export function verifyHandoffDestinationEventArrival(intent: ReturnIntent, handoff: HandoffDestinationEvent, fresh: ReviewPathDestination) {
  return destinationFields(handoff, fresh, verified(handoff, intent));
}
function destination(intent: ReturnIntent, handoff: HandoffDestinationEvent, target: SourceTarget, history: ReviewLineage, checks: HistoryChecks) {
  verifyReturnedEventTarget(intent, target); verifyReviewLineage(history, target);
  const fresh = { metadata: history.context_navigation, selected: history.selected_review, head: history.current_head };
  return structuredClone({ fresh, ...destinationFields(handoff, fresh, checks) });
}
export function compareHandoffDestinationEvent(intent: ReturnIntent, handoff: HandoffDestinationEvent, target: SourceTarget, history: ReviewLineage) {
  return destination(intent, handoff, target, history, verified(handoff, intent));
}
/** Capture only the current verified view's metadata on explicit return. */
export function captureHandoffDestinationEventArrival(intent: ReturnIntent, handoff: HandoffDestinationEvent, target: SourceTarget, meta: NavigationMetadata | null, history: ReviewLineage | null) {
  if (target.kind !== 'selected') fail();
  const checks = verified(handoff, intent), next = returnVerifiedEvent(intent, target, meta, history);
  if (!meta && !history) return { intent: next, arrival: null };
  return { intent: next, arrival: destination(intent, handoff, target, history!, checks).fresh };
}
/** Existing return projection stays unchanged for callers of the original contract. */
export function returnHandoffDestinationEvent(intent: ReturnIntent, handoff: HandoffDestinationEvent, target: SourceTarget, meta: NavigationMetadata | null, history: ReviewLineage | null) {
  const next = captureHandoffDestinationEventArrival(intent, handoff, target, meta, history);
  return { intent: next.intent, observation: next.arrival ? structuredClone(handoff.observation) : null };
}
/** Reconcile original observations first; validate this purpose and saved arrival locally. */
export function reconcileHandoffDestinationEventArrival(intent: ReturnIntent, handoff: HandoffDestinationEvent, saved: ReviewPathDestination,
  page: PortfolioQueuePage, meta: NavigationMetadata | null, history: ReviewLineage | null, offset = 0): ComparisonQueueReconciliation {
  shape(handoff);
  const value = reconcileArrivalHandoffDestinationReturn(intent, handoff.observation, page, meta, history, offset);
  // Original reconciliation checked the complete retained history in this call.
  const checks = retainedChecks(intent, handoff.observation); fields(handoff, checks); destinationFields(handoff, saved, checks);
  if (Date.parse(page.observed_at) < Date.parse(saved.metadata.observed_at)) fail();
  if (value.state === 'not_observed') return value;
  destinationFields(handoff, value.fresh, checks);
  return structuredClone({ ...value, ...compareDestinationIdentities(saved, value.fresh) });
}
