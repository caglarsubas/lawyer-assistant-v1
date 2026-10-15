import { describe, expect, it, vi } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import type { NavigationMetadata, SourceTarget } from '../pages/sourceContextNavigationTypes';
import type { ReviewLineage, ReviewMetadata } from '../pages/sourceReviewLineageTypes';
import type { PortfolioQueuePage } from '../pages/portfolioSourceQueueTypes';
import { PortfolioReturnBook, PrincipalReturnBook, type ReturnIntent } from './portfolioReturn';
import type { ReviewPathHandoff } from './reviewPathHandoff';
import { captureComparisonReturn, reconcileComparisonReturn, type ComparisonReturnReceipt } from './comparisonReturn';

import { prepareComparisonEvent } from './comparisonEventHandoff';
import { captureArrivalReturn, reconcileArrivalReturn, validateArrivalReturn, type ArrivalReturn } from './arrivalReturn';
import ArrivalReturnPanel from '../pages/ArrivalReturnPanel';

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

async function retained(a = arrival()) {
  const f = fixture(), h = await prepare(f), captured = captureArrivalReturn(f.i, h, target(), a.context_navigation, a);
  return { ...f, handoff: h, a, observation: captured.observation! };
}
const later = (head = 4) => { const h = arrival(); h.current_head = row(head); h.context_navigation.historical_review = { id: id(head), state: row(head).state, recorded_at: stamp };
  h.observed_at = h.context_navigation.observed_at = '2026-10-15T02:02:00Z'; return h; };
