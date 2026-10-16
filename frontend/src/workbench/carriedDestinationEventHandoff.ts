import { canonicalJson } from '../pages/matter/sourceReviewTypes';
import type { NavigationMetadata, SourceTarget } from '../pages/sourceContextNavigationTypes';
import { verifyReviewLineage, type ReviewLineage } from '../pages/sourceReviewLineageTypes';
import { validateCarriedDestinationReturn, type CarriedDestinationReturn } from './carriedDestinationReturn';
import { compareDestinationIdentities, validateDestinationObservation, type ComparisonQueueReconciliation, type ObservedComparison } from './comparisonReturn';
import type { ReturnIntent } from './portfolioReturn';
import { returnVerifiedEvent, verifyReturnedEventTarget } from './returnedReviewLineage';
import { verifyReviewPathDestination, type ReviewPathDestination } from './reviewPathHandoff';

/** Fixed-depth purpose contract; carries one original carried destination, never another purpose handoff. */
export type CarriedDestinationEventHandoff = { recipe: 'private-carried-destination-event-handoff-v1'; observation: CarriedDestinationReturn;
  queue: ObservedComparison; prepared: ReviewPathDestination; observed_at: [string, string] };
const equal = (a: unknown, b: unknown) => canonicalJson(a) === canonicalJson(b);
const stable = (v: ReviewPathDestination) => ({ ...v, metadata: { ...v.metadata, observed_at: null } });
const admitted = (v: ReviewPathDestination) => v.metadata.tools_available && v.metadata.analysis.current_version_id !== null
  && v.metadata.admission.context_state === 'complete' && v.metadata.admission.review_state === 'complete'
  && v.selected.integrity === 'verified' && v.selected.admission === 'complete' && v.head?.integrity === 'verified' && v.head.admission === 'complete';
