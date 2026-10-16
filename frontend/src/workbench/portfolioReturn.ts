import { validateCarriedDestinationReturn, type CarriedDestinationReturn } from './carriedDestinationReturn';
import { validateCarriedArrivalEventHandoff, type CarriedArrivalEventHandoff } from './carriedArrivalEventHandoff';
import { validateCarriedArrivalReturn, type CarriedArrivalReturn } from './carriedArrivalReturn';
import { validateOnwardEventHandoff, type OnwardEventHandoff } from './onwardEventHandoff';
import type { PortfolioFilters } from '../types';
import type { PortfolioQueueFilters, PortfolioQueueItem, PortfolioQueuePage } from '../pages/portfolioSourceQueueTypes';
import { canonicalJson } from '../pages/matter/sourceReviewTypes';
import { navigationContextId, navigationIdentifier, navigationReviewId, type NavigationMetadata, type SourceTarget } from '../pages/sourceContextNavigationTypes';
import type { ReviewLineage } from '../pages/sourceReviewLineageTypes';
import { compareReturnIdentities, verifyReturnSelection, type ReturnComparison } from './returnComparison';
import { validateRenewalHandoff, type RenewalHandoff } from './renewalHandoff';
import { validateReviewPathHandoff, type ReviewPathHandoff } from './reviewPathHandoff';
import { validateComparisonReturn, type ComparisonReturnReceipt } from './comparisonReturn';
import { validateComparisonEventHandoff, type ComparisonEventHandoff } from './comparisonEventHandoff';
import { validateArrivalReturn, type ArrivalReturn } from './arrivalReturn';

import { validateArrivalEventHandoff, type ArrivalEventHandoff } from './arrivalEventHandoff';

import { validateOnwardReturn, type OnwardReturn } from './onwardReturn';

export const returnToken = (value: unknown): value is string => typeof value === 'string' && /^[a-f0-9]{32}$/.test(value);
const sha = (value: unknown): value is string => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value);
const stamp = (value: unknown) => typeof value === 'string' && value.length <= 40 && Number.isFinite(Date.parse(value));
const keys = (value: object, names: string[]) => canonicalJson(Object.keys(value).sort()) === canonicalJson(names.sort());
const day = (value: string) => value === '' || /^\d{4}-\d{2}-\d{2}$/.test(value) && value.slice(0, 4) !== '0000' && Number.isFinite(Date.parse(value + 'T00:00:00Z')) && new Date(value + 'T00:00:00Z').toISOString().slice(0, 10) === value;
export type ReturnTarget = { matter_id: string; analysis_id: string; context_id: string; version_id: string | null; manifest_sha256: string | null;
  head_id: string | null; head_state: NavigationMetadata['historical_review']['state']; current_version_id: string | null; version_observed_at: string | null;
  review_id: string | null; review_packet_sha256: string | null; observed_at: string };
