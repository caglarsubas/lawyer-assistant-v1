import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import SourceReviewLineagePanel from './SourceReviewLineagePanel';
import AnalysisSourceReviews from './matter/AnalysisSourceReviews';
import { sourceContextHref, sourceNavigationSelection, type SourceTarget } from './sourceContextNavigationTypes';
import { verifyReviewLineage, type ReviewLineage, type ReviewMetadata } from './sourceReviewLineageTypes';
const context = `sac-${'a'.repeat(20)}-${'b'.repeat(32)}`;
const id = (n: number) => `sar-${'c'.repeat(20)}-${n.toString(16).padStart(32, '0')}`;
const target: SourceTarget = { kind: 'selected', matter_id: 'matter1', analysis_id: 'analysis1', context_id: context, review_id: id(2) };
const row = (n: number): ReviewMetadata => ({ id: id(n), state: n % 2 ? 'reviewed_conditional' : 'changes_requested', sequence: n,
  recorded_at: '2026-10-14T01:00:00Z', packet_sha256: 'd'.repeat(64), manifest_sha256: 'e'.repeat(64), previous_review_id: n === 1 ? null : id(n - 1), admission: 'complete', integrity: 'verified' });
const value = (): ReviewLineage => ({ recipe: 'private-source-review-lineage-v1', ...Object.fromEntries(Object.entries(target).filter(([key]) => key !== 'kind')), matter_id: target.matter_id, analysis_id: target.analysis_id, context_id: context, review_id: target.review_id!,
  observed_at: '2026-10-14T02:00:00Z', context_navigation: { recipe: 'private-source-context-navigation-v1', matter_id: target.matter_id, analysis_id: target.analysis_id, context_id: context,
    observed_at: '2026-10-14T02:00:00Z', analysis: { id: target.analysis_id, current_version_id: 'v1', revision: 1 },
    context: { id: context, version_id: 'v1', manifest_sha256: 'e'.repeat(64), recorded_at: '2026-10-13T01:00:00Z' },
    admission: { context_state: 'complete', review_state: 'complete' }, historical_review: { id: id(3), state: 'reviewed_conditional', recorded_at: '2026-10-14T01:00:00Z' },
    version_relation: 'same', integrity: 'verified', tools_available: true, source_verification: 'not_checked', legal_readiness: 'not_established', qualification_granted: false },
  selected_review: row(2), current_head: row(3), head_relationship: 'different_from_head', lineage: { scope: 'selected_predecessors_only', status: 'complete_to_first_event', window: 10,
    items: [row(2), row(1)], next_review_id: null, total_count: null, head_reachability: 'not_checked' }, tools_available: true, source_verification: 'not_checked', legal_readiness: 'not_established', qualification_granted: false });
const render = (v: ReviewLineage) => renderToStaticMarkup(<SourceReviewLineagePanel value={v} />);

describe('exact historical review metadata and navigation', () => {
  it('round trips an exact local historical event and rejects duplicate or mixed targets', () => {
    const href = sourceContextHref(target.matter_id, target.analysis_id, context, target.review_id)!;
    const [path, query] = href.slice(1).split('?'); expect(sourceNavigationSelection(path, new URLSearchParams(query))).toEqual(target);
    for (const suffix of ['&review=' + id(1), '&work=1', '&document=1']) expect(sourceNavigationSelection(path, new URLSearchParams(query + suffix))).toEqual({ kind: 'invalid' });
    expect(sourceNavigationSelection(path, new URLSearchParams('review=' + id(1)))).toEqual({ kind: 'invalid' });
    expect(sourceContextHref('m', 'a', context, 'https://external')).toBeNull();
  });
  it('separates selected/current heads and displays only bounded metadata with explicit context return', () => {
    const v = value(); verifyReviewLineage(v, target); const html = render(v);
    expect(html).toContain(id(2)); expect(html).toContain(id(3)); expect(html).toContain('Değişiklik istendi'); expect(html).toContain('Koşullu inceleme kaydedildi');
    expect(html).toContain('Son kararın yerine geçmez'); expect(html).toContain('Toplam kapsam bilinmiyor'); expect(html).toContain('Kamu kaynakları kontrol edilmedi');
    expect(html).toContain('Güncel bağlamın kimliğine dön'); expect(html).not.toContain('PRIVATE SOURCE'); expect(html).not.toContain('<textarea'); expect(html).not.toContain('kaynak incelemesini indir');
  });
  it('historical tools expose explicit inspection without export, renewal or new-review controls', () => {
    const html = renderToStaticMarkup(<AnalysisSourceReviews matterId={target.matter_id} record={{ id: target.analysis_id, latest_version_id: 'v1' }}
      selectedContext={{ id: context, version_id: 'v1', manifest_sha256: 'e'.repeat(64) }} selectedReview={{ id: target.review_id!, packet_sha256: 'd'.repeat(64) }} />);
    expect(html).toContain('Seçilen tarihsel kararı ve özgün dayanakları kontrol et'); expect(html).not.toContain('Bağımsız inceleme içeriğini getir');
    expect(html).not.toContain('Bu kaydın kaynak bağlamını yenile'); expect(html).not.toContain('kaynak incelemesini indir'); expect(html).not.toContain('Araştırma pasajlarını getir');
  });
  it('discloses truncated predecessor pointers as a new selection, with unknown total/head reachability', () => {
    const v = value(); Object.assign(v.lineage, { items: [row(2)], window: 1, status: 'truncated', next_review_id: id(1) });
    verifyReviewLineage(v, target); expect(render(v)).toContain('geçmişin devamı bu pencerede incelenmedi'); expect(render(v)).toContain('Önceki bağlantıyı yeni seçim olarak aç');
  });
  it('pending historical admission withholds tools while keeping decision and context distinct', () => {
    const v = value(); v.selected_review.admission = 'pending'; v.lineage.items[0].admission = 'pending'; v.tools_available = false;
    verifyReviewLineage(v, target); expect(render(v)).toContain('Son izin kontrolü bekliyor');
  });
  it.each([
    (v: ReviewLineage) => { v.review_id = id(1); }, (v: ReviewLineage) => { v.selected_review.id = id(1); },
    (v: ReviewLineage) => { v.selected_review.packet_sha256 = null; }, (v: ReviewLineage) => { v.current_head!.id = id(4); },
    (v: ReviewLineage) => { v.head_relationship = 'current_head'; }, (v: ReviewLineage) => { v.selected_review.manifest_sha256 = 'f'.repeat(64); },
    (v: ReviewLineage) => { v.lineage.items[1].sequence = 20; }, (v: ReviewLineage) => { v.lineage.items[1] = row(2); },
    (v: ReviewLineage) => { v.lineage.total_count = 100 as never; }, (v: ReviewLineage) => { v.lineage.head_reachability = 'verified' as never; },
    (v: ReviewLineage) => { v.lineage.window = 11; }, (v: ReviewLineage) => { v.lineage.next_review_id = id(1); },
    (v: ReviewLineage) => { Object.assign(v.selected_review, { note: 'PRIVATE review' }); },
    (v: ReviewLineage) => { Object.assign(v.lineage.items[1], { source: 'PRIVATE source' }); },
    (v: ReviewLineage) => { v.source_verification = 'checked' as never; }, (v: ReviewLineage) => { v.tools_available = true; v.selected_review.admission = 'pending'; },
  ])('closes metadata on forged identity, false lineage/readiness, leaked content or admission upgrades', mutate => {
    const v = value(); mutate(v); expect(() => verifyReviewLineage(v, target)).toThrow();
  });
});
