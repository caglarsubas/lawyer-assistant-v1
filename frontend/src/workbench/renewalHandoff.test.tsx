import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { metadata, parentId } from '../pages/matter/sourceRenewalFixtures';
import { verifyRenewalMetadata, type RenewalMetadata } from '../pages/matter/sourceRenewalTypes';
import AnalysisSourceReviews from '../pages/matter/AnalysisSourceReviews';
import { RenewalHandoffSummary } from '../pages/ComparisonRenewalPage';
import { sourceNavigationSelection, type NavigationMetadata } from '../pages/sourceContextNavigationTypes';
import { PortfolioReturnBook, type ReturnIntent, type ReturnReconciliation } from './portfolioReturn';
import { compareReturnIdentities } from './returnComparison';
import { captureRenewalHandoff, renewalHandoffHref, successorIntent, validateRenewalHandoff, verifyPreparedRenewal, verifyRenewalNavigation } from './renewalHandoff';
const stamp = '2026-10-15T00:00:00Z';
const intent = (): ReturnIntent => ({ recipe: 'private-portfolio-return-intent-v2', filters: { customer_ids: ['A', 'B'], date_field: 'relevant_date', date_from: '2020-01-01', date_to: '2030-12-31', source_date_from: '2026-10-01', source_date_to: '2026-10-31', bucket: 'all' },
  target: { matter_id: 'matter1', analysis_id: 'analysis1', context_id: parentId, version_id: metadata.version_id, manifest_sha256: metadata.manifest_sha256,
    head_id: null, head_state: 'unreviewed', current_version_id: 'latest1', version_observed_at: stamp, review_id: null, review_packet_sha256: null, observed_at: stamp } });
const nav = (): NavigationMetadata => ({ recipe: 'private-source-context-navigation-v1', matter_id: 'matter1', analysis_id: 'analysis1', context_id: parentId, observed_at: stamp,
  analysis: { id: 'analysis1', current_version_id: 'latest2', revision: 2 }, context: { id: parentId, version_id: metadata.version_id, manifest_sha256: metadata.manifest_sha256, recorded_at: stamp },
  historical_review: { id: null, state: 'unreviewed', recorded_at: null }, admission: { context_state: 'complete', review_state: 'not_recorded' }, version_relation: 'different', integrity: 'verified', tools_available: true, source_verification: 'not_checked', legal_readiness: 'not_established', qualification_granted: false });
