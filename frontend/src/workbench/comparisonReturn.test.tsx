import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import ComparisonReturnPanel from '../pages/ComparisonReturnPanel';
import type { NavigationMetadata, SourceTarget } from '../pages/sourceContextNavigationTypes';
import type { ReviewLineage, ReviewMetadata } from '../pages/sourceReviewLineageTypes';
import type { PortfolioQueuePage } from '../pages/portfolioSourceQueueTypes';
import { PortfolioReturnBook, PrincipalReturnBook, type ReturnIntent } from './portfolioReturn';
import type { ReviewPathHandoff } from './reviewPathHandoff';
import { captureComparisonReturn, reconcileComparisonReturn, validateComparisonReturn, type ComparisonReturnReceipt } from './comparisonReturn';

const ctx = `sac-${'a'.repeat(20)}-${'b'.repeat(32)}`, id = (n: number) => `sar-${'c'.repeat(20)}-${n.toString(16).padStart(32, '0')}`;
const stamp = '2026-10-15T01:00:00Z';
const row = (n: number): ReviewMetadata => ({ id: id(n), sequence: n, state: n % 2 ? 'reviewed_conditional' : 'changes_requested',
  recorded_at: stamp, packet_sha256: n.toString(16).padStart(64, '0'), manifest_sha256: 'd'.repeat(64), previous_review_id: n === 1 ? null : id(n - 1), admission: 'complete', integrity: 'verified' });
const meta = (head = 3): NavigationMetadata => ({ recipe: 'private-source-context-navigation-v1', matter_id: 'm', analysis_id: 'a', context_id: ctx, observed_at: stamp,
  analysis: { id: 'a', current_version_id: 'newer', revision: 4 }, context: { id: ctx, version_id: 'frozen', manifest_sha256: 'd'.repeat(64), recorded_at: stamp },
  admission: { context_state: 'complete', review_state: 'complete' }, historical_review: { id: id(head), state: row(head).state, recorded_at: stamp },
  version_relation: 'different', integrity: 'verified', tools_available: true, source_verification: 'not_checked', legal_readiness: 'not_established', qualification_granted: false });
const snapshot = (selected = 2, window = 10, head = 3): ReviewLineage => ({ recipe: 'private-source-review-lineage-v1', matter_id: 'm', analysis_id: 'a', context_id: ctx, review_id: id(selected), observed_at: stamp,
  context_navigation: meta(head), selected_review: row(selected), current_head: row(head), head_relationship: selected === head ? 'current_head' : 'different_from_head',
  lineage: { scope: 'selected_predecessors_only', status: selected > window ? 'truncated' : 'complete_to_first_event', window,
    items: Array.from({ length: Math.min(selected, window) }, (_, i) => row(selected - i)), next_review_id: selected > window ? id(selected - window) : null, total_count: null, head_reachability: 'not_checked' },
  tools_available: true, source_verification: 'not_checked', legal_readiness: 'not_established', qualification_granted: false });
const intent = (selected = 2): ReturnIntent => ({ recipe: 'private-portfolio-return-intent-v2', filters: { customer_ids: ['A', 'B'], date_field: 'relevant_date', date_from: '2020-01-01', date_to: '2030-12-31', source_date_from: '2026-10-01', source_date_to: '2026-10-31', bucket: 'all' },
  target: { matter_id: 'm', analysis_id: 'a', context_id: ctx, version_id: 'frozen', manifest_sha256: 'd'.repeat(64), head_id: id(1), head_state: 'reviewed_conditional', current_version_id: 'original', version_observed_at: stamp,
    review_id: id(selected), review_packet_sha256: row(selected).packet_sha256, observed_at: stamp } });

const handoff = (): ReviewPathHandoff => ({ recipe: 'private-review-path-handoff-v1', matter_id: 'm', analysis_id: 'a', context_id: ctx, frozen_version_id: 'frozen', manifest_sha256: 'd'.repeat(64),
  selected: row(2), head: row(3), current_version_id: 'newer', revision: 4, observed_at: [stamp, stamp, stamp, stamp, stamp] });

const target = (): SourceTarget => ({ kind: 'selected', matter_id: 'm', analysis_id: 'a', context_id: ctx, review_id: id(2) });
const receipt = (h = snapshot(2), i = intent()): ComparisonReturnReceipt => captureComparisonReturn(i, handoff(), target(), h.context_navigation, h).receipt!;
const page = (h = snapshot(2)): PortfolioQueuePage => ({ recipe: 'private-portfolio-source-review-queue-v1', observed_at: h.observed_at, filters: structuredClone(intent().filters),
  items: [{ id: ctx, matter_id: 'm', analysis_id: 'a', matter_title: 'PRIVATE TITLE NOT RETAINED', recorded_at: stamp, state: 'inspection_required', version_id: 'frozen', product_id: 'p', manifest_sha256: 'd'.repeat(64),
    historical_review: structuredClone(h.context_navigation.historical_review), private_observation: { state: 'unchanged', reasons: [] }, source_verification: 'not_checked', legal_readiness: 'not_established' }],
  coverage: { scope: 'authorized_portfolio_window_only', scanned_count: 1, returned_count: 1, locked_matter_count: 1, has_more: false, next_offset: null, pagination_limit_reached: false, priority_scope: 'current_window_only', total_count: null, source_verification: 'not_checked' },
  legal_readiness: 'not_established', qualification_granted: false });
