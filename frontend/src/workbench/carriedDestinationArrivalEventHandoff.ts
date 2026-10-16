import { canonicalJson } from '../pages/matter/sourceReviewTypes';
import type { PortfolioQueuePage } from '../pages/portfolioSourceQueueTypes';
import type { NavigationMetadata, SourceTarget } from '../pages/sourceContextNavigationTypes';
import { verifyReviewLineage, type ReviewLineage } from '../pages/sourceReviewLineageTypes';
import { reconcileCarriedDestinationArrivalReturn, validateCarriedDestinationArrivalReturn, type CarriedDestinationArrivalReturn } from './carriedDestinationArrivalReturn';
import { compareDestinationIdentities, validateDestinationObservation, type ComparisonQueueReconciliation, type ObservedComparison } from './comparisonReturn';
import type { ReturnIntent } from './portfolioReturn';
import { returnVerifiedEvent, verifyReturnedEventTarget } from './returnedReviewLineage';
import { verifyReviewPathDestination, type ReviewPathDestination } from './reviewPathHandoff';

/** Fixed-depth purpose contract; carries one original destination arrival, never another purpose handoff. */
export type CarriedDestinationArrivalEventHandoff = { recipe: 'private-carried-destination-arrival-event-handoff-v1'; observation: CarriedDestinationArrivalReturn;
  queue: ObservedComparison; prepared: ReviewPathDestination; observed_at: [string, string] };
const equal = (a: unknown, b: unknown) => canonicalJson(a) === canonicalJson(b);
const stable = (v: ReviewPathDestination) => ({ ...v, metadata: { ...v.metadata, observed_at: null } });
const admitted = (v: ReviewPathDestination) => v.metadata.tools_available && v.metadata.analysis.current_version_id !== null
  && v.metadata.admission.context_state === 'complete' && v.metadata.admission.review_state === 'complete'
  && v.selected.integrity === 'verified' && v.selected.admission === 'complete' && v.head?.integrity === 'verified' && v.head.admission === 'complete';
