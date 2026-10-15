import { describe, expect, it, vi } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import type { NavigationMetadata, SourceTarget } from '../pages/sourceContextNavigationTypes';
import type { ReviewLineage, ReviewMetadata } from '../pages/sourceReviewLineageTypes';
import type { PortfolioQueuePage } from '../pages/portfolioSourceQueueTypes';
import { PortfolioReturnBook, PrincipalReturnBook, type ReturnIntent } from './portfolioReturn';
import type { ReviewPathHandoff } from './reviewPathHandoff';
import { captureComparisonReturn, reconcileComparisonReturn, type ComparisonReturnReceipt } from './comparisonReturn';

import { comparisonEventAvailable, prepareComparisonEvent, validateComparisonEventHandoff, compareComparisonEventArrival, returnComparisonEvent } from './comparisonEventHandoff';
import ComparisonEventArrivalPanel from '../pages/ComparisonEventArrivalPanel';

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
function unknown(h: ReviewLineage, kind: 'head' | 'version') {
  if (kind === 'head') { h.current_head = null; h.head_relationship = 'unestablished'; h.context_navigation.historical_review = { state: 'unknown', id: null, recorded_at: null }; h.context_navigation.admission.review_state = 'unknown'; }
  else { h.context_navigation.analysis.current_version_id = null; h.context_navigation.version_relation = 'unknown'; h.context_navigation.tools_available = false; h.tools_available = false; }
  return h;
}

function fixture() {
  const i = intent(), r = receipt(), h = snapshot(2, 10, 4);
  h.context_navigation.analysis = { id: 'a', current_version_id: 'queue-version', revision: 5 };
  h.observed_at = h.context_navigation.observed_at = '2026-10-15T02:00:00Z';
  const p = page(h), value = reconcileComparisonReturn(i, r, p, h.context_navigation, h); let calls = 0;
  const read = vi.fn(async (_url: string) => { const v = snapshot(2, 1, 4); v.context_navigation.analysis = structuredClone(h.context_navigation.analysis);
    v.observed_at = v.context_navigation.observed_at = `2026-10-15T02:00:0${++calls}Z`; return v; });
  return { i, r, h, p, value, read };
}
const prepare = (f = fixture()) => prepareComparisonEvent(f.i, f.r, f.value, f.read, () => true);
const arrival = () => { const h = snapshot(2, 10, 4); h.context_navigation.analysis = { id: 'a', current_version_id: 'queue-version', revision: 5 };
  h.observed_at = h.context_navigation.observed_at = '2026-10-15T02:01:00Z'; return h; };
