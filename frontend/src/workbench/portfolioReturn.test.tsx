import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { ReturnFilterSummary, ReturnReconciliationPanel } from '../pages/PortfolioReturnQueue';
import SourceReviewLineagePanel from '../pages/SourceReviewLineagePanel';
import { sourceContextHref, sourceNavigationSelection, type NavigationMetadata } from '../pages/sourceContextNavigationTypes';
import type { ReviewLineage, ReviewMetadata } from '../pages/sourceReviewLineageTypes';
import { queueFilters, type PortfolioQueuePage } from '../pages/portfolioSourceQueueTypes';
import { captureReturn, departingReturn, PortfolioReturnBook, PrincipalReturnBook, queueDestination, queueReturnHref, reconcileReturn, returnMatches, validateReturn, type ReturnIntent } from './portfolioReturn';

const context = `sac-${'a'.repeat(20)}-${'b'.repeat(32)}`, review = (n: number) => `sar-${'c'.repeat(20)}-${n.toString(16).padStart(32, '0')}`;
const filters = queueFilters({ customer_ids: ['customerB', 'customerA'], date_field: 'relevant_date', date_from: '1920-01-01', date_to: '2026-10-14' },
  { source_date_from: '2026-10-01', source_date_to: '2026-10-31', bucket: 'action_required' });
const stamp = '2026-10-14T00:00:00Z';
const page = (): PortfolioQueuePage => ({ recipe: 'private-portfolio-source-review-queue-v1', observed_at: stamp, filters: structuredClone(filters),
  items: [{ id: context, matter_id: 'matter1', analysis_id: 'analysis1', matter_title: 'PRIVATE TITLE not in intent', recorded_at: stamp, state: 'inspection_required', version_id: 'frozen1', product_id: 'p1', manifest_sha256: 'd'.repeat(64),
    historical_review: { id: review(2), state: 'changes_requested', recorded_at: stamp }, private_observation: { state: 'unchanged', reasons: [] }, source_verification: 'not_checked', legal_readiness: 'not_established' }],
  coverage: { scope: 'authorized_portfolio_window_only', scanned_count: 1, returned_count: 1, locked_matter_count: 1, has_more: false, next_offset: null, pagination_limit_reached: false, priority_scope: 'current_window_only', total_count: null, source_verification: 'not_checked' },
  legal_readiness: 'not_established', qualification_granted: false });
const metadata = (): NavigationMetadata => ({ recipe: 'private-source-context-navigation-v1', matter_id: 'matter1', analysis_id: 'analysis1', context_id: context, observed_at: stamp,
  analysis: { id: 'analysis1', current_version_id: 'current1', revision: 2 }, context: { id: context, version_id: 'frozen1', manifest_sha256: 'd'.repeat(64), recorded_at: stamp },
  admission: { context_state: 'complete', review_state: 'complete' }, historical_review: { id: review(2), state: 'changes_requested', recorded_at: stamp }, version_relation: 'different', integrity: 'verified', tools_available: true,
  source_verification: 'not_checked', legal_readiness: 'not_established', qualification_granted: false });
const row = (n: number): ReviewMetadata => ({ id: review(n), sequence: n, state: n === 1 ? 'reviewed_conditional' : 'changes_requested', recorded_at: stamp, previous_review_id: n === 1 ? null : review(n - 1),
  packet_sha256: 'e'.repeat(64), manifest_sha256: 'd'.repeat(64), admission: 'complete', integrity: 'verified' });
const lineage = (): ReviewLineage => ({ recipe: 'private-source-review-lineage-v1', matter_id: 'matter1', analysis_id: 'analysis1', context_id: context, review_id: review(1), observed_at: stamp,
  context_navigation: metadata(), selected_review: row(1), current_head: row(2), head_relationship: 'different_from_head',
  lineage: { scope: 'selected_predecessors_only', status: 'complete_to_first_event', window: 10, items: [row(1)], next_review_id: null, total_count: null, head_reachability: 'not_checked' },
  tools_available: true, source_verification: 'not_checked', legal_readiness: 'not_established', qualification_granted: false });
const intent = () => { const p = page(); return captureReturn(p, p.items[0]); };

