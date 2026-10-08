import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import AuthorityComparisons, { AuthorityComparisonContent } from './AuthorityComparisons';
import { comparisonAssessment, committedComparisonReceipt } from './authorityComparisonTypes';
import type { AuthorityComparisonInputs, AuthorityComparisonView, EditableDisposition } from './authorityComparisonTypes';
import { FINDING_DIMENSIONS } from './authorityFindingTypes';
import type { FindingSnapshot } from './authorityFindingTypes';

const rows: EditableDisposition[] = FINDING_DIMENSIONS.map(dimension => ({ source_index: 0, dimension, outcome: 'unresolved', note: 'SYNTHETIC unresolved <script>private</script>', after_target_ids: ['application:a1'], private_source_refs: ['after:e1'] }));
function inputs(): AuthorityComparisonInputs {
  const original = { sequence: 1, reviewer_id: 'lawyer1', reviewer_name: 'SYNTHETIC lawyer', recorded_at: '2026-01-01T00:00:00Z', context_manifest_sha256: 'b'.repeat(64),
    assessment: { note: 'SYNTHETIC original note', review_seconds: null, sources: [{ assertion_id: 'a1', passage_id: 'p1', authority_id: 'l1', target_ids: ['application:a1'], observations: FINDING_DIMENSIONS.map(dimension => ({ dimension, outcome: 'not_assessed', note: 'SYNTHETIC unknown' })) }] },
    context_snapshot: { manifest: { sources: [] } }, dimensions: Object.fromEntries(FINDING_DIMENSIONS.map(key => [key, key])), previous_review_id: null } as unknown as FindingSnapshot;
  return { can_record: true, freshness: { status: 'current', reasons: [] }, expected_comparison_id: null, basis_sha256: 'a'.repeat(64), comparison: {
    review_id: 'review1', authority_review_snapshot: original, authority_review_sha256: 'b'.repeat(64), base_version_id: 'v1', base_version: 1, base_content_sha256: 'c'.repeat(64), candidate_version_id: 'v2', candidate_version: 2, candidate_content_sha256: 'd'.repeat(64),
    before_targets: { 'application:a1': 'SYNTHETIC before' }, after_targets: { 'application:a1': 'SYNTHETIC after' }, changes: [{ target_id: 'application:a1', before: 'SYNTHETIC before', after: 'SYNTHETIC after' }],
    private_sources: [{ source_ref: 'after:e1', name: 'SYNTHETIC.docx', locator: '§1', text: 'SYNTHETIC original quote <img src="private">', quote_sha256: 'e'.repeat(64), start: 0, end: 25 }], dimensions: original.dimensions, historical_context_changes: ['research_record_changed'] } };
}
function value(): AuthorityComparisonView {
  return { id: 'acr-' + 'a'.repeat(24) + '-' + 'b'.repeat(32), sequence: 1, reviewer_name: 'SYNTHETIC lawyer', recorded_at: '2026-01-01T00:00:00Z', comparison_sha256: 'f'.repeat(64), is_latest_comparison: true, public_source_access: true, freshness: { status: 'current', reasons: [] }, snapshot: { comparison_snapshot: inputs().comparison, assessment: comparisonAssessment(inputs(), rows, 'SYNTHETIC overall', '')!, basis_sha256: inputs().basis_sha256, previous_comparison_id: null } };
}

