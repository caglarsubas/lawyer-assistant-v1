import { describe, expect, it, vi } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import SourceReviewLineagePanel from '../pages/SourceReviewLineagePanel';
import ReturnedReviewLineagePanel from '../pages/ReturnedReviewLineagePanel';
import type { NavigationMetadata } from '../pages/sourceContextNavigationTypes';
import type { ReviewLineage, ReviewMetadata } from '../pages/sourceReviewLineageTypes';
import { departingReturn, PortfolioReturnBook, PrincipalReturnBook, type ReturnIntent, type ReturnReconciliation } from './portfolioReturn';
import { compareReturnIdentities } from './returnComparison';
import type { ReviewPathHandoff } from './reviewPathHandoff';
import { captureReturnedLineage, observeReturnedLineage, prepareReturnedEvent, returnVerifiedEvent, verifyReturnedEventTarget } from './returnedReviewLineage';

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
const comparison = (i: ReturnIntent, h: ReviewLineage): ReturnReconciliation => ({ state: 'observed', comparison: compareReturnIdentities(i, h.context_navigation, h), private_state: 'unchanged', context_state: 'complete', review_state: 'complete', selected_review_state: h.selected_review.state, queue_observed_at: stamp, target_observed_at: stamp });
function fixture(selected = 2, head = 3) {
  const i = intent(selected), h = snapshot(selected, 10, head), c = comparison(i, h), basis = captureReturnedLineage(i, c, h)!;
  const read = vi.fn(async (url: string) => { const match = url.match(/reviews\/([^/]+)\/navigation-context\?window=(\d+)$/)!;
    const n = parseInt(match[1].slice(-32), 16); return snapshot(n, Number(match[2]), head); });
  return { i, h, c, basis, read };
}
const observe = (f: ReturnType<typeof fixture>) => observeReturnedLineage(f.basis, f.read, () => true);

