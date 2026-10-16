import { canonicalJson } from '../pages/matter/sourceReviewTypes';
import type { PortfolioQueuePage } from '../pages/portfolioSourceQueueTypes';
import type { NavigationMetadata, SourceTarget } from '../pages/sourceContextNavigationTypes';
import type { ReviewLineage } from '../pages/sourceReviewLineageTypes';
import { captureHandoffArrivalDestinationArrivalDestinationEventArrival, reconcileHandoffArrivalDestinationArrivalDestinationEventArrival, verifyHandoffArrivalDestinationArrivalDestinationEventArrival, type HandoffArrivalDestinationArrivalDestinationEvent } from './handoffArrivalDestinationArrivalDestinationEvent';
import type { ReturnIntent } from './portfolioReturn';
import type { ReviewPathDestination } from './reviewPathHandoff';

/** One complete handoff and one separate reduced arrival; no recursive return or window. */
export type HandoffArrivalDestinationArrivalDestinationArrivalReturn = { recipe: 'private-handoff-arrival-destination-arrival-destination-arrival-return-v1'; handoff: HandoffArrivalDestinationArrivalDestinationEvent; arrival: ReviewPathDestination };
function shape(value: HandoffArrivalDestinationArrivalDestinationArrivalReturn) {
  if (!value || canonicalJson(Object.keys(value).sort()) !== canonicalJson(['arrival', 'handoff', 'recipe']) || value.recipe !== 'private-handoff-arrival-destination-arrival-destination-arrival-return-v1')
    throw new Error('Geçiş hedefini koruyan yeni geçiş varışının dönüş veya yeni kuyruk bağı doğrulanamadı. Yeni gözlem gerekli; önceki sonuç kullanılmadı.');
}
export function validateHandoffArrivalDestinationArrivalDestinationArrivalReturn(value: HandoffArrivalDestinationArrivalDestinationArrivalReturn, intent: ReturnIntent) {
  shape(value); verifyHandoffArrivalDestinationArrivalDestinationEventArrival(intent, value.handoff, value.arrival);
}
export function captureHandoffArrivalDestinationArrivalDestinationArrivalReturn(intent: ReturnIntent, handoff: HandoffArrivalDestinationArrivalDestinationEvent, target: SourceTarget,
  meta: NavigationMetadata | null, history: ReviewLineage | null): { intent: ReturnIntent; observation: HandoffArrivalDestinationArrivalDestinationArrivalReturn | null } {
  const next = captureHandoffArrivalDestinationArrivalDestinationEventArrival(intent, handoff, target, meta, history);
  return { intent: next.intent, observation: next.arrival ? { recipe: 'private-handoff-arrival-destination-arrival-destination-arrival-return-v1', handoff: structuredClone(handoff), arrival: next.arrival } : null };
}
/** Fresh authorized bounded observations only; omission reveals no saved arrival details. */
export function reconcileHandoffArrivalDestinationArrivalDestinationArrivalReturn(intent: ReturnIntent, observation: HandoffArrivalDestinationArrivalDestinationArrivalReturn,
  page: PortfolioQueuePage, meta: NavigationMetadata | null, history: ReviewLineage | null, offset = 0) {
  shape(observation); return reconcileHandoffArrivalDestinationArrivalDestinationEventArrival(intent, observation.handoff, observation.arrival, page, meta, history, offset);
}
