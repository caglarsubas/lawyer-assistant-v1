import { canonicalJson } from '../pages/matter/sourceReviewTypes';
import type { PortfolioQueuePage } from '../pages/portfolioSourceQueueTypes';
import type { NavigationMetadata, SourceTarget } from '../pages/sourceContextNavigationTypes';
import type { ReviewLineage } from '../pages/sourceReviewLineageTypes';
import { captureHandoffDestinationEventArrival, reconcileHandoffDestinationEventArrival, verifyHandoffDestinationEventArrival, type HandoffDestinationEvent } from './handoffDestinationEvent';
import type { ReturnIntent } from './portfolioReturn';
import type { ReviewPathDestination } from './reviewPathHandoff';

/** Fixed depth: the complete purpose plus one separate reduced arrival, never another return. */
export type HandoffDestinationArrivalReturn = { recipe: 'private-handoff-destination-arrival-return-v1'; handoff: HandoffDestinationEvent; arrival: ReviewPathDestination };
function shape(value: HandoffDestinationArrivalReturn) {
  if (!value || canonicalJson(Object.keys(value).sort()) !== canonicalJson(['arrival', 'handoff', 'recipe']) || value.recipe !== 'private-handoff-destination-arrival-return-v1')
    throw new Error('Geçiş varışının dönüş veya yeni kuyruk bağı doğrulanamadı. Yeni gözlem gerekli; önceki sonuç kullanılmadı.');
}
export function validateHandoffDestinationArrivalReturn(value: HandoffDestinationArrivalReturn, intent: ReturnIntent) {
  shape(value); verifyHandoffDestinationEventArrival(intent, value.handoff, value.arrival);
}
export function captureHandoffDestinationArrivalReturn(intent: ReturnIntent, handoff: HandoffDestinationEvent, target: SourceTarget,
  meta: NavigationMetadata | null, history: ReviewLineage | null): { intent: ReturnIntent; observation: HandoffDestinationArrivalReturn | null } {
  const next = captureHandoffDestinationEventArrival(intent, handoff, target, meta, history);
  return { intent: next.intent, observation: next.arrival ? { recipe: 'private-handoff-destination-arrival-return-v1', handoff: structuredClone(handoff), arrival: next.arrival } : null };
}
/** Fresh authorized bounded reads only; omission never reveals saved details or initiates a scan. */
export function reconcileHandoffDestinationArrivalReturn(intent: ReturnIntent, observation: HandoffDestinationArrivalReturn, page: PortfolioQueuePage,
  meta: NavigationMetadata | null, history: ReviewLineage | null, offset = 0) {
  shape(observation); return reconcileHandoffDestinationEventArrival(intent, observation.handoff, observation.arrival, page, meta, history, offset);
}
