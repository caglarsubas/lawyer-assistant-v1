import { canonicalJson } from '../pages/matter/sourceReviewTypes';
import type { PortfolioQueuePage } from '../pages/portfolioSourceQueueTypes';
import type { NavigationMetadata, SourceTarget } from '../pages/sourceContextNavigationTypes';
import type { ReviewLineage } from '../pages/sourceReviewLineageTypes';
import { captureHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationEventArrival, reconcileHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationEventArrival, verifyHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationEventArrival, type HandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationEvent } from './handoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationEvent';
import type { ReturnIntent } from './portfolioReturn';
import type { ReviewPathDestination } from './reviewPathHandoff';

/** One complete handoff and one separate reduced arrival; no recursive return or window. */
export type HandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalReturn = { recipe: 'private-handoff-arrival-destination-arrival-destination-arrival-destination-arrival-destination-arrival-return-v1'; handoff: HandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationEvent; arrival: ReviewPathDestination };
function shape(value: HandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalReturn) {
  if (!value || canonicalJson(Object.keys(value).sort()) !== canonicalJson(['arrival', 'handoff', 'recipe']) || value.recipe !== 'private-handoff-arrival-destination-arrival-destination-arrival-destination-arrival-destination-arrival-return-v1')
    throw new Error('Tam hedefi koruyan geçiş varışının dönüş veya yeni kuyruk bağı doğrulanamadı. Yeni gözlem gerekli; önceki sonuç kullanılmadı.');
}
export function validateHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalReturn(value: HandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalReturn, intent: ReturnIntent) {
  shape(value); verifyHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationEventArrival(intent, value.handoff, value.arrival);
}
export function captureHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalReturn(intent: ReturnIntent, handoff: HandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationEvent, target: SourceTarget,
  meta: NavigationMetadata | null, history: ReviewLineage | null): { intent: ReturnIntent; observation: HandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalReturn | null } {
  const next = captureHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationEventArrival(intent, handoff, target, meta, history);
  return { intent: next.intent, observation: next.arrival ? { recipe: 'private-handoff-arrival-destination-arrival-destination-arrival-destination-arrival-destination-arrival-return-v1', handoff: structuredClone(handoff), arrival: next.arrival } : null };
}
/** Fresh authorized bounded observations only; omission reveals no saved arrival details. */
export function reconcileHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalReturn(intent: ReturnIntent, observation: HandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalReturn,
  page: PortfolioQueuePage, meta: NavigationMetadata | null, history: ReviewLineage | null, offset = 0) {
  shape(observation); return reconcileHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationEventArrival(intent, observation.handoff, observation.arrival, page, meta, history, offset);
}
