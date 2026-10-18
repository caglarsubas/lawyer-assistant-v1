import type { PortfolioQueuePage } from '../pages/portfolioSourceQueueTypes';
import { canonicalJson } from '../pages/matter/sourceReviewTypes';
import type { NavigationMetadata, SourceTarget } from '../pages/sourceContextNavigationTypes';
import { verifyReviewLineage, type ReviewLineage } from '../pages/sourceReviewLineageTypes';
import { reconcileHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalReturn, validateHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalReturn, type HandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalReturn } from './handoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalReturn';
import { compareDestinationIdentities, validateDestinationObservation, type ComparisonQueueReconciliation, type ObservedComparison } from './comparisonReturn';
import type { ReturnIntent } from './portfolioReturn';
import { returnVerifiedEvent, verifyReturnedEventTarget } from './returnedReviewLineage';
import { verifyReviewPathDestination, type ReviewPathDestination } from './reviewPathHandoff';

/** One complete saved return and one new preparation; no recursive purpose or history window. */
export type HandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalEvent = { recipe: 'private-handoff-arrival-destination-arrival-destination-arrival-destination-arrival-destination-arrival-destination-arrival-destination-arrival-destination-arrival-destination-arrival-destination-arrival-destination-arrival-event-v1'; observation: HandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalReturn;
  queue: ObservedComparison; prepared: ReviewPathDestination; observed_at: [string, string] };
const equal = (a: unknown, b: unknown) => canonicalJson(a) === canonicalJson(b);
const stable = (v: ReviewPathDestination) => ({ ...v, metadata: { ...v.metadata, observed_at: null } });
const admitted = (v: ReviewPathDestination) => v.metadata.tools_available && v.metadata.analysis.current_version_id !== null
  && v.metadata.admission.context_state === 'complete' && v.metadata.admission.review_state === 'complete'
  && v.selected.integrity === 'verified' && v.selected.admission === 'complete' && v.head?.integrity === 'verified' && v.head.admission === 'complete';
