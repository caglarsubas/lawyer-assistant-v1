import { hasExactKeys, scalarDataRecordsEqual } from './privateObservationValidation';
import { canonicalJson } from '../pages/matter/sourceReviewTypes';
import { navigationIdentifier, type NavigationMetadata } from '../pages/sourceContextNavigationTypes';
import { verifyReviewMetadata, type ReviewLineage, type ReviewMetadata } from '../pages/sourceReviewLineageTypes';
import { validateReturn, type ReturnIntent } from './portfolioReturn';
import { compareReturnIdentities, verifyReturnSelection, type IdentityRelation, type ReturnComparison } from './returnComparison';

/** Metadata from the five fresh preparation reads, separate from the original queue baseline. */
export type ReviewPathHandoff = {
  recipe: 'private-review-path-handoff-v1'; matter_id: string; analysis_id: string; context_id: string;
  frozen_version_id: string; manifest_sha256: string; selected: ReviewMetadata; head: ReviewMetadata;
  current_version_id: string; revision: number; observed_at: [string, string, string, string, string];
};
const equal = (a: unknown, b: unknown) => canonicalJson(a) === canonicalJson(b);
const fail = (): never => { throw new Error('Zincir geçişi ile hedefin tam kimlik gözlemleri doğrulanamadı. Yeni portföy gözlemi gerekli; başka kayıt kullanılmadı.'); };
const immutable = ({ admission: _admission, integrity: _integrity, ...value }: ReviewMetadata) => value;
function equalImmutable(left: ReviewMetadata, right: ReviewMetadata) {
  const a = immutable(left), b = immutable(right); return scalarDataRecordsEqual(a, b) ?? equal(a, b);
}
export function validateReviewPathHandoff(value: ReviewPathHandoff, intent: ReturnIntent) {
  validateReturn(intent); const t = intent.target;
  if (!value || !hasExactKeys(value, ['recipe', 'matter_id', 'analysis_id', 'context_id', 'frozen_version_id', 'manifest_sha256', 'selected', 'head', 'current_version_id', 'revision', 'observed_at'])
    || value.recipe !== 'private-review-path-handoff-v1' || value.matter_id !== t.matter_id || value.analysis_id !== t.analysis_id || value.context_id !== t.context_id
    || value.frozen_version_id !== t.version_id || value.manifest_sha256 !== t.manifest_sha256 || !navigationIdentifier(value.current_version_id)
    || !Number.isSafeInteger(value.revision) || value.revision < 1 || !Array.isArray(value.observed_at) || value.observed_at.length !== 5
    || value.observed_at.some((time, index) => typeof time !== 'string' || time.length > 40 || !Number.isFinite(Date.parse(time)) || index > 0 && Date.parse(time) < Date.parse(value.observed_at[index - 1]))) fail();
  verifyReviewMetadata(value.selected, t.manifest_sha256); verifyReviewMetadata(value.head, t.manifest_sha256);
  if (!t.review_id || !t.review_packet_sha256 || value.selected.id !== t.review_id || value.selected.packet_sha256 !== t.review_packet_sha256
    || [value.selected, value.head].some(row => row.integrity !== 'verified' || row.admission !== 'complete')
    || (value.selected.id === value.head.id ? !equal(value.selected, value.head) : value.head.sequence! <= value.selected.sequence!)) fail();
}
export type ReviewPathComparison = {
  original: ReturnComparison; handoff: ReviewPathHandoff;
  destination: { head: ReviewMetadata | null; current_version_id: string | null; revision: number; observed_at: string;
    context_admission: string; selected_admission: string; head_admission: string };
  head_relation: IdentityRelation; version_relation: IdentityRelation; revision_relation: 'same' | 'different';
};
export type ReviewPathDestination = { metadata: NavigationMetadata; selected: ReviewMetadata; head: ReviewMetadata | null };
/** Validate a retained metadata observation without inventing a predecessor window. */
export function verifyReviewPathDestination(intent: ReturnIntent, handoff: ReviewPathHandoff, value: ReviewPathDestination) {
  validateReviewPathHandoff(handoff, intent);
  if (!value || !hasExactKeys(value, ['head', 'metadata', 'selected'])) fail();
  const m = value.metadata, selected = value.selected, head = value.head;
  verifyReturnSelection(intent, m, null); verifyReviewMetadata(selected, intent.target.manifest_sha256);
  if (selected.integrity !== 'verified' || !equalImmutable(selected, handoff.selected)
    || Date.parse(m.observed_at) < Date.parse(handoff.observed_at[4]) || m.analysis.revision < handoff.revision) fail();
  if (head !== null) {
    verifyReviewMetadata(head, intent.target.manifest_sha256);
    if (head.id !== m.historical_review.id || head.id === selected.id && !equal(head, selected)) fail();
    if (head.integrity === 'verified' && (head.state !== m.historical_review.state || head.admission !== m.admission.review_state
      || head.id === handoff.head.id && !equalImmutable(head, handoff.head))) fail();
  }
}
/** Fresh authorized metadata only. Changed current identities are observations, never a new selection. */
export function compareReviewPathHandoff(intent: ReturnIntent, handoff: ReviewPathHandoff, history: ReviewLineage): ReviewPathComparison {
  const original = compareReturnIdentities(intent, history.context_navigation, history);
  const selected = history.selected_review, head = history.current_head, m = history.context_navigation;
  verifyReviewPathDestination(intent, handoff, { metadata: m, selected, head });
  const knownHead = head?.integrity === 'verified' && m.historical_review.state !== 'unknown';
  return structuredClone({ original, handoff,
    destination: { head, current_version_id: m.analysis.current_version_id, revision: m.analysis.revision, observed_at: history.observed_at,
      context_admission: m.admission.context_state, selected_admission: selected.admission, head_admission: m.admission.review_state },
    head_relation: knownHead ? head.id === handoff.head.id ? 'same' : 'different' : 'unknown',
    version_relation: m.analysis.current_version_id === null ? 'unknown' : m.analysis.current_version_id === handoff.current_version_id ? 'same' : 'different',
    revision_relation: m.analysis.revision === handoff.revision ? 'same' : 'different' });
}
