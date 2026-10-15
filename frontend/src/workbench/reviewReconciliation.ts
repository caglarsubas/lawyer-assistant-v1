import { canonicalJson } from '../pages/matter/sourceReviewTypes';
import { navigationIdentifier, navigationReviewId } from '../pages/sourceContextNavigationTypes';
import { verifyReviewLineage, type ReviewLineage, type ReviewMetadata } from '../pages/sourceReviewLineageTypes';
import { validateReturn, type ReturnIntent } from './portfolioReturn';
import { verifyReturnSelection } from './returnComparison';

export type ReviewReceipt = { request_id: string; expected_request_sha256: string; expected_manifest_sha256: string; expected_review_id: string | null; version_id: string };
export type ReviewObservation = { recipe: 'private-source-review-reconciliation-v1'; matter_id: string; analysis_id: string; context_id: string; observed_at: string; receipt: ReviewReceipt;
  outcome: 'verified' | 'not_observed' | 'unavailable'; context: { id: string; version_id: string; manifest_sha256: string; packet_sha256: string } | null;
  review: (ReviewMetadata & { previous_review_packet_sha256: string | null }) | null;
  admission: { context: 'complete' | 'pending'; review: 'complete' | 'pending'; predecessor: 'complete' | 'pending' | 'not_recorded' } | null;
  current_head: 'not_checked'; source_verification: 'not_checked'; legal_readiness: 'not_established'; qualification_granted: false; effects_replayed: false };
