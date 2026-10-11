import { renderToStaticMarkup } from 'react-dom/server';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { setCsrfToken } from '../api';
import SourceSelectionPanel, { SelectionSummary } from './SourceSelectionPanel';
import { comparisonHash } from './sourceComparison';
import { fetchSelection, selectionCanonical, selectionPayload, validateSelection, type SelectionHandoff } from './sourceSelection';

const a = 'a'.repeat(64), b = 'b'.repeat(64), hash = 'c'.repeat(64);
async function fixture(): Promise<SelectionHandoff> {
  return { schema_version: 'source-selection-handoff-v1', scope_sha256: hash, source_ids: [a, b], sources: [a, b].map(source_id => ({
    source_id, title: '<script>synthetic title</script>', source_version_id: 'synthetic-version', review_revision: 0,
    artifacts: Object.fromEntries(['raw.bin', 'text.txt', 'source.json', 'locators.json'].map(name => [name, { sha256: hash, bytes: 100 }])),
    assessments: { rights: null, source_identity: null, extraction: null, legal: null },
  })), pairs: [{ pair_id: await comparisonHash(JSON.stringify([a, b])), source_ids: [a, b], revision: 0, status: 'missing', history_count: 0,
    history_sha256: await comparisonHash('[]'), historical_classifications: {}, historical_classification_changes: 0, latest: null }],
    coverage: { selected_source_count: 2, expected_pair_count: 1, pair_status_counts: { missing: 1, unresolved: 0, stale: 0, resolved: 0 }, all_pairs_current_resolved: false },
    identity_conflicts: [], source_review_gaps: [a, b].map(source_id => ({ source_id, categories: ['rights', 'source_identity', 'extraction', 'legal'] })),
    independent_original_count: null, independent_originals_verified: false, study_qualified: false, publication_eligible: false, current_law_verified: false,
    confidentiality: 'firm_confidential', signed: false, limitations: ['Synthetic engineering fixture only'] };
}
async function envelope(value: SelectionHandoff) {
  const evidence_json = selectionCanonical(value);
  return { evidence_json, evidence_sha256: await comparisonHash(evidence_json) };
}
afterEach(() => { vi.unstubAllGlobals(); setCsrfToken(''); });

