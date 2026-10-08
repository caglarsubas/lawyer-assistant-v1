import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import AuthorityFindings, { FindingViewContent } from './AuthorityFindings';
import { assessmentPayload, committedFindingReceipt, FINDING_DIMENSIONS } from './authorityFindingTypes';
import type { EditableAssessment, FindingView } from './authorityFindingTypes';
import type { AuthorityContext } from './authorityTypes';

const row: EditableAssessment = { assertion_id: 'urn:synthetic:a', passage_id: 'urn:synthetic:p', authority_id: 'urn:synthetic:law', target_ids: ['rule:r1'], observations: FINDING_DIMENSIONS.map(dimension => ({ dimension, outcome: 'not_assessed', note: 'SYNTHETIC unassessed matter <script>private</script>' })) };
const id = 'aaf-' + 'a'.repeat(24) + '-' + 'b'.repeat(32);
function value(): FindingView {
  return { id, sequence: 1, reviewer_name: 'SYNTHETIC lawyer', recorded_at: '2026-01-01T00:00:00Z', review_sha256: 'c'.repeat(64), is_latest_review: true, freshness: { status: 'current', reasons: [] }, public_source_access: true, qualification_granted: false, legal_approval: 'not_granted', runtime_authorization: 'none', snapshot: { context_id: 'context1', context_manifest_sha256: 'd'.repeat(64), basis_sha256: 'e'.repeat(64), context_snapshot: { manifest: { sources: [] } } as unknown as AuthorityContext,
    assessment: assessmentPayload([row], 'SYNTHETIC <img src="private">', '')!, dimensions: Object.fromEntries(FINDING_DIMENSIONS.map(key => [key, key])) as Record<typeof FINDING_DIMENSIONS[number], string>, previous_review_id: null, recipe: 'test-only', scope: 'test-only', sequence: 1, reviewer_id: 'lawyer1', reviewer_name: 'SYNTHETIC lawyer', recorded_at: '2026-01-01T00:00:00Z', legal_approval: 'not_granted', qualification_granted: false, model_use: 'none' } };
}

describe('explicit source-bound lawyer findings', () => {
  it('does not load reviews or inputs automatically and keeps details collapsed', () => {
    const html = renderToStaticMarkup(<AuthorityFindings matterId="m1" analysisId="a1" contextId="c1" />);
    expect(html).toContain('Yeni inceleme için kaynak bağlarını getir'); expect(html).not.toContain('<details open'); expect(html).not.toContain(row.observations[0].note);
  });
  it('preserves human unknowns and time unknowns without qualification, escaping free text', () => {
    const html = renderToStaticMarkup(<FindingViewContent value={value()} />);
    expect(html).toContain('Değerlendirilmedi'); expect(html).toContain('Ölçülmedi'); expect(html).toContain('hukuki engeller'); expect(html).toContain('&lt;script&gt;'); expect(html).not.toContain('<script>'); expect(html).not.toContain('<img src=');
  });
  it('does not render cached notes or passages when public access is withheld', () => {
    const view = value(); view.public_source_access = false; view.freshness.status = 'withheld';
    const html = renderToStaticMarkup(<FindingViewContent value={view} />);
    expect(html).toContain('inceleme notları bekletiliyor'); expect(html).not.toContain('SYNTHETIC unassessed'); expect(html).not.toContain('context1'); expect(html).not.toContain('&lt;img');
  });
  it('labels a superseded/stale review as requiring re-review and keeps historical declarations', () => {
    const view = value(); view.freshness = { status: 'stale', reasons: ['newer_review_exists'] }; view.is_latest_review = false;
    const html = renderToStaticMarkup(<FindingViewContent value={view} />);
    expect(html).toContain('Yeniden inceleme gerekli'); expect(html).toContain('Aktarım kapalı'); expect(html).toContain('Değerlendirilmedi');
  });
  it('requires all dimensions, explicit outcomes and reasons and keeps source identity only', () => {
    expect(assessmentPayload([{ ...row, observations: row.observations.slice(1) }], 'SYNTHETIC note', '')).toBeNull();
    expect(assessmentPayload([{ ...row, observations: row.observations.map(item => ({ ...item, outcome: '' })) }], 'SYNTHETIC note', '')).toBeNull();
    expect(assessmentPayload([{ ...row, observations: row.observations.map(item => ({ ...item, note: '  ' })) }], 'SYNTHETIC note', '')).toBeNull();
    expect(assessmentPayload([row, row], 'SYNTHETIC note', '')).toBeNull();
    expect(assessmentPayload([row], 'SYNTHETIC note', '1.5')).toBeNull();
    expect(assessmentPayload([row], 'SYNTHETIC note', '')?.review_seconds).toBeNull();
    expect(assessmentPayload([row], 'SYNTHETIC note', '30')?.review_seconds).toBe(30);
  });
  it('recognizes only the exact committed-pending authority-review receipt', () => {
    expect(committedFindingReceipt({ id, outcome: 'committed_needs_revalidation', needs_revalidation: true })).toBe(id);
    for (const data of [null, { id }, { id, outcome: 'failed', needs_revalidation: true }, { id: '../private', outcome: 'committed_needs_revalidation', needs_revalidation: true }]) expect(committedFindingReceipt(data)).toBeNull();
  });
});
