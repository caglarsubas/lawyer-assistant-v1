import { canonicalJson } from '../pages/matter/sourceReviewTypes';
import type { NavigationMetadata, SourceTarget } from '../pages/sourceContextNavigationTypes';
import { verifyReviewLineage, type ReviewLineage, type ReviewMetadata } from '../pages/sourceReviewLineageTypes';
import type { ReturnIntent, ReturnReconciliation } from './portfolioReturn';
import { compareReturnIdentities, verifyReturnSelection } from './returnComparison';

export const RETURNED_LINEAGE_WINDOW = 10;
export type ReturnedLineageBasis = { intent: ReturnIntent; metadata: NavigationMetadata; selected: ReviewMetadata; head: ReviewMetadata };
export type ReturnedLineageObservation = {
  status: 'same_event' | 'verified_path' | 'unknown';
  reason: 'same_event' | 'verified_path' | 'truncated' | 'unavailable' | 'pending' | 'not_observed';
  before_observed_at: string; window_observed_at: string; after_observed_at: string;
  selected_id: string; selected_packet_sha256: string; head_id: string; head_packet_sha256: string;
  window: number; observed_count: number; path: ReviewMetadata[];
  source_verification: 'not_checked'; legal_readiness: 'not_established'; qualification_granted: false;
};
const equal = (a: unknown, b: unknown) => canonicalJson(a) === canonicalJson(b);
const stable = ({ observed_at: _observed, ...rest }: NavigationMetadata) => rest;
const fail = (): never => { throw new Error('Karar başı, seçilen kayıt, sürüm veya erişim gözlemi değişti. Yeni portföy gözlemi gerekli; zincir sonucu kullanılmadı.'); };

/** Only an actually observed queue target can nominate a bounded metadata check. */
export function captureReturnedLineage(intent: ReturnIntent, comparison: ReturnReconciliation, history: ReviewLineage | null): ReturnedLineageBasis | null {
  if (comparison.state !== 'observed' || !history || !intent.target.review_id || !intent.target.review_packet_sha256) return null;
  verifyReturnSelection(intent, history.context_navigation, history, intent.target.review_id);
  if (!equal(compareReturnIdentities(intent, history.context_navigation, history), comparison.comparison)) fail();
  const m = history.context_navigation, selected = history.selected_review, head = history.current_head;
  if (m.integrity !== 'verified' || !m.tools_available || m.analysis.current_version_id === null
    || m.admission.context_state !== 'complete' || m.admission.review_state !== 'complete'
    || selected.integrity !== 'verified' || selected.admission !== 'complete' || !head || head.integrity !== 'verified' || head.admission !== 'complete') return null;
  return structuredClone({ intent, metadata: m, selected, head });
}
function verifySnapshot(basis: ReturnedLineageBasis, value: ReviewLineage, review: ReviewMetadata, window: number) {
  const t = basis.intent.target;
  const target: SourceTarget = { kind: 'selected', matter_id: t.matter_id, analysis_id: t.analysis_id, context_id: t.context_id, review_id: review.id };
  verifyReviewLineage(value, target);
  verifyReturnSelection(basis.intent, value.context_navigation, value, review.id);
  if (value.lineage.window !== window || !equal(stable(value.context_navigation), stable(basis.metadata))
    || !equal(value.selected_review, review) || !equal(value.current_head, basis.head)
    || Date.parse(value.observed_at) < Date.parse(basis.metadata.observed_at)) fail();
}

/** Three authorized GETs only: selected identity, one head window, selected identity.
 * Both selected observations also pin today's head/version/revision. No expansion. */
export async function observeReturnedLineage(basis: ReturnedLineageBasis,
  read: (path: string) => Promise<ReviewLineage>, current: () => boolean): Promise<ReturnedLineageObservation> {
  const t = basis.intent.target;
  const base = `/matters/${encodeURIComponent(t.matter_id)}/analyses/${encodeURIComponent(t.analysis_id)}/source-contexts/${encodeURIComponent(t.context_id)}`;
  const get = async (review: ReviewMetadata, window: number) => {
    if (!current()) fail();
    const value = await read(`${base}/reviews/${encodeURIComponent(review.id)}/navigation-context?window=${window}`);
    if (!current()) fail();
    verifySnapshot(basis, value, review, window); return value;
  };
  const before = await get(basis.selected, 1);
  const head = await get(basis.head, RETURNED_LINEAGE_WINDOW);
  const after = await get(basis.selected, 1);
  if (Date.parse(before.observed_at) > Date.parse(head.observed_at) || Date.parse(head.observed_at) > Date.parse(after.observed_at)) fail();
  const rows = head.lineage.items, index = rows.findIndex(row => row.id === basis.selected.id);
  if (index >= 0 && !equal(rows[index], basis.selected)) fail();
  // A complete bounded window is required. Even a matching partial prefix grants no path result.
  const reason = head.lineage.status === 'truncated' ? 'truncated' : head.lineage.status === 'unavailable' ? 'unavailable'
    : rows.some(row => row.admission !== 'complete') ? 'pending' : index < 0 ? 'not_observed'
      : basis.head.id === basis.selected.id ? 'same_event' : 'verified_path';
  const status = reason === 'same_event' || reason === 'verified_path' ? reason : 'unknown';
  return { status, reason, before_observed_at: before.observed_at, window_observed_at: head.observed_at, after_observed_at: after.observed_at,
    selected_id: basis.selected.id, selected_packet_sha256: basis.selected.packet_sha256!, head_id: basis.head.id, head_packet_sha256: basis.head.packet_sha256!,
    window: RETURNED_LINEAGE_WINDOW, observed_count: rows.length, path: status === 'unknown' ? [] : structuredClone(rows.slice(0, index + 1)),
    source_verification: 'not_checked', legal_readiness: 'not_established', qualification_granted: false };
}
