import { canonicalJson } from '../pages/matter/sourceReviewTypes';
import type { PortfolioQueuePage } from '../pages/portfolioSourceQueueTypes';
import type { NavigationMetadata, SourceTarget } from '../pages/sourceContextNavigationTypes';
import type { ReviewLineage } from '../pages/sourceReviewLineageTypes';
import { captureHandoffArrivalDestinationArrivalDestinationArrivalEventDestination, reconcileHandoffArrivalDestinationArrivalDestinationArrivalEventDestination, verifyHandoffArrivalDestinationArrivalDestinationArrivalEventDestination, type HandoffArrivalDestinationArrivalDestinationArrivalEvent } from './handoffArrivalDestinationArrivalDestinationArrivalEvent';
import type { ReturnIntent } from './portfolioReturn';
import type { ReviewPathDestination } from './reviewPathHandoff';

/** Fixed depth: the complete purpose plus one separate reduced destination, never another return. */
export type HandoffArrivalDestinationArrivalDestinationArrivalDestinationReturn = { recipe: 'private-handoff-arrival-destination-arrival-destination-arrival-destination-return-v1'; handoff: HandoffArrivalDestinationArrivalDestinationArrivalEvent; destination: ReviewPathDestination };
function shape(value: HandoffArrivalDestinationArrivalDestinationArrivalDestinationReturn) {
  if (!value || canonicalJson(Object.keys(value).sort()) !== canonicalJson(['destination', 'handoff', 'recipe']) || value.recipe !== 'private-handoff-arrival-destination-arrival-destination-arrival-destination-return-v1')
    throw new Error('Yeni varışı koruyan geçiş hedefinin dönüş veya yeni kuyruk bağı doğrulanamadı. Yeni gözlem gerekli; önceki sonuç kullanılmadı.');
}
export function validateHandoffArrivalDestinationArrivalDestinationArrivalDestinationReturn(value: HandoffArrivalDestinationArrivalDestinationArrivalDestinationReturn, intent: ReturnIntent) {
  shape(value); verifyHandoffArrivalDestinationArrivalDestinationArrivalEventDestination(intent, value.handoff, value.destination);
}
export function captureHandoffArrivalDestinationArrivalDestinationArrivalDestinationReturn(intent: ReturnIntent, handoff: HandoffArrivalDestinationArrivalDestinationArrivalEvent, target: SourceTarget,
  meta: NavigationMetadata | null, history: ReviewLineage | null): { intent: ReturnIntent; observation: HandoffArrivalDestinationArrivalDestinationArrivalDestinationReturn | null } {
  const next = captureHandoffArrivalDestinationArrivalDestinationArrivalEventDestination(intent, handoff, target, meta, history);
  return { intent: next.intent, observation: next.destination ? { recipe: 'private-handoff-arrival-destination-arrival-destination-arrival-destination-return-v1', handoff: structuredClone(handoff), destination: next.destination } : null };
}
/** Fresh authorized bounded reads only; omission never reveals saved details or initiates a scan. */
export function reconcileHandoffArrivalDestinationArrivalDestinationArrivalDestinationReturn(intent: ReturnIntent, observation: HandoffArrivalDestinationArrivalDestinationArrivalDestinationReturn, page: PortfolioQueuePage,
  meta: NavigationMetadata | null, history: ReviewLineage | null, offset = 0) {
  shape(observation); return reconcileHandoffArrivalDestinationArrivalDestinationArrivalEventDestination(intent, observation.handoff, observation.destination, page, meta, history, offset);
}
