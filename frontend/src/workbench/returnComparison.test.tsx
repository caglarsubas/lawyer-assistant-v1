import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import ReturnIdentityComparison from '../pages/ReturnIdentityComparison';
import { ReturnReconciliationPanel } from '../pages/PortfolioReturnQueue';
import type { PortfolioQueuePage } from '../pages/portfolioSourceQueueTypes';
import type { NavigationMetadata } from '../pages/sourceContextNavigationTypes';
import type { ReviewLineage, ReviewMetadata } from '../pages/sourceReviewLineageTypes';
import { captureReturn, departingReturn, reconcileReturn, validateReturn, type ReturnIntent } from './portfolioReturn';
import { compareReturnIdentities, returnComparisonLinks, verifyReturnSelection } from './returnComparison';

const ctx = `sac-${'a'.repeat(20)}-${'b'.repeat(32)}`, id = (n: number) => `sar-${'c'.repeat(20)}-${n.toString(16).padStart(32, '0')}`;
const initialTime = '2026-10-14T01:00:00Z', laterTime = '2026-10-14T02:00:00Z', token = '1'.repeat(32);
const page = (): PortfolioQueuePage => ({ recipe: 'private-portfolio-source-review-queue-v1', observed_at: initialTime,
  filters: { customer_ids: ['A', 'B'], date_field: 'updated_at', date_from: '2020-01-01', date_to: '2030-12-31', source_date_from: '2026-10-01', source_date_to: '2026-10-31', bucket: 'all' },
  items: [{ id: ctx, matter_id: 'm', analysis_id: 'a', matter_title: 'PRIVATE TITLE', recorded_at: initialTime, state: 'inspection_required', version_id: 'frozen', manifest_sha256: 'd'.repeat(64), historical_review: { id: id(2), state: 'changes_requested', recorded_at: initialTime },
    private_observation: { state: 'unchanged', reasons: [] }, source_verification: 'not_checked', legal_readiness: 'not_established' }],
  coverage: { scope: 'authorized_portfolio_window_only', scanned_count: 1, returned_count: 1, locked_matter_count: 1, has_more: false, next_offset: null, pagination_limit_reached: false, priority_scope: 'current_window_only', total_count: null, source_verification: 'not_checked' }, legal_readiness: 'not_established', qualification_granted: false });
const meta = (): NavigationMetadata => ({ recipe: 'private-source-context-navigation-v1', matter_id: 'm', analysis_id: 'a', context_id: ctx, observed_at: laterTime,
  analysis: { id: 'a', current_version_id: 'latest1', revision: 2 }, context: { id: ctx, version_id: 'frozen', manifest_sha256: 'd'.repeat(64), recorded_at: initialTime }, admission: { context_state: 'complete', review_state: 'complete' }, historical_review: { id: id(2), state: 'changes_requested', recorded_at: initialTime }, version_relation: 'different', integrity: 'verified', tools_available: true, source_verification: 'not_checked', legal_readiness: 'not_established', qualification_granted: false });
const row = (n: number): ReviewMetadata => ({ id: id(n), state: n === 1 ? 'reviewed_conditional' : 'changes_requested', sequence: n, recorded_at: initialTime, packet_sha256: 'e'.repeat(64), manifest_sha256: 'd'.repeat(64), previous_review_id: n === 1 ? null : id(n - 1), admission: 'complete', integrity: 'verified' });
const lineage = (m = meta()): ReviewLineage => ({ recipe: 'private-source-review-lineage-v1', matter_id: 'm', analysis_id: 'a', context_id: ctx, review_id: id(1), observed_at: m.observed_at, context_navigation: m, selected_review: row(1), current_head: row(2), head_relationship: 'different_from_head', lineage: { scope: 'selected_predecessors_only', status: 'complete_to_first_event', window: 10, items: [row(1)], next_review_id: null, total_count: null, head_reachability: 'not_checked' }, tools_available: true, source_verification: 'not_checked', legal_readiness: 'not_established', qualification_granted: false });
const initial = (): ReturnIntent => { const p = page(); return captureReturn(p, p.items[0]); };
const selected = (): ReturnIntent => departingReturn(initial(), meta(), lineage(), id(1));

