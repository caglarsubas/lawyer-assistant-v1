import { canonicalJson } from '../pages/matter/sourceReviewTypes';
import type { PortfolioQueuePage } from '../pages/portfolioSourceQueueTypes';
import type { NavigationMetadata, SourceTarget } from '../pages/sourceContextNavigationTypes';
import type { ReviewLineage } from '../pages/sourceReviewLineageTypes';
import { compareArrivalEventDestination, returnArrivalEvent, validateArrivalEventHandoff, type ArrivalEventHandoff } from './arrivalEventHandoff';
import { reconcileArrivalReturn, verifyArrivalDestination } from './arrivalReturn';
import { compareDestinationIdentities, validateDestinationObservation, type ObservedComparison, type ComparisonQueueReconciliation } from './comparisonReturn';
import type { ReturnIntent } from './portfolioReturn';
import type { ReviewPathDestination } from './reviewPathHandoff';

/** Fixed-depth destination observation; original arrival and every preparation stay unchanged. */
export type OnwardReturn = { recipe: 'private-onward-return-v1'; handoff: ArrivalEventHandoff; destination: ReviewPathDestination };
function fail(): never { throw new Error('İleri geçiş hedefinin dönüş veya yeni kuyruk bağı doğrulanamadı. Yeni gözlem gerekli; önceki sonuç kullanılmadı.'); }
export function validateOnwardReturn(value: OnwardReturn, intent: ReturnIntent) {
  if (!value || canonicalJson(Object.keys(value).sort()) !== canonicalJson(['destination', 'handoff', 'recipe']) || value.recipe !== 'private-onward-return-v1') fail();
  validateArrivalEventHandoff(value.handoff, intent);
  verifyArrivalDestination(intent, value.handoff.observation, value.destination);
  compareDestinationIdentities(value.handoff.prepared, value.destination);
}
export function captureOnwardReturn(intent: ReturnIntent, handoff: ArrivalEventHandoff, target: SourceTarget,
  meta: NavigationMetadata | null, history: ReviewLineage | null): { intent: ReturnIntent; observation: OnwardReturn | null } {
  const next = returnArrivalEvent(intent, handoff, target, meta, history);
  if (!next.observation) return { intent: next.intent, observation: null };
  const observation: OnwardReturn = { recipe: 'private-onward-return-v1', handoff: structuredClone(handoff),
    destination: compareArrivalEventDestination(intent, handoff, target, history!).fresh };
  validateOnwardReturn(observation, next.intent); return { intent: next.intent, observation: structuredClone(observation) };
}
/** Existing authorized bounded queue + exact-event reads; never reuse an old target response. */
export function reconcileOnwardReturn(intent: ReturnIntent, observation: OnwardReturn, page: PortfolioQueuePage,
  meta: NavigationMetadata | null, history: ReviewLineage | null, offset = 0): ComparisonQueueReconciliation {
  validateOnwardReturn(observation, intent);
  if (!Number.isFinite(Date.parse(page.observed_at)) || Date.parse(page.observed_at) < Date.parse(observation.destination.metadata.observed_at)) fail();
  const value = reconcileArrivalReturn(intent, observation.handoff.observation, page, meta, history, offset);
  if (value.state === 'not_observed') return value;
  compareDestinationIdentities(observation.handoff.prepared, value.fresh);
  return structuredClone({ ...value, ...compareDestinationIdentities(observation.destination, value.fresh) });
}

/** Validate every historical pin without rebasing the retained onward destination. */
export function verifyOnwardDestination(intent: ReturnIntent, observation: OnwardReturn, fresh: ReviewPathDestination) {
  validateOnwardReturn(observation, intent);
  verifyArrivalDestination(intent, observation.handoff.observation, fresh);
  compareDestinationIdentities(observation.handoff.prepared, fresh);
  return compareDestinationIdentities(observation.destination, fresh);
}
export function validateOnwardObservation(intent: ReturnIntent, observation: OnwardReturn, value: ObservedComparison) {
  validateOnwardReturn(observation, intent);
  validateDestinationObservation(intent, observation.handoff.observation.handoff.receipt.handoff, observation.destination, value);
  verifyOnwardDestination(intent, observation, value.fresh);
}
