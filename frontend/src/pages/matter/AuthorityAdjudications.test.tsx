import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import AuthorityAdjudications, { AdjudicationContent } from './AuthorityAdjudications';
import { adjudicationAssessment, committedAdjudicationReceipt, SEMANTIC_DIMENSIONS } from './authorityAdjudicationTypes';
import type { AdjudicationInputs, AdjudicationView, AdverseScope, FindingJudgment, SemanticObservation } from './authorityAdjudicationTypes';
import { FINDING_DIMENSIONS } from './authorityFindingTypes';
const links = { note: 'SYNTHETIC declaration <script>private</script>', target_refs: ['after:application:a1'], private_source_refs: ['after:e1'], public_source_indices: [0] };
const observations: SemanticObservation[] = SEMANTIC_DIMENSIONS.map(dimension => ({ dimension, outcome: 'supported', ...links }));
const judgments: FindingJudgment[] = FINDING_DIMENSIONS.map(dimension => ({ dimension, source_index: 0, outcome: 'agree', ...links }));
const scope: AdverseScope = { status: 'selected_sources_inspected', inspected_source_indices: [0], limitations: 'SYNTHETIC unknown corpus coverage.' };
function inputs(): AdjudicationInputs {
  return { can_record: true, independent_account: true, expected_adjudication_id: null, basis_sha256: 'a'.repeat(64), freshness: { status: 'current', reasons: [] }, basis: {
    excluded_account_ids: ['author'], account_separation_only: true, dimensions: Object.fromEntries(SEMANTIC_DIMENSIONS.map(key => [key, key])), comparison: {
      assessment: { note: 'SYNTHETIC comparison', review_seconds: null, dispositions: FINDING_DIMENSIONS.map(dimension => ({ source_index: 0, dimension, outcome: 'unresolved', note: 'SYNTHETIC unresolved', after_target_ids: [], private_source_refs: [] })) },
      comparison_snapshot: { before_targets: { 'application:a1': 'SYNTHETIC before' }, after_targets: { 'application:a1': 'SYNTHETIC after' },
        changes: [{ target_id: 'application:a1', before: 'SYNTHETIC before', after: 'SYNTHETIC after' }], private_sources: [{ source_ref: 'after:e1', text: 'SYNTHETIC <img src="private">' }],
        historical_context_changes: [], dimensions: Object.fromEntries(FINDING_DIMENSIONS.map(key => [key,key])), authority_review_snapshot: { assessment: { sources: [{ target_ids: ['application:a1'], observations: [] }] }, context_snapshot: { manifest: { sources: [] } } } }
    } } } as unknown as AdjudicationInputs;
}
function value(): AdjudicationView {
  return { id: 'aij-' + 'a'.repeat(24) + '-' + 'b'.repeat(32), sequence: 1, reviewer_id: 'independent', reviewer_name: 'Test Reviewer', recorded_at: '2026-01-01T00:00:00Z', adjudication_sha256: 'f'.repeat(64), public_source_access: true, is_latest_for_reviewer: true, freshness: { status: 'current', reasons: [] }, snapshot: {
    basis: inputs().basis, basis_sha256: 'a'.repeat(64), assessment: adjudicationAssessment(inputs(), observations, judgments, scope, 'SYNTHETIC note', '')!, coverage: { semantic: { total: 6, assessed: 6 }, findings: { total: 6, assessed: 6 }, corpus_completeness: 'unknown', adverse_recall: null }
  } };
}
describe('separate-account authority adjudication', () => {
  it('starts collapsed and loads nothing automatically', () => {
    const html = renderToStaticMarkup(<AuthorityAdjudications base="/private/adjudications" onUnavailable={() => undefined} />);
    expect(html).toContain('Ayrı değerlendirme girdilerini getir'); expect(html).not.toContain('SYNTHETIC'); expect(html).not.toContain('<details open');
  });
  it('preserves coverage, unknown time and account limits with escaped prose', () => {
    const html = renderToStaticMarkup(<AdjudicationContent value={value()} />);
    for (const text of ['anlam 6/6', 'Ölçülmedi', 'Derlem bütünlüğü bilinmiyor', 'mesleki yeterlilik', '&lt;script&gt;', '&lt;img']) expect(html).toContain(text);
    expect(html).not.toContain('<script>'); expect(html).not.toContain('<img src=');
  });
  it('denial overrides cached content and hides every observation/quote', () => {
    const view = value(); view.public_source_access = false; view.freshness.status = 'withheld';
    const html = renderToStaticMarkup(<AdjudicationContent value={view} />);
    expect(html).toContain('notları ve alıntılar bekletiliyor'); expect(html).not.toContain('SYNTHETIC');
  });
  it('stale history stays inspectable with export closed', () => {
    const view = value(); view.freshness = { status: 'stale', reasons: ['comparison_dependencies_changed'] };
    const html = renderToStaticMarkup(<AdjudicationContent value={view} />);
    expect(html).toContain('Aktarım kapalı'); expect(html).toContain('comparison_dependencies_changed');
  });
  it('requires all dimensions/judgments and explicit outcomes', () => {
    expect(adjudicationAssessment(inputs(), observations, judgments, scope, 'SYNTHETIC note', '')?.review_seconds).toBeNull();
    expect(adjudicationAssessment(inputs(), observations.slice(1), judgments, scope, 'note', '')).toBeNull();
    expect(adjudicationAssessment(inputs(), observations, judgments.slice(1), scope, 'note', '')).toBeNull();
    expect(adjudicationAssessment(inputs(), observations.map(item => ({ ...item, outcome: '' })), judgments, scope, 'note', '')).toBeNull();
    expect(adjudicationAssessment({ ...inputs(), can_record: false }, observations, judgments, scope, 'note', '')).toBeNull();
  });
  it('rejects foreign links, missing candidate quotes, duplicates and fractional times', () => {
    expect(adjudicationAssessment(inputs(), observations.map(item => ({ ...item, target_refs: ['after:foreign'] })), judgments, scope, 'note', '')).toBeNull();
    expect(adjudicationAssessment(inputs(), observations.map(item => ({ ...item, private_source_refs: [] })), judgments, scope, 'note', '')).toBeNull();
    expect(adjudicationAssessment(inputs(), observations, judgments.map(() => judgments[0]), scope, 'note', '')).toBeNull();
    expect(adjudicationAssessment(inputs(), observations, judgments, scope, 'note', '1.5')).toBeNull();
  });
  it('adverse declarations require exact selected-source inspection', () => {
    expect(adjudicationAssessment(inputs(), observations, judgments, { ...scope, status: 'not_searched', inspected_source_indices: [] }, 'note', '')).toBeNull();
    expect(adjudicationAssessment(inputs(), observations, judgments, { ...scope, inspected_source_indices: [7] }, 'note', '')).toBeNull();
    const result = adjudicationAssessment(inputs(), observations.map(item => ({ ...item, outcome: 'not_assessed', target_refs: [], private_source_refs: [], public_source_indices: [] })), judgments.map(item => ({ ...item, outcome: 'unresolved', target_refs: [], private_source_refs: [], public_source_indices: [] })), { ...scope, status: 'not_searched', inspected_source_indices: [] }, 'note', '');
    expect(result).not.toBeNull();
  });
  it('accepts only exact pending-admission identifiers', () => {
    expect(committedAdjudicationReceipt({ outcome: 'committed_needs_revalidation', needs_revalidation: true, id: value().id })).toBe(value().id);
    expect(committedAdjudicationReceipt({ outcome: 'committed_needs_revalidation', needs_revalidation: true, id: '../private' })).toBeNull();
  });
});
