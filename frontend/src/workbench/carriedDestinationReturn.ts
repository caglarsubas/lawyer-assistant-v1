import { canonicalJson } from '../pages/matter/sourceReviewTypes';
import type { PortfolioQueuePage } from '../pages/portfolioSourceQueueTypes';
import type { NavigationMetadata, SourceTarget } from '../pages/sourceContextNavigationTypes';
import type { ReviewLineage } from '../pages/sourceReviewLineageTypes';
import { compareCarriedArrivalEventDestination, returnCarriedArrivalEvent, validateCarriedArrivalEventHandoff, type CarriedArrivalEventHandoff } from './carriedArrivalEventHandoff';
import { reconcileCarriedArrivalReturn, verifyCarriedArrivalDestination } from './carriedArrivalReturn';
import { compareDestinationIdentities, type ComparisonQueueReconciliation } from './comparisonReturn';
import type { ReturnIntent } from './portfolioReturn';
import type { ReviewPathDestination } from './reviewPathHandoff';

/** A separate fixed-depth destination; original carried arrival and preparations stay unchanged. */
export type CarriedDestinationReturn = { recipe: 'private-carried-destination-return-v1'; handoff: CarriedArrivalEventHandoff; destination: ReviewPathDestination };
function fail(): never { throw new Error('Taşınan hedefin dönüş veya yeni kuyruk bağı doğrulanamadı. Yeni gözlem gerekli; önceki sonuç kullanılmadı.'); }
export function validateCarriedDestinationReturn(value: CarriedDestinationReturn, intent: ReturnIntent) {
  if (!value || canonicalJson(Object.keys(value).sort()) !== canonicalJson(['destination', 'handoff', 'recipe']) || value.recipe !== 'private-carried-destination-return-v1') fail();
  validateCarriedArrivalEventHandoff(value.handoff, intent);
  verifyCarriedArrivalDestination(intent, value.handoff.observation, value.destination);
  compareDestinationIdentities(value.handoff.prepared, value.destination);
}
export function captureCarriedDestinationReturn(intent: ReturnIntent, handoff: CarriedArrivalEventHandoff, target: SourceTarget,
  meta: NavigationMetadata | null, history: ReviewLineage | null): { intent: ReturnIntent; observation: CarriedDestinationReturn | null } {
  const next = returnCarriedArrivalEvent(intent, handoff, target, meta, history);
  if (!next.observation) return { intent: next.intent, observation: null };
  const observation: CarriedDestinationReturn = { recipe: 'private-carried-destination-return-v1', handoff: structuredClone(handoff),
    destination: compareCarriedArrivalEventDestination(intent, handoff, target, history!).fresh };
  validateCarriedDestinationReturn(observation, next.intent); return { intent: next.intent, observation: structuredClone(observation) };
}
/** Reuses the authorized bounded queue and exact-event GET; never scans or reads bodies. */
export function reconcileCarriedDestinationReturn(intent: ReturnIntent, observation: CarriedDestinationReturn, page: PortfolioQueuePage,
  meta: NavigationMetadata | null, history: ReviewLineage | null, offset = 0): ComparisonQueueReconciliation {
  validateCarriedDestinationReturn(observation, intent);
  if (!Number.isFinite(Date.parse(page.observed_at)) || Date.parse(page.observed_at) < Date.parse(observation.destination.metadata.observed_at)) fail();
  const value = reconcileCarriedArrivalReturn(intent, observation.handoff.observation, page, meta, history, offset);
  if (value.state === 'not_observed') return value;
  compareDestinationIdentities(observation.handoff.prepared, value.fresh);
  return structuredClone({ ...value, ...compareDestinationIdentities(observation.destination, value.fresh) });
}
