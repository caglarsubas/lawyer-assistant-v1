import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import AnalysisSourceReviews from '../pages/matter/AnalysisSourceReviews';
import { sourceNavigationSelection, type NavigationMetadata } from '../pages/sourceContextNavigationTypes';
import type { ReviewLineage, ReviewMetadata } from '../pages/sourceReviewLineageTypes';
import type { ReturnIntent } from './portfolioReturn';
import type { RenewalObservation } from './renewalReconciliation';
import { completeRenewalAdmissions, independentReviewIntent, parentLineageIntent, reviewPreparationHref, verifyCommittedReview, verifyReviewPreparation, verifySameRenewalLink } from './renewalLineageNavigation';
const parent = `sac-${'a'.repeat(20)}-${'b'.repeat(32)}`, child = `sac-${'a'.repeat(20)}-${'c'.repeat(32)}`, stamp = '2026-10-15T00:00:00Z';
const rid = (n: number) => `sar-${'d'.repeat(20)}-${n.toString(16).padStart(32, '0')}`;
const nav = (): NavigationMetadata => ({ recipe: 'private-source-context-navigation-v1', matter_id: 'matter1', analysis_id: 'analysis1', context_id: parent, observed_at: stamp,
  analysis: { id: 'analysis1', current_version_id: 'new1', revision: 3 }, context: { id: parent, version_id: 'old1', manifest_sha256: '3'.repeat(64), recorded_at: stamp },
  admission: { context_state: 'complete', review_state: 'complete' }, historical_review: { id: rid(3), state: 'changes_requested', recorded_at: stamp }, version_relation: 'different', integrity: 'verified', tools_available: true, source_verification: 'not_checked', legal_readiness: 'not_established', qualification_granted: false });