describe('selected and current return identities', () => {
  it('compares separately timed original/fresh observations while retaining the selected event and frozen evidence', () => {
    const value = selected(), m = meta(); m.observed_at = '2026-10-14T03:00:00Z'; m.analysis.current_version_id = 'latest2';
    const c = compareReturnIdentities(value, m, lineage(m));
    expect(c.before.head_observed_at).toBe(initialTime); expect(c.before.version_observed_at).toBe(laterTime); expect(c.current.observed_at).toBe(m.observed_at);
    expect(c.head_relation).toBe('same'); expect(c.version_relation).toBe('different'); expect(c.selected_head_relation).toBe('different');
    expect(c.fixed.version_id).toBe('frozen'); expect(c.selected!.id).toBe(id(1)); expect(c.current.head_id).toBe(id(2)); expect(JSON.stringify(c)).not.toContain('PRIVATE TITLE');
  });
  it('does not rebase original head/version observations after explicit fresh follow-up navigation', () => {
    const value = selected(), m = meta(); m.observed_at = '2026-10-14T03:00:00Z'; m.analysis.current_version_id = 'latest2';
    const next = departingReturn(value, m, lineage(m), id(1));
    expect(next.target.current_version_id).toBe('latest1'); expect(next.target.version_observed_at).toBe(laterTime); expect(next.target.head_id).toBe(id(2)); expect(next.target.observed_at).toBe(initialTime);
    expect(next.filters).toEqual(value.filters); expect(compareReturnIdentities(next, m, lineage(m)).version_relation).toBe('different');
  });
  it('keeps a missing or explicitly unknown version baseline unknown instead of inferring no change', () => {
    expect(compareReturnIdentities(initial(), meta(), null).version_relation).toBe('unknown');
    const unknown = meta(); unknown.analysis.current_version_id = null; unknown.version_relation = 'unknown'; unknown.tools_available = false;
    const value = departingReturn(initial(), unknown, null); const next = departingReturn(value, meta(), null);
    expect(next.target.current_version_id).toBeNull(); expect(next.target.version_observed_at).toBe(laterTime); expect(compareReturnIdentities(next, meta(), null).version_relation).toBe('unknown');
  });
  it.each(['unknown', 'unreviewed'] as const)('keeps %s original head distinct from a verified newer head', state => {
    const value = initial(); value.target.head_id = null; value.target.head_state = state;
    expect(compareReturnIdentities(value, meta(), null).head_relation).toBe(state === 'unknown' ? 'unknown' : 'different');
  });
  it('does not claim current permission from the same immutable head or selected event', () => {
    const m = meta(), value = departingReturn(initial(), m, null); const c = compareReturnIdentities(value, m, null);
    expect(c.head_relation).toBe('same'); expect(c.version_relation).toBe('same'); expect(c.selected).toBeNull();
    const html = renderToStaticMarkup(<ReturnIdentityComparison value={c} links={{ selected: null, head: null, context: null }} />);
    expect(html).toContain('eski onay veya izin devralınmaz'); expect(html).not.toContain('<button'); expect(html).not.toContain('<textarea'); expect(html).not.toContain('download=');
  });
  it('reports unknown current identities and withholds a current-head link', () => {
    const m = meta(); m.historical_review = { id: null, state: 'unknown', recorded_at: null }; m.admission.review_state = 'unavailable'; m.analysis.current_version_id = null; m.tools_available = false; m.version_relation = 'unknown';
    const p = page(); p.items[0].historical_review = m.historical_review; const value = departingReturn(initial(), meta(), null), result = reconcileReturn(value, p, m, null);
    expect(result.state).toBe('observed'); if (result.state !== 'observed') throw new Error('Missing comparison');
    expect(result.comparison.head_relation).toBe('unknown'); expect(result.comparison.version_relation).toBe('unknown'); expect(returnComparisonLinks(value, result, token).head).toBeNull();
  });
  it('allows pending metadata follow-up without upgrading admission or opening evidence', () => {
    const m = meta(); m.admission.context_state = 'pending'; m.admission.review_state = 'pending'; const value = departingReturn(initial(), meta(), null), result = reconcileReturn(value, page(), m, null);
    const links = returnComparisonLinks(value, result, token); expect(links.head).toContain('review=' + id(2));
    expect(result.state === 'observed' && result.review_state).toBe('pending'); expect(result.state === 'observed' && result.context_state).toBe('pending');
  });
  it('shows unavailable selected-event metadata without substituting the head or offering its inspection link', () => {
    const m = meta(), l = lineage(m); l.selected_review = { ...row(1), state: 'unknown', sequence: null, recorded_at: null, packet_sha256: null, manifest_sha256: null, previous_review_id: null, admission: 'unavailable', integrity: 'unavailable' };
    l.tools_available = false; l.head_relationship = 'unestablished'; l.lineage = { ...l.lineage, status: 'unavailable', items: [] };
    const value = departingReturn(initial(), m, l, id(1)), result = reconcileReturn(value, page(), m, l);
    const links = returnComparisonLinks(value, result, token); expect(links.selected).toBeNull(); expect(links.head).toContain('review=' + id(2));
    expect(result.state === 'observed' && result.comparison.selected_head_relation).toBe('unknown');
  });
  it('builds only exact local context/event links and retains the opaque return token', () => {
    const value = selected(), result = reconcileReturn(value, page(), meta(), lineage()), links = returnComparisonLinks(value, result, token);
    expect(links.selected).toContain('review=' + id(1)); expect(links.head).toContain('review=' + id(2)); expect(links.context).not.toContain('review=');
    for (const href of Object.values(links)) { expect(href).toContain('source_context=' + ctx); expect(href).toContain('return=' + token); expect(href).not.toContain('customer'); expect(href).not.toContain('latest'); }
    expect(returnComparisonLinks(value, result, 'foreign')).toEqual({ selected: null, head: null, context: null });
    expect(returnComparisonLinks({ ...value, target: { ...value.target, matter_id: 'foreign' } }, result, token)).toEqual({ selected: null, head: null, context: null });
  });
  it('withholds all comparison actions outside the returned window', () => {
    const value = selected(), p = page(); p.items = []; const result = reconcileReturn(value, p, null, null), links = returnComparisonLinks(value, result, token);
    expect(links).toEqual({ selected: null, head: null, context: null }); expect(renderToStaticMarkup(<ReturnReconciliationPanel value={result} links={links} />)).not.toContain('<table');
  });
  it.each(['context', 'version', 'manifest', 'event', 'packet', 'foreign'] as const)('rejects changed %s before follow-up tools', field => {
    const value = selected(), m = meta(), l = lineage(m);
    if (field === 'context') m.context_id = `sac-${'f'.repeat(20)}-${'b'.repeat(32)}`;
    if (field === 'version') m.context.version_id = 'other';
    if (field === 'manifest') m.context.manifest_sha256 = 'f'.repeat(64);
    if (field === 'event') l.selected_review.id = id(2);
    if (field === 'packet') { l.selected_review.packet_sha256 = 'f'.repeat(64); l.lineage.items[0].packet_sha256 = 'f'.repeat(64); }
    if (field === 'foreign') m.matter_id = 'foreign';
    expect(() => verifyReturnSelection(value, m, l, id(1))).toThrow();
  });
  it('rejects mixed observation snapshots and a changed declaration on an immutable head', () => {
    const m = meta(), l = lineage(); m.analysis.current_version_id = 'latest2'; expect(() => verifyReturnSelection(selected(), m, l, id(1))).toThrow();
    const changed = meta(); changed.historical_review.state = 'reviewed_conditional'; expect(() => compareReturnIdentities(initial(), changed, null)).toThrow();
    expect(() => verifyReturnSelection(initial(), changed, null)).toThrow();
  });
  it('cannot capture a selected-event observation without its same-context metadata', () => {
    expect(() => departingReturn(initial(), null, lineage(), id(1))).toThrow();
  });
  it.each([
    (v: ReturnIntent) => { v.target.head_state = 'unreviewed'; },
    (v: ReturnIntent) => { v.target.head_id = null; },
    (v: ReturnIntent) => { v.target.current_version_id = 'latest1'; },
    (v: ReturnIntent) => { v.target.version_observed_at = 'invalid'; },
  ])('rejects incomplete or conflicting comparison baseline metadata', mutate => { const v = initial(); mutate(v); expect(() => validateReturn(v)).toThrow(); });
});