describe('bounded returned-queue current-head lineage', () => {
  it('pins the exact observed comparison without rebasing the original head, filters or frozen evidence', () => {
    const f = fixture(), original = structuredClone(f.i);
    expect(f.basis.metadata.analysis).toEqual({ id: 'a', current_version_id: 'newer', revision: 4 });
    expect(f.basis.intent).toEqual(original); f.i.filters.customer_ids.pop(); f.h.selected_review.packet_sha256 = 'f'.repeat(64);
    expect(f.basis.intent.filters.customer_ids).toEqual(['A', 'B']); expect(f.basis.selected.packet_sha256).toBe(row(2).packet_sha256);
    expect(f.basis.intent.target.head_id).toBe(id(1)); expect(f.basis.intent.target.version_id).toBe('frozen');
  });
  it('verifies consecutive exact packet links with one explicit ten-record window and surrounding identity reads', async () => {
    const f = fixture(), result = await observe(f);
    expect(f.read.mock.calls.map(([url]) => url.split('/reviews/')[1])).toEqual([`${id(2)}/navigation-context?window=1`, `${id(3)}/navigation-context?window=10`, `${id(2)}/navigation-context?window=1`]);
    expect(result.status).toBe('verified_path'); expect(result.path.map(r => r.id)).toEqual([id(3), id(2)]);
    expect(result.selected_packet_sha256).toBe(row(2).packet_sha256); expect(result.head_packet_sha256).toBe(row(3).packet_sha256);
    expect(result.source_verification).toBe('not_checked'); expect(result.qualification_granted).toBe(false); expect(f.i.target.head_id).toBe(id(1));
  });
  it('reports same-event identity separately from a multi-event path', async () => {
    const result = await observe(fixture(3, 3)); expect(result.status).toBe('same_event'); expect(result.path).toEqual([row(3)]);
    const html = renderToStaticMarkup(<ReturnedReviewLineagePanel value={result} />);
    expect(html).toContain('aynı doğrulanmış kayıttır'); expect(html).toContain('Hukuki görüş birliği'); expect(html).not.toContain('<a'); expect(html).not.toContain('<button'); expect(html).not.toContain('<textarea');
  });
  it('keeps a real ten-record truncation unknown even if its prefix contains the selected event', async () => {
    const f = fixture(11, 12), result = await observe(f);
    expect(result).toMatchObject({ status: 'unknown', reason: 'truncated', window: 10, observed_count: 10, path: [] }); expect(f.read).toHaveBeenCalledTimes(3);
    const html = renderToStaticMarkup(<ReturnedReviewLineagePanel value={result} />); expect(html).toContain('Geçmiş penceresi kesildi'); expect(html).toContain('Toplam geçmiş bilinmiyor');
  });
  it('does not infer reachability or expand when the selected event is outside the window', async () => {
    const f = fixture(1, 12), result = await observe(f); expect(result.status).toBe('unknown'); expect(result.reason).toBe('truncated'); expect(f.read).toHaveBeenCalledTimes(3);
  });
  it('does not infer nonreachability from a complete observed chain lacking the selected identity', async () => {
    const f = fixture(); const alternate = { ...row(2), id: id(44) };
    f.basis.intent.target.review_id = alternate.id; f.basis.intent.target.review_packet_sha256 = alternate.packet_sha256; f.basis.selected = alternate;
    f.read.mockImplementation(async url => { const head = url.includes('window=10'), v = snapshot(head ? 3 : 2, head ? 10 : 1);
      if (!head) { v.review_id = alternate.id; v.selected_review = alternate; v.lineage.items = [alternate]; } return v; });
    expect(await observe(f)).toMatchObject({ status: 'unknown', reason: 'not_observed', path: [] }); expect(f.read).toHaveBeenCalledTimes(3);
  });
  it.each(['unavailable', 'pending'] as const)('withholds a path for an %s member without repair or extra windows', async reason => {
    const f = fixture(), normal = f.read.getMockImplementation()!;
    f.read.mockImplementation(async url => { const v = await normal(url); if (url.includes('window=10')) {
      if (reason === 'unavailable') { v.lineage.status = 'unavailable'; v.lineage.items = [row(3)]; v.tools_available = false; }
      else v.lineage.items[2].admission = 'pending';
    } return v; });
    expect(await observe(f)).toMatchObject({ status: 'unknown', reason, path: [] }); expect(f.read).toHaveBeenCalledTimes(3);
  });
  it.each(['context-pending', 'review-pending', 'selected-pending', 'head-unavailable', 'version-unknown'] as const)('withholds initial action for %s metadata', kind => {
    const f = fixture(); const h = f.h;
    if (kind === 'context-pending') h.context_navigation.admission.context_state = 'pending';
    if (kind === 'review-pending') { h.context_navigation.admission.review_state = 'pending'; h.current_head!.admission = 'pending'; }
    if (kind === 'selected-pending') { h.selected_review.admission = 'pending'; h.lineage.items[0].admission = 'pending'; h.tools_available = false; }
    if (kind === 'head-unavailable') { h.current_head = { ...row(3), integrity: 'unavailable', state: 'unknown', sequence: null, recorded_at: null, packet_sha256: null, manifest_sha256: null, previous_review_id: null, admission: 'unavailable' }; h.head_relationship = 'unestablished'; h.context_navigation.historical_review.state = 'unknown'; h.context_navigation.admission.review_state = 'unavailable'; h.context_navigation.tools_available = false; h.tools_available = false; }
    if (kind === 'version-unknown') { h.context_navigation.analysis.current_version_id = null; h.context_navigation.version_relation = 'unknown'; h.context_navigation.tools_available = false; h.tools_available = false; }
    expect(captureReturnedLineage(f.i, comparison(f.i, h), h)).toBeNull();
  });
  it('requires an observed target, exact captured comparison and selected packet pin', () => {
    const f = fixture(); expect(captureReturnedLineage(f.i, { state: 'not_observed', queue_observed_at: stamp }, null)).toBeNull();
    const noPin = structuredClone(f.i); noPin.target.review_packet_sha256 = null; expect(captureReturnedLineage(noPin, f.c, f.h)).toBeNull();
    if (f.c.state !== 'observed') throw Error(); f.c.comparison.current.version_id = 'substitute'; expect(() => captureReturnedLineage(f.i, f.c, f.h)).toThrow();
  });
  it.each(['head', 'version', 'revision', 'context', 'manifest', 'selected-packet', 'head-packet', 'foreign', 'admission', 'scope-content', 'older-time'] as const)('retires the result on %s drift', async kind => {
    const f = fixture(), normal = f.read.getMockImplementation()!;
    f.read.mockImplementation(async url => { const v = await normal(url);
      if (kind === 'head') { v.current_head = row(4); v.context_navigation.historical_review = { id: id(4), state: row(4).state, recorded_at: stamp }; }
      if (kind === 'version') v.context_navigation.analysis.current_version_id = 'other';
      if (kind === 'revision') v.context_navigation.analysis.revision++;
      if (kind === 'context') v.context_id = `sac-${'e'.repeat(20)}-${'b'.repeat(32)}`;
      if (kind === 'manifest') v.context_navigation.context.manifest_sha256 = 'f'.repeat(64);
      if (kind === 'selected-packet') { v.selected_review.packet_sha256 = 'f'.repeat(64); v.lineage.items[0].packet_sha256 = 'f'.repeat(64); }
      if (kind === 'head-packet') v.current_head!.packet_sha256 = 'f'.repeat(64);
      if (kind === 'foreign') v.matter_id = 'other';
      if (kind === 'admission') v.context_navigation.admission.context_state = 'pending';
      if (kind === 'scope-content') Object.assign(v.selected_review, { note: 'PRIVATE BODY' });
      if (kind === 'older-time') v.observed_at = v.context_navigation.observed_at = '2026-10-14T01:00:00Z';
      return v;
    });
    await expect(observe(f)).rejects.toThrow(); expect(f.read).toHaveBeenCalledTimes(1);
  });
  it.each(['packet', 'predecessor', 'sequence', 'scope', 'window', 'cycle'] as const)('rejects a forged %s inside the head window', async kind => {
    const f = fixture(), normal = f.read.getMockImplementation()!;
    f.read.mockImplementation(async url => { const v = await normal(url); if (url.includes('window=10')) {
      if (kind === 'packet') v.lineage.items[1].packet_sha256 = 'f'.repeat(64);
      if (kind === 'predecessor') v.lineage.items[0].previous_review_id = id(7);
      if (kind === 'sequence') v.lineage.items[1].sequence = 7;
      if (kind === 'scope') v.analysis_id = 'foreign';
      if (kind === 'window') v.lineage.window = 11;
      if (kind === 'cycle') v.lineage.items[2] = row(3);
    } return v; });
    await expect(observe(f)).rejects.toThrow();
  });
  it('rejects a head or revision change during the final identity observation', async () => {
    const f = fixture(), normal = f.read.getMockImplementation()!; let count = 0;
    f.read.mockImplementation(async url => { const v = await normal(url); if (++count === 3) v.context_navigation.analysis.revision++; return v; });
    await expect(observe(f)).rejects.toThrow(); expect(f.read).toHaveBeenCalledTimes(3);
  });
  it('rejects observations that run backwards between the identity brackets', async () => {
    const f = fixture(), normal = f.read.getMockImplementation()!; let count = 0;
    f.read.mockImplementation(async url => { const v = await normal(url); if (++count === 1) v.observed_at = v.context_navigation.observed_at = '2026-10-15T02:00:00Z'; return v; });
    await expect(observe(f)).rejects.toThrow();
  });
  it('stops before the next request after a late filter, principal, expiry or scope retirement', async () => {
    const f = fixture(); let active = true; const normal = f.read.getMockImplementation()!;
    f.read.mockImplementation(async url => { const value = await normal(url); active = false; return value; });
    await expect(observeReturnedLineage(f.basis, f.read, () => active)).rejects.toThrow(); expect(f.read).toHaveBeenCalledTimes(1);
  });
  it('propagates denied access without fallback, retry, source read or write', async () => {
    const f = fixture(); f.read.mockRejectedValue(new Error('403'));
    await expect(observe(f)).rejects.toThrow('403'); expect(f.read).toHaveBeenCalledTimes(1);
  });
});


