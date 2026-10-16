import { canonicalJson } from '../pages/matter/sourceReviewTypes';
import type { PortfolioQueuePage } from '../pages/portfolioSourceQueueTypes';
import type { NavigationMetadata, SourceTarget } from '../pages/sourceContextNavigationTypes';
import type { ReviewLineage } from '../pages/sourceReviewLineageTypes';
import { captureHandoffArrivalEventDestination, reconcileHandoffArrivalEventDestination, verifyHandoffArrivalEventDestination, type HandoffArrivalEvent } from './handoffArrivalEvent';
import type { ReturnIntent } from './portfolioReturn';
import type { ReviewPathDestination } from './reviewPathHandoff';

/** Fixed depth: the complete purpose plus one separate reduced destination, never another return. */
export type HandoffArrivalDestinationReturn = { recipe: 'private-handoff-arrival-destination-return-v1'; handoff: HandoffArrivalEvent; destination: ReviewPathDestination };
function shape(value: HandoffArrivalDestinationReturn) {
  if (!value || canonicalJson(Object.keys(value).sort()) !== canonicalJson(['destination', 'handoff', 'recipe']) || value.recipe !== 'private-handoff-arrival-destination-return-v1')
    throw new Error('Varış geçişi hedefinin dönüş veya yeni kuyruk bağı doğrulanamadı. Yeni gözlem gerekli; önceki sonuç kullanılmadı.');
}
export function validateHandoffArrivalDestinationReturn(value: HandoffArrivalDestinationReturn, intent: ReturnIntent) {
  shape(value); verifyHandoffArrivalEventDestination(intent, value.handoff, value.destination);
}
export function captureHandoffArrivalDestinationReturn(intent: ReturnIntent, handoff: HandoffArrivalEvent, target: SourceTarget,
  meta: NavigationMetadata | null, history: ReviewLineage | null): { intent: ReturnIntent; observation: HandoffArrivalDestinationReturn | null } {
  const next = captureHandoffArrivalEventDestination(intent, handoff, target, meta, history);
  return { intent: next.intent, observation: next.destination ? { recipe: 'private-handoff-arrival-destination-return-v1', handoff: structuredClone(handoff), destination: next.destination } : null };
}
/** Fresh authorized bounded reads only; omission never reveals saved details or initiates a scan. */
export function reconcileHandoffArrivalDestinationReturn(intent: ReturnIntent, observation: HandoffArrivalDestinationReturn, page: PortfolioQueuePage,
  meta: NavigationMetadata | null, history: ReviewLineage | null, offset = 0) {
  shape(observation); return reconcileHandoffArrivalEventDestination(intent, observation.handoff, observation.destination, page, meta, history, offset);
}
