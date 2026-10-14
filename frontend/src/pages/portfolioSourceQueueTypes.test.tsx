import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { PortfolioQueueResults } from './PortfolioSourceReviewQueue';
import { queueFilters, queueQuery, sourceQueueHref, verifyPortfolioQueue, type PortfolioQueuePage } from './portfolioSourceQueueTypes';
import { EMPTY_FILTERS } from '../workbench/portfolio';

const filters = queueFilters(EMPTY_FILTERS, { bucket: 'all', source_date_from: '', source_date_to: '' });
const page = (): PortfolioQueuePage => ({ recipe: 'private-portfolio-source-review-queue-v1', observed_at: '2026-10-14T12:00:00+00:00',
  filters: { ...filters }, legal_readiness: 'not_established', qualification_granted: false,
  coverage: { scope: 'authorized_portfolio_window_only', scanned_count: 1, returned_count: 1, locked_matter_count: 1,
    has_more: false, next_offset: null, pagination_limit_reached: false, priority_scope: 'current_window_only', total_count: null, source_verification: 'not_checked' },
  items: [{ id: `sac-${'a'.repeat(20)}-${'b'.repeat(32)}`, recorded_at: '2026-10-14T11:00:00+00:00', state: 'inspection_required',
    matter_id: 'matter1', matter_title: 'PRIVATE CASE <script> inert title', analysis_id: 'analysis1', version_id: 'v1', product_id: 'p1', manifest_sha256: 'c'.repeat(64),
    historical_review: { state: 'reviewed_conditional', id: `sar-${'d'.repeat(20)}-${'e'.repeat(32)}`, recorded_at: '2026-10-14T11:05:00+00:00' },
    private_observation: { state: 'unchanged', reasons: [] }, source_verification: 'not_checked', legal_readiness: 'not_established' }],
});
const render = (value: PortfolioQueuePage) => renderToStaticMarkup(<PortfolioQueueResults page={value} busy={false} next={() => {}} />);

describe('authorized portfolio queue windows', () => {
  it('normalizes customer OR selection and keeps workspace and source-record dates separate', () => {
    const value = queueFilters({ customer_ids: ['b', 'a', 'b'], date_field: 'relevant_date', date_from: '2024-01-01', date_to: '' },
      { bucket: 'all', source_date_from: '2026-10-01', source_date_to: '2026-10-31' });
    expect(value.customer_ids).toEqual(['a', 'b']); const params = new URLSearchParams(queueQuery(value, 10));
    expect(params.get('date_from')).toBe('2024-01-01'); expect(params.get('source_date_from')).toBe('2026-10-01');
    expect(params.get('date_field')).toBe('relevant_date'); expect(params.get('offset')).toBe('10');
    expect(params.get('customer_ids')).toBe('a,b');
  });
  it('shows current unknown sources separately from historical positive reviews with an inert scoped link', () => {
    const value = page(); verifyPortfolioQueue(value, filters, 0); const html = render(value);
    expect(html).toContain('PRIVATE CASE &lt;script&gt;'); expect(html).not.toContain('<script>');
    expect(html).toContain('Koşullu inceleme kaydedildi'); expect(html).toContain('Kontrol edilmedi'); expect(html).toContain('Hukuki hazır olma belirlenmedi');
    expect(html).toContain('href="#/matters/matter1?tab=practice"'); expect(html).not.toContain('indir'); expect(html).not.toContain('İncelemeyi tamamla');
  });
  it.each([
    (v: PortfolioQueuePage) => { v.filters = { ...v.filters, customer_ids: ['foreign'] }; },
    (v: PortfolioQueuePage) => { v.coverage.scope = 'all_portfolios' as never; },
    (v: PortfolioQueuePage) => { v.coverage.locked_matter_count = 0; },
    (v: PortfolioQueuePage) => { v.coverage.total_count = 500 as never; },
    (v: PortfolioQueuePage) => { v.qualification_granted = true as never; },
    (v: PortfolioQueuePage) => { v.items[0].source_verification = 'verified' as never; },
    (v: PortfolioQueuePage) => { v.items[0].matter_id = 'https://external'; },
    (v: PortfolioQueuePage) => { v.items[0].analysis_id = '../other'; },
    (v: PortfolioQueuePage) => { Object.assign(v.items[0], { quote: 'withdrawn source' }); },
    (v: PortfolioQueuePage) => { Object.assign(v.items[0].historical_review, { note: 'withdrawn review note' }); },
    (v: PortfolioQueuePage) => { v.items[0].analysis_id = null; },
    (v: PortfolioQueuePage) => { v.coverage.has_more = true; v.coverage.next_offset = 11; },
  ])('rejects mismatched scope/filters, leaked notes, source verdicts and invalid links', mutate => {
    const value = page(); mutate(value); expect(() => verifyPortfolioQueue(value, filters, 0)).toThrow();
  });
  it('cannot open an unavailable analysis routing record', () => {
    const value = page(); value.items[0].analysis_id = null; value.items[0].state = 'unavailable';
    value.items[0].historical_review = { state: 'unknown', id: null, recorded_at: null };
    verifyPortfolioQueue(value, filters, 0); expect(sourceQueueHref(value.items[0])).toBeNull();
    expect(render(value)).toContain('Bu kayıttan inceleme açılamaz'); expect(render(value)).not.toContain('href=');
  });
  it('empty or capped windows never assert complete portfolio coverage', () => {
    const value = page(); value.items = []; Object.assign(value.coverage, { scanned_count: 10, returned_count: 0, locked_matter_count: 2, has_more: true, next_offset: 10 });
    verifyPortfolioQueue(value, filters, 0); expect(render(value)).toContain('Tüm portföyün incelendiği'); expect(render(value)).toContain('Sonraki sınırlı portföy penceresini getir');
    Object.assign(value.coverage, { pagination_limit_reached: true, next_offset: null }); verifyPortfolioQueue(value, filters, 10000);
    expect(render(value)).toContain('Sayfalama sınırına ulaşıldı'); expect(render(value)).not.toContain('Sonraki sınırlı portföy penceresini getir');
  });
});
