import { canonicalJson } from '../pages/matter/sourceReviewTypes';
import type { PortfolioQueuePage } from '../pages/portfolioSourceQueueTypes';
import type { NavigationMetadata, SourceTarget } from '../pages/sourceContextNavigationTypes';
import type { ReviewLineage } from '../pages/sourceReviewLineageTypes';
import { captureHandoffArrivalDestinationEventArrival, reconcileHandoffArrivalDestinationEventArrival, verifyHandoffArrivalDestinationEventArrival, type HandoffArrivalDestinationEvent } from './handoffArrivalDestinationEvent';
import type { ReturnIntent } from './portfolioReturn';
import type { ReviewPathDestination } from './reviewPathHandoff';

/** One complete handoff and one separate reduced arrival; no recursive return or window. */
export type HandoffArrivalDestinationArrivalReturn = { recipe: 'private-handoff-arrival-destination-arrival-return-v1'; handoff: HandoffArrivalDestinationEvent; arrival: ReviewPathDestination };
function shape(value: HandoffArrivalDestinationArrivalReturn) {
  if (!value || canonicalJson(Object.keys(value).sort()) !== canonicalJson(['arrival', 'handoff', 'recipe']) || value.recipe !== 'private-handoff-arrival-destination-arrival-return-v1')
    throw new Error('Hedefi koruyan geçiş varışının dönüş veya yeni kuyruk bağı doğrulanamadı. Yeni gözlem gerekli; önceki sonuç kullanılmadı.');
}
export function validateHandoffArrivalDestinationArrivalReturn(value: HandoffArrivalDestinationArrivalReturn, intent: ReturnIntent) {
  shape(value); verifyHandoffArrivalDestinationEventArrival(intent, value.handoff, value.arrival);
}
export function captureHandoffArrivalDestinationArrivalReturn(intent: ReturnIntent, handoff: HandoffArrivalDestinationEvent, target: SourceTarget,
  meta: NavigationMetadata | null, history: ReviewLineage | null): { intent: ReturnIntent; observation: HandoffArrivalDestinationArrivalReturn | null } {
  const next = captureHandoffArrivalDestinationEventArrival(intent, handoff, target, meta, history);
  return { intent: next.intent, observation: next.arrival ? { recipe: 'private-handoff-arrival-destination-arrival-return-v1', handoff: structuredClone(handoff), arrival: next.arrival } : null };
}
/** Fresh authorized bounded observations only; omission reveals no saved arrival details. */
export function reconcileHandoffArrivalDestinationArrivalReturn(intent: ReturnIntent, observation: HandoffArrivalDestinationArrivalReturn,
  page: PortfolioQueuePage, meta: NavigationMetadata | null, history: ReviewLineage | null, offset = 0) {
  shape(observation); return reconcileHandoffArrivalDestinationEventArrival(intent, observation.handoff, observation.arrival, page, meta, history, offset);
}
