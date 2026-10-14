import type { PortfolioFilters } from '../types';
import type { PortfolioQueueFilters, PortfolioQueueItem, PortfolioQueuePage } from '../pages/portfolioSourceQueueTypes';
import { canonicalJson } from '../pages/matter/sourceReviewTypes';
import { navigationContextId, navigationIdentifier, navigationReviewId, type NavigationMetadata, type SourceTarget } from '../pages/sourceContextNavigationTypes';
import type { ReviewLineage } from '../pages/sourceReviewLineageTypes';

export const returnToken = (value: unknown): value is string => typeof value === 'string' && /^[a-f0-9]{32}$/.test(value);
const sha = (value: unknown): value is string => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value);
const stamp = (value: unknown) => typeof value === 'string' && value.length <= 40 && Number.isFinite(Date.parse(value));
const keys = (value: object, names: string[]) => canonicalJson(Object.keys(value).sort()) === canonicalJson(names.sort());
const day = (value: string) => value === '' || /^\d{4}-\d{2}-\d{2}$/.test(value) && value.slice(0, 4) !== '0000' && Number.isFinite(Date.parse(value + 'T00:00:00Z')) && new Date(value + 'T00:00:00Z').toISOString().slice(0, 10) === value;
export type ReturnTarget = { matter_id: string; analysis_id: string; context_id: string; version_id: string | null; manifest_sha256: string | null;
  head_id: string | null; current_version_id: string | null; review_id: string | null; review_packet_sha256: string | null; observed_at: string };
export type ReturnIntent = { recipe: 'private-portfolio-return-intent-v1'; filters: PortfolioQueueFilters; target: ReturnTarget };
export type QueueDestination = { kind: 'work' | 'invalid' } | { kind: 'sources'; return_token?: string };
export const queueReturnHref = (token?: string) => token === undefined ? '#/work?view=source-reviews' : returnToken(token) ? `#/work?view=source-reviews&return=${token}` : null;
export function queueDestination(params: URLSearchParams): QueueDestination {
  if (![...params.keys()].length) return { kind: 'work' };
  const view = params.getAll('view'), token = params.getAll('return');
  if ([...params.keys()].some(key => !['view', 'return'].includes(key)) || view.length !== 1 || view[0] !== 'source-reviews'
    || token.length > 1 || token.length === 1 && !returnToken(token[0])) return { kind: 'invalid' };
  return { kind: 'sources', ...(token.length ? { return_token: token[0] } : {}) };
}
export function validateReturn(value: ReturnIntent) {
  const fail = () => { throw new Error('Portföy dönüşünün tam filtre veya kayıt bağı doğrulanamadı.'); };
  if (!value || !keys(value, ['recipe', 'filters', 'target']) || value.recipe !== 'private-portfolio-return-intent-v1') fail();
  const f = value.filters, t = value.target;
  if (!f || !keys(f, ['customer_ids', 'date_field', 'date_from', 'date_to', 'source_date_from', 'source_date_to', 'bucket'])
    || !Array.isArray(f.customer_ids) || f.customer_ids.length > 100 || f.customer_ids.some(id => !navigationIdentifier(id))
    || canonicalJson(f.customer_ids) !== canonicalJson([...new Set(f.customer_ids)].sort())
    || !['created_at', 'updated_at', 'relevant_date'].includes(f.date_field) || !['all', 'action_required'].includes(f.bucket)) fail();
  for (const key of ['date_from', 'date_to', 'source_date_from', 'source_date_to'] as const) if (typeof f[key] !== 'string' || !day(f[key])) fail();
  if (f.date_from && f.date_to && f.date_from > f.date_to || f.source_date_from && f.source_date_to && f.source_date_from > f.source_date_to) fail();
  if (!t || !keys(t, ['matter_id', 'analysis_id', 'context_id', 'version_id', 'manifest_sha256', 'head_id', 'current_version_id', 'review_id', 'review_packet_sha256', 'observed_at'])
    || !navigationIdentifier(t.matter_id) || !navigationIdentifier(t.analysis_id) || !navigationContextId(t.context_id) || !stamp(t.observed_at)
    || t.version_id !== null && !navigationIdentifier(t.version_id) || t.current_version_id !== null && !navigationIdentifier(t.current_version_id)
    || t.manifest_sha256 !== null && !sha(t.manifest_sha256) || t.head_id !== null && !navigationReviewId(t.head_id)
    || t.review_id !== null && !navigationReviewId(t.review_id) || t.review_packet_sha256 !== null && !sha(t.review_packet_sha256)
    || (t.review_id === null && t.review_packet_sha256 !== null) || (t.version_id === null) !== (t.manifest_sha256 === null)) fail();
}
export function captureReturn(page: PortfolioQueuePage, item: PortfolioQueueItem): ReturnIntent {
  if (!item.analysis_id || !page.items.includes(item)) throw new Error('Seçilen portföy kaydı bu gözlemde yok.');
  const value: ReturnIntent = { recipe: 'private-portfolio-return-intent-v1', filters: structuredClone(page.filters), target: {
    matter_id: item.matter_id, analysis_id: item.analysis_id, context_id: item.id, version_id: item.version_id || null, manifest_sha256: item.manifest_sha256 || null,
    head_id: item.historical_review.id, current_version_id: null, review_id: null, review_packet_sha256: null, observed_at: page.observed_at } };
  validateReturn(value); return value;
}
export function returnMatches(value: ReturnIntent, target: SourceTarget) { return value.target.matter_id === target.matter_id && value.target.analysis_id === target.analysis_id && value.target.context_id === target.context_id; }
export function departingReturn(value: ReturnIntent, meta: NavigationMetadata | null, lineage: ReviewLineage | null, reviewId?: string): ReturnIntent {
  if (meta && (value.target.matter_id !== meta.matter_id || value.target.analysis_id !== meta.analysis_id || value.target.context_id !== meta.context_id
    || value.target.version_id !== meta.context.version_id || value.target.manifest_sha256 !== meta.context.manifest_sha256 || meta.integrity !== 'verified')) throw new Error('Sabit portföy seçimi değişti; dönüş yeniden kurulmalıdır.');
  const next = structuredClone(value);
  next.target.current_version_id = meta?.analysis.current_version_id || null;
  next.target.review_id = reviewId || null; next.target.review_packet_sha256 = lineage?.selected_review.packet_sha256 || null;
  if (lineage && lineage.selected_review.id !== reviewId) throw new Error('Seçilen inceleme kimliği eşleşmiyor.');
  validateReturn(next); return next;
}
export const portfolioPart = (value: PortfolioQueueFilters): PortfolioFilters => ({ customer_ids: [...value.customer_ids], date_field: value.date_field, date_from: value.date_from, date_to: value.date_to });
export class PortfolioReturnBook {
  private rows = new Map<string, { expires: number; value: ReturnIntent }>();
  constructor(private now = () => Date.now(), private nonce = () => crypto.randomUUID().replaceAll('-', '')) {}
  put(value: ReturnIntent): string { validateReturn(value); this.prune();
    const id = this.nonce(); if (!returnToken(id) || this.rows.has(id)) throw new Error('Dönüş kimliği oluşturulamadı.');
    while (this.rows.size >= 8) this.rows.delete(this.rows.keys().next().value!);
    this.rows.set(id, { value: structuredClone(value), expires: this.now() + 30 * 60 * 1000 }); return id; }
  get(id: string): ReturnIntent | null { this.prune(); const row = returnToken(id) ? this.rows.get(id) : undefined; return row ? structuredClone(row.value) : null; }
  remaining(id: string) { this.prune(); return Math.max(0, (this.rows.get(id)?.expires || 0) - this.now()); }
  private prune() { for (const [id, row] of this.rows) if (row.expires <= this.now()) this.rows.delete(id); }
}
/** Suspension clears private views; only the same verified principal can resume intent. */
export class PrincipalReturnBook {
  private principal: string | null = null;
  private book = new PortfolioReturnBook();
  forPrincipal(principal: string | null) {
    if (principal !== this.principal) { this.principal = principal; this.book = new PortfolioReturnBook(); }
    return this.book;
  }
}
export type ReturnReconciliation = { state: 'not_observed' | 'observed'; head_changed?: boolean; current_version_changed?: boolean;
  private_state?: string; context_state?: string; review_state?: string; selected_review_state?: string; queue_observed_at: string; target_observed_at?: string };