const reconcile = (r = receipt(), h = snapshot(2), p = page(h)) => reconcileComparisonReturn(r.intent, r, p, h.context_navigation, h);
function unknown(h: ReviewLineage, kind: 'head' | 'version') {
  if (kind === 'head') { h.current_head = null; h.head_relationship = 'unestablished'; h.context_navigation.historical_review = { state: 'unknown', id: null, recorded_at: null }; h.context_navigation.admission.review_state = 'unknown'; }
  else { h.context_navigation.analysis.current_version_id = null; h.context_navigation.version_relation = 'unknown'; h.context_navigation.tools_available = false; h.tools_available = false; }
  return h;
}
describe('guarded comparison return and fresh bounded queue reconciliation', () => {
  it('captures only the observed identities while retaining exact filters, baseline, evidence and event pin', () => {
    const i = intent(), h = snapshot(2, 10, 4); h.context_navigation.analysis = { id: 'a', current_version_id: 'destination', revision: 5 };
    const r = receipt(h, i), before = structuredClone({ i, h });
    expect(r.intent).toEqual(i); expect(r.handoff.head.id).toBe(id(3)); expect(r.destination.head?.id).toBe(id(4)); expect(r.destination.metadata.analysis.current_version_id).toBe('destination');
    expect(r.intent.target.head_id).toBe(id(1)); expect(r.intent.target.current_version_id).toBe('original'); expect(r.intent.target.review_id).toBe(id(2));
    expect(Object.keys(r.destination).sort()).toEqual(['head', 'metadata', 'selected']); expect(JSON.stringify(r)).not.toContain('lineage'); expect(JSON.stringify(r)).not.toContain('PRIVATE TITLE');
    r.destination.metadata.analysis.current_version_id = 'mutated'; r.intent.filters.customer_ids.pop(); expect({ i, h }).toEqual(before);
  });
  it('preserves explicitly unknown original baseline fields rather than initializing them from the destination', () => {
    const i = intent(); i.target.head_id = null; i.target.head_state = 'unknown'; i.target.current_version_id = null; i.target.version_observed_at = null;
    const r = receipt(snapshot(2), i); const p = page(); const result = reconcileComparisonReturn(i, r, p, snapshot(2).context_navigation, snapshot(2));
    expect(result.state).toBe('observed'); expect(r.intent).toEqual(i); expect(r.intent.target.version_observed_at).toBeNull();
  });
  it('uses a selection-only return when metadata is unavailable, with no receipt or erased packet', () => {
    const result = captureComparisonReturn(intent(), handoff(), target(), null, null); expect(result.receipt).toBeNull(); expect(result.intent).toEqual(intent());
    expect(() => captureComparisonReturn(intent(), handoff(), target(), meta(), null)).toThrow();
  });
  it.each(['other-event', 'context-only', 'prepare', 'foreign', 'selected-packet'] as const)('rejects a %s return rather than transferring its comparison', kind => {
    const t = target(), h = snapshot(2);
    if (kind === 'other-event') t.review_id = id(3);
    if (kind === 'context-only') delete t.review_id;
    if (kind === 'prepare') t.prepare = 'renewal';
    if (kind === 'foreign') t.matter_id = 'other';
    if (kind === 'selected-packet') { h.selected_review.packet_sha256 = 'e'.repeat(64); h.lineage.items[0].packet_sha256 = 'e'.repeat(64); }
    expect(() => captureComparisonReturn(intent(), handoff(), t, h.context_navigation, h)).toThrow();
  });
  it('reports stable identities against the retained destination without rebasing older observations', () => {
    const r = receipt(), before = structuredClone(r), result = reconcile(r);
    expect(result).toMatchObject({ state: 'observed', head_relation: 'same', version_relation: 'same', revision_relation: 'same' }); expect(r).toEqual(before);
  });
  it('compares later opposing heads and current versions with the destination, separately from handoff and original', () => {
    const dest = snapshot(2, 10, 4); dest.context_navigation.analysis = { id: 'a', current_version_id: 'destination', revision: 5 };
    const r = receipt(dest), fresh = snapshot(2, 10, 5); fresh.context_navigation.analysis = { id: 'a', current_version_id: 'fresh', revision: 6 };
    const result = reconcile(r, fresh); expect(result).toMatchObject({ state: 'observed', head_relation: 'different', version_relation: 'different', revision_relation: 'different' });
    expect(r.handoff.head.id).toBe(id(3)); expect(r.destination.head?.id).toBe(id(4)); expect(r.intent.target.head_id).toBe(id(1)); expect(r.intent.target.review_id).toBe(id(2));
    if (result.state !== 'observed') throw Error(); expect(result.fresh.head?.id).toBe(id(5)); expect(result.fresh.selected.id).toBe(id(2));
  });
  it('shows revision drift even when head and current version identities are unchanged', () => {
    const h = snapshot(2); h.context_navigation.analysis.revision++;
    expect(reconcile(receipt(), h)).toMatchObject({ head_relation: 'same', version_relation: 'same', revision_relation: 'different' });
  });
  it.each(['head', 'version'] as const)('preserves unknown %s observations in either direction without filling them from fresh data', kind => {
    const previous = receipt(unknown(snapshot(2), kind)); expect(reconcile(previous)).toMatchObject({ [kind === 'head' ? 'head_relation' : 'version_relation']: 'unknown' });
    const fresh = unknown(snapshot(2), kind); expect(reconcile(receipt(), fresh)).toMatchObject({ [kind === 'head' ? 'head_relation' : 'version_relation']: 'unknown' });
  });
  it.each(['context', 'selected', 'head'] as const)('retains %s pending admission without repair or approval transfer', kind => {
    const h = snapshot(2);
    if (kind === 'context') h.context_navigation.admission.context_state = 'pending';
    if (kind === 'selected') { h.selected_review.admission = 'pending'; h.lineage.items[0].admission = 'pending'; h.tools_available = false; }
    if (kind === 'head') { h.current_head!.admission = 'pending'; h.context_navigation.admission.review_state = 'pending'; }
    const r = receipt(h), result = reconcile(r, h); expect(result.state).toBe('observed'); expect(r.destination[kind === 'selected' ? 'selected' : 'head']?.admission === 'pending' || r.destination.metadata.admission.context_state === 'pending').toBe(true);
  });
  it('leaves out-of-window selection unobserved and withholds all retained private comparison details', () => {
    const r = receipt(), p = page(); p.items = []; p.coverage.returned_count = 0;
    const result = reconcileComparisonReturn(r.intent, r, p, null, null); expect(result.state).toBe('not_observed');
    const html = renderToStaticMarkup(<ComparisonReturnPanel receipt={r} value={result} />); expect(html).not.toContain(id(2)); expect(html).not.toContain('original'); expect(html).toContain('ayrıntıları açılmadı');
    expect(() => reconcileComparisonReturn(r.intent, r, p, meta(), snapshot(2))).toThrow();
  });
  it.each(['customers', 'date-field', 'date-from', 'date-to', 'source-from', 'source-to', 'bucket', 'baseline', 'packet', 'extra'] as const)('rejects a receipt bound to changed %s intent', kind => {
    const r = receipt(), i = structuredClone(r.intent);
    if (kind === 'customers') i.filters.customer_ids = ['A'];
    if (kind === 'date-field') i.filters.date_field = 'created_at';
    if (kind === 'date-from') i.filters.date_from = '2021-01-01';
    if (kind === 'date-to') i.filters.date_to = '2029-01-01';
    if (kind === 'source-from') i.filters.source_date_from = '2026-10-02';
    if (kind === 'source-to') i.filters.source_date_to = '2026-10-30';
    if (kind === 'bucket') i.filters.bucket = 'action_required';
    if (kind === 'baseline') i.target.current_version_id = 'different-original';
    if (kind === 'packet') i.target.review_packet_sha256 = 'e'.repeat(64);
    if (kind === 'extra') Object.assign(r, { note: 'PRIVATE CONTENT' });
    expect(() => validateComparisonReturn(r, i)).toThrow(); expect(() => new PortfolioReturnBook().putComparisonReturn(i, r)).toThrow();
  });
  it.each(['foreign-metadata', 'extra-metadata', 'extra-selected', 'extra-head', 'same-head-packet', 'selected-state', 'missing', 'regressive'] as const)('rejects a forged %s retained observation', kind => {
    const r = receipt();
    if (kind === 'foreign-metadata') r.destination.metadata.matter_id = 'other';
    if (kind === 'extra-metadata') Object.assign(r.destination.metadata, { text: 'PRIVATE CONTENT' });
    if (kind === 'extra-selected') Object.assign(r.destination.selected, { note: 'PRIVATE CONTENT' });
    if (kind === 'extra-head') Object.assign(r.destination.head!, { note: 'PRIVATE CONTENT' });
    if (kind === 'same-head-packet') r.destination.head!.packet_sha256 = 'e'.repeat(64);
    if (kind === 'selected-state') r.destination.selected.state = 'reviewed_conditional';
    if (kind === 'missing') delete (r.destination as Partial<typeof r.destination>).selected;
    if (kind === 'regressive') r.destination.metadata.analysis.revision = 3;
    expect(() => validateComparisonReturn(r, r.intent)).toThrow();
  });
  it.each(['queue-before-destination', 'metadata-before-queue', 'revision-before-destination', 'queue-filters', 'queue-head', 'queue-scope', 'selected-packet', 'selected-predecessor', 'frozen-evidence'] as const)('closes fresh %s drift without fallback', kind => {
    const r = receipt(), h = snapshot(2), p = page(h);
    if (kind === 'queue-before-destination') p.observed_at = '2026-10-14T00:00:00Z';
    if (kind === 'metadata-before-queue') p.observed_at = '2026-10-15T02:00:00Z';
    if (kind === 'revision-before-destination') { r.destination.metadata.analysis.revision = 5; }
    if (kind === 'queue-filters') p.filters.source_date_from = '';
    if (kind === 'queue-head') p.items[0].historical_review.id = id(4);
    if (kind === 'queue-scope') p.coverage.scope = 'all' as never;
    if (kind === 'selected-packet') { h.selected_review.packet_sha256 = 'e'.repeat(64); h.lineage.items[0].packet_sha256 = 'e'.repeat(64); }
    if (kind === 'selected-predecessor') { h.selected_review.previous_review_id = id(9); h.lineage.items[0].previous_review_id = id(9); }
    if (kind === 'frozen-evidence') p.items[0].version_id = 'new';
    expect(() => reconcileComparisonReturn(r.intent, r, p, h.context_navigation, h)).toThrow();
  });
  it('rejects a same destination-head packet substitution even when that head differs from the older handoff', () => {
    const r = receipt(snapshot(2, 10, 4)), h = snapshot(2, 10, 4); h.current_head!.packet_sha256 = 'e'.repeat(64); expect(() => reconcile(r, h)).toThrow();
  });
  it('keeps the receipt cloned, principal-bound, expiring and bounded with its intent; it grants no path destination', () => {
    let now = 0, n = 0; const b = new PortfolioReturnBook(() => now, () => (++n).toString(16).padStart(32, '0')), r = receipt(), token = b.putComparisonReturn(r.intent, r);
    r.intent.filters.customer_ids.pop(); r.destination.metadata.analysis.current_version_id = 'mutated'; expect(b.getComparisonReturn(token)?.intent.filters.customer_ids).toEqual(['A', 'B']); expect(b.get(token)?.filters.customer_ids).toEqual(['A', 'B']);
    b.getComparisonReturn(token)!.destination.metadata.analysis.current_version_id = 'other'; expect(b.getComparisonReturn(token)?.destination.metadata.analysis.current_version_id).toBe('newer'); expect(b.isReviewPath(token)).toBe(false);
    for (let x = 0; x < 8; x++) b.putComparisonReturn(intent(), receipt()); expect(b.getComparisonReturn(token)).toBeNull();
    const t = b.putComparisonReturn(intent(), receipt()); now = 30 * 60 * 1000; expect(b.getComparisonReturn(t)).toBeNull(); expect(b.get(t)).toBeNull();
    expect(b.getComparisonReturn(b.put(intent()))).toBeNull(); expect(new PortfolioReturnBook().getComparisonReturn(t)).toBeNull();
    const principals = new PrincipalReturnBook(), p = principals.forPrincipal('A').putComparisonReturn(intent(), receipt()); expect(principals.forPrincipal('B').getComparisonReturn(p)).toBeNull(); expect(principals.forPrincipal('A').getComparisonReturn(p)).toBeNull();
  });
  it('renders historical and fresh identities separately without body content, approval or new actions', () => {
    const r = receipt(), h = snapshot(2, 10, 4); h.context_navigation.analysis = { id: 'a', current_version_id: 'fresh', revision: 5 };
    const html = renderToStaticMarkup(<ComparisonReturnPanel receipt={r} value={reconcile(r, h)} />);
    for (const text of ['Özgün kuyruk gözlemi', 'Korunan geçiş gözlemi', 'Korunan hedef gözlemi', 'Yeni kuyrukta', 'Farklı kimlik gözlendi', id(1), id(2), id(3), id(4), 'original', 'newer', 'fresh', 'önceki onay taşınmaz']) expect(html).toContain(text);
    expect(html).not.toMatch(/<(a |button|input|textarea)/); expect(html).not.toContain('PRIVATE TITLE');
  });
});
