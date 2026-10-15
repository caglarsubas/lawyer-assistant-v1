import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { ReviewOutcomeSummary } from '../pages/IndependentReviewPreparationPage';
import type { NavigationMetadata } from '../pages/sourceContextNavigationTypes';
import type { ReviewLineage, ReviewMetadata } from '../pages/sourceReviewLineageTypes';
import type { ReturnIntent } from './portfolioReturn';
import { completeReviewAdmissions, reconciledReviewIntent, reviewReceipt, reviewReceiptQuery, verifyReviewObservation, verifySameReviewOutcome, type ReviewObservation } from './reviewReconciliation';

const cid = `sac-${'a'.repeat(20)}-${'b'.repeat(32)}`, rid = (n: number) => `sar-${'c'.repeat(20)}-${n.toString(16).padStart(32, '0')}`, stamp = '2026-10-15T00:00:00Z';
const receipt = () => ({ request_id: 'd'.repeat(32), expected_request_sha256: '1'.repeat(64), expected_manifest_sha256: '2'.repeat(64), expected_review_id: rid(1), version_id: 'v1' });
const intent = (): ReturnIntent => ({ recipe: 'private-portfolio-return-intent-v2', filters: { customer_ids: ['A', 'B'], date_field: 'relevant_date', date_from: '2020-01-01', date_to: '2030-12-31', source_date_from: '2026-10-01', source_date_to: '2026-10-31', bucket: 'action_required' }, target: { matter_id: 'matter1', analysis_id: 'analysis1', context_id: cid, version_id: 'v1', manifest_sha256: '2'.repeat(64), head_id: rid(1), head_state: 'reviewed_conditional', current_version_id: 'v1', version_observed_at: stamp, review_id: null, review_packet_sha256: null, observed_at: stamp } });
const event = (n: number): ReviewMetadata => ({ id: rid(n), state: 'changes_requested', sequence: n, recorded_at: stamp, packet_sha256: '3'.repeat(64), manifest_sha256: '2'.repeat(64), previous_review_id: rid(n - 1), admission: 'complete', integrity: 'verified' });
const value = (): ReviewObservation => ({ recipe: 'private-source-review-reconciliation-v1', matter_id: 'matter1', analysis_id: 'analysis1', context_id: cid, observed_at: stamp, receipt: receipt(), outcome: 'verified', context: { id: cid, version_id: 'v1', manifest_sha256: '2'.repeat(64), packet_sha256: '4'.repeat(64) }, review: { ...event(2), previous_review_packet_sha256: '5'.repeat(64) }, admission: { context: 'complete', review: 'complete', predecessor: 'complete' }, current_head: 'not_checked', source_verification: 'not_checked', legal_readiness: 'not_established', qualification_granted: false, effects_replayed: false });
const history = (): ReviewLineage => {
  const meta: NavigationMetadata = { recipe: 'private-source-context-navigation-v1', matter_id: 'matter1', analysis_id: 'analysis1', context_id: cid, observed_at: stamp, analysis: { id: 'analysis1', current_version_id: 'v2', revision: 4 }, context: { id: cid, version_id: 'v1', manifest_sha256: '2'.repeat(64), recorded_at: stamp }, admission: { context_state: 'complete', review_state: 'complete' }, historical_review: { id: rid(3), state: 'changes_requested', recorded_at: stamp }, version_relation: 'different', integrity: 'verified', tools_available: true, source_verification: 'not_checked', legal_readiness: 'not_established', qualification_granted: false };
  return { recipe: 'private-source-review-lineage-v1', matter_id: 'matter1', analysis_id: 'analysis1', context_id: cid, review_id: rid(2), observed_at: stamp, context_navigation: meta, selected_review: event(2), current_head: event(3), head_relationship: 'different_from_head', lineage: { scope: 'selected_predecessors_only', status: 'truncated', window: 1, items: [event(2)], next_review_id: rid(1), total_count: null, head_reachability: 'not_checked' }, tools_available: true, source_verification: 'not_checked', legal_readiness: 'not_established', qualification_granted: false };
};
describe('read-only independent-review reconciliation', () => {
  it('keeps a bounded body-free request digest matching legacy canonicalization', async () => {
    const body = { request_id: 'd'.repeat(32), expected_review_id: null, expected_manifest_sha256: '2'.repeat(64), note: 'PRIVATE Türkçe 📄', renewal_assessment: null };
    const v = await reviewReceipt(body, { version_id: 'v1', manifest_sha256: '2'.repeat(64) });
    expect(Object.keys(v).length).toBe(5); expect(JSON.stringify(v)).not.toContain('PRIVATE');
    const { renewal_assessment: _, ...withoutNull } = body;
    expect(await reviewReceipt(withoutNull, { version_id: 'v1', manifest_sha256: '2'.repeat(64) })).toEqual(v);
    expect(reviewReceiptQuery(v)).not.toContain('expected_review_id');
    expect(await reviewReceipt({ ...body, note: 'PRIVATE changed' }, { version_id: 'v1', manifest_sha256: '2'.repeat(64) })).not.toEqual(v);
    await expect(reviewReceipt(body, { version_id: 'v1', manifest_sha256: '9'.repeat(64) })).rejects.toThrow();
  });
  it('observes the exact immutable event without interpreting the current head', () => {
    expect(() => verifyReviewObservation(value(), receipt(), intent())).not.toThrow(); expect(completeReviewAdmissions(value())).toBe(true);
    const next = reconciledReviewIntent(intent(), value(), history());
    expect(next.target.review_id).toBe(rid(2)); expect(next.target.review_packet_sha256).toBe('3'.repeat(64)); expect(next.target.head_id).toBe(rid(3));
    expect(next.target.version_id).toBe('v1'); expect(next.target.current_version_id).toBe('v2'); expect(next.filters).toEqual(intent().filters);
    next.filters.customer_ids.push('foreign'); expect(intent().filters.customer_ids).toEqual(['A', 'B']);
  });
  it.each(['context', 'review', 'predecessor'] as const)('keeps %s pending and withholds event handoff without repair', key => {
    const v = value(); v.admission![key] = 'pending'; if (key === 'review') v.review!.admission = 'pending';
    verifyReviewObservation(v, receipt(), intent()); expect(completeReviewAdmissions(v)).toBe(false);
    expect(() => reconciledReviewIntent(intent(), v, history())).toThrow();
  });
  it.each(['not_observed', 'unavailable'] as const)('does not turn %s into absence, retry permission or event navigation', outcome => {
    const v = value(); v.outcome = outcome; v.context = v.review = v.admission = null;
    verifyReviewObservation(v, receipt(), intent()); expect(completeReviewAdmissions(v)).toBe(false);
    expect(() => reconciledReviewIntent(intent(), v, history())).toThrow();
    const html = renderToStaticMarkup(<ReviewOutcomeSummary value={v} />); expect(html).not.toContain('<button'); expect(html).not.toContain('<a ');
  });
  it.each(['scope', 'context', 'version', 'manifest', 'request', 'predecessor', 'sequence', 'effect', 'head', 'packet', 'extra'] as const)('rejects %s substitutions in the response', fault => {
    const v = value();
    if (fault === 'scope') v.matter_id = 'foreign';
    if (fault === 'context') v.context!.id = cid.replaceAll('b', 'e');
    if (fault === 'version') v.context!.version_id = 'v2';
    if (fault === 'manifest') v.review!.manifest_sha256 = '8'.repeat(64);
    if (fault === 'request') v.receipt.request_id = 'e'.repeat(32);
    if (fault === 'predecessor') v.review!.previous_review_id = rid(4);
    if (fault === 'sequence') v.review!.sequence = 1;
    if (fault === 'effect') Object.assign(v, { effects_replayed: true });
    if (fault === 'head') Object.assign(v, { current_head: 'current' });
    if (fault === 'packet') v.review!.packet_sha256 = null;
    if (fault === 'extra') Object.assign(v.review!, { note: 'PRIVATE' });
    expect(() => verifyReviewObservation(v, receipt(), intent())).toThrow();
  });
  it('requires fresh matching request observations around exact historical metadata', () => {
    const before = value(), changed = value(); changed.review!.packet_sha256 = '8'.repeat(64);
    expect(() => verifySameReviewOutcome(before, changed, intent())).toThrow();
    expect(() => reconciledReviewIntent(intent(), changed, history())).toThrow();
    const swapped = history(); swapped.selected_review = event(3);
    expect(() => reconciledReviewIntent(intent(), before, swapped)).toThrow();
  });
  it('keeps sequence-one decisions without inventing a predecessor', () => {
    const v = value(); v.receipt.expected_review_id = null; v.review = { ...event(1), previous_review_id: null, previous_review_packet_sha256: null }; v.admission!.predecessor = 'not_recorded';
    expect(() => verifyReviewObservation(v, v.receipt, intent())).not.toThrow();
    v.admission!.predecessor = 'complete'; expect(() => verifyReviewObservation(v, v.receipt, intent())).toThrow();
  });
});