describe('guarded comparison-to-exact-event handoff', () => {
  it('performs exactly two fresh one-record GETs and retains distinct original, receipt, queue and prepared observations', async () => {
    const f = fixture(), before = structuredClone({ i: f.i, r: f.r, v: f.value }), h = await prepare(f);
    expect(f.read).toHaveBeenCalledTimes(2); expect(f.read.mock.calls.every(([url]) => url.endsWith(`/reviews/${id(2)}/navigation-context?window=1`))).toBe(true);
    expect(h.receipt.intent).toEqual(f.i); expect(h.receipt.intent.target.current_version_id).toBe('original'); expect(h.receipt.intent.target.head_id).toBe(id(1));
    expect(h.receipt.handoff.head.id).toBe(id(3)); expect(h.receipt.destination.head?.id).toBe(id(3)); expect(h.queue.fresh.head?.id).toBe(id(4)); expect(h.prepared.head?.id).toBe(id(4));
    expect(h.observed_at).toEqual(['2026-10-15T02:00:01Z', '2026-10-15T02:00:02Z']); expect(h.prepared.metadata.observed_at).toBe(h.observed_at[1]);
    h.queue.fresh.metadata.analysis.current_version_id = 'mutated'; h.receipt.intent.filters.customer_ids.pop(); expect({ i: f.i, r: f.r, v: f.value }).toEqual(before);
    expect(JSON.stringify(h)).not.toContain('lineage'); expect(JSON.stringify(h)).not.toContain('PRIVATE TITLE');
  });
  it('does not require or infer head-to-selected reachability from a truncated one-record window', async () => {
    const f = fixture(); expect((await f.read('')).lineage.status).toBe('truncated'); f.read.mockClear(); await expect(prepare(f)).resolves.toBeTruthy(); expect(f.read).toHaveBeenCalledTimes(2);
  });
  it('preserves unknown original baselines without initializing them from the new queue or preparation', async () => {
    const f = fixture(); f.i.target.current_version_id = null; f.i.target.version_observed_at = null; f.i.target.head_id = null; f.i.target.head_state = 'unknown'; f.r.intent = structuredClone(f.i);
    const h = await prepare(f); expect(h.receipt.intent).toEqual(f.i); expect(h.receipt.intent.target.version_observed_at).toBeNull();
  });
  it.each(['context', 'selected', 'head', 'version', 'missing-head', 'tools'] as const)('withholds preparation for incomplete %s observation without reads', async kind => {
    const f = fixture(), h = f.h;
    if (kind === 'context') h.context_navigation.admission.context_state = 'pending';
    if (kind === 'selected') { h.selected_review.admission = 'pending'; h.lineage.items[0].admission = 'pending'; h.tools_available = false; }
    if (kind === 'head') { h.current_head!.admission = 'pending'; h.context_navigation.admission.review_state = 'pending'; }
    if (kind === 'version') unknown(h, 'version');
    if (kind === 'missing-head') unknown(h, 'head');
    if (kind === 'tools') { h.context_navigation.tools_available = false; h.tools_available = false; }
    const v = reconcileComparisonReturn(f.i, f.r, page(h), h.context_navigation, h);
    expect(comparisonEventAvailable(f.i, f.r, v)).toBeFalsy(); await expect(prepareComparisonEvent(f.i, f.r, v, f.read, () => true)).rejects.toThrow(); expect(f.read).not.toHaveBeenCalled();
  });
  it('never reads or creates a destination for an out-of-window selection', async () => {
    const f = fixture(), p = page(f.h); p.items = []; p.coverage.returned_count = 0; const v = reconcileComparisonReturn(f.i, f.r, p, null, null);
    expect(comparisonEventAvailable(f.i, f.r, v)).toBe(false); await expect(prepareComparisonEvent(f.i, f.r, v, f.read, () => true)).rejects.toThrow(); expect(f.read).not.toHaveBeenCalled();
  });
  it.each([1, 2])('closes a changed revision at preparation read %s', async stage => {
    const f = fixture(), normal = f.read.getMockImplementation()!; let n = 0;
    f.read.mockImplementation(async url => { const h = await normal(url); if (++n === stage) h.context_navigation.analysis.revision++; return h; });
    await expect(prepare(f)).rejects.toThrow(); expect(f.read).toHaveBeenCalledTimes(stage);
  });
  it.each(['head', 'version', 'frozen', 'manifest', 'selected-packet', 'selected-state', 'head-packet', 'pending', 'extra-content', 'window', 'old-time'] as const)('closes fresh %s drift without fallback, traversal or retry', async kind => {
    const f = fixture(), normal = f.read.getMockImplementation()!;
    f.read.mockImplementation(async url => { const h = await normal(url);
      if (kind === 'head') { h.current_head = row(5); h.context_navigation.historical_review = { id: id(5), state: row(5).state, recorded_at: stamp }; }
      if (kind === 'version') h.context_navigation.analysis.current_version_id = 'different';
      if (kind === 'frozen') h.context_navigation.context.version_id = 'other';
      if (kind === 'manifest') h.context_navigation.context.manifest_sha256 = 'e'.repeat(64);
      if (kind === 'selected-packet') { h.selected_review.packet_sha256 = 'e'.repeat(64); h.lineage.items[0].packet_sha256 = 'e'.repeat(64); }
      if (kind === 'selected-state') { h.selected_review.state = 'reviewed_conditional'; h.lineage.items[0].state = 'reviewed_conditional'; }
      if (kind === 'head-packet') h.current_head!.packet_sha256 = 'e'.repeat(64);
      if (kind === 'pending') { h.context_navigation.admission.context_state = 'pending'; }
      if (kind === 'extra-content') Object.assign(h, { note: 'PRIVATE CONTENT' });
      if (kind === 'window') h.lineage.window = 2;
      if (kind === 'old-time') h.observed_at = h.context_navigation.observed_at = stamp;
      return h;
    }); await expect(prepare(f)).rejects.toThrow(); expect(f.read).toHaveBeenCalledTimes(1);
  });
  it('rejects a forged queue comparison before reading, including a fabricated relation', async () => {
    const f = fixture(); if (f.value.state !== 'observed') throw Error(); f.value.head_relation = 'same';
    await expect(prepare(f)).rejects.toThrow(); expect(f.read).not.toHaveBeenCalled();
  });
  it('retires a late response after scope/filter/expiry change before dispatching another read', async () => {
    const f = fixture(); let active = false;
    await expect(prepareComparisonEvent(f.i, f.r, f.value, f.read, () => active)).rejects.toThrow(); expect(f.read).not.toHaveBeenCalled();
    active = true; const normal = f.read.getMockImplementation()!; f.read.mockImplementation(async url => { const h = await normal(url); active = false; return h; });
    await expect(prepareComparisonEvent(f.i, f.r, f.value, f.read, () => active)).rejects.toThrow(); expect(f.read).toHaveBeenCalledTimes(1);
  });
  it('propagates denied access without retry or inherited approval', async () => {
    const f = fixture(); f.read.mockRejectedValue(new Error('403')); await expect(prepare(f)).rejects.toThrow('403'); expect(f.read).toHaveBeenCalledTimes(1);
  });
  it('requires monotonic observation times across both fresh reads', async () => {
    const f = fixture(), normal = f.read.getMockImplementation()!; let n = 0;
    f.read.mockImplementation(async url => { const h = await normal(url); h.observed_at = h.context_navigation.observed_at = ++n === 1 ? '2026-10-15T02:00:05Z' : '2026-10-15T02:00:03Z'; return h; });
    await expect(prepare(f)).rejects.toThrow(); expect(f.read).toHaveBeenCalledTimes(2);
  });
  it.each(['extra', 'filters', 'baseline', 'queue', 'prepared-packet', 'prepared-revision', 'time-count', 'time-order', 'time-final'] as const)('rejects forged retained %s payload before creating a token', async kind => {
    const f = fixture(), h = await prepare(f);
    if (kind === 'extra') Object.assign(h, { note: 'PRIVATE CONTENT' });
    if (kind === 'filters') h.receipt.intent.filters.customer_ids = ['A'];
    if (kind === 'baseline') h.receipt.intent.target.current_version_id = 'other';
    if (kind === 'queue') h.queue.head_relation = 'same';
    if (kind === 'prepared-packet') h.prepared.selected.packet_sha256 = 'e'.repeat(64);
    if (kind === 'prepared-revision') h.prepared.metadata.analysis.revision++;
    if (kind === 'time-count') h.observed_at.pop();
    if (kind === 'time-order') h.observed_at[0] = '2026-10-15T03:00:00Z';
    if (kind === 'time-final') h.observed_at[1] = '2026-10-15T02:00:04Z';
    expect(() => validateComparisonEventHandoff(h, f.i)).toThrow(); expect(() => new PortfolioReturnBook().putComparisonEvent(f.i, h)).toThrow();
  });
  it('observes a real later head/version separately on arrival without substituting the selected event', async () => {
    const f = fixture(), h = await prepare(f), a = arrival(); a.current_head = row(5); a.context_navigation.historical_review = { id: id(5), state: row(5).state, recorded_at: stamp }; a.context_navigation.analysis = { id: 'a', current_version_id: 'arrival-version', revision: 6 };
    const result = compareComparisonEventArrival(f.i, h, target(), a); expect(result).toMatchObject({ head_relation: 'different', version_relation: 'different', revision_relation: 'different' });
    expect(result.fresh.selected.id).toBe(id(2)); expect(h.queue.fresh.head?.id).toBe(id(4)); expect(h.receipt.intent.target.head_id).toBe(id(1));
  });
  it.each(['head', 'version'] as const)('keeps an unknown arrival %s explicit rather than inferring approval', async kind => {
    const f = fixture(), h = await prepare(f), a = unknown(arrival(), kind); expect(compareComparisonEventArrival(f.i, h, target(), a)).toMatchObject({ [kind === 'head' ? 'head_relation' : 'version_relation']: 'unknown' });
  });
  it.each(['context', 'selected', 'head'] as const)('retains pending %s admission at arrival without completing it', async kind => {
    const f = fixture(), h = await prepare(f), a = arrival();
    if (kind === 'context') a.context_navigation.admission.context_state = 'pending';
    if (kind === 'selected') { a.selected_review.admission = 'pending'; a.lineage.items[0].admission = 'pending'; a.tools_available = false; }
    if (kind === 'head') { a.current_head!.admission = 'pending'; a.context_navigation.admission.review_state = 'pending'; }
    const r = compareComparisonEventArrival(f.i, h, target(), a); expect(r.fresh.metadata.admission.context_state === 'pending' || r.fresh.selected.admission === 'pending' || r.fresh.head?.admission === 'pending').toBe(true);
  });
  it.each(['chosen-packet', 'same-head-packet', 'old-time', 'revision', 'foreign'] as const)('rejects %s arrival rather than using a newer or unpinned event', async kind => {
    const f = fixture(), h = await prepare(f), a = arrival();
    if (kind === 'chosen-packet') { a.selected_review.packet_sha256 = 'e'.repeat(64); a.lineage.items[0].packet_sha256 = 'e'.repeat(64); }
    if (kind === 'same-head-packet') a.current_head!.packet_sha256 = 'e'.repeat(64);
    if (kind === 'old-time') a.observed_at = a.context_navigation.observed_at = '2026-10-15T02:00:01Z';
    if (kind === 'revision') a.context_navigation.analysis.revision--;
    if (kind === 'foreign') a.context_id = `sac-${'e'.repeat(20)}-${'b'.repeat(32)}`;
    expect(() => compareComparisonEventArrival(f.i, h, target(), a)).toThrow();
  });
  it.each(['review', 'context-only', 'context', 'prepare'] as const)('rejects %s redirection of the purpose-bound selection', async kind => {
    const f = fixture(), h = await prepare(f), t = target();
    if (kind === 'review') t.review_id = id(4);
    if (kind === 'context-only') delete t.review_id;
    if (kind === 'context') t.context_id = `sac-${'e'.repeat(20)}-${'b'.repeat(32)}`;
    if (kind === 'prepare') t.prepare = 'review';
    expect(() => compareComparisonEventArrival(f.i, h, t, arrival())).toThrow();
  });
  it('keeps the original receipt only after a verified arrival and uses selection-only return after missing metadata', async () => {
    const f = fixture(), h = await prepare(f), a = arrival();
    const valid = returnComparisonEvent(f.i, h, target(), a.context_navigation, a); expect(valid.receipt).toEqual(f.r); expect(valid.intent).toEqual(f.i);
    const missing = returnComparisonEvent(f.i, h, target(), null, null); expect(missing.receipt).toBeNull(); expect(missing.intent).toEqual(f.i);
    expect(() => returnComparisonEvent(f.i, h, target(), a.context_navigation, null)).toThrow();
  });
  it('bounds and clones the purpose payload with its intent, across eviction, expiry, reload and principal transitions', async () => {
    const f = fixture(), h = await prepare(f); let now = 0, n = 0; const b = new PortfolioReturnBook(() => now, () => (++n).toString(16).padStart(32, '0')), t = b.putComparisonEvent(f.i, h);
    h.receipt.intent.filters.customer_ids.pop(); expect(b.get(t)).toEqual(f.i); expect(b.getComparisonEvent(t)?.receipt.intent.filters.customer_ids).toEqual(['A', 'B']);
    b.getComparisonEvent(t)!.prepared.metadata.analysis.current_version_id = 'mutated'; expect(b.getComparisonEvent(t)?.prepared.metadata.analysis.current_version_id).toBe('queue-version');
    const clean = await prepare(fixture()); for (let k = 0; k < 8; k++) b.putComparisonEvent(f.i, clean); expect(b.getComparisonEvent(t)).toBeNull();
    const last = b.putComparisonEvent(f.i, clean); now = 30 * 60 * 1000; expect(b.getComparisonEvent(last)).toBeNull(); expect(new PortfolioReturnBook().getComparisonEvent(last)).toBeNull();
    const principal = new PrincipalReturnBook(), token = principal.forPrincipal('A').putComparisonEvent(f.i, clean); expect(principal.forPrincipal('B').getComparisonEvent(token)).toBeNull(); expect(principal.forPrincipal('A').getComparisonEvent(token)).toBeNull();
    expect(b.getComparisonEvent(b.put(f.i))).toBeNull(); expect(b.getComparisonEvent('bad')).toBeNull();
  });
  it('renders an observation-only destination with no content or implied legal effect', async () => {
    const f = fixture(), h = await prepare(f), html = renderToStaticMarkup(<ComparisonEventArrivalPanel handoff={h} value={compareComparisonEventArrival(f.i, h, target(), arrival())} />);
    for (const v of [id(1), id(2), id(3), id(4), 'queue-version', 'Aynı kimlik gözlendi', 'ayrı ve güncel kontroller gerektirir']) expect(html).toContain(v);
    expect(html).not.toMatch(/<(a |button|input|textarea)/); expect(html).not.toContain('PRIVATE TITLE');
  });
});
