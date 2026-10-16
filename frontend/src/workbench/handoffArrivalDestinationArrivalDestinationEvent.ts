import { canonicalJson } from '../pages/matter/sourceReviewTypes';
import type { NavigationMetadata, SourceTarget } from '../pages/sourceContextNavigationTypes';
import { verifyReviewLineage, type ReviewLineage } from '../pages/sourceReviewLineageTypes';
import { validateHandoffArrivalDestinationArrivalDestinationReturn, type HandoffArrivalDestinationArrivalDestinationReturn } from './handoffArrivalDestinationArrivalDestinationReturn';
import { compareDestinationIdentities, validateDestinationObservation, type ComparisonQueueReconciliation, type ObservedComparison } from './comparisonReturn';
import type { ReturnIntent } from './portfolioReturn';
import { returnVerifiedEvent, verifyReturnedEventTarget } from './returnedReviewLineage';
import { verifyReviewPathDestination, type ReviewPathDestination } from './reviewPathHandoff';

/** One complete saved return and one new preparation; no recursive purpose or history window. */
export type HandoffArrivalDestinationArrivalDestinationEvent = { recipe: 'private-handoff-arrival-destination-arrival-destination-event-v1'; observation: HandoffArrivalDestinationArrivalDestinationReturn;
  queue: ObservedComparison; prepared: ReviewPathDestination; observed_at: [string, string] };
const equal = (a: unknown, b: unknown) => canonicalJson(a) === canonicalJson(b);
const stable = (v: ReviewPathDestination) => ({ ...v, metadata: { ...v.metadata, observed_at: null } });
const admitted = (v: ReviewPathDestination) => v.metadata.tools_available && v.metadata.analysis.current_version_id !== null
  && v.metadata.admission.context_state === 'complete' && v.metadata.admission.review_state === 'complete'
  && v.selected.integrity === 'verified' && v.selected.admission === 'complete' && v.head?.integrity === 'verified' && v.head.admission === 'complete';
