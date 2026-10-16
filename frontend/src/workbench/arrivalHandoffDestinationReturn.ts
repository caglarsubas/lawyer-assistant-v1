import { canonicalJson } from '../pages/matter/sourceReviewTypes';
import type { PortfolioQueuePage } from '../pages/portfolioSourceQueueTypes';
import type { NavigationMetadata, SourceTarget } from '../pages/sourceContextNavigationTypes';
import type { ReviewLineage } from '../pages/sourceReviewLineageTypes';
import { captureCarriedDestinationArrivalEventReturn, reconcileCarriedDestinationArrivalEventDestination, verifyCarriedDestinationArrivalEventDestination, type CarriedDestinationArrivalEventHandoff } from './carriedDestinationArrivalEventHandoff';
import type { ReturnIntent } from './portfolioReturn';
import type { ReviewPathDestination } from './reviewPathHandoff';

/** Fixed depth: the complete purpose plus one separate reduced destination, never another return. */
export type ArrivalHandoffDestinationReturn = { recipe: 'private-arrival-handoff-destination-return-v1'; handoff: CarriedDestinationArrivalEventHandoff; destination: ReviewPathDestination };
function shape(value: ArrivalHandoffDestinationReturn) {
  if (!value || canonicalJson(Object.keys(value).sort()) !== canonicalJson(['destination', 'handoff', 'recipe']) || value.recipe !== 'private-arrival-handoff-destination-return-v1')
    throw new Error('Geçiş hedefinin dönüş veya yeni kuyruk bağı doğrulanamadı. Yeni gözlem gerekli; önceki sonuç kullanılmadı.');
}
export function validateArrivalHandoffDestinationReturn(value: ArrivalHandoffDestinationReturn, intent: ReturnIntent) {
  shape(value); verifyCarriedDestinationArrivalEventDestination(intent, value.handoff, value.destination);
}
export function captureArrivalHandoffDestinationReturn(intent: ReturnIntent, handoff: CarriedDestinationArrivalEventHandoff, target: SourceTarget,
  meta: NavigationMetadata | null, history: ReviewLineage | null): { intent: ReturnIntent; observation: ArrivalHandoffDestinationReturn | null } {
  const next = captureCarriedDestinationArrivalEventReturn(intent, handoff, target, meta, history);
  return { intent: next.intent, observation: next.destination ? { recipe: 'private-arrival-handoff-destination-return-v1', handoff: structuredClone(handoff), destination: next.destination } : null };
}
/** Fresh authorized bounded reads only; omission never reveals saved details or initiates a scan. */
export function reconcileArrivalHandoffDestinationReturn(intent: ReturnIntent, observation: ArrivalHandoffDestinationReturn, page: PortfolioQueuePage,
  meta: NavigationMetadata | null, history: ReviewLineage | null, offset = 0) {
  shape(observation); return reconcileCarriedDestinationArrivalEventDestination(intent, observation.handoff, observation.destination, page, meta, history, offset);
}