describe('explicit authority-findings revision comparisons', () => {
  it('loads no records or draft inputs automatically', () => {
    const html = renderToStaticMarkup(<AuthorityComparisons matterId="m1" analysisId="a1" contextId="c1" reviewId="r1" onUnavailable={() => undefined} />);
    expect(html).toContain('Yeni taslakla karşılaştırma girdilerini getir'); expect(html).not.toContain('SYNTHETIC'); expect(html).not.toContain('<details open');
  });
  it('preserves original and revised steps, uncertainty, unknown time and escaped private notes', () => {
    const html = renderToStaticMarkup(<AuthorityComparisonContent value={value()} />);
    for (const text of ['SYNTHETIC before', 'SYNTHETIC after', 'Çözümlenmedi', 'Ölçülmedi', 'araştırma kapsamını', 'otomatik hukuki onay', '&lt;script&gt;', '&lt;img']) expect(html).toContain(text);
    expect(html).not.toContain('<script>'); expect(html).not.toContain('<img src=');
  });
  it('withholds the entire frozen payload on denial even if a cached snapshot was supplied', () => {
    const view = value(); view.public_source_access = false; view.freshness.status = 'withheld';
    const html = renderToStaticMarkup(<AuthorityComparisonContent value={view} />);
    expect(html).toContain('tüm karşılaştırma notları bekletiliyor'); expect(html).not.toContain('SYNTHETIC before'); expect(html).not.toContain('SYNTHETIC overall'); expect(html).not.toContain('SYNTHETIC original quote');
  });
  it('shows historical judgments as stale without declaring repair', () => {
    const view = value(); view.freshness = { status: 'stale', reasons: ['candidate_evidence_changed'] };
    const html = renderToStaticMarkup(<AuthorityComparisonContent value={view} />);
    expect(html).toContain('Aktarım kapalı'); expect(html).toContain('Çözümlenmedi'); expect(html).toContain('candidate_evidence_changed');
  });
  it('requires each exact observation, explicit outcomes and explained bounded time', () => {
    expect(comparisonAssessment(inputs(), rows.slice(1), 'SYNTHETIC note', '')).toBeNull();
    expect(comparisonAssessment(inputs(), rows.map(item => ({ ...item, outcome: '' })), 'SYNTHETIC note', '')).toBeNull();
    expect(comparisonAssessment(inputs(), rows.map(item => ({ ...item, note: '  ' })), 'SYNTHETIC note', '')).toBeNull();
    expect(comparisonAssessment(inputs(), rows, 'SYNTHETIC note', '1.5')).toBeNull();
    expect(comparisonAssessment(inputs(), rows, 'SYNTHETIC note', '')?.review_seconds).toBeNull();
  });
  it('requires real changed after steps and after evidence for an addressed declaration', () => {
    const addressed = rows.map(item => ({ ...item, outcome: 'addressed' as const }));
    expect(comparisonAssessment(inputs(), addressed, 'SYNTHETIC note', '30')?.review_seconds).toBe(30);
    const unchanged = inputs(); unchanged.comparison.after_targets = unchanged.comparison.before_targets;
    expect(comparisonAssessment(unchanged, addressed, 'SYNTHETIC note', '')).toBeNull();
    expect(comparisonAssessment(inputs(), addressed.map(item => ({ ...item, private_source_refs: [] })), 'SYNTHETIC note', '')).toBeNull();
    expect(comparisonAssessment(inputs(), addressed.map(item => ({ ...item, after_target_ids: ['foreign'] })), 'SYNTHETIC note', '')).toBeNull();
  });
  it('retained/removed declarations check the original target group instead of silently mapping it', () => {
    const unchanged = inputs(); unchanged.comparison.after_targets = unchanged.comparison.before_targets;
    expect(comparisonAssessment(unchanged, rows.map(item => ({ ...item, outcome: 'retained' })), 'SYNTHETIC note', '')).not.toBeNull();
    expect(comparisonAssessment(inputs(), rows.map(item => ({ ...item, outcome: 'retained' })), 'SYNTHETIC note', '')).toBeNull();
    const removed = inputs(); removed.comparison.after_targets = {};
    expect(comparisonAssessment(removed, rows.map(item => ({ ...item, outcome: 'removed', after_target_ids: [] })), 'SYNTHETIC note', '')).not.toBeNull();
  });
  it('recognizes only exact committed-pending comparison receipts', () => {
    const id = value().id;
    expect(committedComparisonReceipt({ id, outcome: 'committed_needs_revalidation', needs_revalidation: true })).toBe(id);
    expect(committedComparisonReceipt({ id: '../private', outcome: 'committed_needs_revalidation', needs_revalidation: true })).toBeNull();
    expect(committedComparisonReceipt({ id })).toBeNull();
  });
});
