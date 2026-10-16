import { canonicalJson } from '../pages/matter/sourceReviewTypes';
import type { NavigationMetadata, SourceTarget } from '../pages/sourceContextNavigationTypes';
import { verifyReviewLineage, type ReviewLineage } from '../pages/sourceReviewLineageTypes';
import { validateCarriedDestinationArrivalObservation, verifyCarriedDestinationArrivalDestination, type CarriedDestinationArrivalReturn } from './carriedDestinationArrivalReturn';
import { compareDestinationIdentities, type ComparisonQueueReconciliation, type ObservedComparison } from './comparisonReturn';
import type { ReturnIntent } from './portfolioReturn';
import { returnVerifiedEvent, verifyReturnedEventTarget } from './returnedReviewLineage';
import { verifyReviewPathDestination, type ReviewPathDestination } from './reviewPathHandoff';

/** Fixed-depth purpose contract; carries one original destination arrival, never another purpose handoff. */
export type CarriedDestinationArrivalEventHandoff = { recipe: 'private-carried-destination-arrival-event-handoff-v1'; observation: CarriedDestinationArrivalReturn;
  queue: ObservedComparison; prepared: ReviewPathDestination; observed_at: [string, string] };
const equal = (a: unknown, b: unknown) => canonicalJson(a) === canonicalJson(b);
const stable = (v: ReviewPathDestination) => ({ ...v, metadata: { ...v.metadata, observed_at: null } });
const admitted = (v: ReviewPathDestination) => v.metadata.tools_available && v.metadata.analysis.current_version_id !== null
  && v.metadata.admission.context_state === 'complete' && v.metadata.admission.review_state === 'complete'
  && v.selected.integrity === 'verified' && v.selected.admission === 'complete' && v.head?.integrity === 'verified' && v.head.admission === 'complete';
function fail(): never { throw new Error('Hedef varışını koruyan tam karar geçişi doğrulanamadı. Yeni kuyruk gözlemi gerekli; başka kayıt veya önceki sonuç kullanılmadı.'); }
const stamp = (v: unknown): v is string => typeof v === 'string' && v.length <= 40 && Number.isFinite(Date.parse(v));
export function carriedDestinationArrivalEventAvailable(intent: ReturnIntent, observation: CarriedDestinationArrivalReturn, value: ComparisonQueueReconciliation) {
  if (value.state !== 'observed') return false;
  validateCarriedDestinationArrivalObservation(intent, observation, value); return admitted(value.fresh);
}
export function validateCarriedDestinationArrivalEventHandoff(value: CarriedDestinationArrivalEventHandoff, intent: ReturnIntent) {
  if (!value || !equal(Object.keys(value).sort(), ['observation', 'observed_at', 'prepared', 'queue', 'recipe']) || value.recipe !== 'private-carried-destination-arrival-event-handoff-v1') fail();
  validateCarriedDestinationArrivalObservation(intent, value.observation, value.queue);
  const destination = value.observation.handoff.observation, carried = destination.handoff.observation;
  const onward = carried.handoff.observation, arrival = onward.handoff.observation;
  // Check the prepared schema independently, including keys JSON equality would omit.
  verifyReviewPathDestination(intent, arrival.handoff.receipt.handoff, value.prepared);
  // Exact stable equality preserves every checked historical pin; compare its separate clock.
  compareDestinationIdentities(value.queue.fresh, value.prepared);
  if (!admitted(value.queue.fresh) || !admitted(value.prepared) || !equal(stable(value.queue.fresh), stable(value.prepared))
    || !Array.isArray(value.observed_at) || value.observed_at.length !== 2 || value.observed_at.some(time => !stamp(time))
    || Date.parse(value.observed_at[0]) < Date.parse(value.queue.fresh.metadata.observed_at)
    || Date.parse(value.observed_at[1]) < Date.parse(value.observed_at[0]) || value.prepared.metadata.observed_at !== value.observed_at[1]) fail();
}
export async function prepareCarriedDestinationArrivalEvent(intent: ReturnIntent, observation: CarriedDestinationArrivalReturn, value: ComparisonQueueReconciliation,
  read: (url: string) => Promise<ReviewLineage>, current: () => boolean): Promise<CarriedDestinationArrivalEventHandoff> {
  if (value.state !== 'observed' || !carriedDestinationArrivalEventAvailable(intent, observation, value)) fail();
  const queued = value, t = intent.target;
  const target: SourceTarget = { kind: 'selected', matter_id: t.matter_id, analysis_id: t.analysis_id, context_id: t.context_id, review_id: t.review_id! };
  verifyReturnedEventTarget(intent, target);
  const url = `/matters/${encodeURIComponent(t.matter_id)}/analyses/${encodeURIComponent(t.analysis_id)}/source-contexts/${encodeURIComponent(t.context_id)}/reviews/${encodeURIComponent(t.review_id!)}/navigation-context?window=1`;
  async function observe() {
    if (!current()) fail(); const h = await read(url); if (!current()) fail();
    verifyReviewLineage(h, target);
    const fresh = { metadata: h.context_navigation, selected: h.selected_review, head: h.current_head };
    verifyCarriedDestinationArrivalDestination(intent, observation, fresh);
    if (h.lineage.window !== 1 || !h.tools_available || !admitted(fresh) || !equal(stable(queued.fresh), stable(fresh))
      || Date.parse(h.observed_at) < Date.parse(queued.fresh.metadata.observed_at)) fail();
    return fresh;
  }
  const before = await observe(), after = await observe();
  const result: CarriedDestinationArrivalEventHandoff = { recipe: 'private-carried-destination-arrival-event-handoff-v1', observation: structuredClone(observation), queue: structuredClone(queued), prepared: after,
    observed_at: [before.metadata.observed_at, after.metadata.observed_at] };
  validateCarriedDestinationArrivalEventHandoff(result, intent); if (!current()) fail(); return structuredClone(result);
}
export function compareCarriedDestinationArrivalEventDestination(intent: ReturnIntent, handoff: CarriedDestinationArrivalEventHandoff, target: SourceTarget, history: ReviewLineage) {
  validateCarriedDestinationArrivalEventHandoff(handoff, intent); verifyReturnedEventTarget(intent, target); verifyReviewLineage(history, target);
  const fresh = { metadata: history.context_navigation, selected: history.selected_review, head: history.current_head };
  verifyCarriedDestinationArrivalDestination(intent, handoff.observation, fresh);
  return structuredClone({ fresh, ...compareDestinationIdentities(handoff.prepared, fresh) });
}
/** A verified return restores the original observation, never captures or nests a new arrival. */
export function returnCarriedDestinationArrivalEvent(intent: ReturnIntent, handoff: CarriedDestinationArrivalEventHandoff, target: SourceTarget, meta: NavigationMetadata | null, history: ReviewLineage | null) {
  validateCarriedDestinationArrivalEventHandoff(handoff, intent); const next = returnVerifiedEvent(intent, target, meta, history);
  if (!meta && !history) return { intent: next, observation: null };
  compareCarriedDestinationArrivalEventDestination(intent, handoff, target, history!);
  return { intent: next, observation: structuredClone(handoff.observation) };
}