const hash = (v: unknown): v is string => typeof v === 'string' && /^[a-f0-9]{64}$/.test(v);
const closed = (v: unknown, keys: string[]): v is Record<string, unknown> => !!v && typeof v === 'object' && canonicalJson(Object.keys(v).sort()) === canonicalJson([...keys].sort());
export function validateReviewReceipt(v: ReviewReceipt) {
  if (!closed(v, ['request_id', 'expected_request_sha256', 'expected_manifest_sha256', 'expected_review_id', 'version_id'])
    || typeof v.request_id !== 'string' || !/^[a-f0-9]{32}$/.test(v.request_id) || !hash(v.expected_request_sha256) || !hash(v.expected_manifest_sha256)
    || v.expected_review_id !== null && !navigationReviewId(v.expected_review_id) || !navigationIdentifier(v.version_id)) throw new Error('Tam bağımsız inceleme istek özeti doğrulanamadı.');
}
export async function reviewReceipt(body: Record<string, unknown>, context: { version_id: string; manifest_sha256: string }): Promise<ReviewReceipt> {
  const { request_id, ...submitted } = body;
  // Match the server's legacy-compatible review canonicalization.
  if (submitted.renewal_assessment === null) delete submitted.renewal_assessment;
  const sha = [...new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(canonicalJson(submitted))))].map(v => v.toString(16).padStart(2, '0')).join('');
  const receipt: ReviewReceipt = { request_id: request_id as string, expected_request_sha256: sha, expected_manifest_sha256: submitted.expected_manifest_sha256 as string,
    expected_review_id: submitted.expected_review_id as string | null, version_id: context.version_id };
  validateReviewReceipt(receipt);
  if (receipt.expected_manifest_sha256 !== context.manifest_sha256) throw new Error('İstek seçilen sabit kanıta ait değil.');
  return receipt;
}
export function reviewReceiptQuery(value: ReviewReceipt) { validateReviewReceipt(value); return new URLSearchParams(Object.entries(value).filter(([, v]) => v !== null) as [string, string][]).toString(); }
export function verifyReviewObservation(v: ReviewObservation, receipt: ReviewReceipt, intent: ReturnIntent) {
  validateReviewReceipt(receipt); validateReturn(intent); const t = intent.target;
  if (receipt.version_id !== t.version_id || receipt.expected_manifest_sha256 !== t.manifest_sha256
    || !closed(v, ['recipe', 'matter_id', 'analysis_id', 'context_id', 'observed_at', 'receipt', 'outcome', 'context', 'review', 'admission', 'current_head', 'source_verification', 'legal_readiness', 'qualification_granted', 'effects_replayed'])
    || v.recipe !== 'private-source-review-reconciliation-v1' || v.matter_id !== t.matter_id || v.analysis_id !== t.analysis_id || v.context_id !== t.context_id
    || canonicalJson(v.receipt) !== canonicalJson(receipt) || typeof v.observed_at !== 'string' || v.observed_at.length > 40 || !Number.isFinite(Date.parse(v.observed_at))
    || !['verified', 'not_observed', 'unavailable'].includes(v.outcome) || v.current_head !== 'not_checked' || v.source_verification !== 'not_checked'
    || v.legal_readiness !== 'not_established' || v.qualification_granted !== false || v.effects_replayed !== false) throw new Error('Salt okunur bağımsız inceleme gözlemi doğrulanamadı.');
  if (v.outcome !== 'verified') { if (v.context !== null || v.review !== null || v.admission !== null) throw new Error('Bilinmeyen sonuç karar veya izin veremez.'); return; }
  const c = v.context, r = v.review, a = v.admission;
  if (!c || !r || !a || !closed(c, ['id', 'version_id', 'manifest_sha256', 'packet_sha256']) || c.id !== t.context_id || c.version_id !== receipt.version_id || c.manifest_sha256 !== receipt.expected_manifest_sha256 || !hash(c.packet_sha256)
    || !closed(r, ['id', 'state', 'sequence', 'recorded_at', 'packet_sha256', 'manifest_sha256', 'previous_review_id', 'admission', 'integrity', 'previous_review_packet_sha256'])
    || !navigationReviewId(r.id) || !['changes_requested', 'reviewed_conditional'].includes(r.state) || !Number.isSafeInteger(r.sequence) || r.sequence! < 1 || r.sequence! > 100
    || typeof r.recorded_at !== 'string' || r.recorded_at.length > 40 || !Number.isFinite(Date.parse(r.recorded_at)) || !hash(r.packet_sha256) || r.manifest_sha256 !== c.manifest_sha256
    || r.previous_review_id !== receipt.expected_review_id || (r.sequence === 1) !== (r.previous_review_id === null) || (r.previous_review_id === null ? r.previous_review_packet_sha256 !== null : !hash(r.previous_review_packet_sha256))
    || r.integrity !== 'verified' || !['complete', 'pending'].includes(r.admission) || !closed(a, ['context', 'review', 'predecessor']) || !['complete', 'pending'].includes(a.context)
    || a.review !== r.admission || (r.previous_review_id === null ? a.predecessor !== 'not_recorded' : !['complete', 'pending'].includes(a.predecessor))) throw new Error('Tam karar, kanıt sürümü veya önceki karar bağı değişti.');
}
export const completeReviewAdmissions = (v: ReviewObservation) => v.outcome === 'verified' && v.admission?.context === 'complete' && v.admission.review === 'complete' && ['complete', 'not_recorded'].includes(v.admission.predecessor);
export function verifySameReviewOutcome(before: ReviewObservation, after: ReviewObservation, intent: ReturnIntent) {
  verifyReviewObservation(before, before.receipt, intent); verifyReviewObservation(after, before.receipt, intent);
  if (!completeReviewAdmissions(before) || !completeReviewAdmissions(after) || canonicalJson({ c: before.context, r: before.review, a: before.admission }) !== canonicalJson({ c: after.context, r: after.review, a: after.admission })) throw new Error('Tam karar veya kabul gözlemi değişti; yeniden gözlemleyin.');
}
export function reconciledReviewIntent(intent: ReturnIntent, observation: ReviewObservation, history: ReviewLineage): ReturnIntent {
  verifySameReviewOutcome(observation, observation, intent); const r = observation.review!;
  verifyReviewLineage(history, { kind: 'selected', matter_id: intent.target.matter_id, analysis_id: intent.target.analysis_id, context_id: intent.target.context_id, review_id: r.id });
  verifyReturnSelection(intent, history.context_navigation, null);
  const { previous_review_packet_sha256: _previous, ...expected } = r;
  if (canonicalJson(history.selected_review) !== canonicalJson(expected) || !history.tools_available || history.context_navigation.admission.context_state !== 'complete'
    || !['complete', 'not_recorded'].includes(history.context_navigation.admission.review_state)) throw new Error('Seçilen kararın yeni yetkili gözlemi doğrulanamadı.');
  const next = structuredClone(intent), m = history.context_navigation;
  next.target = { ...next.target, review_id: r.id, review_packet_sha256: r.packet_sha256, head_id: m.historical_review.id, head_state: m.historical_review.state,
    observed_at: m.observed_at, current_version_id: m.analysis.current_version_id, version_observed_at: m.observed_at };
  validateReturn(next); return next;
}
/** A queue comparison keeps its original baseline, separate from fresh navigation. */
export function reconciledReviewReturnIntent(intent: ReturnIntent, observation: ReviewObservation, history: ReviewLineage): ReturnIntent {
  if (intent.target.review_id !== null || intent.target.review_packet_sha256 !== null) throw new Error('Yeni inceleme dönüşü önceki tarihsel seçimi değiştiremez.');
  const verified = reconciledReviewIntent(intent, observation, history), next = structuredClone(intent);
  next.target.review_id = verified.target.review_id; next.target.review_packet_sha256 = verified.target.review_packet_sha256;
  validateReturn(next); return next;
}
