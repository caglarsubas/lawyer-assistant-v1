import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { SourceReviewQueue } from './SourceReviewQueue';
import { verifyReadiness, type ReadinessPage } from './sourceReadinessTypes';

const page = (): ReadinessPage => ({ recipe: 'private-source-review-readiness-v1', matter_id: 'matter1', analysis_id: 'analysis1',
  observed_at: '2026-10-14T12:00:00+00:00', qualification_granted: false, legal_readiness: 'not_established',
  coverage: { scope: 'authorized_analysis_window_only', scanned_count: 1, returned_count: 1, has_more: false, next_offset: null,
    pagination_limit_reached: false, priority_scope: 'current_window_only', total_count: null, source_verification: 'not_checked' },
  items: [{ id: `sac-${'a'.repeat(20)}-${'b'.repeat(32)}`, recorded_at: '2026-10-14T11:00:00+00:00', state: 'inspection_required',
    version_id: 'v1', product_id: 'p1', manifest_sha256: 'c'.repeat(64),
    historical_review: { state: 'reviewed_conditional', id: `sar-${'d'.repeat(20)}-${'e'.repeat(32)}`, recorded_at: '2026-10-14T11:05:00+00:00' },
    private_observation: { state: 'unchanged', reasons: [] }, source_verification: 'not_checked', legal_readiness: 'not_established' }],
});
const render = (value: ReadinessPage | null) => renderToStaticMarkup(<SourceReviewQueue page={value} busy={false} load={() => {}} clear={() => {}} inspect={() => {}} renew={() => {}} />);

describe('bounded source-review observations', () => {
  it('shows historical positive separately from current unchecked sources and never offers export', () => {
    const value = page(); verifyReadiness(value, 'matter1', 'analysis1', 0);
    const html = render(value);
    expect(html).toContain('Koşullu inceleme kaydedildi'); expect(html).toContain('Kontrol edilmedi'); expect(html).toContain('Hukuki hazır olma belirlenmedi');
    expect(html).toContain('toplam kapsam bilinmiyor'); expect(html).toContain('Kaynak ve karar bağlarını kontrol et');
    expect(html).not.toContain('indir'); expect(html).not.toContain('PRIVATE');
  });
  it('starts with no records or automatic protected content and includes explicit date filters', () => {
    const html = render(null); expect(html).toContain('İnceleme kuyruğunu güncelle'); expect(html).toContain('type="date"');
    expect(html).not.toContain('sac-'); expect(html).not.toContain('Koşullu inceleme kaydedildi');
  });
  it.each(['pending', 'unavailable', 'needs_renewal', 'changes_requested', 'awaiting_review'] as const)('does not offer automatic review or renewal for %s', state => {
    const value = page(); value.items[0].state = state;
    const html = render(value); expect(html).toContain('Kaynak ve karar bağlarını kontrol et'); expect(html).not.toContain('İncelemeyi tamamla');
    if (state === 'pending' || state === 'unavailable') expect(html).toContain('disabled=""');
  });
  it.each([
    (v: ReadinessPage) => { v.matter_id = 'foreign'; }, (v: ReadinessPage) => { v.analysis_id = 'foreign'; },
    (v: ReadinessPage) => { v.qualification_granted = true as never; }, (v: ReadinessPage) => { v.coverage.total_count = 1 as never; },
    (v: ReadinessPage) => { v.items[0].source_verification = 'verified' as never; },
    (v: ReadinessPage) => { v.items[0].state = 'ready' as never; }, (v: ReadinessPage) => { v.items[0].state = 'constructor' as never; },
    (v: ReadinessPage) => { v.items[0].private_observation.reasons.push('PRIVATE NOTE' as never); },
    (v: ReadinessPage) => { Object.assign(v.items[0], { text: 'withdrawn quote' }); },
    (v: ReadinessPage) => { Object.assign(v.items[0].historical_review, { note: 'withdrawn review note' }); },
    (v: ReadinessPage) => { v.items.push(v.items[0]); v.coverage.returned_count = 2; v.coverage.scanned_count = 2; },
    (v: ReadinessPage) => { v.coverage.has_more = true; v.coverage.next_offset = 5; },
  ])('rejects foreign scope, borrowed readiness, protected text and invalid windows', mutate => {
    const value = page(); mutate(value); expect(() => verifyReadiness(value, 'matter1', 'analysis1', 0)).toThrow();
  });
  it('keeps a filtered empty window separate from completion and stops at the explicit pagination cap', () => {
    const value = page(); value.items = []; Object.assign(value.coverage, { returned_count: 0, scanned_count: 10, has_more: true, next_offset: 10 });
    verifyReadiness(value, 'matter1', 'analysis1', 0);
    expect(render(value)).toContain('Tüm incelemelerin tamamlandığı anlamına gelmez');
    expect(render(value)).toContain('Sonraki sınırlı pencereyi getir');
    Object.assign(value.coverage, { next_offset: null, pagination_limit_reached: true }); verifyReadiness(value, 'matter1', 'analysis1', 10000);
    expect(render(value)).toContain('Sayfalama sınırına ulaşıldı'); expect(render(value)).not.toContain('Sonraki sınırlı pencereyi getir');
  });
});