const stamp = (v: unknown): v is string => typeof v === 'string' && v.length <= 40 && Number.isFinite(Date.parse(v));
function fail(): never { throw new Error('Varışı koruyan geçiş hedefini koruyan tam karar geçişi doğrulanamadı. Yeni kuyruk gözlemi gerekli; başka kayıt veya önceki sonuç kullanılmadı.'); }
/** Parent validation occurs in this operation before these private checks are used. */
function retainedChecks(intent: ReturnIntent, observation: HandoffArrivalDestinationArrivalDestinationReturn) {
  const savedReturn = observation.handoff.observation, parent = savedReturn.handoff.observation, newest = parent.handoff, carried = newest.observation, saved = carried.handoff.observation, purpose = saved.handoff;
  const arrival = purpose.observation, latest = arrival.handoff, d = latest.observation, h = d.handoff, c = h.observation;
  const o = c.handoff.observation, old = o.handoff.observation, r = old.handoff.receipt;
  const snapshots = [r.destination, old.arrival, o.handoff.queue.fresh, o.handoff.prepared, o.destination,
    c.handoff.queue.fresh, c.handoff.prepared, c.arrival, h.queue.fresh, h.prepared, d.destination,
    latest.queue.fresh, latest.prepared, arrival.arrival, purpose.queue.fresh, purpose.prepared, saved.destination,
    carried.handoff.queue.fresh, carried.handoff.prepared, carried.arrival, newest.queue.fresh, newest.prepared, parent.destination,
    savedReturn.handoff.queue.fresh, savedReturn.handoff.prepared, savedReturn.arrival,
    observation.handoff.queue.fresh, observation.handoff.prepared, observation.destination];
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
function historyChecks(intent: ReturnIntent, observation: HandoffArrivalDestinationArrivalDestinationReturn) {
  validateHandoffArrivalDestinationArrivalDestinationReturn(observation, intent); return retainedChecks(intent, observation);
}
type HistoryChecks = ReturnType<typeof historyChecks>;
function fields(value: HandoffArrivalDestinationArrivalDestinationEvent, checks: HistoryChecks) {
  checks.queue(value.queue); checks.destination(value.prepared);
  if (!admitted(value.queue.fresh) || !admitted(value.prepared) || !equal(stable(value.queue.fresh), stable(value.prepared))
    || !Array.isArray(value.observed_at) || value.observed_at.length !== 2 || value.observed_at.some(time => !stamp(time))
    || Date.parse(value.observed_at[0]) < Date.parse(value.queue.fresh.metadata.observed_at)
    || Date.parse(value.observed_at[1]) < Date.parse(value.observed_at[0]) || value.prepared.metadata.observed_at !== value.observed_at[1]) fail();
}
function shape(value: HandoffArrivalDestinationArrivalDestinationEvent) {
  if (!value || !equal(Object.keys(value).sort(), ['observation', 'observed_at', 'prepared', 'queue', 'recipe']) || value.recipe !== 'private-handoff-arrival-destination-arrival-destination-event-v1') fail();
}
function verified(value: HandoffArrivalDestinationArrivalDestinationEvent, intent: ReturnIntent) {
  shape(value); const checks = historyChecks(intent, value.observation); fields(value, checks); return checks;
}
export function validateHandoffArrivalDestinationArrivalDestinationEvent(value: HandoffArrivalDestinationArrivalDestinationEvent, intent: ReturnIntent) { verified(value, intent); }
export function handoffArrivalDestinationArrivalDestinationEventAvailable(intent: ReturnIntent, observation: HandoffArrivalDestinationArrivalDestinationReturn, value: ComparisonQueueReconciliation) {
  const checks = historyChecks(intent, observation);
  if (value.state !== 'observed') return false;
  checks.queue(value); return admitted(value.fresh);
}
export async function prepareHandoffArrivalDestinationArrivalDestinationEvent(intent: ReturnIntent, observation: HandoffArrivalDestinationArrivalDestinationReturn, value: ComparisonQueueReconciliation,
  read: (url: string) => Promise<ReviewLineage>, current: () => boolean): Promise<HandoffArrivalDestinationArrivalDestinationEvent> {
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
  const result: HandoffArrivalDestinationArrivalDestinationEvent = { recipe: 'private-handoff-arrival-destination-arrival-destination-event-v1', observation: retained, queue: queued, prepared: after,
    observed_at: [before.metadata.observed_at, after.metadata.observed_at] };
  fields(result, checks); if (!current()) fail(); return structuredClone(result);
}
function arrivalFields(handoff: HandoffArrivalDestinationArrivalDestinationEvent, fresh: ReviewPathDestination, checks: HistoryChecks) {
  checks.destination(fresh); compareDestinationIdentities(handoff.queue.fresh, fresh);
  return compareDestinationIdentities(handoff.prepared, fresh);
}
function destination(intent: ReturnIntent, handoff: HandoffArrivalDestinationArrivalDestinationEvent, target: SourceTarget, history: ReviewLineage, checks: HistoryChecks) {
  if (target.kind !== 'selected') fail();
  verifyReturnedEventTarget(intent, target); verifyReviewLineage(history, target);
  const fresh = { metadata: history.context_navigation, selected: history.selected_review, head: history.current_head };
  return structuredClone({ fresh, ...arrivalFields(handoff, fresh, checks) });
}
export function compareHandoffArrivalDestinationArrivalDestinationEvent(intent: ReturnIntent, handoff: HandoffArrivalDestinationArrivalDestinationEvent, target: SourceTarget, history: ReviewLineage) {
  return destination(intent, handoff, target, history, verified(handoff, intent));
}
/** Explicit verified return restores the complete original return without another capture. */
export function returnHandoffArrivalDestinationArrivalDestinationEvent(intent: ReturnIntent, handoff: HandoffArrivalDestinationArrivalDestinationEvent, target: SourceTarget,
  meta: NavigationMetadata | null, history: ReviewLineage | null) {
  if (target.kind !== 'selected') fail();
  const checks = verified(handoff, intent), next = returnVerifiedEvent(intent, target, meta, history);
  if (!meta && !history) return { intent: next, observation: null };
  destination(intent, handoff, target, history!, checks);
  return { intent: next, observation: structuredClone(handoff.observation) };
}