describe('guarded portfolio return intent', () => {
  it('captures exact OR/date/bucket semantics and immutable evidence without titles or old result buffers', () => {
    const p = page(), value = captureReturn(p, p.items[0]);
    expect(value.filters).toEqual(filters); expect(value.target.version_id).toBe('frozen1'); expect(value.target.head_id).toBe(review(2));
    expect(JSON.stringify(value)).not.toContain('PRIVATE TITLE'); expect(Object.keys(value)).toEqual(['recipe', 'filters', 'target']);
    p.filters.customer_ids.push('foreign'); p.items[0].manifest_sha256 = 'f'.repeat(64); expect(value.filters.customer_ids).toEqual(['customerA', 'customerB']); expect(value.target.manifest_sha256).toBe('d'.repeat(64));
    expect(() => captureReturn(page(), structuredClone(page().items[0]))).toThrow();
  });
  it('bounds and clones a session-only pool; eviction, expiry and a new session never restore evidence', () => {
    let time = 0, nonce = 0; const book = new PortfolioReturnBook(() => time, () => (++nonce).toString(16).padStart(32, '0'));
    const value = intent(), first = book.put(value); value.target.manifest_sha256 = 'f'.repeat(64);
    const read = book.get(first)!; read.filters.customer_ids.push('foreign'); expect(book.get(first)!.filters.customer_ids).toEqual(['customerA', 'customerB']);
    expect(book.get(first)!.target.manifest_sha256).toBe('d'.repeat(64)); expect(new PortfolioReturnBook().get(first)).toBeNull();
    for (let n = 0; n < 8; n++) book.put(intent()); expect(book.get(first)).toBeNull();
    const last = book.put(intent()); time = 30 * 60 * 1000; expect(book.get(last)).toBeNull(); expect(book.remaining(last)).toBe(0);
  });
  it('uses only one opaque token in source/queue routes and rejects mixed or duplicate destinations', () => {
    const token = '1'.repeat(32), value = intent(), href = sourceContextHref('matter1', 'analysis1', context, review(1), token)!;
    const [path, query] = href.slice(1).split('?'); const selected = sourceNavigationSelection(path, new URLSearchParams(query));
    expect(selected.kind).toBe('selected'); if (selected.kind === 'selected') expect(returnMatches(value, selected)).toBe(true);
    expect(href).not.toContain('customerA'); expect(href).not.toContain('2026-10'); expect(href).not.toContain('frozen1');
    expect(sourceNavigationSelection(path, new URLSearchParams(query + '&return=' + token)).kind).toBe('invalid');
    expect(sourceContextHref('m', 'a', context, undefined, '../foreign')).toBeNull();
    expect(queueReturnHref(token)).toBe('#/work?view=source-reviews&return=' + token);
    expect(queueDestination(new URLSearchParams('view=source-reviews&return=' + token))).toEqual({ kind: 'sources', return_token: token });
    expect(sourceNavigationSelection('/work', new URLSearchParams('view=source-reviews&return=' + token))).toEqual({ kind: 'none' });
    for (const bad of ['return=' + token, 'view=source-reviews&return=bad', 'view=source-reviews&work=other', 'view=source-reviews&view=source-reviews', 'view=source-reviews&return=' + token + '&return=' + token]) expect(queueDestination(new URLSearchParams(bad)).kind).toBe('invalid');
    expect(queueDestination(new URLSearchParams())).toEqual({ kind: 'work' });
  });
  it('retains only intent across same-principal suspension and discards it on capability, actor or logout transitions', () => {
    const owner = new PrincipalReturnBook(), first = owner.forPrincipal('actor1:firm1:lawyer'), token = first.put(intent());
    expect(owner.forPrincipal('actor1:firm1:lawyer').get(token)).toEqual(intent());
    expect(owner.forPrincipal('actor1:firm1:revoked').get(token)).toBeNull();
    const next = owner.forPrincipal('actor1:firm1:lawyer'), second = next.put(intent());
    expect(owner.forPrincipal(null).get(second)).toBeNull(); expect(owner.forPrincipal('actor1:firm1:lawyer').get(second)).toBeNull();
    const third = owner.forPrincipal('actor1:firm1:lawyer').put(intent()); expect(owner.forPrincipal('actor2:firm1:lawyer').get(third)).toBeNull();
  });
  it('closes unknown work subpaths and unconsumed query delimiters', () => {
    expect(queueDestination(new URLSearchParams('view=source-reviews'), '/work/foreign').kind).toBe('invalid');
    expect(queueDestination(new URLSearchParams('view=source-reviews?return=ignored')).kind).toBe('invalid');
    expect(queueDestination(new URLSearchParams('view=source-reviews&return=' + '1'.repeat(32) + '?work=ignored')).kind).toBe('invalid');
  });
  it.each([
    (v: ReturnIntent) => { v.filters.customer_ids = ['customerB', 'customerA']; },
    (v: ReturnIntent) => { v.filters.customer_ids = ['customerA', 'customerA']; },
    (v: ReturnIntent) => { v.filters.date_from = '2026-02-29'; },
    (v: ReturnIntent) => { v.filters.date_from = '0000-01-01'; },
    (v: ReturnIntent) => { v.filters.date_from = '2026-11-01'; },
    (v: ReturnIntent) => { v.filters.source_date_to = '2026-09-30'; },
    (v: ReturnIntent) => { v.filters.source_date_from = '2026-1-01'; },
    (v: ReturnIntent) => { v.target.manifest_sha256 = null; },
    (v: ReturnIntent) => { v.target.context_id = 'external'; },
    (v: ReturnIntent) => { v.target.review_packet_sha256 = 'e'.repeat(64); },
    (v: ReturnIntent) => { Object.assign(v.target, { note: 'private note' }); },
    (v: ReturnIntent) => { Object.assign(v.filters, { label: 'private customer' }); },
    (v: ReturnIntent) => { Object.assign(v, { results: [] }); },
  ])('rejects ambiguous filters, calendar drift and content-bearing return intent', mutate => {
    const value = intent(); mutate(value); expect(() => validateReturn(value)).toThrow();
  });
  it('keeps an exact selected old event separate from a changed head and current version', () => {
    const original = intent(); original.target.head_id = review(1);
    const next = departingReturn(original, metadata(), lineage(), review(1));
    const m = metadata(); m.analysis.current_version_id = 'current2';
    const result = reconcileReturn(next, page(), m, lineage());
    expect(result.head_changed).toBe(true); expect(result.current_version_changed).toBe(true); expect(result.selected_review_state).toBe('reviewed_conditional');
    expect(next.target.review_id).toBe(review(1)); expect(next.target.version_id).toBe('frozen1'); expect(next.target.manifest_sha256).toBe('d'.repeat(64));
    const pending = metadata(); pending.admission.review_state = 'pending'; expect(reconcileReturn(next, page(), pending, lineage()).review_state).toBe('pending');
    expect(JSON.stringify(result)).not.toContain('qualified'); expect(JSON.stringify(result)).not.toContain('PRIVATE');
  });
  it('preserves an unavailable exact historical selection without inventing its packet or probing outside a returned window', () => {
    const value = departingReturn(intent(), null, null, review(1)); expect(value.target.review_id).toBe(review(1)); expect(value.target.review_packet_sha256).toBeNull();
    const p = page(); p.items = []; expect(reconcileReturn(value, p, null, null).state).toBe('not_observed');
    expect(() => reconcileReturn(value, p, metadata(), null)).toThrow();
  });
  it.each([
    (p: PortfolioQueuePage, _m: NavigationMetadata, _l: ReviewLineage) => { p.filters.customer_ids = []; },
    (_p: PortfolioQueuePage, m: NavigationMetadata, _l: ReviewLineage) => { m.historical_review.id = review(3); },
    (_p: PortfolioQueuePage, m: NavigationMetadata, _l: ReviewLineage) => { m.historical_review.state = 'reviewed_conditional'; },
    (_p: PortfolioQueuePage, m: NavigationMetadata, _l: ReviewLineage) => { m.matter_id = 'foreign'; },
    (_p: PortfolioQueuePage, m: NavigationMetadata, _l: ReviewLineage) => { m.context.manifest_sha256 = 'f'.repeat(64); },
    (p: PortfolioQueuePage, _m: NavigationMetadata, _l: ReviewLineage) => { p.items[0].version_id = 'current2'; },
    (_p: PortfolioQueuePage, _m: NavigationMetadata, l: ReviewLineage) => { l.selected_review.id = review(2); },
    (_p: PortfolioQueuePage, _m: NavigationMetadata, l: ReviewLineage) => { l.selected_review.packet_sha256 = 'f'.repeat(64); },
    (_p: PortfolioQueuePage, m: NavigationMetadata, _l: ReviewLineage) => { m.integrity = 'unavailable'; },
  ])('rejects non-atomic head drift, foreign contexts, changed evidence and substituted events', mutate => {
    const value = departingReturn(intent(), metadata(), lineage(), review(1)), p = page(), m = metadata(), l = lineage(); mutate(p, m, l);
    expect(() => reconcileReturn(value, p, m, l)).toThrow();
  });
  it('binds departure to the original frozen context instead of silently adopting newer evidence', () => {
    const m = metadata(); m.context.version_id = 'other'; expect(() => departingReturn(intent(), m, null)).toThrow();
    expect(returnMatches(intent(), { kind: 'selected', matter_id: 'foreign', analysis_id: 'analysis1', context_id: context })).toBe(false);
  });
  it('renders captured filter intent and bounded reconciliation without an approval or historical note', () => {
    const html = renderToStaticMarkup(<ReturnFilterSummary intent={intent()} />);
    expect(html).toContain('customerA, customerB'); expect(html).toContain('1920-01-01'); expect(html).toContain('2026-10-31'); expect(html).not.toContain('PRIVATE TITLE');
    const absent = renderToStaticMarkup(<ReturnReconciliationPanel value={{ state: 'not_observed', queue_observed_at: stamp }} reopen="#/any" />);
    expect(absent).toContain('bu sınırlı pencerede gözlenmedi'); expect(absent).not.toContain('href=');
    const history = renderToStaticMarkup(<SourceReviewLineagePanel value={lineage()} returnToken={'1'.repeat(32)} />);
    expect(history).toContain('return=' + '1'.repeat(32)); expect(history).toContain('review=' + review(2)); expect(history).not.toContain('textarea');
  });
});
