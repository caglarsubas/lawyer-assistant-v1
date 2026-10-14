import { describe, expect, it } from 'vitest';
import { ApiError } from '../../api';
import { canonicalJson, canExport, pendingReceipt, reviewPayload, selectionsPayload, SourceReadFence, verifyManifest, verifyQuotes, verifyView } from './sourceReviewTypes';
import type { Quote } from './sourceReviewTypes';
import { assessments, inputs, manifest, quote, selection, text, view } from './sourceReviewFixtures';

describe('private source review contracts', () => {
  it('sends exact source identities and chosen targets without source text or invented authorities', () => {
    expect(selectionsPayload([{ ...quote, ...selection }], ['rule:r1'])).toEqual([selection]);
    expect(JSON.stringify(selectionsPayload([selection], ['rule:r1']))).not.toContain(quote.text);
    for (const row of [{ ...selection, relationship: '' as const }, { ...selection, note: '   ' }, { ...selection, target_ids: [] }, { ...selection, target_ids: ['unknown'] }, { ...selection, target_ids: ['rule:r1', 'rule:r1'] }]) expect(selectionsPayload([row], ['rule:r1'])).toBeNull();
    expect(selectionsPayload([selection, selection], ['rule:r1'])).toBeNull();
  });
  it('validates actual UTF-8 quote hashes and Unicode offsets without normalizing CRLF', async () => {
    await expect(verifyQuotes([quote], manifest.graph_release_pin)).resolves.toBeUndefined();
    for (const bad of [{ ...quote, text: text.replaceAll('\r\n', '\n') }, { ...quote, quote_sha256: '0'.repeat(64) }, { ...quote, source_version_id: 'wrong identity' }, { ...quote, end_offset: quote.end_offset + 1 }, { ...quote, assertion_id: 'urn:test:invented' }, { ...quote, release_id: '0'.repeat(64) }]) {
      await expect(verifyQuotes([bad as Quote], manifest.graph_release_pin)).rejects.toBeInstanceOf(Error);
    }
  });
  it('rejects cross-matter manifests and mismatched selection identities without a version substitute', async () => {
    await expect(verifyManifest(manifest, 'matter1', 'analysis1')).resolves.toBeUndefined();
    await expect(verifyManifest(manifest, 'different', 'analysis1')).rejects.toBeInstanceOf(Error);
    const changed = structuredClone(manifest); changed.selections[0].source_version_id = 'urn:test:current';
    await expect(verifyManifest(changed, 'matter1', 'analysis1')).rejects.toBeInstanceOf(Error);
  });
  it('allows a different reviewer interpretation while retaining exact source and target sets', () => {
    const result = reviewPayload(assessments(), 'TEST ONLY reviewed', 'reviewed_conditional', inputs)!;
    expect(result.sources[0].relationship).toBe('adverse_candidate'); expect(selection.relationship).toBe('unresolved');
    const rows = assessments(); rows[0].target_ids = ['conclusion']; expect(reviewPayload(rows, 'TEST ONLY reviewed', 'reviewed_conditional', inputs)).toBeNull();
    rows[0].target_ids = ['rule:r1']; rows[0].source_version_id = 'urn:test:other'; expect(reviewPayload(rows, 'TEST ONLY reviewed', 'reviewed_conditional', inputs)).toBeNull();
  });
  it('requires every review dimension and explicit changes, with no preset affirmative decision', () => {
    const rows = assessments(); rows[0].observations[0].outcome = '';
    expect(reviewPayload(rows, 'TEST ONLY note', 'reviewed_conditional', inputs)).toBeNull();
    rows[0].observations[0].outcome = 'not_assessed'; expect(reviewPayload(rows, 'TEST ONLY note', 'reviewed_conditional', inputs)).toBeNull();
    expect(reviewPayload(assessments(), 'TEST ONLY note', 'changes_requested', inputs)).toBeNull();
    rows[0].observations[0].outcome = 'needs_change'; expect(reviewPayload(rows, 'TEST ONLY note', 'changes_requested', inputs)).not.toBeNull();
    rows[0].observations[1].dimension = 'quote_identity'; expect(reviewPayload(rows, 'TEST ONLY note', 'changes_requested', inputs)).toBeNull();
  });
  it('recognizes pending receipts only with the correct operation kind and safe exact IDs', () => {
    const id = view().id; const data = { id, outcome: 'committed_needs_revalidation' };
    expect(pendingReceipt(new ApiError('TEST ONLY pending', 409, data), 'context')).toBe(id);
    for (const error of [new ApiError('x', 0, data), new ApiError('x', 409, { id }), new ApiError('x', 409, { ...data, id: '../secret' })]) expect(pendingReceipt(error, 'context')).toBeNull();
    expect(pendingReceipt(new ApiError('x', 409, data), 'review')).toBeNull();
  });
  it('requires current positive latest independent review for exports, and verifies the actor binding', async () => {
    const value = view(); expect(canExport(value)).toBe(true); await expect(verifyView(value, 'matter1', 'analysis1')).resolves.toBeUndefined();
    value.review.is_latest = false; expect(canExport(value)).toBe(false);
    value.review.snapshot!.recorded_by = manifest.analysis_author_id; await expect(verifyView(value, 'matter1', 'analysis1')).rejects.toBeInstanceOf(Error);
    value.freshness.status = 'stale'; expect(canExport(value)).toBe(false);
  });
  it('compares payloads independently of object property ordering while preserving exact strings and list order', () => {
    expect(canonicalJson({ b: 1, a: { z: 2, x: 3 } })).toBe(canonicalJson({ a: { x: 3, z: 2 }, b: 1 }));
    expect(canonicalJson({ text: '\r\n' })).not.toBe(canonicalJson({ text: '\n' }));
    expect(canonicalJson(['a', 'b'])).not.toBe(canonicalJson(['b', 'a']));
  });
  it('retires delayed quote responses after a new inspection, scope change or permission failure', async () => {
    const fence = new SourceReadFence(); const first = fence.begin(); const visible: string[] = [];
    let resolve!: (value: string) => void;
    const late = new Promise<string>(accept => { resolve = accept; }).then(value => { if (first.current()) visible.push(value); });
    const next = fence.begin(); expect(first.signal.aborted).toBe(true); expect(next.current()).toBe(true);
    fence.invalidate(); resolve('PRIVATE delayed quote'); await late; expect(visible).toEqual([]); expect(next.current()).toBe(false);
  });
});
