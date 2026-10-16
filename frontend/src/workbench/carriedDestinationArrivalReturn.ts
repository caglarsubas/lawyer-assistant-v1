import { canonicalJson } from '../pages/matter/sourceReviewTypes';
import type { PortfolioQueuePage } from '../pages/portfolioSourceQueueTypes';
import type { NavigationMetadata, SourceTarget } from '../pages/sourceContextNavigationTypes';
import type { ReviewLineage } from '../pages/sourceReviewLineageTypes';
import { compareCarriedDestinationEventDestination, returnCarriedDestinationEvent, validateCarriedDestinationEventHandoff, type CarriedDestinationEventHandoff } from './carriedDestinationEventHandoff';
import { reconcileCarriedDestinationReturn, verifyCarriedDestinationDestination } from './carriedDestinationReturn';
import { compareDestinationIdentities, type ComparisonQueueReconciliation } from './comparisonReturn';
import type { ReturnIntent } from './portfolioReturn';
import type { ReviewPathDestination } from './reviewPathHandoff';

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
