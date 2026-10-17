import { canonicalJson } from '../pages/matter/sourceReviewTypes';
import type { PortfolioQueuePage } from '../pages/portfolioSourceQueueTypes';
import type { NavigationMetadata, SourceTarget } from '../pages/sourceContextNavigationTypes';
import type { ReviewLineage } from '../pages/sourceReviewLineageTypes';
import { captureHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalEventDestination, reconcileHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalEventDestination, verifyHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalEventDestination, type HandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalEvent } from './handoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalEvent';
import type { ReturnIntent } from './portfolioReturn';
import type { ReviewPathDestination } from './reviewPathHandoff';

/** Fixed depth: the complete purpose plus one separate reduced destination, never another return. */
export type HandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationReturn = { recipe: 'private-handoff-arrival-destination-arrival-destination-arrival-destination-arrival-destination-return-v1'; handoff: HandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalEvent; destination: ReviewPathDestination };
function shape(value: HandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationReturn) {
  if (!value || canonicalJson(Object.keys(value).sort()) !== canonicalJson(['destination', 'handoff', 'recipe']) || value.recipe !== 'private-handoff-arrival-destination-arrival-destination-arrival-destination-arrival-destination-return-v1')
    throw new Error('Tam varışı koruyan geçiş hedefinin dönüş veya yeni kuyruk bağı doğrulanamadı. Yeni gözlem gerekli; önceki sonuç kullanılmadı.');
}
export function validateHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationReturn(value: HandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationReturn, intent: ReturnIntent) {
  shape(value); verifyHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalEventDestination(intent, value.handoff, value.destination);
}
export function captureHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationReturn(intent: ReturnIntent, handoff: HandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalEvent, target: SourceTarget,
  meta: NavigationMetadata | null, history: ReviewLineage | null): { intent: ReturnIntent; observation: HandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationReturn | null } {
  const next = captureHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalEventDestination(intent, handoff, target, meta, history);
  return { intent: next.intent, observation: next.destination ? { recipe: 'private-handoff-arrival-destination-arrival-destination-arrival-destination-arrival-destination-return-v1', handoff: structuredClone(handoff), destination: next.destination } : null };
}
/** Fresh authorized bounded reads only; omission never reveals saved details or initiates a scan. */
export function reconcileHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationReturn(intent: ReturnIntent, observation: HandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationReturn, page: PortfolioQueuePage,
  meta: NavigationMetadata | null, history: ReviewLineage | null, offset = 0) {
  shape(observation); return reconcileHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalEventDestination(intent, observation.handoff, observation.destination, page, meta, history, offset);
}
