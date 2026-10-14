import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { renewalPayload, verifyRenewalMetadata, verifyRenewalComparison } from './sourceRenewalTypes';
import { assessments, inputs, selection, view } from './sourceReviewFixtures';
import { comparison, metadata, parentId, renewal, renewedManifest } from './sourceRenewalFixtures';
import { canExport, reviewPayload, verifyManifest } from './sourceReviewTypes';
import { SourceRenewalMapping, SourceRenewalComparison } from './SourceRenewalMapping';
import { SourceContextView } from './SourceReviewEvidence';

describe('explicit private source-context renewal', () => {
  it('requires complete explicit mappings, explanations and declarations of new sources', () => {
    expect(renewalPayload(metadata, renewal.mappings, renewal.reason, [], [selection])).toEqual(renewal);
    expect(renewalPayload(metadata, [], renewal.reason, [], [selection])).toBeNull();
    expect(renewalPayload(metadata, renewal.mappings, '  ', [], [selection])).toBeNull();
    expect(renewalPayload(metadata, [{ ...renewal.mappings[0], disposition: 'omitted', new_passage_ids: [] }], renewal.reason, [], [selection])).toBeNull();
    expect(renewalPayload(metadata, [{ ...renewal.mappings[0], disposition: 'omitted', new_passage_ids: [] }], renewal.reason, [selection.passage_id], [selection])).not.toBeNull();
    expect(renewalPayload(metadata, renewal.mappings, renewal.reason, [selection.passage_id], [selection])).toBeNull();
    expect(renewalPayload({ ...metadata, admission_completed: false }, renewal.mappings, renewal.reason, [], [selection])).toBeNull();
  });
  it('does not infer source-version equivalence from a shared passage ID', () => {
    expect(renewalPayload(metadata, renewal.mappings, renewal.reason, [], [{ ...selection, source_version_id: 'urn:test:new-version' }])).toBeNull();
    expect(renewalPayload(metadata, [{ ...renewal.mappings[0], disposition: 'replaced' }], renewal.reason, [], [{ ...selection, source_version_id: 'urn:test:new-version' }])).not.toBeNull();
  });
  it('rejects private scope or original identity metadata mismatches', () => {
    expect(() => verifyRenewalMetadata(metadata, 'matter1', 'analysis1', parentId)).not.toThrow();
    expect(() => verifyRenewalMetadata(metadata, 'another-matter', 'analysis1', parentId)).toThrow();
    expect(() => verifyRenewalMetadata(metadata, 'matter1', 'another-analysis', parentId)).toThrow();
    expect(() => verifyRenewalMetadata({ ...metadata, sources: [...metadata.sources, ...metadata.sources] }, 'matter1', 'analysis1', parentId)).toThrow();
    const unexpectedText = structuredClone(metadata); Object.assign(unexpectedText.sources[0].identity, { text: 'WITHHELD OLD QUOTE' });
    expect(() => verifyRenewalMetadata(unexpectedText, 'matter1', 'analysis1', parentId)).toThrow();
  });
  it('requires a fresh independent replacement assessment bound to the exact comparison', () => {
    const fresh = { ...inputs, manifest: renewedManifest };
    expect(reviewPayload(assessments(), 'TEST ONLY review', 'reviewed_conditional', fresh)).toBeNull();
    const assessment = { expected_comparison_sha256: renewedManifest.renewal_comparison_sha256, outcome: 'confirmed' as const, note: 'TEST ONLY independent map inspection' };
    expect(reviewPayload(assessments(), 'TEST ONLY review', 'reviewed_conditional', fresh, assessment)?.renewal_assessment).toEqual(assessment);
    expect(reviewPayload(assessments(), 'TEST ONLY review', 'reviewed_conditional', fresh, { ...assessment, outcome: 'not_assessed' })).toBeNull();
    expect(reviewPayload(assessments(), 'TEST ONLY review', 'reviewed_conditional', fresh, { ...assessment, expected_comparison_sha256: '0'.repeat(64) })).toBeNull();
    expect(reviewPayload(assessments(), 'TEST ONLY review', 'changes_requested', fresh, { ...assessment, outcome: 'needs_change' })).not.toBeNull();
  });
  it('checks the full comparison digest and fails closed on changed evidence or target flags', async () => {
    await expect(verifyManifest(renewedManifest, 'matter1', 'analysis1')).resolves.toBeUndefined();
    const altered = structuredClone(renewedManifest); altered.renewal_comparison.entries[0].successors[0].exact_targets_same = true;
    expect(() => verifyRenewalComparison(altered)).toThrow();
    await expect(verifyManifest({ ...renewedManifest, renewal_comparison_sha256: '0'.repeat(64) }, 'matter1', 'analysis1')).rejects.toThrow();
    expect(() => verifyRenewalComparison({ ...renewedManifest, renewal: { ...renewal, expected_parent_review_id: 'unbound-review' } })).toThrow();
  });
  it('starts replacement choices blank and exposes no old source text or private target text', () => {
    const html = renderToStaticMarkup(<SourceRenewalMapping meta={metadata} rows={[{ ...renewal.mappings[0], disposition: '', new_passage_ids: [], note: '' }]} reason="" added={[]} selections={[selection]} change={() => {}} />);
    expect(html).toContain('Beyan seçin'); expect(html).not.toContain('Özgün alıntı'); expect(html).not.toContain('PRIVATE analysis step');
    expect(html).not.toContain('value="retained" selected'); expect(html).not.toContain('checked=""');
  });
  it('shows exact changed target content and preserves original review history without promotion', () => {
    const html = renderToStaticMarkup(<SourceRenewalComparison value={comparison} reason={renewal.reason} />);
    expect(html).toContain('yeni bağımsız inceleme'); expect(html).toContain('Farklı'); expect(html).toContain('old-v1');
    expect(html).not.toContain('Özgün alıntı'); expect(html).not.toContain('PRIVATE analysis step');
    const fresh = view(); fresh.manifest = renewedManifest; fresh.review = { effective_state: 'unreviewed', snapshot: null };
    expect(canExport(fresh)).toBe(false);
    fresh.freshness.status = 'stale';
    const hidden = renderToStaticMarkup(<SourceContextView value={fresh} />);
    expect(hidden).not.toContain(renewal.reason); expect(hidden).not.toContain('old-v1'); expect(hidden).not.toContain('PRIVATE analysis step');
  });
});
