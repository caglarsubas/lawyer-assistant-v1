import { canonicalJson } from '../pages/matter/sourceReviewTypes';
import type { PortfolioQueuePage } from '../pages/portfolioSourceQueueTypes';
import type { NavigationMetadata, SourceTarget } from '../pages/sourceContextNavigationTypes';
import type { ReviewLineage } from '../pages/sourceReviewLineageTypes';
import { captureHandoffArrivalDestinationArrivalEventDestination, reconcileHandoffArrivalDestinationArrivalEventDestination, verifyHandoffArrivalDestinationArrivalEventDestination, type HandoffArrivalDestinationArrivalEvent } from './handoffArrivalDestinationArrivalEvent';
import type { ReturnIntent } from './portfolioReturn';
import type { ReviewPathDestination } from './reviewPathHandoff';

/** Fixed depth: the complete purpose plus one separate reduced destination, never another return. */
export type HandoffArrivalDestinationArrivalDestinationReturn = { recipe: 'private-handoff-arrival-destination-arrival-destination-return-v1'; handoff: HandoffArrivalDestinationArrivalEvent; destination: ReviewPathDestination };
function shape(value: HandoffArrivalDestinationArrivalDestinationReturn) {
  if (!value || canonicalJson(Object.keys(value).sort()) !== canonicalJson(['destination', 'handoff', 'recipe']) || value.recipe !== 'private-handoff-arrival-destination-arrival-destination-return-v1')
    throw new Error('Korunan hedef geçişi varışı hedefinin dönüş veya yeni kuyruk bağı doğrulanamadı. Yeni gözlem gerekli; önceki sonuç kullanılmadı.');
}
export function validateHandoffArrivalDestinationArrivalDestinationReturn(value: HandoffArrivalDestinationArrivalDestinationReturn, intent: ReturnIntent) {
  shape(value); verifyHandoffArrivalDestinationArrivalEventDestination(intent, value.handoff, value.destination);
}
export function captureHandoffArrivalDestinationArrivalDestinationReturn(intent: ReturnIntent, handoff: HandoffArrivalDestinationArrivalEvent, target: SourceTarget,
  meta: NavigationMetadata | null, history: ReviewLineage | null): { intent: ReturnIntent; observation: HandoffArrivalDestinationArrivalDestinationReturn | null } {
  const next = captureHandoffArrivalDestinationArrivalEventDestination(intent, handoff, target, meta, history);
  return { intent: next.intent, observation: next.destination ? { recipe: 'private-handoff-arrival-destination-arrival-destination-return-v1', handoff: structuredClone(handoff), destination: next.destination } : null };
}
/** Fresh authorized bounded reads only; omission never reveals saved details or initiates a scan. */
export function reconcileHandoffArrivalDestinationArrivalDestinationReturn(intent: ReturnIntent, observation: HandoffArrivalDestinationArrivalDestinationReturn, page: PortfolioQueuePage,
  meta: NavigationMetadata | null, history: ReviewLineage | null, offset = 0) {
  shape(observation); return reconcileHandoffArrivalDestinationArrivalEventDestination(intent, observation.handoff, observation.destination, page, meta, history, offset);
}
