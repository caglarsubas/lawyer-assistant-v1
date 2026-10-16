import { canonicalJson } from '../pages/matter/sourceReviewTypes';
import type { PortfolioQueuePage } from '../pages/portfolioSourceQueueTypes';
import type { NavigationMetadata, SourceTarget } from '../pages/sourceContextNavigationTypes';
import type { ReviewLineage } from '../pages/sourceReviewLineageTypes';
import { compareCarriedDestinationEventDestination, returnCarriedDestinationEvent, validateCarriedDestinationEventHandoff, type CarriedDestinationEventHandoff } from './carriedDestinationEventHandoff';
import { reconcileCarriedDestinationReturn, verifyCarriedDestinationDestination } from './carriedDestinationReturn';
import { compareDestinationIdentities, validateDestinationObservation, type ObservedComparison, type ComparisonQueueReconciliation } from './comparisonReturn';
import type { ReturnIntent } from './portfolioReturn';
import { verifyReviewPathDestination, type ReviewPathDestination } from './reviewPathHandoff';

/** A separate fixed-depth arrival; original carried destination and all preparations stay unchanged. */
export type CarriedDestinationArrivalReturn = { recipe: 'private-carried-destination-arrival-return-v1'; handoff: CarriedDestinationEventHandoff; arrival: ReviewPathDestination };
function fail(): never { throw new Error('Hedef varışının dönüş veya yeni kuyruk bağı doğrulanamadı. Yeni gözlem gerekli; önceki sonuç kullanılmadı.'); }
export function validateCarriedDestinationArrivalReturn(value: CarriedDestinationArrivalReturn, intent: ReturnIntent) {
  if (!value || canonicalJson(Object.keys(value).sort()) !== canonicalJson(['arrival', 'handoff', 'recipe']) || value.recipe !== 'private-carried-destination-arrival-return-v1') fail();
  validateCarriedDestinationEventHandoff(value.handoff, intent);
  verifyCarriedDestinationDestination(intent, value.handoff.observation, value.arrival);
  compareDestinationIdentities(value.handoff.prepared, value.arrival);
}
export function captureCarriedDestinationArrivalReturn(intent: ReturnIntent, handoff: CarriedDestinationEventHandoff, target: SourceTarget,
  meta: NavigationMetadata | null, history: ReviewLineage | null): { intent: ReturnIntent; observation: CarriedDestinationArrivalReturn | null } {
  const next = returnCarriedDestinationEvent(intent, handoff, target, meta, history);
  if (!next.observation) return { intent: next.intent, observation: null };
  const observation: CarriedDestinationArrivalReturn = { recipe: 'private-carried-destination-arrival-return-v1', handoff: structuredClone(handoff),
    arrival: compareCarriedDestinationEventDestination(intent, handoff, target, history!).fresh };
  validateCarriedDestinationArrivalReturn(observation, next.intent); return { intent: next.intent, observation: structuredClone(observation) };
}
/** Reuses the authorized bounded queue and exact-event GET; never scans or reads bodies. */
export function reconcileCarriedDestinationArrivalReturn(intent: ReturnIntent, observation: CarriedDestinationArrivalReturn, page: PortfolioQueuePage,
  meta: NavigationMetadata | null, history: ReviewLineage | null, offset = 0): ComparisonQueueReconciliation {
  validateCarriedDestinationArrivalReturn(observation, intent);
  if (!Number.isFinite(Date.parse(page.observed_at)) || Date.parse(page.observed_at) < Date.parse(observation.arrival.metadata.observed_at)) fail();
  const value = reconcileCarriedDestinationReturn(intent, observation.handoff.observation, page, meta, history, offset);
  if (value.state === 'not_observed') return value;
  compareDestinationIdentities(observation.handoff.prepared, value.fresh);
  return structuredClone({ ...value, ...compareDestinationIdentities(observation.arrival, value.fresh) });
}

/** A fixed inventory of already-validated historical observations, never a recursive traversal. */
function arrivalHistory(observation: CarriedDestinationArrivalReturn) {
  const latest = observation.handoff, d = latest.observation, h = d.handoff, c = h.observation;
  const o = c.handoff.observation, old = o.handoff.observation, r = old.handoff.receipt;
  return { root: r.handoff, snapshots: [r.destination, old.arrival, o.handoff.queue.fresh, o.handoff.prepared, o.destination,
    c.handoff.queue.fresh, c.handoff.prepared, c.arrival, h.queue.fresh, h.prepared, d.destination,
    latest.queue.fresh, latest.prepared, observation.arrival] };
}
/** Validate history once per call, then compare every retained pin with this fresh observation. */
export function verifyCarriedDestinationArrivalDestination(intent: ReturnIntent, observation: CarriedDestinationArrivalReturn, fresh: ReviewPathDestination) {
  validateCarriedDestinationArrivalReturn(observation, intent);
  const { root, snapshots } = arrivalHistory(observation);
  verifyReviewPathDestination(intent, root, fresh);
  for (const previous of snapshots) compareDestinationIdentities(previous, fresh);
  return compareDestinationIdentities(observation.arrival, fresh);
}
export function validateCarriedDestinationArrivalObservation(intent: ReturnIntent, observation: CarriedDestinationArrivalReturn, value: ObservedComparison) {
  validateCarriedDestinationArrivalReturn(observation, intent);
  const { root, snapshots } = arrivalHistory(observation);
  validateDestinationObservation(intent, root, observation.arrival, value);
  for (const previous of snapshots) compareDestinationIdentities(previous, value.fresh);
}
