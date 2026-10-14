import { canonicalJson } from '../pages/matter/sourceReviewTypes';
import { verifyRenewalMetadata, type RenewalMetadata } from '../pages/matter/sourceRenewalTypes';
import { navigationIdentifier, navigationReviewId, sourceContextHref, verifyNavigation, type NavigationMetadata } from '../pages/sourceContextNavigationTypes';
import type { ReturnIntent, ReturnReconciliation } from './portfolioReturn';
import { returnComparisonLinks, verifyReturnSelection } from './returnComparison';

export type RenewalHandoff = { recipe: 'private-comparison-renewal-handoff-v1'; matter_id: string; analysis_id: string; context_id: string; manifest_sha256: string; frozen_version_id: string; version_id: string; head_id: string | null;
  head_state: 'unreviewed' | 'changes_requested' | 'reviewed_conditional'; observed_at: string };
export function validateRenewalHandoff(value: RenewalHandoff, intent?: ReturnIntent) {
  if (!value || canonicalJson(Object.keys(value).sort()) !== canonicalJson(['recipe', 'matter_id', 'analysis_id', 'context_id', 'manifest_sha256', 'frozen_version_id', 'version_id', 'head_id', 'head_state', 'observed_at'].sort())
    || !navigationIdentifier(value.matter_id) || !navigationIdentifier(value.analysis_id) || !/^sac-[a-f0-9]{20}-[a-f0-9]{32}$/.test(value.context_id) || !/^[a-f0-9]{64}$/.test(value.manifest_sha256) || !navigationIdentifier(value.frozen_version_id)
    || value.recipe !== 'private-comparison-renewal-handoff-v1' || !navigationIdentifier(value.version_id) || !['unreviewed', 'changes_requested', 'reviewed_conditional'].includes(value.head_state)
    || (value.head_id !== null && !navigationReviewId(value.head_id)) || (value.head_state === 'unreviewed') !== (value.head_id === null)
    || typeof value.observed_at !== 'string' || value.observed_at.length > 40 || !Number.isFinite(Date.parse(value.observed_at))) throw new Error('Yenileme geçişinin tam hedefi doğrulanamadı.');
  if (intent && (value.matter_id !== intent.target.matter_id || value.analysis_id !== intent.target.analysis_id || value.context_id !== intent.target.context_id
    || value.manifest_sha256 !== intent.target.manifest_sha256 || value.frozen_version_id !== intent.target.version_id)) throw new Error('Yenileme geçişi başka özel kayda ait.');
}
export function captureRenewalHandoff(intent: ReturnIntent, result: ReturnReconciliation): RenewalHandoff | null {
  if (result.state !== 'observed' || !returnComparisonLinks(intent, result, '0'.repeat(32)).context || !result.comparison.current.version_id
    || result.comparison.current.head_state === 'unknown' || result.context_state !== 'complete' || !['complete', 'not_recorded'].includes(result.review_state)) return null;
  const fixed = result.comparison.fixed;
  const value: RenewalHandoff = { recipe: 'private-comparison-renewal-handoff-v1', matter_id: fixed.matter_id, analysis_id: fixed.analysis_id, context_id: fixed.context_id, manifest_sha256: fixed.manifest_sha256, frozen_version_id: fixed.version_id, version_id: result.comparison.current.version_id,
    head_id: result.comparison.current.head_id, head_state: result.comparison.current.head_state, observed_at: result.comparison.current.observed_at };
  validateRenewalHandoff(value, intent); return value;
}
export function renewalHandoffHref(intent: ReturnIntent, token: string) {
  const t = intent.target, href = sourceContextHref(t.matter_id, t.analysis_id, t.context_id, undefined, token);
  return href ? `${href}&prepare=renewal` : null;
}
export function verifyRenewalNavigation(intent: ReturnIntent, handoff: RenewalHandoff, meta: NavigationMetadata) {
  validateRenewalHandoff(handoff, intent); verifyReturnSelection(intent, meta, null);
  if (meta.analysis.current_version_id !== handoff.version_id || meta.historical_review.id !== handoff.head_id || meta.historical_review.state !== handoff.head_state
    || meta.admission.context_state !== 'complete' || !['complete', 'not_recorded'].includes(meta.admission.review_state)) throw new Error('Yenileme hedef sürümü, karar başı veya kabulü değişti; portföy karşılaştırmasını yeniden gözlemleyin.');
}
export function verifyPreparedRenewal(intent: ReturnIntent, handoff: RenewalHandoff, before: NavigationMetadata, value: RenewalMetadata, after: NavigationMetadata) {
  verifyRenewalNavigation(intent, handoff, before); verifyRenewalNavigation(intent, handoff, after);
  verifyRenewalMetadata(value, intent.target.matter_id, intent.target.analysis_id, intent.target.context_id);
  if (value.manifest_sha256 !== intent.target.manifest_sha256 || value.version_id !== intent.target.version_id || value.review_id !== handoff.head_id
    || !value.admission_completed || !value.can_record || before.analysis.revision !== after.analysis.revision)
    throw new Error('Yenilemenin özgün bağları veya yazma yetkisi değişti; yeniden gözlemleyin.');
}
export function successorIntent(intent: ReturnIntent, id: string, meta: NavigationMetadata, expected?: { version_id: string; manifest_sha256: string }): ReturnIntent {
  verifyNavigation(meta, { kind: 'selected', matter_id: intent.target.matter_id, analysis_id: intent.target.analysis_id, context_id: id });
  if (id === intent.target.context_id || meta.integrity !== 'verified' || expected && (meta.context.version_id !== expected.version_id || meta.context.manifest_sha256 !== expected.manifest_sha256))
    throw new Error('Bildirilen yeni kaydın ayrı tam kimliği doğrulanamadı.');
  return { recipe: 'private-portfolio-return-intent-v2', filters: structuredClone(intent.filters), target: {
    matter_id: meta.matter_id, analysis_id: meta.analysis_id, context_id: meta.context_id, version_id: meta.context.version_id, manifest_sha256: meta.context.manifest_sha256,
    head_id: meta.historical_review.id, head_state: meta.historical_review.state, observed_at: meta.observed_at, current_version_id: meta.analysis.current_version_id,
    version_observed_at: meta.observed_at, review_id: null, review_packet_sha256: null } };
}