export type ReturnIntent = { recipe: 'private-portfolio-return-intent-v2'; filters: PortfolioQueueFilters; target: ReturnTarget };
export type QueueDestination = { kind: 'work' | 'invalid' } | { kind: 'sources'; return_token?: string };
export const queueReturnHref = (token?: string) => token === undefined ? '#/work?view=source-reviews' : returnToken(token) ? `#/work?view=source-reviews&return=${token}` : null;
export function queueDestination(params: URLSearchParams, pathname = '/work'): QueueDestination {
  if (pathname !== '/work') return { kind: 'invalid' };
  if (![...params.keys()].length) return { kind: 'work' };
  const view = params.getAll('view'), token = params.getAll('return');
  if ([...params.keys()].some(key => !['view', 'return'].includes(key)) || view.length !== 1 || view[0] !== 'source-reviews'
    || token.length > 1 || token.length === 1 && !returnToken(token[0])) return { kind: 'invalid' };
  return { kind: 'sources', ...(token.length ? { return_token: token[0] } : {}) };
}
export function validateReturn(value: ReturnIntent) {
  const fail = () => { throw new Error('Portföy dönüşünün tam filtre veya kayıt bağı doğrulanamadı.'); };
  if (!value || !keys(value, ['recipe', 'filters', 'target']) || value.recipe !== 'private-portfolio-return-intent-v2') fail();
  const f = value.filters, t = value.target;
  if (!f || !keys(f, ['customer_ids', 'date_field', 'date_from', 'date_to', 'source_date_from', 'source_date_to', 'bucket'])
    || !Array.isArray(f.customer_ids) || f.customer_ids.length > 100 || f.customer_ids.some(id => !navigationIdentifier(id))
    || canonicalJson(f.customer_ids) !== canonicalJson([...new Set(f.customer_ids)].sort())
    || !['created_at', 'updated_at', 'relevant_date'].includes(f.date_field) || !['all', 'action_required'].includes(f.bucket)) fail();
  for (const key of ['date_from', 'date_to', 'source_date_from', 'source_date_to'] as const) if (typeof f[key] !== 'string' || !day(f[key])) fail();
  if (f.date_from && f.date_to && f.date_from > f.date_to || f.source_date_from && f.source_date_to && f.source_date_from > f.source_date_to) fail();
  if (!t || !keys(t, ['matter_id', 'analysis_id', 'context_id', 'version_id', 'manifest_sha256', 'head_id', 'head_state', 'current_version_id', 'version_observed_at', 'review_id', 'review_packet_sha256', 'observed_at'])
    || !navigationIdentifier(t.matter_id) || !navigationIdentifier(t.analysis_id) || !navigationContextId(t.context_id) || !stamp(t.observed_at)
    || t.version_id !== null && !navigationIdentifier(t.version_id) || t.current_version_id !== null && !navigationIdentifier(t.current_version_id)
    || t.manifest_sha256 !== null && !sha(t.manifest_sha256) || t.head_id !== null && !navigationReviewId(t.head_id)
    || !['unknown', 'unreviewed', 'changes_requested', 'reviewed_conditional'].includes(t.head_state)
    || t.head_state === 'unreviewed' && t.head_id !== null || ['changes_requested', 'reviewed_conditional'].includes(t.head_state) && t.head_id === null
    || t.version_observed_at !== null && !stamp(t.version_observed_at) || t.current_version_id !== null && t.version_observed_at === null
    || t.review_id !== null && !navigationReviewId(t.review_id) || t.review_packet_sha256 !== null && !sha(t.review_packet_sha256)
    || (t.review_id === null && t.review_packet_sha256 !== null) || (t.version_id === null) !== (t.manifest_sha256 === null)) fail();
}
export function captureReturn(page: PortfolioQueuePage, item: PortfolioQueueItem): ReturnIntent {
  if (!item.analysis_id || !page.items.includes(item)) throw new Error('Seçilen portföy kaydı bu gözlemde yok.');
  const value: ReturnIntent = { recipe: 'private-portfolio-return-intent-v2', filters: structuredClone(page.filters), target: {
    matter_id: item.matter_id, analysis_id: item.analysis_id, context_id: item.id, version_id: item.version_id || null, manifest_sha256: item.manifest_sha256 || null,
    head_id: item.historical_review.id, head_state: item.historical_review.state, current_version_id: null, version_observed_at: null,
    review_id: null, review_packet_sha256: null, observed_at: page.observed_at } };
  validateReturn(value); return value;
}
export function returnMatches(value: ReturnIntent, target: SourceTarget) { return value.target.matter_id === target.matter_id && value.target.analysis_id === target.analysis_id && value.target.context_id === target.context_id; }
export function departingReturn(value: ReturnIntent, meta: NavigationMetadata | null, lineage: ReviewLineage | null, reviewId?: string): ReturnIntent {
  if (lineage && !meta) throw new Error('Seçilen kararın bağlam gözlemi yok; dönüş kurulmadı.');
  if (meta) verifyReturnSelection(value, meta, lineage, reviewId);
  const next = structuredClone(value);
  // Only a first unselected departure may establish an unobserved version baseline.
  // An already selected historical event retains even an explicitly unknown baseline.
  if (next.target.version_observed_at === null && next.target.review_id === null && meta) {
    next.target.current_version_id = meta.analysis.current_version_id;
    next.target.version_observed_at = meta.observed_at;
  }
  next.target.review_id = reviewId || null; next.target.review_packet_sha256 = lineage?.selected_review.packet_sha256 || null;
  if (lineage && lineage.selected_review.id !== reviewId) throw new Error('Seçilen inceleme kimliği eşleşmiyor.');
  validateReturn(next); return next;
}
export const portfolioPart = (value: PortfolioQueueFilters): PortfolioFilters => ({ customer_ids: [...value.customer_ids], date_field: value.date_field, date_from: value.date_from, date_to: value.date_to });
export class PortfolioReturnBook {
  private rows = new Map<string, { expires: number; value: ReturnIntent; renewal?: RenewalHandoff; reviewPath?: ReviewPathHandoff; comparisonReturn?: ComparisonReturnReceipt; comparisonEvent?: ComparisonEventHandoff; arrivalReturn?: ArrivalReturn; arrivalEvent?: ArrivalEventHandoff; onwardReturn?: OnwardReturn; onwardEvent?: OnwardEventHandoff; carriedArrival?: CarriedArrivalReturn; carriedArrivalEvent?: CarriedArrivalEventHandoff; carriedDestination?: CarriedDestinationReturn }>();
  constructor(private now = () => Date.now(), private nonce = () => crypto.randomUUID().replaceAll('-', '')) {}
  put(value: ReturnIntent, renewal?: RenewalHandoff): string { validateReturn(value); if (renewal) validateRenewalHandoff(renewal, value); this.prune();
    const id = this.nonce(); if (!returnToken(id) || this.rows.has(id)) throw new Error('Dönüş kimliği oluşturulamadı.');
    while (this.rows.size >= 8) this.rows.delete(this.rows.keys().next().value!);
    this.rows.set(id, { value: structuredClone(value), ...(renewal ? { renewal: structuredClone(renewal) } : {}), expires: this.now() + 30 * 60 * 1000 }); return id; }
  putReviewPath(value: ReturnIntent, handoff: ReviewPathHandoff): string {
    validateReturn(value);
    validateReviewPathHandoff(handoff, value);
    const id = this.put(value); this.rows.get(id)!.reviewPath = structuredClone(handoff); return id;
  }
  putComparisonReturn(value: ReturnIntent, receipt: ComparisonReturnReceipt): string {
    validateComparisonReturn(receipt, value); const id = this.put(value); this.rows.get(id)!.comparisonReturn = structuredClone(receipt); return id;
  }
  putCarriedDestinationReturn(value: ReturnIntent, observation: CarriedDestinationReturn): string {
    validateCarriedDestinationReturn(observation, value); const id = this.putCarriedArrivalReturn(value, observation.handoff.observation);
    this.rows.get(id)!.carriedDestination = structuredClone(observation); return id;
  }
  getCarriedDestinationReturn(id: string): CarriedDestinationReturn | null { this.prune(); const row = returnToken(id) ? this.rows.get(id) : undefined; return row?.carriedDestination ? structuredClone(row.carriedDestination) : null; }
  putCarriedArrivalEvent(value: ReturnIntent, handoff: CarriedArrivalEventHandoff): string { validateCarriedArrivalEventHandoff(handoff, value); const id = this.put(value); this.rows.get(id)!.carriedArrivalEvent = structuredClone(handoff); return id; }
  getCarriedArrivalEvent(id: string): CarriedArrivalEventHandoff | null { this.prune(); const row = returnToken(id) ? this.rows.get(id) : undefined; return row?.carriedArrivalEvent ? structuredClone(row.carriedArrivalEvent) : null; }
  putCarriedArrivalReturn(value: ReturnIntent, observation: CarriedArrivalReturn): string {
    validateCarriedArrivalReturn(observation, value); const id = this.put(value), row = this.rows.get(id)!;
    row.carriedArrival = structuredClone(observation);
    row.onwardReturn = structuredClone(observation.handoff.observation);
    row.arrivalReturn = structuredClone(observation.handoff.observation.handoff.observation);
    row.comparisonReturn = structuredClone(observation.handoff.observation.handoff.observation.handoff.receipt); return id;
  }
  getCarriedArrivalReturn(id: string): CarriedArrivalReturn | null { this.prune(); const row = returnToken(id) ? this.rows.get(id) : undefined; return row?.carriedArrival ? structuredClone(row.carriedArrival) : null; }
  putOnwardEvent(value: ReturnIntent, handoff: OnwardEventHandoff): string { validateOnwardEventHandoff(handoff, value); const id = this.put(value); this.rows.get(id)!.onwardEvent = structuredClone(handoff); return id; }
  getOnwardEvent(id: string): OnwardEventHandoff | null { this.prune(); const row = returnToken(id) ? this.rows.get(id) : undefined; return row?.onwardEvent ? structuredClone(row.onwardEvent) : null; }
  putOnwardReturn(value: ReturnIntent, observation: OnwardReturn): string {
    validateOnwardReturn(observation, value); const id = this.put(value);
    this.rows.get(id)!.onwardReturn = structuredClone(observation);
    this.rows.get(id)!.arrivalReturn = structuredClone(observation.handoff.observation);
    this.rows.get(id)!.comparisonReturn = structuredClone(observation.handoff.observation.handoff.receipt); return id;
  }
  getOnwardReturn(id: string): OnwardReturn | null { this.prune(); const row = returnToken(id) ? this.rows.get(id) : undefined; return row?.onwardReturn ? structuredClone(row.onwardReturn) : null; }
  putArrivalEvent(value: ReturnIntent, handoff: ArrivalEventHandoff): string { validateArrivalEventHandoff(handoff, value); const id = this.put(value); this.rows.get(id)!.arrivalEvent = structuredClone(handoff); return id; }
  getArrivalEvent(id: string): ArrivalEventHandoff | null { this.prune(); const row = returnToken(id) ? this.rows.get(id) : undefined; return row?.arrivalEvent ? structuredClone(row.arrivalEvent) : null; }
  putArrivalReturn(value: ReturnIntent, observation: ArrivalReturn): string {
    validateArrivalReturn(observation, value); const id = this.put(value);
    this.rows.get(id)!.arrivalReturn = structuredClone(observation);
    this.rows.get(id)!.comparisonReturn = structuredClone(observation.handoff.receipt); return id;
  }
  getArrivalReturn(id: string): ArrivalReturn | null { this.prune(); const row = returnToken(id) ? this.rows.get(id) : undefined; return row?.arrivalReturn ? structuredClone(row.arrivalReturn) : null; }
  putComparisonEvent(value: ReturnIntent, handoff: ComparisonEventHandoff): string { validateComparisonEventHandoff(handoff, value); const id = this.put(value); this.rows.get(id)!.comparisonEvent = structuredClone(handoff); return id; }
  getComparisonEvent(id: string): ComparisonEventHandoff | null { this.prune(); const row = returnToken(id) ? this.rows.get(id) : undefined; return row?.comparisonEvent ? structuredClone(row.comparisonEvent) : null; }
  getComparisonReturn(id: string): ComparisonReturnReceipt | null { this.prune(); const row = returnToken(id) ? this.rows.get(id) : undefined; return row?.comparisonReturn ? structuredClone(row.comparisonReturn) : null; }
  isReviewPath(id: string): boolean { this.prune(); return returnToken(id) && !!this.rows.get(id)?.reviewPath; }
  getReviewPath(id: string): ReviewPathHandoff | null { this.prune(); const row = returnToken(id) ? this.rows.get(id) : undefined; return row?.reviewPath ? structuredClone(row.reviewPath) : null; }
  get(id: string): ReturnIntent | null { this.prune(); const row = returnToken(id) ? this.rows.get(id) : undefined; return row ? structuredClone(row.value) : null; }
  getRenewal(id: string): RenewalHandoff | null { this.prune(); const row = returnToken(id) ? this.rows.get(id) : undefined; return row?.renewal ? structuredClone(row.renewal) : null; }
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
export type ReturnReconciliation = { state: 'not_observed'; queue_observed_at: string } | { state: 'observed'; comparison: ReturnComparison;
  private_state: PortfolioQueueItem['private_observation']['state']; context_state: NavigationMetadata['admission']['context_state']; review_state: NavigationMetadata['admission']['review_state'];
  selected_review_state?: string; queue_observed_at: string; target_observed_at: string };
export function reconcileReturn(intent: ReturnIntent, page: PortfolioQueuePage, meta: NavigationMetadata | null, lineage: ReviewLineage | null): ReturnReconciliation {
  validateReturn(intent);
  if (canonicalJson(page.filters) !== canonicalJson(intent.filters)) throw new Error('Dönüşün tam filtreleri değişti; yeniden hazırlayın.');
  const t = intent.target, item = page.items.find(row => row.id === t.context_id);
  if (!item) { if (meta || lineage) throw new Error('Bu pencerenin dışında kayıt bağları kullanılamaz.'); return { state: 'not_observed', queue_observed_at: page.observed_at }; }
  if (!meta || meta.integrity !== 'verified' || t.version_id === null || t.manifest_sha256 === null || item.matter_id !== t.matter_id || item.analysis_id !== t.analysis_id || !returnMatches(intent, { kind: 'selected', matter_id: meta.matter_id, analysis_id: meta.analysis_id, context_id: meta.context_id })
    || item.version_id !== t.version_id || item.manifest_sha256 !== t.manifest_sha256 || meta.context.version_id !== t.version_id || meta.context.manifest_sha256 !== t.manifest_sha256
    || item.historical_review.id !== meta.historical_review.id || item.historical_review.state !== meta.historical_review.state) throw new Error('Kuyruk ve seçilen kaydın ayrı gözlemleri eşleşmiyor; yeniden gözlemleyin.');
  if (t.review_id && (!lineage || lineage.selected_review.id !== t.review_id || t.review_packet_sha256 !== null && lineage.selected_review.packet_sha256 !== t.review_packet_sha256)) throw new Error('Seçilen tarihsel inceleme değişti; başka karar kullanılmaz.');
  return { state: 'observed', comparison: compareReturnIdentities(intent, meta, lineage),
    private_state: item.private_observation.state, context_state: meta.admission.context_state, review_state: meta.admission.review_state,
    selected_review_state: lineage?.selected_review.state, queue_observed_at: page.observed_at, target_observed_at: meta.observed_at };
}
