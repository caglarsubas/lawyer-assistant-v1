import { ApiError } from '../api';
import { canonicalJson } from '../pages/matter/sourceReviewTypes';
import type { RenewalMetadata } from '../pages/matter/sourceRenewalTypes';
import { navigationContextId, navigationIdentifier, navigationReviewId } from '../pages/sourceContextNavigationTypes';

export type RenewalReceipt = { request_id: string; expected_request_sha256: string; expected_preview_sha256: string; parent_context_id: string;
  expected_parent_manifest_sha256: string; expected_parent_review_id: string | null; parent_version_id: string; version_id: string };
export type RenewalObservation = { recipe: 'private-renewal-reconciliation-v1'; matter_id: string; analysis_id: string; observed_at: string; receipt: RenewalReceipt;
  outcome: 'verified' | 'not_observed' | 'unavailable'; successor: { id: string; version_id: string; manifest_sha256: string; packet_sha256: string } | null;
  lineage: { scope: 'one_historical_link'; parent_context_id: string; parent_version_id: string; parent_manifest_sha256: string; parent_packet_sha256: string;
    parent_review_id: string | null; parent_review_packet_sha256: string | null; comparison_sha256: string; depth: number; current_parent_head: 'not_checked'; legal_equivalence: 'not_assessed' } | null;
  admission: { successor: 'complete' | 'pending'; parent: 'complete' | 'pending'; parent_review: 'complete' | 'pending' | 'not_recorded' } | null;
  source_verification: 'not_checked'; legal_readiness: 'not_established'; review_inheritance: 'none'; qualification_granted: false; effects_replayed: false };
const hash = (v: unknown): v is string => typeof v === 'string' && /^[a-f0-9]{64}$/.test(v);
const closed = (v: unknown, keys: string[]): v is Record<string, unknown> => !!v && typeof v === 'object' && canonicalJson(Object.keys(v).sort()) === canonicalJson([...keys].sort());
export function uncertainRenewalOutcome(cause: unknown) {
  if (cause instanceof ApiError) return ![400, 401, 403, 404, 422].includes(cause.status);
  return !(cause instanceof DOMException && cause.name === 'AbortError');
}
export function validateRenewalReceipt(v: RenewalReceipt) {
  if (!closed(v, ['request_id', 'expected_request_sha256', 'expected_preview_sha256', 'parent_context_id', 'expected_parent_manifest_sha256', 'expected_parent_review_id', 'parent_version_id', 'version_id'])
    || typeof v.request_id !== 'string' || !/^[a-f0-9]{32}$/.test(v.request_id) || !hash(v.expected_request_sha256) || !hash(v.expected_preview_sha256) || !hash(v.expected_parent_manifest_sha256)
    || !navigationContextId(v.parent_context_id) || !navigationIdentifier(v.parent_version_id) || !navigationIdentifier(v.version_id)
    || v.expected_parent_review_id !== null && !navigationReviewId(v.expected_parent_review_id)) throw new Error('Tam yenileme istek özeti doğrulanamadı.');
}
export async function renewalReceipt(body: Record<string, unknown>, parent: RenewalMetadata): Promise<RenewalReceipt> {
  const { request_id, ...submitted } = body, renewal = submitted.renewal as Record<string, unknown>;
  const bytes = new TextEncoder().encode(canonicalJson(submitted));
  const sha = [...new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))].map(v => v.toString(16).padStart(2, '0')).join('');
  const receipt: RenewalReceipt = { request_id: request_id as string, expected_request_sha256: sha, expected_preview_sha256: submitted.expected_preview_sha256 as string,
    parent_context_id: renewal?.parent_context_id as string, expected_parent_manifest_sha256: renewal?.expected_parent_manifest_sha256 as string,
    expected_parent_review_id: renewal?.expected_parent_review_id as string | null, parent_version_id: parent.version_id, version_id: submitted.version_id as string };
  validateRenewalReceipt(receipt);
  if (receipt.parent_context_id !== parent.id || receipt.expected_parent_manifest_sha256 !== parent.manifest_sha256 || receipt.expected_parent_review_id !== parent.review_id) throw new Error('İstek özgün yenileme bağlamına ait değil.');
  return receipt;
}
export function renewalReceiptQuery(receipt: RenewalReceipt) { validateRenewalReceipt(receipt); return new URLSearchParams(Object.entries(receipt).filter(([, v]) => v !== null) as [string, string][]).toString(); }
export function verifyRenewalObservation(v: RenewalObservation, receipt: RenewalReceipt, matter: string, analysis: string) {
  validateRenewalReceipt(receipt);
  if (!closed(v, ['recipe', 'matter_id', 'analysis_id', 'observed_at', 'receipt', 'outcome', 'successor', 'lineage', 'admission', 'source_verification', 'legal_readiness', 'review_inheritance', 'qualification_granted', 'effects_replayed'])
    || v.recipe !== 'private-renewal-reconciliation-v1' || v.matter_id !== matter || v.analysis_id !== analysis || canonicalJson(v.receipt) !== canonicalJson(receipt)
    || typeof v.observed_at !== 'string' || v.observed_at.length > 40 || !Number.isFinite(Date.parse(v.observed_at)) || !['verified', 'not_observed', 'unavailable'].includes(v.outcome)
    || v.source_verification !== 'not_checked' || v.legal_readiness !== 'not_established' || v.review_inheritance !== 'none' || v.qualification_granted !== false || v.effects_replayed !== false) throw new Error('Salt okunur yenileme gözlemi doğrulanamadı.');
  if (v.outcome !== 'verified') { if (v.successor !== null || v.lineage !== null || v.admission !== null) throw new Error('Bilinmeyen sonuç kimlik veya izin veremez.'); return; }
  const s = v.successor, l = v.lineage, a = v.admission;
  if (!s || !l || !a || !closed(s, ['id', 'version_id', 'manifest_sha256', 'packet_sha256']) || !navigationContextId(s.id) || s.id === receipt.parent_context_id
    || s.version_id !== receipt.version_id || s.manifest_sha256 !== receipt.expected_preview_sha256 || !hash(s.packet_sha256)
    || !closed(l, ['scope', 'parent_context_id', 'parent_version_id', 'parent_manifest_sha256', 'parent_packet_sha256', 'parent_review_id', 'parent_review_packet_sha256', 'comparison_sha256', 'depth', 'current_parent_head', 'legal_equivalence'])
    || l.scope !== 'one_historical_link' || l.parent_context_id !== receipt.parent_context_id || l.parent_version_id !== receipt.parent_version_id || l.parent_manifest_sha256 !== receipt.expected_parent_manifest_sha256
    || l.parent_review_id !== receipt.expected_parent_review_id || !hash(l.parent_packet_sha256) || !hash(l.comparison_sha256) || !Number.isSafeInteger(l.depth) || l.depth < 1 || l.depth > 8
    || (l.parent_review_id === null ? l.parent_review_packet_sha256 !== null : !hash(l.parent_review_packet_sha256)) || l.current_parent_head !== 'not_checked' || l.legal_equivalence !== 'not_assessed'
    || !closed(a, ['successor', 'parent', 'parent_review']) || !['complete', 'pending'].includes(a.successor) || !['complete', 'pending'].includes(a.parent)
    || !(l.parent_review_id === null ? a.parent_review === 'not_recorded' : ['complete', 'pending'].includes(a.parent_review))) throw new Error('Tam ardıl, tarihsel yenileme bağı veya kabul durumu değişti.');
}
