import { canonicalJson } from '../pages/matter/sourceReviewTypes';
import type { PortfolioQueuePage } from '../pages/portfolioSourceQueueTypes';
import type { NavigationMetadata, SourceTarget } from '../pages/sourceContextNavigationTypes';
import type { ReviewLineage } from '../pages/sourceReviewLineageTypes';
import { compareOnwardEventDestination, returnOnwardEvent, validateOnwardEventHandoff, type OnwardEventHandoff } from './onwardEventHandoff';
import { reconcileOnwardReturn, verifyOnwardDestination } from './onwardReturn';
import { compareDestinationIdentities, validateDestinationObservation, type ComparisonQueueReconciliation, type ObservedComparison } from './comparisonReturn';
import type { ReturnIntent } from './portfolioReturn';
import type { ReviewPathDestination } from './reviewPathHandoff';

/** A separate fixed-depth arrival; no original return or preparation is rebased. */
export type CarriedArrivalReturn = { recipe: 'private-carried-arrival-return-v1'; handoff: OnwardEventHandoff; arrival: ReviewPathDestination };
function fail(): never { throw new Error('Taşınan varışın dönüş veya yeni kuyruk bağı doğrulanamadı. Yeni gözlem gerekli; önceki sonuç kullanılmadı.'); }
export function validateCarriedArrivalReturn(value: CarriedArrivalReturn, intent: ReturnIntent) {
  if (!value || canonicalJson(Object.keys(value).sort()) !== canonicalJson(['arrival', 'handoff', 'recipe']) || value.recipe !== 'private-carried-arrival-return-v1') fail();
  validateOnwardEventHandoff(value.handoff, intent);
  verifyOnwardDestination(intent, value.handoff.observation, value.arrival);
  compareDestinationIdentities(value.handoff.prepared, value.arrival);
}
export function captureCarriedArrivalReturn(intent: ReturnIntent, handoff: OnwardEventHandoff, target: SourceTarget,
  meta: NavigationMetadata | null, history: ReviewLineage | null): { intent: ReturnIntent; observation: CarriedArrivalReturn | null } {
  const next = returnOnwardEvent(intent, handoff, target, meta, history);
  if (!next.observation) return { intent: next.intent, observation: null };
  const observation: CarriedArrivalReturn = { recipe: 'private-carried-arrival-return-v1', handoff: structuredClone(handoff),
    arrival: compareOnwardEventDestination(intent, handoff, target, history!).fresh };
  validateCarriedArrivalReturn(observation, next.intent); return { intent: next.intent, observation: structuredClone(observation) };
}
/** Reuses the authorized bounded queue and exact-event GET; never scans or reads bodies. */
export function reconcileCarriedArrivalReturn(intent: ReturnIntent, observation: CarriedArrivalReturn, page: PortfolioQueuePage,
  meta: NavigationMetadata | null, history: ReviewLineage | null, offset = 0): ComparisonQueueReconciliation {
  validateCarriedArrivalReturn(observation, intent);
  if (!Number.isFinite(Date.parse(page.observed_at)) || Date.parse(page.observed_at) < Date.parse(observation.arrival.metadata.observed_at)) fail();
  const value = reconcileOnwardReturn(intent, observation.handoff.observation, page, meta, history, offset);
  if (value.state === 'not_observed') return value;
  compareDestinationIdentities(observation.handoff.prepared, value.fresh);
  return structuredClone({ ...value, ...compareDestinationIdentities(observation.arrival, value.fresh) });
}

/** Check every retained pin without replacing any original observation. */
export function verifyCarriedArrivalDestination(intent: ReturnIntent, observation: CarriedArrivalReturn, fresh: ReviewPathDestination) {
  validateCarriedArrivalReturn(observation, intent);
  verifyOnwardDestination(intent, observation.handoff.observation, fresh);
  compareDestinationIdentities(observation.handoff.prepared, fresh);
  return compareDestinationIdentities(observation.arrival, fresh);
}
export function validateCarriedArrivalObservation(intent: ReturnIntent, observation: CarriedArrivalReturn, value: ObservedComparison) {
  validateCarriedArrivalReturn(observation, intent);
  const receipt = observation.handoff.observation.handoff.observation.handoff.receipt;
  validateDestinationObservation(intent, receipt.handoff, observation.arrival, value);
  verifyCarriedArrivalDestination(intent, observation, value.fresh);
}
