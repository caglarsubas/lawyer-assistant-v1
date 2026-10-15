import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { RenewalOutcomeSummary } from '../pages/ComparisonRenewalPage';
import { metadata } from '../pages/matter/sourceRenewalFixtures';
import { ApiError } from '../api';
import { renewalReceipt, renewalReceiptQuery, uncertainRenewalOutcome, validateRenewalReceipt, verifyRenewalObservation, type RenewalObservation, type RenewalReceipt } from './renewalReconciliation';
const parent = `sac-${'a'.repeat(20)}-${'b'.repeat(32)}`, child = `sac-${'a'.repeat(20)}-${'c'.repeat(32)}`;
const receipt = (): RenewalReceipt => ({ request_id: 'd'.repeat(32), expected_request_sha256: '1'.repeat(64), expected_preview_sha256: '2'.repeat(64), parent_context_id: parent,
  expected_parent_manifest_sha256: '3'.repeat(64), expected_parent_review_id: null, parent_version_id: 'old1', version_id: 'new1' });
const result = (): RenewalObservation => ({ recipe: 'private-renewal-reconciliation-v1', matter_id: 'matter1', analysis_id: 'analysis1', observed_at: '2026-10-15T00:00:00Z', receipt: receipt(), outcome: 'verified',
  successor: { id: child, version_id: 'new1', manifest_sha256: '2'.repeat(64), packet_sha256: '4'.repeat(64) },
  lineage: { scope: 'one_historical_link', parent_context_id: parent, parent_version_id: 'old1', parent_manifest_sha256: '3'.repeat(64), parent_packet_sha256: '5'.repeat(64), parent_review_id: null, parent_review_packet_sha256: null,
    comparison_sha256: '6'.repeat(64), depth: 1, current_parent_head: 'not_checked', legal_equivalence: 'not_assessed' },
  admission: { successor: 'complete', parent: 'complete', parent_review: 'not_recorded' }, source_verification: 'not_checked', legal_readiness: 'not_established', review_inheritance: 'none', qualification_granted: false, effects_replayed: false });
describe('read-only renewal reconciliation', () => {
  it.each([new SyntaxError('Truncated JSON after commit'), new TypeError('Body stream lost'), new ApiError('Gateway outcome unknown', 502), new ApiError('Connection lost', 0), new ApiError('Truncated conflict', 409), new ApiError('Timeout', 408), new ApiError('Throttled outcome', 429)])('retains read-only receipt for uncertain %s without replay', cause => {
    expect(uncertainRenewalOutcome(cause)).toBe(true);
  });
  it('closes aborted, forbidden and invalid writes instead of treating them as an admitted result', () => {
    for (const cause of [new DOMException('Retired', 'AbortError'), new ApiError('Forbidden', 403), new ApiError('Invalid request', 422)]) expect(uncertainRenewalOutcome(cause)).toBe(false);
  });
  it('retains bounded exact request identity and omits null head from the query', () => {
    validateRenewalReceipt(receipt()); const q = new URLSearchParams(renewalReceiptQuery(receipt()));
    expect(q.get('request_id')).toBe(receipt().request_id); expect(q.has('expected_parent_review_id')).toBe(false);
    expect(() => validateRenewalReceipt({ ...receipt(), note: 'PRIVATE' } as never)).toThrow();
    expect(() => validateRenewalReceipt({ ...receipt(), request_id: 'malformed' })).toThrow();
  });
  it('hashes submitted content excluding nonce and retains no request body', async () => {
    const body = { request_id: 'a'.repeat(32), expected_preview_sha256: '2'.repeat(64), version_id: 'new1', title: 'PRIVATE TITLE', purpose: 'PRIVATE PURPOSE',
      renewal: { parent_context_id: metadata.id, expected_parent_manifest_sha256: metadata.manifest_sha256, expected_parent_review_id: metadata.review_id, reason: 'PRIVATE REASON' } };
    const a = await renewalReceipt(body, metadata), b = await renewalReceipt({ ...body, request_id: 'b'.repeat(32) }, metadata);
    expect(a.expected_request_sha256).toBe(b.expected_request_sha256); expect(JSON.stringify(a)).not.toContain('PRIVATE'); expect(a.parent_version_id).toBe(metadata.version_id);
    expect((await renewalReceipt({ ...body, purpose: 'different' }, metadata)).expected_request_sha256).not.toBe(a.expected_request_sha256);
    await expect(renewalReceipt({ ...body, renewal: { ...body.renewal, parent_context_id: child } }, metadata)).rejects.toThrow();
  });
  it('keeps structural verification distinct from pending admission and source permission', () => {
    const v = result(); v.admission!.successor = 'pending'; verifyRenewalObservation(v, receipt(), 'matter1', 'analysis1');
    const html = renderToStaticMarkup(<RenewalOutcomeSummary value={v} />);
    expect(html).toContain('Bekliyor'); expect(html).toContain('Bekleyen kabul tamamlanmaz'); expect(html).toContain('yeni bağımsız inceleme');
  });
  it.each(['not_observed', 'unavailable'] as const)('does not turn %s into identity or retry authority', outcome => {
    const v = { ...result(), outcome, successor: null, lineage: null, admission: null }; verifyRenewalObservation(v, receipt(), 'matter1', 'analysis1');
    expect(renderToStaticMarkup(<RenewalOutcomeSummary value={v} />)).not.toContain(child);
    expect(() => verifyRenewalObservation({ ...v, successor: result().successor }, receipt(), 'matter1', 'analysis1')).toThrow();
  });
  it.each(['foreign', 'nonce', 'hash', 'version', 'parent', 'parent_version', 'review', 'packet', 'inheritance', 'replay', 'approval', 'notes', 'admission'] as const)('rejects %s substitution or promotion', fault => {
    const v = result();
    if (fault === 'foreign') v.matter_id = 'other';
    if (fault === 'nonce') v.receipt.request_id = 'f'.repeat(32);
    if (fault === 'hash') v.successor!.manifest_sha256 = '9'.repeat(64);
    if (fault === 'version') v.successor!.version_id = 'other';
    if (fault === 'parent') v.lineage!.parent_context_id = child;
    if (fault === 'parent_version') v.lineage!.parent_version_id = 'other';
    if (fault === 'review') v.lineage!.parent_review_id = `sar-${'a'.repeat(20)}-${'c'.repeat(32)}`;
    if (fault === 'packet') v.lineage!.parent_packet_sha256 = 'bad';
    if (fault === 'inheritance') v.review_inheritance = 'inherited' as never;
    if (fault === 'replay') v.effects_replayed = true as never;
    if (fault === 'approval') v.qualification_granted = true as never;
    if (fault === 'notes') Object.assign(v.lineage!, { note: 'PRIVATE old quote' });
    if (fault === 'admission') v.admission!.successor = 'unknown' as never;
    expect(() => verifyRenewalObservation(v, receipt(), 'matter1', 'analysis1')).toThrow();
  });
});
