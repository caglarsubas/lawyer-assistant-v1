import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { assessmentPayload, emptyAssessment, permitsPositiveReview, RevisionAssessmentDetails, RevisionAssessmentEditor, RevisionComparisonDetails, SEMANTIC_LABELS } from './AnalysisAdjudication';
import type { RevisionComparison } from './analysisTypes';

export function comparison(): RevisionComparison {
  return { recipe: 'private-revision-adjudication-v1', scope: 'selected_private_evidence_only', review_recipe: 'private-lawyer-review-v1', comparison_sha256: 'c'.repeat(64), base_version_id: 'v1', base_version: 1, base_content_sha256: 'a'.repeat(64), base_review_id: 'r1', candidate_version_id: 'v2', candidate_version: 2, candidate_content_sha256: 'b'.repeat(64), candidate_disposition: 'conditional', targets: ['conclusion', 'application:a1', 'premise:p1'], changes: [{ target_id: 'conclusion', before: { text: 'SYNTHETIC before <script>untrusted</script>' }, after: { text: 'SYNTHETIC after <img src="untrusted">' } }], findings: [{ finding_index: 0, target_id: 'conclusion', severity: 'major', text: 'SYNTHETIC original finding', suggested_change: '', evidence_ids: ['e1'] }], sources: ['before:e1', 'after:e1'].map((source_ref) => ({ source_ref, evidence_id: 'e1', document_id: 'd1', document_revision: 1, document_sha256: 'd'.repeat(64), name: 'SYNTHETIC.txt', locator: '§1', passage_sha256: 'e'.repeat(64), quote_sha256: 'f'.repeat(64), start: 0, end: 18, text: 'SYNTHETIC quotation' })), dimensions: SEMANTIC_LABELS, freshness: { status: 'current', reasons: [] }, public_adverse_authority_qualified: false, benefit_established: false };
}

function ready(data = comparison()) {
  const value = emptyAssessment(data);
  value.observations.forEach((item) => { item.outcome = 'confirmed'; item.note = 'SYNTHETIC source comparison'; item.source_refs = ['after:e1']; });
  value.finding_dispositions[0] = { finding_index: 0, outcome: 'repaired', note: 'SYNTHETIC changed conclusion', target_ids: ['conclusion'], source_refs: ['after:e1'] };
  return value;
}

describe('source-linked human revision adjudication', () => {
  it('begins without inferred verdicts, repaired findings or measured review time', () => {
    const data = comparison(); const value = emptyAssessment(data);
    expect(assessmentPayload(value, data)).toBeNull();
    expect(value.review_seconds).toBe('');
    const html = renderToStaticMarkup(<RevisionAssessmentEditor comparison={data} value={value} onChange={() => {}} busy={false} />);
    expect(html).not.toContain('value="confirmed" selected'); expect(html).not.toContain('value="repaired" selected');
    expect(html).toContain('Önceki bulgu 1'); expect(html).toContain('Otomatik kronometre'); expect(html).not.toContain('<details open');
  });
  it('exposes before/after text, source spans and exact bindings as escaped private evidence', () => {
    const html = renderToStaticMarkup(<RevisionComparisonDetails comparison={comparison()} onSource={() => {}} />);
    for (const text of ['Önceki sürüm 1', 'Gösterilen sürüm 2', 'SYNTHETIC before', 'SYNTHETIC after', 'SYNTHETIC quotation', '[0, 18)', 'Özgün belgenin bağlamını aç', 'karşı içtihat araştırması değildir', 'model faydası ölçülmedi']) expect(html).toContain(text);
    expect(html).not.toContain('<script>untrusted'); expect(html).not.toContain('<img src="untrusted">'); expect(html).not.toContain('<details open');
  });
  it('requires current evidence for positive observations and actual changed steps for repair', () => {
    const data = comparison(); const value = ready(data);
    expect(assessmentPayload(value, data)?.comparison_sha256).toBe(data.comparison_sha256);
    value.observations[0].source_refs = ['before:e1']; expect(assessmentPayload(value, data)).toBeNull();
    value.observations[0].source_refs = ['after:e1']; value.finding_dispositions[0].target_ids = ['premise:p1']; expect(assessmentPayload(value, data)).toBeNull();
    value.finding_dispositions[0].target_ids = ['conclusion']; data.changes = []; expect(assessmentPayload(value, data)).toBeNull();
  });
  it('withholds positive review for substantive unresolved findings and semantic defects', () => {
    const data = comparison(); const value = ready(data);
    expect(permitsPositiveReview(value, data)).toBe(true);
    value.finding_dispositions[0].outcome = 'unresolved'; expect(permitsPositiveReview(value, data)).toBe(false);
    data.findings[0].severity = 'note'; expect(permitsPositiveReview(value, data)).toBe(true);
    value.observations[0].outcome = 'needs_change'; expect(permitsPositiveReview(value, data)).toBe(false);
  });
  it('cannot declare a repair when meaning or conclusion strength is unassessed or concerns a different step', () => {
    const data = comparison(); const value = ready(data);
    value.observations[0].outcome = 'not_assessed'; expect(assessmentPayload(value, data)).toBeNull();
    value.observations[0].outcome = 'confirmed'; value.observations[5].target_ids = ['premise:p1']; expect(assessmentPayload(value, data)).toBeNull();
    data.changes.push({ target_id: 'application:a1', before: 'SYNTHETIC old', after: 'SYNTHETIC new' });
    value.finding_dispositions[0].target_ids = ['application:a1', 'conclusion'];
    value.observations[0].target_ids = ['application:a1']; value.observations[5].target_ids = ['conclusion'];
    expect(assessmentPayload(value, data)).toBeNull();
  });
  it('does not substitute a review label for genuine withheld text and rejects stale comparisons', () => {
    const data = comparison(); const value = ready(data);
    value.finding_dispositions[0].outcome = 'withheld'; expect(assessmentPayload(value, data)).toBeNull();
    data.candidate_disposition = 'withheld'; expect(assessmentPayload(value, data)).not.toBeNull();
    data.freshness = { status: 'stale', reasons: ['SYNTHETIC changed source'] }; expect(assessmentPayload(value, data)).toBeNull();
    const html = renderToStaticMarkup(<RevisionComparisonDetails comparison={data} onSource={() => {}} />);
    expect(html).toContain('SYNTHETIC changed source'); expect(html).toContain('kaydedilemez');
  });
  it('retains unassessed dimensions, missing time and qualified human claims in recorded details', () => {
    const data = comparison(); const value = ready(data);
    value.observations[4].outcome = 'not_assessed'; value.observations[4].source_refs = [];
    const assessment = assessmentPayload(value, data)!;
    const html = renderToStaticMarkup(<RevisionAssessmentDetails assessment={assessment} comparison={data} onSource={() => {}} />);
    for (const text of ['Ölçülmedi', 'Değerlendirilmedi', 'Giderildi · Avukat beyanı', 'Önceki bulgular korunur', 'Zaman kazanımı', 'SYNTHETIC original finding', 'Bu karşılaştırmadaki avukat beyanı', 'Gösterilen', 'Anlamsal gözlemler (6)']) expect(html).toContain(text);
    expect(html).not.toContain('<details open');
    value.review_seconds = '90'; expect(assessmentPayload(value, data)?.review_seconds).toBe(90);
    for (const time of ['0', '-1', 'NaN', '1.5', '28801']) { value.review_seconds = time; expect(assessmentPayload(value, data)).toBeNull(); }
  });
});