describe('guarded exact-event selection from a verified path', () => {
  async function prepared(selected = 1, head = 3) { const f = fixture(selected, head), previous = await observe(f); f.read.mockClear(); return { ...f, previous }; }
  it.each([1, 2, 3])('selects only exact path member %s with five fresh bounded reads and unchanged original fields', async chosen => {
    const f = await prepared(), before = structuredClone(f.i);
    const { intent: next } = await prepareReturnedEvent(f.basis, f.previous, id(chosen), f.read, () => true);
    expect(f.read.mock.calls.map(([url]) => url.split('/reviews/')[1])).toEqual([`${id(1)}/navigation-context?window=1`, `${id(chosen)}/navigation-context?window=1`, `${id(3)}/navigation-context?window=10`, `${id(chosen)}/navigation-context?window=1`, `${id(1)}/navigation-context?window=1`]);
    expect(next).toEqual({ ...before, target: { ...before.target, review_id: id(chosen), review_packet_sha256: row(chosen).packet_sha256 } });
    expect(f.i).toEqual(before); next.filters.customer_ids.pop(); expect(f.i.filters.customer_ids).toEqual(['A', 'B']);
  });
  it('captures handoff metadata and all five timestamps from the fresh reads rather than the original baseline', async () => {
    const f = await prepared(), normal = f.read.getMockImplementation()!; let n = 0;
    f.read.mockImplementation(async url => { const v = await normal(url); v.observed_at = v.context_navigation.observed_at = `2026-10-15T01:00:0${++n}Z`; return v; });
    const { intent: next, handoff } = await prepareReturnedEvent(f.basis, f.previous, id(2), f.read, () => true);
    expect(handoff.observed_at).toEqual([1, 2, 3, 4, 5].map(v => `2026-10-15T01:00:0${v}Z`));
    expect(handoff.current_version_id).toBe('newer'); expect(handoff.revision).toBe(4); expect(handoff.head).toEqual(row(3)); expect(handoff.selected).toEqual(row(2));
    expect(next.target.current_version_id).toBe('original'); expect(next.target.head_id).toBe(id(1)); expect(next.target.version_observed_at).toBe(stamp);
    handoff.head.state = 'changes_requested'; expect(f.basis.head).toEqual(row(3));
  });
  it('supports a complete same-event path without interpreting it as approval', async () => {
    const f = await prepared(1, 1); const { intent: next } = await prepareReturnedEvent(f.basis, f.previous, id(1), f.read, () => true);
    expect(next.target.review_id).toBe(id(1)); expect(f.read).toHaveBeenCalledTimes(5);
  });
  it('preserves unknown original baselines on preparation and a subsequent exact-event queue return', async () => {
    const f = await prepared(); f.basis.intent.target.current_version_id = null; f.basis.intent.target.version_observed_at = null; f.basis.intent.target.head_id = null; f.basis.intent.target.head_state = 'unknown';
    const { intent: next } = await prepareReturnedEvent(f.basis, f.previous, id(2), f.read, () => true);
    const history = snapshot(2), returned = departingReturn(next, history.context_navigation, history, id(2));
    expect(returned).toEqual(next); expect(returned.target.version_observed_at).toBeNull(); expect(returned.target.head_state).toBe('unknown');
  });
  it('does not read metadata for a nonmember or unknown/truncated observation', async () => {
    const f = await prepared(); await expect(prepareReturnedEvent(f.basis, f.previous, id(4), f.read, () => true)).rejects.toThrow(); expect(f.read).not.toHaveBeenCalled();
    const u = await prepared(1, 12); expect(u.previous.status).toBe('unknown');
    await expect(prepareReturnedEvent(u.basis, u.previous, id(1), u.read, () => true)).rejects.toThrow(); expect(u.read).not.toHaveBeenCalled();
  });
  it.each(['selected', 'head', 'window', 'readiness', 'origin', 'empty', 'status'] as const)('rejects an unbound previous %s observation before reads', async kind => {
    const f = await prepared(), v = structuredClone(f.previous);
    if (kind === 'selected') v.selected_packet_sha256 = 'f'.repeat(64);
    if (kind === 'head') v.head_id = id(4);
    if (kind === 'window') v.window = 11;
    if (kind === 'readiness') v.qualification_granted = true as never;
    if (kind === 'origin') v.path[0] = row(4);
    if (kind === 'empty') v.path = [];
    if (kind === 'status') v.status = 'unknown';
    await expect(prepareReturnedEvent(f.basis, v, id(2), f.read, () => true)).rejects.toThrow(); expect(f.read).not.toHaveBeenCalled();
  });
  it.each(['packet', 'state', 'sequence', 'predecessor', 'foreign-content'] as const)('rejects a substituted intermediate %s even in an otherwise matching prior path', async kind => {
    const f = await prepared(), v = structuredClone(f.previous), member = v.path[1];
    if (kind === 'packet') member.packet_sha256 = 'f'.repeat(64);
    if (kind === 'state') member.state = 'reviewed_conditional';
    if (kind === 'sequence') member.sequence = 99;
    if (kind === 'predecessor') member.previous_review_id = id(7);
    if (kind === 'foreign-content') Object.assign(member, { note: 'PRIVATE' });
    await expect(prepareReturnedEvent(f.basis, v, id(2), f.read, () => true)).rejects.toThrow();
  });
  it.each(['pending', 'unavailable'] as const)('withholds a link after fresh %s history without expansion or repair', async kind => {
    const f = await prepared(2, 3), normal = f.read.getMockImplementation()!;
    f.read.mockImplementation(async url => { const v = await normal(url); if (url.includes('window=10')) {
      if (kind === 'pending') v.lineage.items.at(-1)!.admission = 'pending';
      else { v.lineage.status = 'unavailable'; v.lineage.items = [row(3)]; v.tools_available = false; }
    } return v; });
    await expect(prepareReturnedEvent(f.basis, f.previous, id(3), f.read, () => true)).rejects.toThrow(); expect(f.read).toHaveBeenCalledTimes(5);
  });
  it.each([1, 2, 3, 4, 5])('retires a revision drift at fresh observation %s', async stage => {
    const f = await prepared(), normal = f.read.getMockImplementation()!; let call = 0;
    f.read.mockImplementation(async url => { const v = await normal(url); if (++call === stage) v.context_navigation.analysis.revision++; return v; });
    await expect(prepareReturnedEvent(f.basis, f.previous, id(2), f.read, () => true)).rejects.toThrow(); expect(f.read).toHaveBeenCalledTimes(stage);
  });
  it.each(['head', 'version', 'context', 'manifest', 'chosen-packet', 'admission'] as const)('closes on %s changes during the chosen-member observation', async kind => {
    const f = await prepared(), normal = f.read.getMockImplementation()!;
    f.read.mockImplementation(async url => { const v = await normal(url); if (url.includes(id(2))) {
      if (kind === 'head') { v.current_head = row(4); v.context_navigation.historical_review = { id: id(4), state: row(4).state, recorded_at: stamp }; }
      if (kind === 'version') v.context_navigation.analysis.current_version_id = 'other';
      if (kind === 'context') v.context_id = `sac-${'f'.repeat(20)}-${'b'.repeat(32)}`;
      if (kind === 'manifest') v.context_navigation.context.manifest_sha256 = 'f'.repeat(64);
      if (kind === 'chosen-packet') { v.selected_review.packet_sha256 = 'f'.repeat(64); v.lineage.items[0].packet_sha256 = 'f'.repeat(64); }
      if (kind === 'admission') { v.selected_review.admission = 'pending'; v.lineage.items[0].admission = 'pending'; v.tools_available = false; }
    } return v; });
    await expect(prepareReturnedEvent(f.basis, f.previous, id(2), f.read, () => true)).rejects.toThrow(); expect(f.read).toHaveBeenCalledTimes(2);
  });
  it('rejects a past observation and stops further dispatch after a retired scope or access denial', async () => {
    const f = await prepared(); f.previous.after_observed_at = '2026-10-15T03:00:00Z';
    await expect(prepareReturnedEvent(f.basis, f.previous, id(2), f.read, () => true)).rejects.toThrow();
    f.previous.after_observed_at = stamp; let active = true; const normal = f.read.getMockImplementation()!; f.read.mockClear();
    f.read.mockImplementation(async url => { const v = await normal(url); active = false; return v; });
    await expect(prepareReturnedEvent(f.basis, f.previous, id(2), f.read, () => active)).rejects.toThrow(); expect(f.read).toHaveBeenCalledTimes(1);
    f.read.mockClear(); f.read.mockRejectedValue(new Error('403')); await expect(prepareReturnedEvent(f.basis, f.previous, id(2), f.read, () => true)).rejects.toThrow('403'); expect(f.read).toHaveBeenCalledTimes(1);
  });
  it('keeps path markers session-local, bounded, cloned and principal-bound', () => {
    let now = 0, nonce = 0; const book = new PortfolioReturnBook(() => now, () => (++nonce).toString(16).padStart(32, '0')), value = intent();
    const handoff: ReviewPathHandoff = { recipe: 'private-review-path-handoff-v1', matter_id: 'm', analysis_id: 'a', context_id: ctx, frozen_version_id: 'frozen', manifest_sha256: 'd'.repeat(64), selected: row(2), head: row(3), current_version_id: 'newer', revision: 4, observed_at: [stamp, stamp, stamp, stamp, stamp] };
    const token = book.putReviewPath(value, handoff); expect(book.isReviewPath(token)).toBe(true); expect(book.get(token)).toEqual(value);
    value.filters.customer_ids.pop(); expect(book.get(token)!.filters.customer_ids).toEqual(['A', 'B']); expect(book.isReviewPath('foreign')).toBe(false);
    const ordinary = book.put(intent()); expect(book.isReviewPath(ordinary)).toBe(false);
    for (let i = 0; i < 7; i++) book.putReviewPath(intent(), handoff); expect(book.isReviewPath(token)).toBe(false);
    now = 30 * 60 * 1000; expect(book.isReviewPath(ordinary)).toBe(false);
    const principals = new PrincipalReturnBook(), old = principals.forPrincipal('lawyer:A'), p = old.putReviewPath(intent(), handoff); expect(principals.forPrincipal('lawyer:B').isReviewPath(p)).toBe(false);
    const noPin = intent(); noPin.target.review_packet_sha256 = null; expect(() => book.putReviewPath(noPin, handoff)).toThrow();
  });
  it.each(['review', 'context-only', 'context', 'matter', 'prepare', 'packet'] as const)('rejects destination redirection through %s', field => {
    const v = intent(), target = { kind: 'selected' as const, matter_id: 'm', analysis_id: 'a', context_id: ctx, review_id: id(2) };
    verifyReturnedEventTarget(v, target);
    if (field === 'review') target.review_id = id(3);
    if (field === 'context-only') Object.assign(target, { review_id: undefined });
    if (field === 'context') target.context_id = `sac-${'e'.repeat(20)}-${'b'.repeat(32)}`;
    if (field === 'matter') target.matter_id = 'foreign';
    if (field === 'prepare') Object.assign(target, { prepare: 'renewal' });
    if (field === 'packet') v.target.review_packet_sha256 = null;
    expect(() => verifyReturnedEventTarget(v, target)).toThrow();
  });
  it('offers explicit member preparation only for verified results and locks destination follow-up navigation', async () => {
    const f = await prepared();
    const html = renderToStaticMarkup(<ReturnedReviewLineagePanel value={f.previous} choose={() => {}} busy />);
    expect(html).toContain('2. kaydın tam kimlik geçişini doğrula'); expect(html).toContain('disabled'); expect(html).not.toContain('<a');
    expect(renderToStaticMarkup(<ReturnedReviewLineagePanel value={{ ...f.previous, status: 'unknown', path: [] }} choose={() => {}} />)).not.toContain('<button');
    const locked = renderToStaticMarkup(<SourceReviewLineagePanel value={snapshot(2)} lockedSelection returnToken={'a'.repeat(32)} />);
    expect(locked).not.toContain('<a'); expect(locked).toContain('yalnızca doğrulanan tam kaydı seçer');
  });
});


describe('path selection return after metadata failure', () => {
  const target = { kind: 'selected' as const, matter_id: 'm', analysis_id: 'a', context_id: ctx, review_id: id(2) };
  it('keeps the exact pin and unknown original baseline even when no metadata was returned', () => {
    const v = intent(); v.target.current_version_id = null; v.target.version_observed_at = null;
    const next = returnVerifiedEvent(v, target, null, null); expect(next).toEqual(v); expect(next).not.toBe(v);
    expect(next.target.review_packet_sha256).toBe(row(2).packet_sha256);
  });
  it('requires consistent available metadata and rejects a substituted packet rather than erasing its pin', () => {
    const v = intent(), h = snapshot(2);
    expect(returnVerifiedEvent(v, target, h.context_navigation, h)).toEqual(v);
    expect(() => returnVerifiedEvent(v, target, h.context_navigation, null)).toThrow();
    h.selected_review.packet_sha256 = 'f'.repeat(64); h.lineage.items[0].packet_sha256 = 'f'.repeat(64);
    expect(() => returnVerifiedEvent(v, target, h.context_navigation, h)).toThrow();
  });
});