const stamp = (v: unknown): v is string => typeof v === 'string' && v.length <= 40 && Number.isFinite(Date.parse(v));
function fail(): never { throw new Error('Tam varış zincirini koruyan tam karar geçişi doğrulanamadı. Yeni kuyruk gözlemi gerekli; başka kayıt veya önceki sonuç kullanılmadı.'); }
/** Parent validation occurs in this operation before these private checks are used. */
function retainedChecks(intent: ReturnIntent, observation: HandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalReturn) {
  const completeDestinationReturn = observation.handoff.observation;
  const priorCompleteArrival = completeDestinationReturn.handoff.observation;
  const priorCompleteDestination = priorCompleteArrival.handoff.observation;
  const savedArrival = priorCompleteDestination.handoff.observation;
  const savedDestination = savedArrival.handoff.observation;
  const originalCompleteArrival = savedDestination.handoff.observation;
  const originalDestination = originalCompleteArrival.handoff.observation;
  const originalArrival = originalDestination.handoff.observation;
  const wholeCompleteDestination = originalArrival.handoff.observation, wholeCompleteArrival = wholeCompleteDestination.handoff.observation, wholeDestination = wholeCompleteArrival.handoff.observation, wholeArrival = wholeDestination.handoff.observation, retainedDestination = wholeArrival.handoff.observation, retainedArrival = retainedDestination.handoff.observation, completeDestination = retainedArrival.handoff.observation, completeArrival = completeDestination.handoff.observation, destinationReturn = completeArrival.handoff.observation, savedReturn = destinationReturn.handoff.observation, parent = savedReturn.handoff.observation, newest = parent.handoff, carried = newest.observation, saved = carried.handoff.observation, purpose = saved.handoff;
  const arrival = purpose.observation, latest = arrival.handoff, d = latest.observation, h = d.handoff, c = h.observation;
  const o = c.handoff.observation, old = o.handoff.observation, r = old.handoff.receipt;
  const snapshots = [r.destination, old.arrival, o.handoff.queue.fresh, o.handoff.prepared, o.destination,
    c.handoff.queue.fresh, c.handoff.prepared, c.arrival, h.queue.fresh, h.prepared, d.destination,
    latest.queue.fresh, latest.prepared, arrival.arrival, purpose.queue.fresh, purpose.prepared, saved.destination,
    carried.handoff.queue.fresh, carried.handoff.prepared, carried.arrival, newest.queue.fresh, newest.prepared, parent.destination,
    savedReturn.handoff.queue.fresh, savedReturn.handoff.prepared, savedReturn.arrival,
    destinationReturn.handoff.queue.fresh, destinationReturn.handoff.prepared, destinationReturn.destination,
    completeArrival.handoff.queue.fresh, completeArrival.handoff.prepared, completeArrival.arrival,
    completeDestination.handoff.queue.fresh, completeDestination.handoff.prepared, completeDestination.destination,
    retainedArrival.handoff.queue.fresh, retainedArrival.handoff.prepared, retainedArrival.arrival,
    retainedDestination.handoff.queue.fresh, retainedDestination.handoff.prepared, retainedDestination.destination,
    wholeArrival.handoff.queue.fresh, wholeArrival.handoff.prepared, wholeArrival.arrival,
    wholeDestination.handoff.queue.fresh, wholeDestination.handoff.prepared, wholeDestination.destination,
    wholeCompleteArrival.handoff.queue.fresh, wholeCompleteArrival.handoff.prepared, wholeCompleteArrival.arrival,
    wholeCompleteDestination.handoff.queue.fresh, wholeCompleteDestination.handoff.prepared, wholeCompleteDestination.destination,
    originalArrival.handoff.queue.fresh, originalArrival.handoff.prepared, originalArrival.arrival,
    originalDestination.handoff.queue.fresh, originalDestination.handoff.prepared, originalDestination.destination,
    originalCompleteArrival.handoff.queue.fresh, originalCompleteArrival.handoff.prepared, originalCompleteArrival.arrival,
    savedDestination.handoff.queue.fresh, savedDestination.handoff.prepared, savedDestination.destination,
    savedArrival.handoff.queue.fresh, savedArrival.handoff.prepared, savedArrival.arrival,
    priorCompleteDestination.handoff.queue.fresh, priorCompleteDestination.handoff.prepared, priorCompleteDestination.destination,
    priorCompleteArrival.handoff.queue.fresh, priorCompleteArrival.handoff.prepared, priorCompleteArrival.arrival,
    completeDestinationReturn.handoff.queue.fresh, completeDestinationReturn.handoff.prepared, completeDestinationReturn.destination,
    observation.handoff.queue.fresh, observation.handoff.prepared, observation.arrival];
  return {
    destination(fresh: ReviewPathDestination) {
      verifyReviewPathDestination(intent, r.handoff, fresh);
      for (const previous of snapshots) compareDestinationIdentities(previous, fresh);
    },
    queue(value: ObservedComparison) {
      validateDestinationObservation(intent, r.handoff, observation.arrival, value);
      for (const previous of snapshots) compareDestinationIdentities(previous, value.fresh);
    },
  };
}
function historyChecks(intent: ReturnIntent, observation: HandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalReturn) {
  validateHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalReturn(observation, intent); return retainedChecks(intent, observation);
}
type HistoryChecks = ReturnType<typeof historyChecks>;
function fields(value: HandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalEvent, checks: HistoryChecks) {
  checks.queue(value.queue); checks.destination(value.prepared);
  if (!admitted(value.queue.fresh) || !admitted(value.prepared) || !equal(stable(value.queue.fresh), stable(value.prepared))
    || !Array.isArray(value.observed_at) || value.observed_at.length !== 2 || value.observed_at.some(time => !stamp(time))
    || Date.parse(value.observed_at[0]) < Date.parse(value.queue.fresh.metadata.observed_at)
    || Date.parse(value.observed_at[1]) < Date.parse(value.observed_at[0]) || value.prepared.metadata.observed_at !== value.observed_at[1]) fail();
}
function shape(value: HandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalEvent) {
  if (!value || !equal(Object.keys(value).sort(), ['observation', 'observed_at', 'prepared', 'queue', 'recipe']) || value.recipe !== 'private-handoff-arrival-destination-arrival-destination-arrival-destination-arrival-destination-arrival-destination-arrival-destination-arrival-destination-arrival-destination-arrival-destination-arrival-destination-arrival-event-v1') fail();
}
function verified(value: HandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalEvent, intent: ReturnIntent) {
  shape(value); const checks = historyChecks(intent, value.observation); fields(value, checks); return checks;
}
export function validateHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalEvent(value: HandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalEvent, intent: ReturnIntent) { verified(value, intent); }
export function handoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalEventAvailable(intent: ReturnIntent, observation: HandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalReturn, value: ComparisonQueueReconciliation) {
  const checks = historyChecks(intent, observation);
  if (value.state !== 'observed') return false;
  checks.queue(value); return admitted(value.fresh);
}
export async function prepareHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalEvent(intent: ReturnIntent, observation: HandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalReturn, value: ComparisonQueueReconciliation,
  read: (url: string) => Promise<ReviewLineage>, current: () => boolean): Promise<HandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalEvent> {
  const anchored = structuredClone(intent), retained = structuredClone(observation), queued = structuredClone(value);
  if (queued.state !== 'observed') fail();
  const checks = historyChecks(anchored, retained); checks.queue(queued); const initial = queued.fresh; if (!admitted(initial)) fail();
  const t = anchored.target, target: SourceTarget = { kind: 'selected', matter_id: t.matter_id, analysis_id: t.analysis_id, context_id: t.context_id, review_id: t.review_id! };
  verifyReturnedEventTarget(anchored, target);
  const url = `/matters/${encodeURIComponent(t.matter_id)}/analyses/${encodeURIComponent(t.analysis_id)}/source-contexts/${encodeURIComponent(t.context_id)}/reviews/${encodeURIComponent(t.review_id!)}/navigation-context?window=1`;
  async function observe() {
    if (!current()) fail(); const history = structuredClone(await read(url)); if (!current()) fail();
    verifyReviewLineage(history, target);
    const fresh = { metadata: history.context_navigation, selected: history.selected_review, head: history.current_head }; checks.destination(fresh);
    if (history.lineage.window !== 1 || !history.tools_available || !admitted(fresh) || !equal(stable(initial), stable(fresh))
      || Date.parse(history.observed_at) < Date.parse(initial.metadata.observed_at)) fail();
    return fresh;
  }
  const before = await observe(), after = await observe();
  const result: HandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalEvent = { recipe: 'private-handoff-arrival-destination-arrival-destination-arrival-destination-arrival-destination-arrival-destination-arrival-destination-arrival-destination-arrival-destination-arrival-destination-arrival-destination-arrival-event-v1', observation: retained, queue: queued, prepared: after,
    observed_at: [before.metadata.observed_at, after.metadata.observed_at] };
  fields(result, checks); if (!current()) fail(); return structuredClone(result);
}
function arrivalFields(handoff: HandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalEvent, fresh: ReviewPathDestination, checks: HistoryChecks) {
  checks.destination(fresh); compareDestinationIdentities(handoff.queue.fresh, fresh);
  return compareDestinationIdentities(handoff.prepared, fresh);
}
export function verifyHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalEventDestination(intent: ReturnIntent, handoff: HandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalEvent, fresh: ReviewPathDestination) {
  return arrivalFields(handoff, fresh, verified(handoff, intent));
}
function destination(intent: ReturnIntent, handoff: HandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalEvent, target: SourceTarget, history: ReviewLineage, checks: HistoryChecks) {
  if (target.kind !== 'selected') fail();
  verifyReturnedEventTarget(intent, target); verifyReviewLineage(history, target);
  const fresh = { metadata: history.context_navigation, selected: history.selected_review, head: history.current_head };
  return structuredClone({ fresh, ...arrivalFields(handoff, fresh, checks) });
}
export function compareHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalEvent(intent: ReturnIntent, handoff: HandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalEvent, target: SourceTarget, history: ReviewLineage) {
  return destination(intent, handoff, target, history, verified(handoff, intent));
}
/** Capture only currently verified metadata on explicit return, without reads or writes. */
export function captureHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalEventDestination(intent: ReturnIntent, handoff: HandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalEvent, target: SourceTarget,
  meta: NavigationMetadata | null, history: ReviewLineage | null) {
  if (target.kind !== 'selected') fail();
  const checks = verified(handoff, intent), next = returnVerifiedEvent(intent, target, meta, history);
  if (!meta && !history) return { intent: next, destination: null };
  return { intent: next, destination: destination(intent, handoff, target, history!, checks).fresh };
}
/** Explicit verified return restores all 80 original observations; no further arrival is captured. */
export function returnHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalEvent(intent: ReturnIntent, handoff: HandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalEvent, target: SourceTarget,
  meta: NavigationMetadata | null, history: ReviewLineage | null) {
  if (target.kind !== 'selected') fail();
  const checks = verified(handoff, intent), next = returnVerifiedEvent(intent, target, meta, history);
  if (!meta && !history) return { intent: next, observation: null };
  destination(intent, handoff, target, history!, checks);
  return { intent: next, observation: structuredClone(handoff.observation) };
}

/** Reconcile complete parent history first, then this purpose and separate destination locally. */
export function reconcileHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalEventDestination(intent: ReturnIntent, handoff: HandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalEvent, saved: ReviewPathDestination,
  page: PortfolioQueuePage, meta: NavigationMetadata | null, history: ReviewLineage | null, offset = 0): ComparisonQueueReconciliation {
  shape(handoff);
  const value = reconcileHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalReturn(intent, handoff.observation, page, meta, history, offset);
  // Complete parent history was validated in this call; no verdict survives it.
  const checks = retainedChecks(intent, handoff.observation); fields(handoff, checks); arrivalFields(handoff, saved, checks);
  if (Date.parse(page.observed_at) < Date.parse(saved.metadata.observed_at)) fail();
  if (value.state === 'not_observed') return value;
  arrivalFields(handoff, value.fresh, checks);
  return structuredClone({ ...value, ...compareDestinationIdentities(saved, value.fresh) });
}