function fail(): never { throw new Error('Taşınan hedefi koruyan tam karar geçişi doğrulanamadı. Yeni kuyruk gözlemi gerekli; başka kayıt veya önceki sonuç kullanılmadı.'); }
const stamp = (v: unknown): v is string => typeof v === 'string' && v.length <= 40 && Number.isFinite(Date.parse(v));
/** Local to one operation; no verdict or checker survives across public calls. */
function retainedChecks(intent: ReturnIntent, observation: CarriedDestinationReturn) {
  const h = observation.handoff, c = h.observation;
  const o = c.handoff.observation, old = o.handoff.observation, r = old.handoff.receipt;
  const snapshots = [r.destination, old.arrival, o.handoff.queue.fresh, o.handoff.prepared, o.destination,
    c.handoff.queue.fresh, c.handoff.prepared, c.arrival, h.queue.fresh, h.prepared, observation.destination];
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
function historyChecks(intent: ReturnIntent, observation: CarriedDestinationReturn) {
  validateCarriedDestinationReturn(observation, intent); return retainedChecks(intent, observation);
}
type HistoryChecks = ReturnType<typeof historyChecks>;
function handoffFields(value: CarriedDestinationEventHandoff, checks: HistoryChecks) {
  checks.queue(value.queue); checks.destination(value.prepared);
  if (!admitted(value.queue.fresh) || !admitted(value.prepared) || !equal(stable(value.queue.fresh), stable(value.prepared))
    || !Array.isArray(value.observed_at) || value.observed_at.length !== 2 || value.observed_at.some(time => !stamp(time))
    || Date.parse(value.observed_at[0]) < Date.parse(value.queue.fresh.metadata.observed_at)
    || Date.parse(value.observed_at[1]) < Date.parse(value.observed_at[0]) || value.prepared.metadata.observed_at !== value.observed_at[1]) fail();
}
function handoffShape(value: CarriedDestinationEventHandoff) {
  if (!value || !equal(Object.keys(value).sort(), ['observation', 'observed_at', 'prepared', 'queue', 'recipe']) || value.recipe !== 'private-carried-destination-event-handoff-v1') fail();
}
function verifiedHandoff(value: CarriedDestinationEventHandoff, intent: ReturnIntent) {
  handoffShape(value); const checks = historyChecks(intent, value.observation); handoffFields(value, checks); return checks;
}
export function carriedDestinationEventAvailable(intent: ReturnIntent, observation: CarriedDestinationReturn, value: ComparisonQueueReconciliation) {
  if (value.state !== 'observed') return false;
  historyChecks(intent, observation).queue(value); return admitted(value.fresh);
}
export function validateCarriedDestinationEventHandoff(value: CarriedDestinationEventHandoff, intent: ReturnIntent) { verifiedHandoff(value, intent); }
export async function prepareCarriedDestinationEvent(intent: ReturnIntent, observation: CarriedDestinationReturn, value: ComparisonQueueReconciliation,
  read: (url: string) => Promise<ReviewLineage>, current: () => boolean): Promise<CarriedDestinationEventHandoff> {
  // Awaited reads cannot mutate the original filter/history baseline through shared references.
  const anchored = structuredClone(intent), retained = structuredClone(observation), queued = structuredClone(value);
  if (queued.state !== 'observed') fail();
  const checks = historyChecks(anchored, retained); checks.queue(queued); const initialFresh = queued.fresh; if (!admitted(initialFresh)) fail();
  const t = anchored.target;
  const target: SourceTarget = { kind: 'selected', matter_id: t.matter_id, analysis_id: t.analysis_id, context_id: t.context_id, review_id: t.review_id! };
  verifyReturnedEventTarget(anchored, target);
  const url = `/matters/${encodeURIComponent(t.matter_id)}/analyses/${encodeURIComponent(t.analysis_id)}/source-contexts/${encodeURIComponent(t.context_id)}/reviews/${encodeURIComponent(t.review_id!)}/navigation-context?window=1`;
  async function observe() {
    if (!current()) fail(); const h = structuredClone(await read(url)); if (!current()) fail();
    verifyReviewLineage(h, target);
    const fresh = { metadata: h.context_navigation, selected: h.selected_review, head: h.current_head };
    checks.destination(fresh);
    if (h.lineage.window !== 1 || !h.tools_available || !admitted(fresh) || !equal(stable(initialFresh), stable(fresh))
      || Date.parse(h.observed_at) < Date.parse(initialFresh.metadata.observed_at)) fail();
    return fresh;
  }
  const before = await observe(), after = await observe();
  const result: CarriedDestinationEventHandoff = { recipe: 'private-carried-destination-event-handoff-v1', observation: retained, queue: queued, prepared: after,
    observed_at: [before.metadata.observed_at, after.metadata.observed_at] };
  handoffFields(result, checks); if (!current()) fail(); return structuredClone(result);
}
function destinationFields(handoff: CarriedDestinationEventHandoff, fresh: ReviewPathDestination, checks: HistoryChecks) {
  checks.destination(fresh); compareDestinationIdentities(handoff.queue.fresh, fresh);
  return compareDestinationIdentities(handoff.prepared, fresh);
}
function destination(intent: ReturnIntent, handoff: CarriedDestinationEventHandoff, target: SourceTarget, history: ReviewLineage, checks: HistoryChecks) {
  verifyReturnedEventTarget(intent, target); verifyReviewLineage(history, target);
  const fresh = { metadata: history.context_navigation, selected: history.selected_review, head: history.current_head };
  return structuredClone({ fresh, ...destinationFields(handoff, fresh, checks) });
}
export function compareCarriedDestinationEventDestination(intent: ReturnIntent, handoff: CarriedDestinationEventHandoff, target: SourceTarget, history: ReviewLineage) {
  return destination(intent, handoff, target, history, verifiedHandoff(handoff, intent));
}
/** A verified return restores the original observation, never captures or nests a new arrival. */
export function returnCarriedDestinationEvent(intent: ReturnIntent, handoff: CarriedDestinationEventHandoff, target: SourceTarget, meta: NavigationMetadata | null, history: ReviewLineage | null) {
  const checks = verifiedHandoff(handoff, intent), next = returnVerifiedEvent(intent, target, meta, history);
  if (!meta && !history) return { intent: next, observation: null };
  destination(intent, handoff, target, history!, checks);
  return { intent: next, observation: structuredClone(handoff.observation) };
}