describe('confidential source selection handoff', () => {
  it('canonicalizes only selected exact IDs without supplying actors or qualification', () => {
    expect(selectionPayload([b, a])).toEqual({ source_ids: [a, b] });
    expect(selectionPayload([b, a])).not.toHaveProperty('study_qualified');
  });
  it.each([[], [a], [a, a], [a, 'BAD'], Array.from({ length: 7 }, (_, index) => String(index).repeat(64))].map(ids => ({ ids })))('rejects invalid or oversized selection $ids', ({ ids }) => {
    expect(() => selectionPayload(ids)).toThrow();
  });
  it('checks exact receipt digest, missing pair, source gaps and unknown independent count', async () => {
    const value = await fixture(), encoded = await envelope(value);
    expect((await validateSelection(encoded, [b, a])).receipt).toEqual(value);
    await expect(validateSelection({ ...encoded, evidence_sha256: hash }, [a, b])).rejects.toThrow();
    await expect(validateSelection(encoded, [a, 'd'.repeat(64)])).rejects.toThrow();
  });
  it('retains optional source review artifacts without treating them as approvals', async () => {
    const value = await fixture();
    value.sources[0].artifacts['rights-review.json'] = { sha256: hash, bytes: 100 };
    value.sources[0].artifacts['identity-review.json'] = { sha256: hash, bytes: 100 };
    const result = await validateSelection(await envelope(value), [a, b]);
    expect(result.receipt.source_review_gaps).toHaveLength(2); expect(result.receipt.study_qualified).toBe(false);
  });
  it.each(['independence', 'count', 'study', 'public', 'signed', 'current', 'pair_id', 'missing_pair', 'revision', 'history', 'counts', 'conflicts', 'gaps', 'artifacts'])('rejects corrupt scope even with a matching content digest: %s', async kind => {
    const value = await fixture();
    if (kind === 'independence') value.independent_originals_verified = true as false;
    if (kind === 'count') value.independent_original_count = 2 as unknown as null;
    if (kind === 'study') value.study_qualified = true as false;
    if (kind === 'public') value.confidentiality = 'public' as 'firm_confidential';
    if (kind === 'signed') value.signed = true as false;
    if (kind === 'current') value.current_law_verified = true as false;
    if (kind === 'pair_id') value.pairs[0].pair_id = hash;
    if (kind === 'missing_pair') value.pairs = [];
    if (kind === 'revision') value.pairs[0].revision = 1;
    if (kind === 'history') value.pairs[0].historical_classification_changes = 1;
    if (kind === 'counts') value.coverage.pair_status_counts.missing = 0;
    if (kind === 'conflicts') value.identity_conflicts = [{ source_id: a, declarations: [] }];
    if (kind === 'gaps') value.source_review_gaps = [];
    if (kind === 'artifacts') delete value.sources[0].artifacts['raw.bin'];
    await expect(validateSelection(await envelope(value), [a, b])).rejects.toThrow();
  });
  it('reads a fresh CSRF-bound export, with no cached report fallback', async () => {
    const encoded = await envelope(await fixture());
    const fetch = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({ schema_version: 'source-selection-dossier-v1', ...encoded }) });
    vi.stubGlobal('fetch', fetch); setCsrfToken('selection-csrf');
    const result = await fetchSelection([b, a], new AbortController().signal, true);
    expect(result.evidence_sha256).toBe(encoded.evidence_sha256);
    const [path, options] = fetch.mock.calls[0];
    expect(path).toBe('/api/v1/public-sources/selection-review/export'); expect(options.cache).toBe('no-store');
    expect(options.method).toBe('POST'); expect(options.body).toBe(JSON.stringify({ source_ids: [a, b] }));
    expect(options.headers.get('X-CSRF-Token')).toBe('selection-csrf');
    fetch.mockResolvedValue({ ok: false, status: 403, json: async () => ({ detail: 'scope revoked' }) });
    await expect(fetchSelection([a, b], new AbortController().signal, true)).rejects.toThrow('scope revoked');
  });
  it('discards a response after selection cancellation', async () => {
    const controller = new AbortController(), encoded = await envelope(await fixture());
    vi.stubGlobal('fetch', vi.fn().mockImplementation(async () => { controller.abort(); return { ok: true, status: 200, json: async () => encoded }; }));
    await expect(fetchSelection([a, b], controller.signal)).rejects.toThrow();
  });
  it('escapes confidential metadata and states the incomplete scope without calling it independence', async () => {
    const value = await fixture();
    const html = renderToStaticMarkup(<SelectionSummary value={value} />);
    expect(html).toContain('&lt;script&gt;'); expect(html).not.toContain('<script>'); expect(html).toContain('belirlenmedi');
    expect(html).toContain('Görüş yok'); expect(html).toContain('İlişki kapsamı eksik');
    expect(html).toContain(`/compare?other_source_id=${b}`);
    expect(renderToStaticMarkup(<SourceSelectionPanel sources={[]} />)).toContain('kurumunuza özeldir');
  });
  it('retains a stale resolved opinion without upgrading current coverage', async () => {
    const value = await fixture(), pair = value.pairs[0];
    pair.status = 'stale'; pair.revision = pair.history_count = 1; pair.historical_classifications = { same_work_same_version: 1 };
    pair.latest = { id: 'opinion', revision: 1, reviewer: { id: 'human', name: 'Synthetic human' }, created_at: '2026-10-11T10:00:00Z',
      event_sha256: hash, comparison_sha256: hash, input: { classification: 'same_work_same_version', rationale: 'Invented example only',
        identities: [a, b].map(source_id => ({ source_id, work_ref: 'synthetic-work', version_ref: 'synthetic-version' })) } };
    value.coverage.pair_status_counts = { missing: 0, unresolved: 0, stale: 1, resolved: 0 };
    const result = await validateSelection(await envelope(value), [a, b]);
    expect(result.receipt.coverage.all_pairs_current_resolved).toBe(false);
    expect(result.receipt.independent_original_count).toBeNull();
    expect(renderToStaticMarkup(<SelectionSummary value={result.receipt} />)).toContain('Yeniden inceleme gerekiyor');
  });
});