const reconcile = (f: Awaited<ReturnType<typeof retained>>, h = later(), p = page(h)) => reconcileArrivalReturn(f.i, f.observation, p, h.context_navigation, h);
describe('guarded arrival return and fresh bounded queue reconciliation', () => {
  it('captures a separate fixed-depth arrival without rebasing receipt, queue, preparation, original unknowns or filters', async () => {
    const f = await retained(), before = structuredClone({ i: f.i, h: f.handoff, a: f.a });
    expect(f.observation.handoff).toEqual(f.handoff); expect(f.observation.arrival.metadata).toEqual(f.a.context_navigation);
    expect(f.observation.handoff.receipt.intent).toEqual(f.i); expect(Object.keys(f.observation).sort()).toEqual(['arrival', 'handoff', 'recipe']);
    expect(f.observation.handoff.receipt.intent.target.head_id).toBe(id(1)); expect(f.observation.arrival.selected.id).toBe(id(2));
    for (const word of ['lineage', 'PRIVATE TITLE', 'source_body', 'note']) expect(JSON.stringify(f.observation)).not.toContain(word);
    f.observation.arrival.metadata.analysis.current_version_id = 'mutated'; f.observation.handoff.receipt.intent.filters.customer_ids.pop();
    expect({ i: f.i, h: f.handoff, a: f.a }).toEqual(before);
    const g = fixture(); g.i.target.current_version_id = null; g.i.target.version_observed_at = null; g.i.target.head_id = null; g.i.target.head_state = 'unknown'; g.r.intent = structuredClone(g.i);
    const h = await prepare(g), r = captureArrivalReturn(g.i, h, target(), arrival().context_navigation, arrival());
    expect(r.observation!.handoff.receipt.intent.target.version_observed_at).toBeNull(); expect(r.intent).toEqual(g.i);
  });
  it('keeps selection only for unavailable metadata, without restoring the old receipt or inventing an arrival', async () => {
    const f = await retained(), r = captureArrivalReturn(f.i, f.handoff, target(), null, null); expect(r).toEqual({ intent: f.i, observation: null });
    expect(() => captureArrivalReturn(f.i, f.handoff, target(), f.a.context_navigation, null)).toThrow();
    expect(() => captureArrivalReturn(f.i, f.handoff, target(), null, f.a)).toThrow();
  });
  it.each(['review', 'context', 'prepare', 'meta', 'selected'] as const)('rejects %s substitution at explicit return', async kind => {
    const f = await retained(), t = target(), m = structuredClone(f.a.context_navigation);
    if (kind === 'review') t.review_id = id(4); if (kind === 'context') delete t.review_id; if (kind === 'prepare') t.prepare = 'renewal';
    if (kind === 'meta') m.analysis.revision++; if (kind === 'selected') { f.a.selected_review.packet_sha256 = 'e'.repeat(64); f.a.lineage.items[0].packet_sha256 = 'e'.repeat(64); }
    expect(() => captureArrivalReturn(f.i, f.handoff, t, m, f.a)).toThrow();
  });
  it('compares the arrival separately from the older receipt and preparation with no added requests', async () => {
    const a = later(5); a.context_navigation.analysis = { id: 'a', current_version_id: 'arrival-version', revision: 6 };
    const f = await retained(a), h = later(6); h.observed_at = h.context_navigation.observed_at = '2026-10-15T02:03:00Z'; h.context_navigation.analysis = { id: 'a', current_version_id: 'fresh-version', revision: 7 };
    const before = structuredClone(f.observation), r = reconcile(f, h);
    expect(r).toMatchObject({ state: 'observed', head_relation: 'different', version_relation: 'different', revision_relation: 'different' });
    expect(f.observation).toEqual(before); expect(f.observation.handoff.receipt.handoff.head.id).toBe(id(3)); expect(f.observation.handoff.prepared.head?.id).toBe(id(4)); expect(f.observation.arrival.head?.id).toBe(id(5));
    if (r.state !== 'observed') throw Error(); expect(r.fresh.head?.id).toBe(id(6)); expect(r.fresh.selected.id).toBe(id(2)); expect(f.read).toHaveBeenCalledTimes(2);
  });
  it('reports same head/version and independently changed revision without replacing historical values', async () => {
    const f = await retained(); expect(reconcile(f)).toMatchObject({ head_relation: 'same', version_relation: 'same', revision_relation: 'same' });
    const h = later(); h.context_navigation.analysis.revision++; expect(reconcile(f, h)).toMatchObject({ head_relation: 'same', version_relation: 'same', revision_relation: 'different' });
  });
  it.each(['head', 'version'] as const)('preserves unknown %s in either observation instead of inheriting known values', async kind => {
    const f = await retained(unknown(arrival(), kind)); expect(reconcile(f)).toMatchObject({ [kind === 'head' ? 'head_relation' : 'version_relation']: 'unknown' });
    const g = await retained(); expect(reconcile(g, unknown(later(), kind))).toMatchObject({ [kind === 'head' ? 'head_relation' : 'version_relation']: 'unknown' });
  });
  it.each(['context', 'selected', 'head'] as const)('keeps pending %s admissions in both observations without granting approval', async kind => {
    const a = arrival(); if (kind === 'context') a.context_navigation.admission.context_state = 'pending';
    if (kind === 'selected') { a.selected_review.admission = a.lineage.items[0].admission = 'pending'; a.tools_available = false; }
    if (kind === 'head') { a.current_head!.admission = 'pending'; a.context_navigation.admission.review_state = 'pending'; }
    const f = await retained(a); expect(f.observation.arrival).toMatchObject({ selected: a.selected_review, head: a.current_head });
    const r = reconcile(f); expect(r.state).toBe('observed'); expect(f.observation.arrival).toEqual({ metadata: a.context_navigation, selected: a.selected_review, head: a.current_head });
  });
  it.each(['extra', 'recursive', 'filters', 'baseline', 'frozen', 'manifest', 'selected', 'head', 'revision', 'time', 'prepared', 'queue'] as const)('rejects malformed retained %s before token allocation or eviction', async kind => {
    const f = await retained(), o = f.observation;
    if (kind === 'extra') Object.assign(o, { source_body: 'PRIVATE' }); if (kind === 'recursive') Object.assign(o, { previous: structuredClone(o) });
    if (kind === 'filters') o.handoff.receipt.intent.filters.customer_ids.pop(); if (kind === 'baseline') o.handoff.receipt.intent.target.current_version_id = 'rebased';
    if (kind === 'frozen') o.arrival.metadata.context.version_id = 'other'; if (kind === 'manifest') o.arrival.metadata.context.manifest_sha256 = 'e'.repeat(64);
    if (kind === 'selected') o.arrival.selected.packet_sha256 = 'e'.repeat(64); if (kind === 'head') o.arrival.head!.packet_sha256 = 'e'.repeat(64);
    if (kind === 'revision') o.arrival.metadata.analysis.revision--; if (kind === 'time') o.arrival.metadata.observed_at = stamp;
    if (kind === 'prepared') o.handoff.prepared.metadata.analysis.revision++; if (kind === 'queue') o.handoff.queue.head_relation = 'same';
    expect(() => validateArrivalReturn(o, f.i)).toThrow();
    let n = 0; const b = new PortfolioReturnBook(() => 0, () => (++n).toString(16).padStart(32, '0')); const tokens = Array.from({ length: 8 }, () => b.put(f.i));
    expect(() => b.putArrivalReturn(f.i, o)).toThrow(); expect(n).toBe(8); expect(b.get(tokens[0])).toEqual(f.i);
  });
  it.each(['customer_ids', 'date_field', 'date_from', 'date_to', 'source_date_from', 'source_date_to', 'bucket'] as const)('rejects changed exact %s filters', async key => {
    const f = await retained(), p = page(later());
    if (key === 'customer_ids') p.filters.customer_ids = ['A']; else if (key === 'date_field') p.filters.date_field = 'updated_at'; else if (key === 'bucket') p.filters.bucket = 'action_required'; else p.filters[key] = '';
    expect(() => reconcile(f, later(), p)).toThrow();
  });
  it('withholds retained details for a bounded omission, without using an old target response or inferring access loss', async () => {
    const f = await retained(), p = page(later()); p.items = []; p.coverage.returned_count = 0; p.coverage.scanned_count = 0; p.coverage.locked_matter_count = 0;
    const r = reconcileArrivalReturn(f.i, f.observation, p, null, null); expect(r).toEqual({ state: 'not_observed', queue_observed_at: p.observed_at });
    const html = renderToStaticMarkup(<ArrivalReturnPanel observation={f.observation} value={r} />); expect(html).toContain('ayrıntıları açılmadı'); for (const secret of [id(1), id(2), id(3), id(4), 'queue-version', 'frozen']) expect(html).not.toContain(secret);
    expect(() => reconcile(f, later(), p)).toThrow();
  });
  it.each(['queue-time', 'event-time', 'revision', 'chosen-packet', 'arrival-head-packet', 'prepared-head-packet', 'receipt-head-packet', 'frozen', 'manifest', 'scope', 'queue-head'] as const)('closes a fresh %s mismatch instead of rebasing history', async kind => {
    const a = arrival(); a.current_head = row(5); a.context_navigation.historical_review = { id: id(5), state: row(5).state, recorded_at: stamp };
    const f = await retained(a), h = later(5), p = page(h);
    if (kind === 'queue-time') p.observed_at = '2026-10-15T02:00:59Z'; if (kind === 'event-time') h.observed_at = h.context_navigation.observed_at = '2026-10-15T02:01:59Z';
    if (kind === 'revision') h.context_navigation.analysis.revision--; if (kind === 'chosen-packet') { h.selected_review.packet_sha256 = 'e'.repeat(64); h.lineage.items[0].packet_sha256 = 'e'.repeat(64); }
    if (kind.endsWith('head-packet')) { const n = kind === 'arrival-head-packet' ? 5 : kind === 'prepared-head-packet' ? 4 : 3; h.current_head = row(n); h.current_head.packet_sha256 = 'e'.repeat(64); h.context_navigation.historical_review = { id: id(n), state: row(n).state, recorded_at: stamp }; p.items[0].historical_review = structuredClone(h.context_navigation.historical_review); }
    if (kind === 'frozen') h.context_navigation.context.version_id = 'other'; if (kind === 'manifest') h.context_navigation.context.manifest_sha256 = 'e'.repeat(64); if (kind === 'scope') h.matter_id = 'other'; if (kind === 'queue-head') p.items[0].historical_review.id = id(6);
    expect(() => reconcile(f, h, p)).toThrow();
  });
  it('bounds and clones retained arrival records across eight-entry eviction, expiry, reload and principal changes', async () => {
    const f = await retained(); let now = 0, n = 0; const b = new PortfolioReturnBook(() => now, () => (++n).toString(16).padStart(32, '0'));
    const original = structuredClone(f.observation), token = b.putArrivalReturn(f.i, f.observation); f.observation.arrival.metadata.analysis.current_version_id = 'mutated';
    expect(b.getArrivalReturn(token)).toEqual(original); b.getArrivalReturn(token)!.handoff.receipt.intent.filters.customer_ids.pop(); expect(b.get(token)).toEqual(f.i); expect(b.getComparisonReturn(token)).toEqual(f.r);
    for (let k = 0; k < 8; k++) b.putArrivalReturn(f.i, original); expect(b.getArrivalReturn(token)).toBeNull();
    const last = b.putArrivalReturn(f.i, original); now = 30 * 60 * 1000; expect(b.getArrivalReturn(last)).toBeNull(); expect(new PortfolioReturnBook().getArrivalReturn(last)).toBeNull();
    const principal = new PrincipalReturnBook(), t = principal.forPrincipal('A').putArrivalReturn(f.i, original); expect(principal.forPrincipal('B').getArrivalReturn(t)).toBeNull(); expect(principal.forPrincipal('A').getArrivalReturn(t)).toBeNull();
    expect(b.getArrivalReturn(b.put(f.i))).toBeNull(); expect(b.getArrivalReturn('bad')).toBeNull();
  });
  it('renders historical arrival and fresh identities separately as metadata with no form, tool, link or approval', async () => {
    const f = await retained(), r = reconcile(f), html = renderToStaticMarkup(<ArrivalReturnPanel observation={f.observation} value={r} />);
    for (const word of [id(1), id(2), id(3), id(4), 'Varıştan portföye dönüş', 'önceki onay taşınmaz', 'Sabit karar, kanıt ve özgün filtreler korundu']) expect(html).toContain(word);
    expect(html).not.toMatch(/<(a |button|input|textarea)/); expect(html).not.toContain('PRIVATE TITLE');
    expect(Object.keys(f.observation).length).toBe(3); expect((f.observation as ArrivalReturn).recipe).toBe('private-arrival-return-v1');
  });
});
