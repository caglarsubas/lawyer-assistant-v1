import type { PortfolioFilters } from '../types';
import { canonicalJson } from './matter/sourceReviewTypes';
import { verifyReadinessItem, type ReadinessItem } from './matter/sourceReadinessTypes';

export type QueueFilters = { bucket: 'all' | 'action_required'; source_date_from: string; source_date_to: string };
export type PortfolioQueueFilters = PortfolioFilters & QueueFilters;
export type PortfolioQueueItem = ReadinessItem & { matter_id: string; matter_title: string; analysis_id: string | null };
export type PortfolioQueuePage = {
  recipe: 'private-portfolio-source-review-queue-v1'; observed_at: string; filters: PortfolioQueueFilters; items: PortfolioQueueItem[];
  coverage: { scope: 'authorized_portfolio_window_only'; scanned_count: number; returned_count: number; locked_matter_count: number;
    has_more: boolean; next_offset: number | null; pagination_limit_reached: boolean; priority_scope: 'current_window_only'; total_count: null; source_verification: 'not_checked' };
  legal_readiness: 'not_established'; qualification_granted: false;
};
const keys = (value: object, allowed: string[]) => Object.keys(value).every(key => allowed.includes(key));
const identifier = (value: unknown) => typeof value === 'string' && /^[a-zA-Z0-9_-]{1,64}$/.test(value);
export function queueFilters(portfolio: PortfolioFilters, sources: QueueFilters): PortfolioQueueFilters {
  return { ...portfolio, customer_ids: [...new Set(portfolio.customer_ids)].sort(), ...sources };
}
export function queueQuery(filters: PortfolioQueueFilters, offset: number) {
  const params = new URLSearchParams({ bucket: filters.bucket, date_field: filters.date_field, offset: String(offset) });
  if (filters.customer_ids.length) params.set('customer_ids', filters.customer_ids.join(','));
  for (const key of ['date_from', 'date_to', 'source_date_from', 'source_date_to'] as const) if (filters[key]) params.set(key, filters[key]);
  return params.toString();
}
export function sourceQueueHref(item: PortfolioQueueItem): string | null {
  return identifier(item.matter_id) && identifier(item.analysis_id) ? `#/matters/${encodeURIComponent(item.matter_id)}?tab=practice` : null;
}
export function verifyPortfolioQueue(value: PortfolioQueuePage, expected: PortfolioQueueFilters, offset: number) {
  const fail = () => { throw new Error('Portföy kaynak kuyruğunun filtre veya kapsam bağı doğrulanamadı.'); };
  if (!value || !keys(value, ['recipe', 'observed_at', 'filters', 'items', 'coverage', 'legal_readiness', 'qualification_granted'])
    || value.recipe !== 'private-portfolio-source-review-queue-v1' || canonicalJson(value.filters) !== canonicalJson(expected)
    || typeof value.observed_at !== 'string' || value.observed_at.length > 40 || !Number.isFinite(Date.parse(value.observed_at))
    || value.legal_readiness !== 'not_established' || value.qualification_granted !== false || !Array.isArray(value.items) || value.items.length > 10 || !value.coverage) fail();
  const c = value.coverage;
  if (!keys(c, ['scope', 'scanned_count', 'returned_count', 'locked_matter_count', 'has_more', 'next_offset', 'pagination_limit_reached', 'priority_scope', 'total_count', 'source_verification'])
    || c.scope !== 'authorized_portfolio_window_only' || c.total_count !== null || c.priority_scope !== 'current_window_only' || c.source_verification !== 'not_checked'
    || !Number.isInteger(c.scanned_count) || c.scanned_count < 0 || c.scanned_count > 10 || c.returned_count !== value.items.length || c.returned_count > c.scanned_count
    || !Number.isInteger(c.locked_matter_count) || c.locked_matter_count < 0 || c.locked_matter_count > c.scanned_count
    || typeof c.has_more !== 'boolean' || typeof c.pagination_limit_reached !== 'boolean'
    || c.pagination_limit_reached !== (c.has_more && offset + 10 > 10000)
    || (c.has_more && !c.pagination_limit_reached ? c.scanned_count !== 10 || c.next_offset !== offset + 10 : c.next_offset !== null)) fail();
  if (new Set(value.items.map(item => item.id)).size !== value.items.length || new Set(value.items.map(item => item.matter_id)).size > c.locked_matter_count) fail();
  for (const item of value.items) {
    const { matter_id, matter_title, analysis_id, ...observation } = item;
    if (!identifier(matter_id) || typeof matter_title !== 'string' || matter_title.length > 200 || (analysis_id !== null && !identifier(analysis_id))) fail();
    verifyReadinessItem(observation);
    if (analysis_id === null && (item.state !== 'unavailable' || item.historical_review.state !== 'unknown')) fail();
  }
}