export function reconcileReturn(intent: ReturnIntent, page: PortfolioQueuePage, meta: NavigationMetadata | null, lineage: ReviewLineage | null): ReturnReconciliation {
  validateReturn(intent);
  if (canonicalJson(page.filters) !== canonicalJson(intent.filters)) throw new Error('Dönüşün tam filtreleri değişti; yeniden hazırlayın.');
  const t = intent.target, item = page.items.find(row => row.id === t.context_id);
  if (!item) { if (meta || lineage) throw new Error('Bu pencerenin dışında kayıt bağları kullanılamaz.'); return { state: 'not_observed', queue_observed_at: page.observed_at }; }
  if (!meta || meta.integrity !== 'verified' || t.version_id === null || t.manifest_sha256 === null || item.matter_id !== t.matter_id || item.analysis_id !== t.analysis_id || !returnMatches(intent, { kind: 'selected', matter_id: meta.matter_id, analysis_id: meta.analysis_id, context_id: meta.context_id })
    || item.version_id !== t.version_id || item.manifest_sha256 !== t.manifest_sha256 || meta.context.version_id !== t.version_id || meta.context.manifest_sha256 !== t.manifest_sha256
    || item.historical_review.id !== meta.historical_review.id || item.historical_review.state !== meta.historical_review.state) throw new Error('Kuyruk ve seçilen kaydın ayrı gözlemleri eşleşmiyor; yeniden gözlemleyin.');
  if (t.review_id && (!lineage || lineage.selected_review.id !== t.review_id || t.review_packet_sha256 !== null && lineage.selected_review.packet_sha256 !== t.review_packet_sha256)) throw new Error('Seçilen tarihsel inceleme değişti; başka karar kullanılmaz.');
  return { state: 'observed', head_changed: meta.historical_review.id !== t.head_id,
    current_version_changed: t.current_version_id !== null && meta.analysis.current_version_id !== t.current_version_id,
    private_state: item.private_observation.state, context_state: meta.admission.context_state, review_state: meta.admission.review_state,
    selected_review_state: lineage?.selected_review.state, queue_observed_at: page.observed_at, target_observed_at: meta.observed_at };
}
