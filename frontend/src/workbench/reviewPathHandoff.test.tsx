import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import ReviewPathIdentityComparison from '../pages/ReviewPathIdentityComparison';
import type { NavigationMetadata } from '../pages/sourceContextNavigationTypes';
import type { ReviewLineage, ReviewMetadata } from '../pages/sourceReviewLineageTypes';
import { PortfolioReturnBook, PrincipalReturnBook, type ReturnIntent } from './portfolioReturn';
import { compareReviewPathHandoff, validateReviewPathHandoff, type ReviewPathHandoff } from './reviewPathHandoff';

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
const compare = (h = snapshot(2)) => compareReviewPathHandoff(intent(), handoff(), h);

describe('separate path-handoff and destination identity observations', () => {
  it('preserves the older original baseline, chosen event and handoff as three distinct observations', () => {
    const i = intent(), p = handoff(), h = snapshot(2), before = structuredClone({ i, p, h });
    const c = compareReviewPathHandoff(i, p, h);
    expect(c.head_relation).toBe('same'); expect(c.version_relation).toBe('same'); expect(c.revision_relation).toBe('same');
    expect(c.original.before.head_id).toBe(id(1)); expect(c.original.before.version_id).toBe('original');
    expect(c.handoff.selected.id).toBe(id(2)); expect(c.handoff.head.id).toBe(id(3)); expect(c.handoff.current_version_id).toBe('newer');
    c.handoff.head.packet_sha256 = 'e'.repeat(64); expect({ i, p, h }).toEqual(before);
  });
  it('reports real changed head, version and revision without substituting the selected event or rebasing', () => {
    const h = snapshot(2, 10, 4); h.context_navigation.analysis = { id: 'a', current_version_id: 'latest', revision: 5 };
    const c = compare(h); expect(c).toMatchObject({ head_relation: 'different', version_relation: 'different', revision_relation: 'different' });
    expect(c.original.selected?.id).toBe(id(2)); expect(c.original.fixed.version_id).toBe('frozen'); expect(c.original.before.head_id).toBe(id(1)); expect(c.destination.head?.state).toBe('changes_requested');
  });
  it('does not use same version identity to hide a changed analysis revision', () => {
    const h = snapshot(2); h.context_navigation.analysis.revision++;
    expect(compare(h)).toMatchObject({ head_relation: 'same', version_relation: 'same', revision_relation: 'different' });
  });
  it('supports choosing the current head without inferring approval', () => {
    const p = handoff(), i = intent(3); p.selected = row(3);
    const c = compareReviewPathHandoff(i, p, snapshot(3)); expect(c.original.selected_head_relation).toBe('same');
  });
  it.each(['missing-head', 'unavailable-head', 'unknown-version'] as const)('keeps %s explicit without inventing an identity', kind => {
    const h = snapshot(2);
    if (kind === 'missing-head') h.current_head = null;
    if (kind === 'unavailable-head') {
      h.current_head = { id: id(3), state: 'unknown', sequence: null, recorded_at: null, packet_sha256: null, manifest_sha256: null, previous_review_id: null, admission: 'unavailable', integrity: 'unavailable' };
      h.context_navigation.historical_review.state = 'unknown'; h.context_navigation.admission.review_state = 'unavailable';
    }
    if (kind === 'unknown-version') { h.context_navigation.analysis.current_version_id = null; h.context_navigation.version_relation = 'unknown'; h.context_navigation.tools_available = false; h.tools_available = false; }
    else h.head_relationship = 'unestablished';
    const c = compare(h); expect(kind === 'unknown-version' ? c.version_relation : c.head_relation).toBe('unknown');
    expect(c.handoff.head.id).toBe(id(3)); expect(c.handoff.current_version_id).toBe('newer');
  });
  it('does not initialize unknown original baselines from the known handoff', () => {
    const i = intent(); i.target.current_version_id = null; i.target.version_observed_at = null; i.target.head_id = null; i.target.head_state = 'unknown';
    const c = compareReviewPathHandoff(i, handoff(), snapshot(2)); expect(c.original.before.version_observed_at).toBeNull(); expect(c.original.head_relation).toBe('unknown'); expect(c.original.version_relation).toBe('unknown'); expect(i.target.current_version_id).toBeNull();
  });
  it.each(['context', 'selected', 'head'] as const)('reports %s pending admission without completing or transferring it', kind => {
    const h = snapshot(2);
    if (kind === 'context') h.context_navigation.admission.context_state = 'pending';
    if (kind === 'selected') { h.selected_review.admission = 'pending'; h.lineage.items[0].admission = 'pending'; h.tools_available = false; }
    if (kind === 'head') { h.current_head!.admission = 'pending'; h.context_navigation.admission.review_state = 'pending'; }
    const c = compare(h); expect(c.destination[kind === 'context' ? 'context_admission' : kind === 'selected' ? 'selected_admission' : 'head_admission']).toBe('pending');
    expect(c.handoff.selected.admission).toBe('complete');
  });
  it.each(['packet', 'state', 'sequence', 'predecessor', 'recorded-at'] as const)('rejects immutable selected %s substitution even if its ID remains the same', kind => {
    const h = snapshot(2), changed = h.selected_review;
    if (kind === 'packet') changed.packet_sha256 = 'e'.repeat(64);
    if (kind === 'state') changed.state = 'reviewed_conditional';
    if (kind === 'sequence') changed.sequence = 7;
    if (kind === 'predecessor') changed.previous_review_id = id(9);
    if (kind === 'recorded-at') changed.recorded_at = '2026-10-14T01:00:00Z';
    h.lineage.items = [structuredClone(changed)]; h.lineage.status = 'truncated'; h.lineage.window = 1; h.lineage.next_review_id = changed.previous_review_id;
    expect(() => compare(h)).toThrow();
  });
  it.each(['packet', 'state', 'sequence', 'predecessor', 'recorded-at'] as const)('rejects immutable handoff-head %s substitution at the destination', kind => {
    const h = snapshot(2), head = h.current_head!;
    if (kind === 'packet') head.packet_sha256 = 'e'.repeat(64);
    if (kind === 'state') { head.state = 'changes_requested'; h.context_navigation.historical_review.state = head.state; }
    if (kind === 'sequence') head.sequence = 9;
    if (kind === 'predecessor') head.previous_review_id = id(9);
    if (kind === 'recorded-at') head.recorded_at = '2026-10-14T01:00:00Z';
    expect(() => compare(h)).toThrow();
  });
  it.each(['older-observation', 'lower-revision', 'foreign', 'changed-evidence', 'extra-content'] as const)('rejects %s metadata with no inferred substitute', kind => {
    const h = snapshot(2);
    if (kind === 'older-observation') h.observed_at = h.context_navigation.observed_at = '2026-10-14T01:00:00Z';
    if (kind === 'lower-revision') h.context_navigation.analysis.revision = 3;
    if (kind === 'foreign') h.matter_id = 'other';
    if (kind === 'changed-evidence') h.context_navigation.context.version_id = 'other';
    if (kind === 'extra-content') Object.assign(h, { note: 'PRIVATE CONTENT' });
    expect(() => compare(h)).toThrow();
  });
  it.each(['missing', 'version', 'packet', 'head', 'extra-content', 'time-order', 'time-count', 'revision', 'readiness', 'pending'] as const)('rejects %s handoff payload before retaining it', kind => {
    const p = handoff();
    if (kind === 'missing') delete (p as Partial<ReviewPathHandoff>).head;
    if (kind === 'version') p.frozen_version_id = 'substitute';
    if (kind === 'packet') p.selected.packet_sha256 = 'e'.repeat(64);
    if (kind === 'head') p.head.sequence = 1;
    if (kind === 'extra-content') Object.assign(p.head, { note: 'PRIVATE CONTENT' });
    if (kind === 'time-order') p.observed_at[3] = '2026-10-14T01:00:00Z';
    if (kind === 'time-count') p.observed_at.pop();
    if (kind === 'revision') p.revision = -1;
    if (kind === 'readiness') Object.assign(p, { qualification_granted: true });
    if (kind === 'pending') p.selected.admission = 'pending';
    expect(() => validateReviewPathHandoff(p, intent())).toThrow(); expect(() => new PortfolioReturnBook().putReviewPath(intent(), p)).toThrow();
  });
  it('clones both observations and retires them together at eviction, expiry and principal change', () => {
    let now = 0, n = 0; const b = new PortfolioReturnBook(() => now, () => (++n).toString(16).padStart(32, '0')), p = handoff(), i = intent();
    const t = b.putReviewPath(i, p); p.head.packet_sha256 = 'e'.repeat(64); i.filters.customer_ids.pop();
    expect(b.getReviewPath(t)?.head.packet_sha256).toBe(row(3).packet_sha256); expect(b.get(t)?.filters.customer_ids).toEqual(['A', 'B']);
    b.getReviewPath(t)!.observed_at[0] = 'mutated'; expect(b.getReviewPath(t)?.observed_at[0]).toBe(stamp);
    for (let x = 0; x < 8; x++) b.putReviewPath(intent(), handoff()); expect(b.getReviewPath(t)).toBeNull();
    const fresh = b.putReviewPath(intent(), handoff()); now = 30 * 60 * 1000; expect(b.getReviewPath(fresh)).toBeNull(); expect(b.get(fresh)).toBeNull();
    const principals = new PrincipalReturnBook(), token = principals.forPrincipal('A').putReviewPath(intent(), handoff()); expect(principals.forPrincipal('B').getReviewPath(token)).toBeNull(); expect(principals.forPrincipal('A').getReviewPath(token)).toBeNull();
    expect(b.getReviewPath('malformed')).toBeNull(); expect(b.getReviewPath(b.put(intent()))).toBeNull();
  });
  it('renders a read-only comparison with original unknowns, changed identities and no implied source approval', () => {
    const h = snapshot(2, 10, 4); h.context_navigation.analysis.current_version_id = 'latest'; h.context_navigation.analysis.revision = 5;
    const html = renderToStaticMarkup(<ReviewPathIdentityComparison value={compare(h)} />);
    expect(html).toContain('Farklı kimlik gözlendi'); expect(html).toContain('Özgün kuyruk'); expect(html).toContain('İnceleme onayı aktarılmadı');
    expect(html).toContain(id(1)); expect(html).toContain(id(2)); expect(html).toContain(id(3)); expect(html).toContain(id(4)); expect(html).toContain('frozen'); expect(html).toContain('original'); expect(html).toContain('newer'); expect(html).toContain('latest');
    expect(html).not.toMatch(/<(a |button|textarea|input)/); expect(html).toContain('Kaynak araçları ayrı ve güncel kontroller gerektirir');
  });
});