const result = (): ReturnReconciliation => ({ state: 'observed', comparison: compareReturnIdentities(intent(), nav(), null), private_state: 'changed', context_state: 'complete', review_state: 'not_recorded', queue_observed_at: stamp, target_observed_at: stamp });
const handoff = () => captureRenewalHandoff(intent(), result())!;
describe('guarded comparison to renewal', () => {
  it('captures only scoped verified identities and round-trips a local explicit preparation route', () => {
    const h = handoff(); expect(h.version_id).toBe('latest2'); expect(h.frozen_version_id).toBe(metadata.version_id);
    const href = renewalHandoffHref(intent(), 'a'.repeat(32))!, [path, query] = href.slice(1).split('?');
    const selection = sourceNavigationSelection(path, new URLSearchParams(query)); expect(selection.kind === 'selected' && selection.prepare).toBe('renewal');
    expect(href).not.toContain('latest2'); expect(href).not.toContain('2030-12-31');
    for (const suffix of ['&prepare=renewal', '&review=sar-' + 'a'.repeat(20) + '-' + 'b'.repeat(32), '&work=other']) expect(sourceNavigationSelection(path, new URLSearchParams(query + suffix)).kind).toBe('invalid');
    expect(sourceNavigationSelection(path, new URLSearchParams(query.replace(/&return=[a-f0-9]+/, ''))).kind).toBe('invalid');
    expect(sourceNavigationSelection('/work', new URLSearchParams('prepare=renewal')).kind).toBe('invalid');
  });
  it.each(['pending', 'unavailable', 'unknown'] as const)('does not capture %s admission as renewal permission', state => {
    const r = result(); if (r.state !== 'observed') throw new Error(); r.review_state = state; expect(captureRenewalHandoff(intent(), r)).toBeNull();
  });
  it('withholds unknown target/head or unobserved-window handoff', () => {
    expect(captureRenewalHandoff(intent(), { state: 'not_observed', queue_observed_at: stamp })).toBeNull();
    const r = result(); if (r.state !== 'observed') throw new Error(); r.comparison.current.version_id = null; expect(captureRenewalHandoff(intent(), r)).toBeNull();
    r.comparison.current.version_id = 'latest2'; r.comparison.current.head_state = 'unknown'; expect(captureRenewalHandoff(intent(), r)).toBeNull();
  });
  it('clones bounded attachment metadata and discards it with its session/expiry', () => {
    let time = 0; const book = new PortfolioReturnBook(() => time), h = handoff(), token = book.put(intent(), h); h.version_id = 'altered';
    expect(book.getRenewal(token)!.version_id).toBe('latest2'); expect(book.get(token)!.filters).toEqual(intent().filters); expect(new PortfolioReturnBook().getRenewal(token)).toBeNull();
    expect(() => book.put({ ...intent(), target: { ...intent().target, matter_id: 'foreign' } }, handoff())).toThrow();
    time += 1800000; expect(book.getRenewal(token)).toBeNull();
  });
  it('checks original bindings across before/after metadata without promoting source access', () => {
    expect(() => verifyPreparedRenewal(intent(), handoff(), nav(), metadata, nav())).not.toThrow();
    expect(nav().source_verification).toBe('not_checked'); expect(metadata.review_inheritance).toBe('none');
  });
  it.each(['version', 'head', 'hash', 'revision', 'pending', 'archive', 'foreign'] as const)('closes %s drift before preparation accepts metadata', field => {
    const before = nav(), after = nav(), meta = structuredClone(metadata);
    if (field === 'version') after.analysis.current_version_id = 'latest3';
    if (field === 'head') after.historical_review = { id: `sar-${'a'.repeat(20)}-${'b'.repeat(32)}`, state: 'changes_requested', recorded_at: stamp };
    if (field === 'hash') meta.manifest_sha256 = '0'.repeat(64);
    if (field === 'revision') after.analysis.revision++;
    if (field === 'pending') meta.admission_completed = false;
    if (field === 'archive') meta.can_record = false;
    if (field === 'foreign') after.matter_id = 'foreign';
    expect(() => verifyPreparedRenewal(intent(), handoff(), before, meta, after)).toThrow();
  });
  it('rejects mixed or content-bearing handoff envelopes', () => {
    const h = handoff(); Object.assign(h, { note: 'PRIVATE note' }); expect(() => validateRenewalHandoff(h)).toThrow();
    expect(() => verifyRenewalNavigation(intent(), { ...handoff(), context_id: `sac-${'f'.repeat(20)}-${'b'.repeat(32)}` }, nav())).toThrow();
  });
  it.each([
    (m: RenewalMetadata) => { Object.assign(m, { text: 'PRIVATE OLD QUOTE' }); },
    (m: RenewalMetadata) => { m.can_record = 'true' as never; },
    (m: RenewalMetadata) => { m.graph_release_pin.serving_sha256 = 'broken'; },
    (m: RenewalMetadata) => { Object.assign(m.sources[0], { note: 'PRIVATE old interpretation' }); },
    (m: RenewalMetadata) => { m.review_inheritance = 'inherited' as never; },
  ])('rejects leaked metadata, forged flags and implicit inherited review', mutate => {
    const m = structuredClone(metadata); mutate(m); expect(() => verifyRenewalMetadata(m, 'matter1', 'analysis1', parentId)).toThrow();
  });
  it('starts separately observed successor baselines while retaining exact customer/date filters', () => {
    const m = nav(), id = `sac-${'a'.repeat(20)}-${'c'.repeat(32)}`; m.context_id = id; m.context.id = id; m.context.version_id = 'latest2'; m.version_relation = 'same';
    const next = successorIntent(intent(), id, m, { version_id: 'latest2', manifest_sha256: metadata.manifest_sha256 });
    expect(next.filters).toEqual(intent().filters); expect(next.target.context_id).toBe(id); expect(next.target.review_id).toBeNull(); expect(next.target.review_packet_sha256).toBeNull();
    expect(next.target.current_version_id).toBe('latest2'); expect(next.target.head_id).toBeNull(); expect(next.target.version_id).not.toBe(intent().target.version_id);
    next.filters.customer_ids.push('foreign'); expect(intent().filters.customer_ids).toEqual(['A', 'B']);
    expect(() => successorIntent(intent(), id, m, { version_id: 'other', manifest_sha256: metadata.manifest_sha256 })).toThrow();
    expect(() => successorIntent(intent(), parentId, nav())).toThrow();
  });
  it('renders metadata-only preparation and separate renewal controls with no inherited inspection/review/export', () => {
    const html = renderToStaticMarkup(<RenewalHandoffSummary intent={intent()} handoff={handoff()} />); expect(html).toContain('latest2'); expect(html).not.toContain('Özgün alıntı');
    const editor = renderToStaticMarkup(<AnalysisSourceReviews matterId="matter1" record={{ id: 'analysis1', latest_version_id: 'latest2' }} selectedContext={{ id: parentId, version_id: metadata.version_id, manifest_sha256: metadata.manifest_sha256 }} preparedRenewal={metadata} />);
    expect(editor).toContain('Araştırma pasajlarını getir'); expect(editor).not.toContain('Bağımsız inceleme içeriğini getir'); expect(editor).not.toContain('kaynak incelemesini indir'); expect(editor).not.toContain('Güncel kaynak ve karar bağlarını kontrol et'); expect(editor).not.toContain('Ayrı kaynak seçimine dön');
  });
});
