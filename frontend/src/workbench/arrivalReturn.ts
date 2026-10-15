import { canonicalJson } from '../pages/matter/sourceReviewTypes';
import type { PortfolioQueuePage } from '../pages/portfolioSourceQueueTypes';
import type { NavigationMetadata, SourceTarget } from '../pages/sourceContextNavigationTypes';
import type { ReviewLineage } from '../pages/sourceReviewLineageTypes';
import { compareComparisonEventArrival, returnComparisonEvent, validateComparisonEventHandoff, type ComparisonEventHandoff } from './comparisonEventHandoff';
import { compareDestinationIdentities, reconcileComparisonReturn, type ComparisonQueueReconciliation } from './comparisonReturn';
import type { ReturnIntent } from './portfolioReturn';
import { verifyReviewPathDestination, type ReviewPathDestination } from './reviewPathHandoff';

/** A fixed-depth observation; the original receipt and preparation are never rebased. */
export type ArrivalReturn = { recipe: 'private-arrival-return-v1'; handoff: ComparisonEventHandoff; arrival: ReviewPathDestination };
function fail(): never { throw new Error('Varış gözleminin dönüş veya yeni kuyruk bağı doğrulanamadı. Yeni gözlem gerekli; önceki sonuç kullanılmadı.'); }
export function validateArrivalReturn(value: ArrivalReturn, intent: ReturnIntent) {
  if (!value || canonicalJson(Object.keys(value).sort()) !== canonicalJson(['arrival', 'handoff', 'recipe']) || value.recipe !== 'private-arrival-return-v1') fail();
  validateComparisonEventHandoff(value.handoff, intent);
  verifyReviewPathDestination(intent, value.handoff.receipt.handoff, value.arrival);
  compareDestinationIdentities(value.handoff.receipt.destination, value.arrival);
  compareDestinationIdentities(value.handoff.prepared, value.arrival);
}

/** Called only for an explicit return with a currently available, verified arrival. */
export function captureArrivalReturn(intent: ReturnIntent, handoff: ComparisonEventHandoff, target: SourceTarget,
  meta: NavigationMetadata | null, history: ReviewLineage | null): { intent: ReturnIntent; observation: ArrivalReturn | null } {
  const next = returnComparisonEvent(intent, handoff, target, meta, history);
  if (!next.receipt) return { intent: next.intent, observation: null };
  const arrival = compareComparisonEventArrival(intent, handoff, target, history!).fresh;
  const observation: ArrivalReturn = { recipe: 'private-arrival-return-v1', handoff: structuredClone(handoff), arrival };
  validateArrivalReturn(observation, next.intent); return { intent: next.intent, observation: structuredClone(observation) };
}

/** Reuses the bounded authorized queue + exact-event reads; never scans or reads bodies. */
export function reconcileArrivalReturn(intent: ReturnIntent, observation: ArrivalReturn, page: PortfolioQueuePage,
  meta: NavigationMetadata | null, history: ReviewLineage | null, offset = 0): ComparisonQueueReconciliation {
  validateArrivalReturn(observation, intent);
  if (!Number.isFinite(Date.parse(page.observed_at)) || Date.parse(page.observed_at) < Date.parse(observation.arrival.metadata.observed_at)) fail();
  const value = reconcileComparisonReturn(intent, observation.handoff.receipt, page, meta, history, offset);
  if (value.state === 'not_observed') return value;
  compareDestinationIdentities(observation.handoff.prepared, value.fresh);
  return structuredClone({ ...value, ...compareDestinationIdentities(observation.arrival, value.fresh) });
}