function fail(): never { throw new Error('Hedef varışını koruyan tam karar geçişi doğrulanamadı. Yeni kuyruk gözlemi gerekli; başka kayıt veya önceki sonuç kullanılmadı.'); }
const stamp = (v: unknown): v is string => typeof v === 'string' && v.length <= 40 && Number.isFinite(Date.parse(v));
/** Local to one operation; no verdict or checker survives across public calls. */
function retainedChecks(intent: ReturnIntent, observation: CarriedDestinationArrivalReturn) {
  const latest = observation.handoff, d = latest.observation, h = d.handoff, c = h.observation;
  const o = c.handoff.observation, old = o.handoff.observation, r = old.handoff.receipt;
  const snapshots = [r.destination, old.arrival, o.handoff.queue.fresh, o.handoff.prepared, o.destination,
    c.handoff.queue.fresh, c.handoff.prepared, c.arrival, h.queue.fresh, h.prepared, d.destination,
    latest.queue.fresh, latest.prepared, observation.arrival];
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
function historyChecks(intent: ReturnIntent, observation: CarriedDestinationArrivalReturn) {
  validateCarriedDestinationArrivalReturn(observation, intent); return retainedChecks(intent, observation);
}
type HistoryChecks = ReturnType<typeof historyChecks>;
function handoffFields(value: CarriedDestinationArrivalEventHandoff, checks: HistoryChecks) {
  checks.queue(value.queue); checks.destination(value.prepared);
  if (!admitted(value.queue.fresh) || !admitted(value.prepared) || !equal(stable(value.queue.fresh), stable(value.prepared))
    || !Array.isArray(value.observed_at) || value.observed_at.length !== 2 || value.observed_at.some(time => !stamp(time))
    || Date.parse(value.observed_at[0]) < Date.parse(value.queue.fresh.metadata.observed_at)
    || Date.parse(value.observed_at[1]) < Date.parse(value.observed_at[0]) || value.prepared.metadata.observed_at !== value.observed_at[1]) fail();
}
function handoffShape(value: CarriedDestinationArrivalEventHandoff) {
  if (!value || !equal(Object.keys(value).sort(), ['observation', 'observed_at', 'prepared', 'queue', 'recipe']) || value.recipe !== 'private-carried-destination-arrival-event-handoff-v1') fail();
}
function verifiedHandoff(value: CarriedDestinationArrivalEventHandoff, intent: ReturnIntent) {
  handoffShape(value); const checks = historyChecks(intent, value.observation); handoffFields(value, checks); return checks;
}
export function carriedDestinationArrivalEventAvailable(intent: ReturnIntent, observation: CarriedDestinationArrivalReturn, value: ComparisonQueueReconciliation) {
  if (value.state !== 'observed') return false;
  historyChecks(intent, observation).queue(value); return admitted(value.fresh);
}
export function validateCarriedDestinationArrivalEventHandoff(value: CarriedDestinationArrivalEventHandoff, intent: ReturnIntent) { verifiedHandoff(value, intent); }
export async function prepareCarriedDestinationArrivalEvent(intent: ReturnIntent, observation: CarriedDestinationArrivalReturn, value: ComparisonQueueReconciliation,
  read: (url: string) => Promise<ReviewLineage>, current: () => boolean): Promise<CarriedDestinationArrivalEventHandoff> {
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
  const result: CarriedDestinationArrivalEventHandoff = { recipe: 'private-carried-destination-arrival-event-handoff-v1', observation: retained, queue: queued, prepared: after,
    observed_at: [before.metadata.observed_at, after.metadata.observed_at] };
  handoffFields(result, checks); if (!current()) fail(); return structuredClone(result);
}
function destinationFields(handoff: CarriedDestinationArrivalEventHandoff, fresh: ReviewPathDestination, checks: HistoryChecks) {
  checks.destination(fresh); compareDestinationIdentities(handoff.queue.fresh, fresh);
  return compareDestinationIdentities(handoff.prepared, fresh);
}
/** Stateless reduced-destination validation; the complete history is checked afresh per call. */
export function verifyCarriedDestinationArrivalEventDestination(intent: ReturnIntent, handoff: CarriedDestinationArrivalEventHandoff, fresh: ReviewPathDestination) {
  return destinationFields(handoff, fresh, verifiedHandoff(handoff, intent));
}
function destination(intent: ReturnIntent, handoff: CarriedDestinationArrivalEventHandoff, target: SourceTarget, history: ReviewLineage, checks: HistoryChecks) {
  verifyReturnedEventTarget(intent, target); verifyReviewLineage(history, target);
  const fresh = { metadata: history.context_navigation, selected: history.selected_review, head: history.current_head };
  return structuredClone({ fresh, ...destinationFields(handoff, fresh, checks) });
}
export function compareCarriedDestinationArrivalEventDestination(intent: ReturnIntent, handoff: CarriedDestinationArrivalEventHandoff, target: SourceTarget, history: ReviewLineage) {
  return destination(intent, handoff, target, history, verifiedHandoff(handoff, intent));
}
/** Capture only metadata already verified in this view. No data request or write. */
export function captureCarriedDestinationArrivalEventReturn(intent: ReturnIntent, handoff: CarriedDestinationArrivalEventHandoff, target: SourceTarget, meta: NavigationMetadata | null, history: ReviewLineage | null) {
  const checks = verifiedHandoff(handoff, intent), next = returnVerifiedEvent(intent, target, meta, history);
  if (!meta && !history) return { intent: next, destination: null };
  return { intent: next, destination: destination(intent, handoff, target, history!, checks).fresh };
}
/** Original return projection remains unchanged for existing callers. */
export function returnCarriedDestinationArrivalEvent(intent: ReturnIntent, handoff: CarriedDestinationArrivalEventHandoff, target: SourceTarget, meta: NavigationMetadata | null, history: ReviewLineage | null) {
  const next = captureCarriedDestinationArrivalEventReturn(intent, handoff, target, meta, history);
  return { intent: next.intent, observation: next.destination ? structuredClone(handoff.observation) : null };
}
/** Reuse the original reconciliation, then check all additional pins within this operation. */
export function reconcileCarriedDestinationArrivalEventDestination(intent: ReturnIntent, handoff: CarriedDestinationArrivalEventHandoff, saved: ReviewPathDestination,
  page: PortfolioQueuePage, meta: NavigationMetadata | null, history: ReviewLineage | null, offset = 0): ComparisonQueueReconciliation {
  handoffShape(handoff);
  // This existing reconciliation performs the complete retained-history validation.
  // Private checks below add this purpose and destination; no verdict crosses calls.
  const value = reconcileCarriedDestinationArrivalReturn(intent, handoff.observation, page, meta, history, offset);
  const checks = retainedChecks(intent, handoff.observation); handoffFields(handoff, checks); destinationFields(handoff, saved, checks);
  if (Date.parse(page.observed_at) < Date.parse(saved.metadata.observed_at)) fail();
  if (value.state === 'not_observed') return value;
  destinationFields(handoff, value.fresh, checks);
  return structuredClone({ ...value, ...compareDestinationIdentities(saved, value.fresh) });
}
