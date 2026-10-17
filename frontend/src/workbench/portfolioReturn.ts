import { validateHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationEvent, type HandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationEvent } from './handoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationEvent';
import { validateHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationReturn, type HandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationReturn } from './handoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationReturn';
import { validateHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalEvent, type HandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalEvent } from './handoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalEvent';
import { validateHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalReturn, type HandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalReturn } from './handoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalReturn';
import { validateHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationEvent, type HandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationEvent } from './handoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationEvent';
import { validateHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationReturn, type HandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationReturn } from './handoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationReturn';
import { validateHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalEvent, type HandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalEvent } from './handoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalEvent';
import { validateHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalReturn, type HandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalReturn } from './handoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalReturn';
import { validateHandoffArrivalDestinationArrivalDestinationArrivalDestinationEvent, type HandoffArrivalDestinationArrivalDestinationArrivalDestinationEvent } from './handoffArrivalDestinationArrivalDestinationArrivalDestinationEvent';
import { validateHandoffArrivalDestinationArrivalDestinationArrivalDestinationReturn, type HandoffArrivalDestinationArrivalDestinationArrivalDestinationReturn } from './handoffArrivalDestinationArrivalDestinationArrivalDestinationReturn';
import { validateHandoffArrivalDestinationArrivalDestinationArrivalEvent, type HandoffArrivalDestinationArrivalDestinationArrivalEvent } from './handoffArrivalDestinationArrivalDestinationArrivalEvent';
import { validateHandoffArrivalDestinationArrivalDestinationArrivalReturn, type HandoffArrivalDestinationArrivalDestinationArrivalReturn } from './handoffArrivalDestinationArrivalDestinationArrivalReturn';
import { validateHandoffArrivalDestinationArrivalDestinationEvent, type HandoffArrivalDestinationArrivalDestinationEvent } from './handoffArrivalDestinationArrivalDestinationEvent';
import { validateHandoffArrivalDestinationArrivalDestinationReturn, type HandoffArrivalDestinationArrivalDestinationReturn } from './handoffArrivalDestinationArrivalDestinationReturn';
import { validateHandoffArrivalDestinationArrivalEvent, type HandoffArrivalDestinationArrivalEvent } from './handoffArrivalDestinationArrivalEvent';
import { validateHandoffArrivalDestinationArrivalReturn, type HandoffArrivalDestinationArrivalReturn } from './handoffArrivalDestinationArrivalReturn';
import { validateHandoffArrivalDestinationEvent, type HandoffArrivalDestinationEvent } from './handoffArrivalDestinationEvent';
import { validateHandoffArrivalDestinationReturn, type HandoffArrivalDestinationReturn } from './handoffArrivalDestinationReturn';
import { validateHandoffArrivalEvent, type HandoffArrivalEvent } from './handoffArrivalEvent';
import { validateHandoffDestinationArrivalReturn, type HandoffDestinationArrivalReturn } from './handoffDestinationArrivalReturn';
import { validateHandoffDestinationEvent, type HandoffDestinationEvent } from './handoffDestinationEvent';
import { validateArrivalHandoffDestinationReturn, type ArrivalHandoffDestinationReturn } from './arrivalHandoffDestinationReturn';
import { validateCarriedDestinationArrivalEventHandoff, type CarriedDestinationArrivalEventHandoff } from './carriedDestinationArrivalEventHandoff';
import { validateCarriedDestinationArrivalReturn, type CarriedDestinationArrivalReturn } from './carriedDestinationArrivalReturn';
import { validateCarriedDestinationEventHandoff, type CarriedDestinationEventHandoff } from './carriedDestinationEventHandoff';
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
  private rows = new Map<string, { expires: number; value: ReturnIntent; renewal?: RenewalHandoff; reviewPath?: ReviewPathHandoff; comparisonReturn?: ComparisonReturnReceipt; comparisonEvent?: ComparisonEventHandoff; arrivalReturn?: ArrivalReturn; arrivalEvent?: ArrivalEventHandoff; onwardReturn?: OnwardReturn; onwardEvent?: OnwardEventHandoff; carriedArrival?: CarriedArrivalReturn; carriedArrivalEvent?: CarriedArrivalEventHandoff; carriedDestination?: CarriedDestinationReturn; carriedDestinationEvent?: CarriedDestinationEventHandoff; destinationArrival?: CarriedDestinationArrivalReturn; destinationArrivalEvent?: CarriedDestinationArrivalEventHandoff; handoffDestination?: ArrivalHandoffDestinationReturn; handoffDestinationEvent?: HandoffDestinationEvent; handoffDestinationArrival?: HandoffDestinationArrivalReturn; handoffArrivalEvent?: HandoffArrivalEvent; handoffArrivalDestination?: HandoffArrivalDestinationReturn; handoffArrivalDestinationEvent?: HandoffArrivalDestinationEvent; handoffArrivalDestinationArrival?: HandoffArrivalDestinationArrivalReturn; handoffArrivalDestinationArrivalEvent?: HandoffArrivalDestinationArrivalEvent; handoffArrivalDestinationArrivalDestination?: HandoffArrivalDestinationArrivalDestinationReturn; handoffArrivalDestinationArrivalDestinationEvent?: HandoffArrivalDestinationArrivalDestinationEvent; handoffArrivalDestinationArrivalDestinationArrival?: HandoffArrivalDestinationArrivalDestinationArrivalReturn; handoffArrivalDestinationArrivalDestinationArrivalEvent?: HandoffArrivalDestinationArrivalDestinationArrivalEvent; handoffArrivalDestinationArrivalDestinationArrivalDestination?: HandoffArrivalDestinationArrivalDestinationArrivalDestinationReturn; handoffArrivalDestinationArrivalDestinationArrivalDestinationEvent?: HandoffArrivalDestinationArrivalDestinationArrivalDestinationEvent; handoffArrivalDestinationArrivalDestinationArrivalDestinationArrival?: HandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalReturn; handoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalEvent?: HandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalEvent; handoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestination?: HandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationReturn; handoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationEvent?: HandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationEvent; handoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrival?: HandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalReturn; handoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalEvent?: HandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalEvent; handoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestination?: HandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationReturn; handoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationEvent?: HandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationEvent }>();
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
  putHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationEvent(value: ReturnIntent, handoff: HandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationEvent): string {
    validateHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationEvent(handoff, value); const id = this.put(value); this.rows.get(id)!.handoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationEvent = structuredClone(handoff); return id;
  }
  getHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationEvent(id: string): HandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationEvent | null { this.prune(); const row = returnToken(id) ? this.rows.get(id) : undefined; return row?.handoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationEvent ? structuredClone(row.handoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationEvent) : null; }
  putHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationReturn(value: ReturnIntent, observation: HandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationReturn): string {
    validateHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationReturn(observation, value); const id = this.putHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalReturn(value, observation.handoff.observation);
    this.rows.get(id)!.handoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestination = structuredClone(observation); return id;
  }
  getHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationReturn(id: string): HandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationReturn | null { this.prune(); const row = returnToken(id) ? this.rows.get(id) : undefined; return row?.handoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestination ? structuredClone(row.handoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestination) : null; }
  putHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalEvent(value: ReturnIntent, handoff: HandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalEvent): string {
    validateHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalEvent(handoff, value); const id = this.put(value); this.rows.get(id)!.handoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalEvent = structuredClone(handoff); return id;
  }
  getHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalEvent(id: string): HandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalEvent | null { this.prune(); const row = returnToken(id) ? this.rows.get(id) : undefined; return row?.handoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalEvent ? structuredClone(row.handoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalEvent) : null; }
  putHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalReturn(value: ReturnIntent, observation: HandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalReturn): string {
    validateHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalReturn(observation, value); const id = this.putHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationReturn(value, observation.handoff.observation);
    this.rows.get(id)!.handoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrival = structuredClone(observation); return id;
  }
  getHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalReturn(id: string): HandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalReturn | null { this.prune(); const row = returnToken(id) ? this.rows.get(id) : undefined; return row?.handoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrival ? structuredClone(row.handoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrival) : null; }
  putHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationEvent(value: ReturnIntent, handoff: HandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationEvent): string {
    validateHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationEvent(handoff, value); const id = this.put(value); this.rows.get(id)!.handoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationEvent = structuredClone(handoff); return id;
  }
  getHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationEvent(id: string): HandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationEvent | null { this.prune(); const row = returnToken(id) ? this.rows.get(id) : undefined; return row?.handoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationEvent ? structuredClone(row.handoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationEvent) : null; }
  putHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationReturn(value: ReturnIntent, observation: HandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationReturn): string {
    validateHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationReturn(observation, value); const id = this.putHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalReturn(value, observation.handoff.observation);
    this.rows.get(id)!.handoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestination = structuredClone(observation); return id;
  }
  getHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationReturn(id: string): HandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationReturn | null { this.prune(); const row = returnToken(id) ? this.rows.get(id) : undefined; return row?.handoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestination ? structuredClone(row.handoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestination) : null; }
  putHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalEvent(value: ReturnIntent, handoff: HandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalEvent): string {
    validateHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalEvent(handoff, value); const id = this.put(value); this.rows.get(id)!.handoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalEvent = structuredClone(handoff); return id;
  }
  getHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalEvent(id: string): HandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalEvent | null { this.prune(); const row = returnToken(id) ? this.rows.get(id) : undefined; return row?.handoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalEvent ? structuredClone(row.handoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalEvent) : null; }
  putHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalReturn(value: ReturnIntent, observation: HandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalReturn): string {
    validateHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalReturn(observation, value); const id = this.putHandoffArrivalDestinationArrivalDestinationArrivalDestinationReturn(value, observation.handoff.observation);
    this.rows.get(id)!.handoffArrivalDestinationArrivalDestinationArrivalDestinationArrival = structuredClone(observation); return id;
  }
  getHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalReturn(id: string): HandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalReturn | null { this.prune(); const row = returnToken(id) ? this.rows.get(id) : undefined; return row?.handoffArrivalDestinationArrivalDestinationArrivalDestinationArrival ? structuredClone(row.handoffArrivalDestinationArrivalDestinationArrivalDestinationArrival) : null; }
  putHandoffArrivalDestinationArrivalDestinationArrivalDestinationEvent(value: ReturnIntent, handoff: HandoffArrivalDestinationArrivalDestinationArrivalDestinationEvent): string {
    validateHandoffArrivalDestinationArrivalDestinationArrivalDestinationEvent(handoff, value); const id = this.put(value); this.rows.get(id)!.handoffArrivalDestinationArrivalDestinationArrivalDestinationEvent = structuredClone(handoff); return id;
  }
  getHandoffArrivalDestinationArrivalDestinationArrivalDestinationEvent(id: string): HandoffArrivalDestinationArrivalDestinationArrivalDestinationEvent | null { this.prune(); const row = returnToken(id) ? this.rows.get(id) : undefined; return row?.handoffArrivalDestinationArrivalDestinationArrivalDestinationEvent ? structuredClone(row.handoffArrivalDestinationArrivalDestinationArrivalDestinationEvent) : null; }
  putHandoffArrivalDestinationArrivalDestinationArrivalDestinationReturn(value: ReturnIntent, observation: HandoffArrivalDestinationArrivalDestinationArrivalDestinationReturn): string {
    validateHandoffArrivalDestinationArrivalDestinationArrivalDestinationReturn(observation, value); const id = this.putHandoffArrivalDestinationArrivalDestinationArrivalReturn(value, observation.handoff.observation);
    this.rows.get(id)!.handoffArrivalDestinationArrivalDestinationArrivalDestination = structuredClone(observation); return id;
  }
  getHandoffArrivalDestinationArrivalDestinationArrivalDestinationReturn(id: string): HandoffArrivalDestinationArrivalDestinationArrivalDestinationReturn | null { this.prune(); const row = returnToken(id) ? this.rows.get(id) : undefined; return row?.handoffArrivalDestinationArrivalDestinationArrivalDestination ? structuredClone(row.handoffArrivalDestinationArrivalDestinationArrivalDestination) : null; }
  putHandoffArrivalDestinationArrivalDestinationArrivalEvent(value: ReturnIntent, handoff: HandoffArrivalDestinationArrivalDestinationArrivalEvent): string {
    validateHandoffArrivalDestinationArrivalDestinationArrivalEvent(handoff, value); const id = this.put(value); this.rows.get(id)!.handoffArrivalDestinationArrivalDestinationArrivalEvent = structuredClone(handoff); return id;
  }
  getHandoffArrivalDestinationArrivalDestinationArrivalEvent(id: string): HandoffArrivalDestinationArrivalDestinationArrivalEvent | null { this.prune(); const row = returnToken(id) ? this.rows.get(id) : undefined; return row?.handoffArrivalDestinationArrivalDestinationArrivalEvent ? structuredClone(row.handoffArrivalDestinationArrivalDestinationArrivalEvent) : null; }
  putHandoffArrivalDestinationArrivalDestinationArrivalReturn(value: ReturnIntent, observation: HandoffArrivalDestinationArrivalDestinationArrivalReturn): string {
    validateHandoffArrivalDestinationArrivalDestinationArrivalReturn(observation, value); const id = this.putHandoffArrivalDestinationArrivalDestinationReturn(value, observation.handoff.observation);
    this.rows.get(id)!.handoffArrivalDestinationArrivalDestinationArrival = structuredClone(observation); return id;
  }
  getHandoffArrivalDestinationArrivalDestinationArrivalReturn(id: string): HandoffArrivalDestinationArrivalDestinationArrivalReturn | null { this.prune(); const row = returnToken(id) ? this.rows.get(id) : undefined; return row?.handoffArrivalDestinationArrivalDestinationArrival ? structuredClone(row.handoffArrivalDestinationArrivalDestinationArrival) : null; }
  putHandoffArrivalDestinationArrivalDestinationEvent(value: ReturnIntent, handoff: HandoffArrivalDestinationArrivalDestinationEvent): string {
    validateHandoffArrivalDestinationArrivalDestinationEvent(handoff, value); const id = this.put(value); this.rows.get(id)!.handoffArrivalDestinationArrivalDestinationEvent = structuredClone(handoff); return id;
  }
  getHandoffArrivalDestinationArrivalDestinationEvent(id: string): HandoffArrivalDestinationArrivalDestinationEvent | null { this.prune(); const row = returnToken(id) ? this.rows.get(id) : undefined; return row?.handoffArrivalDestinationArrivalDestinationEvent ? structuredClone(row.handoffArrivalDestinationArrivalDestinationEvent) : null; }
  putHandoffArrivalDestinationArrivalDestinationReturn(value: ReturnIntent, observation: HandoffArrivalDestinationArrivalDestinationReturn): string {
    validateHandoffArrivalDestinationArrivalDestinationReturn(observation, value); const id = this.putHandoffArrivalDestinationArrivalReturn(value, observation.handoff.observation);
    this.rows.get(id)!.handoffArrivalDestinationArrivalDestination = structuredClone(observation); return id;
  }
  getHandoffArrivalDestinationArrivalDestinationReturn(id: string): HandoffArrivalDestinationArrivalDestinationReturn | null { this.prune(); const row = returnToken(id) ? this.rows.get(id) : undefined; return row?.handoffArrivalDestinationArrivalDestination ? structuredClone(row.handoffArrivalDestinationArrivalDestination) : null; }
  putHandoffArrivalDestinationArrivalEvent(value: ReturnIntent, handoff: HandoffArrivalDestinationArrivalEvent): string {
    validateHandoffArrivalDestinationArrivalEvent(handoff, value); const id = this.put(value); this.rows.get(id)!.handoffArrivalDestinationArrivalEvent = structuredClone(handoff); return id;
  }
  getHandoffArrivalDestinationArrivalEvent(id: string): HandoffArrivalDestinationArrivalEvent | null { this.prune(); const row = returnToken(id) ? this.rows.get(id) : undefined; return row?.handoffArrivalDestinationArrivalEvent ? structuredClone(row.handoffArrivalDestinationArrivalEvent) : null; }
  putHandoffArrivalDestinationArrivalReturn(value: ReturnIntent, observation: HandoffArrivalDestinationArrivalReturn): string {
    validateHandoffArrivalDestinationArrivalReturn(observation, value); const id = this.putHandoffArrivalDestinationReturn(value, observation.handoff.observation);
    this.rows.get(id)!.handoffArrivalDestinationArrival = structuredClone(observation); return id;
  }
  getHandoffArrivalDestinationArrivalReturn(id: string): HandoffArrivalDestinationArrivalReturn | null { this.prune(); const row = returnToken(id) ? this.rows.get(id) : undefined; return row?.handoffArrivalDestinationArrival ? structuredClone(row.handoffArrivalDestinationArrival) : null; }
  putHandoffArrivalDestinationEvent(value: ReturnIntent, handoff: HandoffArrivalDestinationEvent): string {
    validateHandoffArrivalDestinationEvent(handoff, value); const id = this.put(value); this.rows.get(id)!.handoffArrivalDestinationEvent = structuredClone(handoff); return id;
  }
  getHandoffArrivalDestinationEvent(id: string): HandoffArrivalDestinationEvent | null { this.prune(); const row = returnToken(id) ? this.rows.get(id) : undefined; return row?.handoffArrivalDestinationEvent ? structuredClone(row.handoffArrivalDestinationEvent) : null; }
  putHandoffArrivalDestinationReturn(value: ReturnIntent, observation: HandoffArrivalDestinationReturn): string {
    validateHandoffArrivalDestinationReturn(observation, value); const id = this.putHandoffDestinationArrivalReturn(value, observation.handoff.observation);
    this.rows.get(id)!.handoffArrivalDestination = structuredClone(observation); return id;
  }
  getHandoffArrivalDestinationReturn(id: string): HandoffArrivalDestinationReturn | null { this.prune(); const row = returnToken(id) ? this.rows.get(id) : undefined; return row?.handoffArrivalDestination ? structuredClone(row.handoffArrivalDestination) : null; }
  putHandoffArrivalEvent(value: ReturnIntent, handoff: HandoffArrivalEvent): string {
    validateHandoffArrivalEvent(handoff, value); const id = this.put(value); this.rows.get(id)!.handoffArrivalEvent = structuredClone(handoff); return id;
  }
  getHandoffArrivalEvent(id: string): HandoffArrivalEvent | null { this.prune(); const row = returnToken(id) ? this.rows.get(id) : undefined; return row?.handoffArrivalEvent ? structuredClone(row.handoffArrivalEvent) : null; }
  putHandoffDestinationArrivalReturn(value: ReturnIntent, observation: HandoffDestinationArrivalReturn): string {
    validateHandoffDestinationArrivalReturn(observation, value); const id = this.putArrivalHandoffDestinationReturn(value, observation.handoff.observation);
    this.rows.get(id)!.handoffDestinationArrival = structuredClone(observation); return id;
  }
  getHandoffDestinationArrivalReturn(id: string): HandoffDestinationArrivalReturn | null { this.prune(); const row = returnToken(id) ? this.rows.get(id) : undefined; return row?.handoffDestinationArrival ? structuredClone(row.handoffDestinationArrival) : null; }
  putHandoffDestinationEvent(value: ReturnIntent, handoff: HandoffDestinationEvent): string {
    validateHandoffDestinationEvent(handoff, value); const id = this.put(value); this.rows.get(id)!.handoffDestinationEvent = structuredClone(handoff); return id;
  }
  getHandoffDestinationEvent(id: string): HandoffDestinationEvent | null { this.prune(); const row = returnToken(id) ? this.rows.get(id) : undefined; return row?.handoffDestinationEvent ? structuredClone(row.handoffDestinationEvent) : null; }
  putArrivalHandoffDestinationReturn(value: ReturnIntent, observation: ArrivalHandoffDestinationReturn): string {
    validateArrivalHandoffDestinationReturn(observation, value); const id = this.putCarriedDestinationArrivalReturn(value, observation.handoff.observation);
    this.rows.get(id)!.handoffDestination = structuredClone(observation); return id;
  }
  getArrivalHandoffDestinationReturn(id: string): ArrivalHandoffDestinationReturn | null { this.prune(); const row = returnToken(id) ? this.rows.get(id) : undefined; return row?.handoffDestination ? structuredClone(row.handoffDestination) : null; }
  putCarriedDestinationArrivalEvent(value: ReturnIntent, handoff: CarriedDestinationArrivalEventHandoff): string {
    validateCarriedDestinationArrivalEventHandoff(handoff, value); const id = this.put(value); this.rows.get(id)!.destinationArrivalEvent = structuredClone(handoff); return id;
  }
  getCarriedDestinationArrivalEvent(id: string): CarriedDestinationArrivalEventHandoff | null { this.prune(); const row = returnToken(id) ? this.rows.get(id) : undefined; return row?.destinationArrivalEvent ? structuredClone(row.destinationArrivalEvent) : null; }
  putCarriedDestinationArrivalReturn(value: ReturnIntent, observation: CarriedDestinationArrivalReturn): string {
    validateCarriedDestinationArrivalReturn(observation, value); const id = this.putCarriedDestinationReturn(value, observation.handoff.observation);
    this.rows.get(id)!.destinationArrival = structuredClone(observation); return id;
  }
  getCarriedDestinationArrivalReturn(id: string): CarriedDestinationArrivalReturn | null { this.prune(); const row = returnToken(id) ? this.rows.get(id) : undefined; return row?.destinationArrival ? structuredClone(row.destinationArrival) : null; }
  putCarriedDestinationEvent(value: ReturnIntent, handoff: CarriedDestinationEventHandoff): string { validateCarriedDestinationEventHandoff(handoff, value); const id = this.put(value); this.rows.get(id)!.carriedDestinationEvent = structuredClone(handoff); return id; }
  getCarriedDestinationEvent(id: string): CarriedDestinationEventHandoff | null { this.prune(); const row = returnToken(id) ? this.rows.get(id) : undefined; return row?.carriedDestinationEvent ? structuredClone(row.carriedDestinationEvent) : null; }
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