const intent = (): ReturnIntent => ({ recipe: 'private-portfolio-return-intent-v2', filters: { customer_ids: ['A', 'B'], date_field: 'relevant_date', date_from: '2020-01-01', date_to: '2030-12-31', source_date_from: '2026-10-01', source_date_to: '2026-10-31', bucket: 'action_required' }, target: { matter_id: 'matter1', analysis_id: 'analysis1', context_id: parent, version_id: 'old1', manifest_sha256: '3'.repeat(64), head_id: rid(2), head_state: 'reviewed_conditional', current_version_id: 'old1', version_observed_at: stamp, review_id: null, review_packet_sha256: null, observed_at: stamp } });
const row = (n: number): ReviewMetadata => ({ id: rid(n), state: n === 2 ? 'reviewed_conditional' : 'changes_requested', sequence: n, recorded_at: stamp, packet_sha256: '7'.repeat(64), manifest_sha256: '3'.repeat(64), previous_review_id: rid(n - 1), admission: 'complete', integrity: 'verified' });
const history = (): ReviewLineage => ({ recipe: 'private-source-review-lineage-v1', matter_id: 'matter1', analysis_id: 'analysis1', context_id: parent, review_id: rid(2), observed_at: stamp, context_navigation: nav(), selected_review: row(2), current_head: row(3), head_relationship: 'different_from_head', lineage: { scope: 'selected_predecessors_only', status: 'truncated', window: 1, items: [row(2)], next_review_id: rid(1), total_count: null, head_reachability: 'not_checked' }, tools_available: true, source_verification: 'not_checked', legal_readiness: 'not_established', qualification_granted: false });
const link = (): RenewalObservation => ({ recipe: 'private-renewal-reconciliation-v1', matter_id: 'matter1', analysis_id: 'analysis1', observed_at: stamp, receipt: { request_id: 'e'.repeat(32), expected_request_sha256: '1'.repeat(64), expected_preview_sha256: '2'.repeat(64), parent_context_id: parent, expected_parent_manifest_sha256: '3'.repeat(64), expected_parent_review_id: rid(2), parent_version_id: 'old1', version_id: 'new1' }, outcome: 'verified', successor: { id: child, version_id: 'new1', manifest_sha256: '2'.repeat(64), packet_sha256: '4'.repeat(64) }, lineage: { scope: 'one_historical_link', parent_context_id: parent, parent_version_id: 'old1', parent_manifest_sha256: '3'.repeat(64), parent_packet_sha256: '5'.repeat(64), parent_review_id: rid(2), parent_review_packet_sha256: '7'.repeat(64), comparison_sha256: '6'.repeat(64), depth: 1, current_parent_head: 'not_checked', legal_equivalence: 'not_assessed' }, admission: { successor: 'complete', parent: 'complete', parent_review: 'complete' }, source_verification: 'not_checked', legal_readiness: 'not_established', review_inheritance: 'none', qualification_granted: false, effects_replayed: false });
const childNav = () => { const v = nav(); v.context_id = child; v.context = { ...v.context, id: child, version_id: 'new1', manifest_sha256: '2'.repeat(64) }; v.version_relation = 'same'; v.historical_review = { id: null, state: 'unreviewed', recorded_at: null }; v.admission.review_state = 'not_recorded'; return v; };
const childIntent = () => { const i = intent(); i.target.context_id = child; i.target.version_id = i.target.current_version_id = 'new1'; i.target.manifest_sha256 = '2'.repeat(64); i.target.head_id = null; i.target.head_state = 'unreviewed'; return i; };
describe('guarded parent lineage and separate successor review', () => {
  it('pins the captured historical packet instead of selecting a later head and clones every filter', () => {
    const i = intent(), next = parentLineageIntent(i, link(), nav(), history());
    expect(next.target.review_id).toBe(rid(2)); expect(next.target.review_packet_sha256).toBe('7'.repeat(64)); expect(next.target.head_id).toBe(rid(3)); expect(next.target.version_id).toBe('old1'); expect(next.target.current_version_id).toBe('new1'); expect(next.filters).toEqual(i.filters);
    next.filters.customer_ids.push('foreign'); expect(i.filters.customer_ids).toEqual(['A', 'B']); expect(i.target.head_id).toBe(rid(2)); expect(i.target.review_id).toBeNull();
  });
  it('does not invent a captured decision when the parent was originally unreviewed', () => {
    const v = link(); v.receipt.expected_parent_review_id = v.lineage!.parent_review_id = v.lineage!.parent_review_packet_sha256 = null; v.admission!.parent_review = 'not_recorded';
    const next = parentLineageIntent(intent(), v, nav(), null); expect(next.target.review_id).toBeNull(); expect(next.target.review_packet_sha256).toBeNull(); expect(next.target.head_id).toBe(rid(3));
    expect(() => parentLineageIntent(intent(), v, nav(), history())).toThrow();
  });
  it.each(['packet', 'version', 'scope', 'missing', 'pending', 'head_substitution'] as const)('closes parent %s substitution before navigation', fault => {
    const m = nav(), h = history(), l = link();
    if (fault === 'packet') h.selected_review.packet_sha256 = '9'.repeat(64);
    if (fault === 'version') m.context.version_id = 'different';
    if (fault === 'scope') m.matter_id = 'foreign';
    if (fault === 'pending') h.selected_review.admission = 'pending';
    if (fault === 'head_substitution') h.selected_review = row(3);
    expect(() => parentLineageIntent(intent(), l, m, fault === 'missing' ? null : h)).toThrow();
  });
  it.each(['successor', 'parent', 'parent_review'] as const)('withholds all follow-up when %s admission is pending', key => {
    const l = link(); l.admission![key] = 'pending'; expect(completeRenewalAdmissions(l)).toBe(false); expect(() => verifySameRenewalLink(link(), l)).toThrow();
  });
  it('drops a link changed between guarded observations, without inferring legal equivalence', () => {
    const l = link(); l.lineage!.comparison_sha256 = '9'.repeat(64); expect(() => verifySameRenewalLink(link(), l)).toThrow();
    expect(() => verifySameRenewalLink(link(), link())).not.toThrow(); expect(link().lineage!.legal_equivalence).toBe('not_assessed');
  });
  it('makes separate review intent and a closed opaque route without historical approval or filter changes', () => {
    const next = independentReviewIntent(childIntent(), childNav()), href = reviewPreparationHref(next, 'f'.repeat(32))!;
    expect(next.target.review_id).toBeNull(); expect(next.target.review_packet_sha256).toBeNull(); expect(next.filters).toEqual(intent().filters);
    const [path, query] = href.slice(1).split('?'); expect(sourceNavigationSelection(path, new URLSearchParams(query))).toMatchObject({ prepare: 'review', context_id: child });
    for (const suffix of ['&prepare=review', '&prepare=renewal', '&review=' + rid(2), '&work=foreign']) expect(sourceNavigationSelection(path, new URLSearchParams(query + suffix)).kind).toBe('invalid');
    expect(sourceNavigationSelection(path, new URLSearchParams(query.replace(/&return=[a-f0-9]+/, ''))).kind).toBe('invalid');
    expect(href).not.toContain('2030-12-31'); expect(href).not.toContain('customer');
  });
  it.each(['pending', 'stale', 'unknown_head', 'head', 'revision', 'hash', 'foreign'] as const)('withholds review tools for %s state', fault => {
    const before = childNav(), m = childNav();
    if (fault === 'pending') m.admission.context_state = 'pending';
    if (fault === 'stale') { m.analysis.current_version_id = 'later'; m.version_relation = 'different'; }
    if (fault === 'unknown_head') m.historical_review.state = 'unknown';
    if (fault === 'head') { m.historical_review = { id: rid(4), state: 'changes_requested', recorded_at: stamp }; m.admission.review_state = 'complete'; }
    if (fault === 'revision') m.analysis.revision++;
    if (fault === 'hash') m.context.manifest_sha256 = '9'.repeat(64);
    if (fault === 'foreign') m.matter_id = 'foreign';
    expect(() => verifyReviewPreparation(childIntent(), m, before)).toThrow();
  });
  it('accepts only the separately verified new post-commit head while keeping the original preparation unchanged', () => {
    const before = childNav(), after = childNav(); after.historical_review = { id: rid(1), state: 'changes_requested', recorded_at: stamp }; after.admission.review_state = 'complete';
    expect(() => verifyReviewPreparation(childIntent(), after, before)).toThrow();
    expect(() => verifyReviewPreparation(childIntent(), after, before, { id: rid(1), packet_sha256: '8'.repeat(64), state: 'changes_requested' })).not.toThrow();
    after.historical_review.id = rid(2); expect(() => verifyReviewPreparation(childIntent(), after, before, { id: rid(1), packet_sha256: '8'.repeat(64), state: 'changes_requested' })).toThrow();
    expect(before.historical_review.id).toBeNull();
  });
  it('renders only explicit fresh review controls, without renewal, history or export', () => {
    const html = renderToStaticMarkup(<AnalysisSourceReviews matterId="matter1" record={{ id: 'analysis1', latest_version_id: 'new1' }} selectedContext={{ id: child, version_id: 'new1', manifest_sha256: '2'.repeat(64) }} reviewOnly />);
    expect(html).toContain('Yeni bağımsız inceleme içeriğini ayrıca getir');
    for (const text of ['Araştırma pasajlarını getir', 'Bu kaydın kaynak bağlamını yenile', 'Güncel kaynak ve karar bağlarını kontrol et', 'Bağımsız karar geçmişini getir', 'kaynak incelemesini indir']) expect(html).not.toContain(text);
  });
  it('confirms the exact new packet and predecessor while rejecting a substituted confirmation', () => {
    const m = childNav(); m.historical_review = { id: rid(1), state: 'reviewed_conditional', recorded_at: stamp }; m.admission.review_state = 'complete';
    const event: ReviewMetadata = { ...row(1), state: 'reviewed_conditional', manifest_sha256: '2'.repeat(64), previous_review_id: null };
    const h: ReviewLineage = { ...history(), context_id: child, review_id: rid(1), context_navigation: m, selected_review: event, current_head: event, head_relationship: 'current_head', lineage: { scope: 'selected_predecessors_only', status: 'complete_to_first_event', window: 1, items: [event], next_review_id: null, total_count: null, head_reachability: 'not_checked' } };
    const pin = { id: rid(1), packet_sha256: event.packet_sha256!, state: 'reviewed_conditional' as const };
    expect(() => verifyCommittedReview(childIntent(), childNav(), pin, h)).not.toThrow();
    expect(() => verifyCommittedReview(childIntent(), childNav(), { ...pin, packet_sha256: '9'.repeat(64) }, h)).toThrow();
    const wrongBefore = childNav(); wrongBefore.historical_review = { id: rid(4), state: 'changes_requested', recorded_at: stamp }; wrongBefore.admission.review_state = 'complete';
    expect(() => verifyCommittedReview(childIntent(), wrongBefore, pin, h)).toThrow();
  });
});
