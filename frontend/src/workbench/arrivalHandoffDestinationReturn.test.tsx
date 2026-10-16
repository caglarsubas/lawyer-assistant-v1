import { captureCarriedDestinationReturn, reconcileCarriedDestinationReturn } from './carriedDestinationReturn';
import { beforeAll, describe, expect, it, vi } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import type { NavigationMetadata, SourceTarget } from '../pages/sourceContextNavigationTypes';
import type { ReviewLineage, ReviewMetadata } from '../pages/sourceReviewLineageTypes';
import type { PortfolioQueuePage } from '../pages/portfolioSourceQueueTypes';
import { PortfolioReturnBook, PrincipalReturnBook, type ReturnIntent } from './portfolioReturn';
import type { ReviewPathHandoff } from './reviewPathHandoff';
import { captureComparisonReturn, reconcileComparisonReturn, type ComparisonReturnReceipt } from './comparisonReturn';

import { prepareComparisonEvent } from './comparisonEventHandoff';
import { captureArrivalReturn, reconcileArrivalReturn } from './arrivalReturn';
import { prepareArrivalEvent } from './arrivalEventHandoff';
import { prepareCarriedArrivalEvent } from './carriedArrivalEventHandoff';
import { captureCarriedArrivalReturn, reconcileCarriedArrivalReturn } from './carriedArrivalReturn';
import { prepareOnwardEvent } from './onwardEventHandoff';
import { captureOnwardReturn, reconcileOnwardReturn } from './onwardReturn';

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

const target = (): SourceTarget => ({ kind: 'selected', matter_id: 'm', analysis_id: 'a', context_id: ctx, review_id: id(2) });
const receipt = (h = snapshot(2), i = intent()): ComparisonReturnReceipt => captureComparisonReturn(i, handoff(), target(), h.context_navigation, h).receipt!;
const page = (h = snapshot(2)): PortfolioQueuePage => ({ recipe: 'private-portfolio-source-review-queue-v1', observed_at: h.observed_at, filters: structuredClone(intent().filters),
  items: [{ id: ctx, matter_id: 'm', analysis_id: 'a', matter_title: 'PRIVATE TITLE NOT RETAINED', recorded_at: stamp, state: 'inspection_required', version_id: 'frozen', product_id: 'p', manifest_sha256: 'd'.repeat(64),
    historical_review: structuredClone(h.context_navigation.historical_review), private_observation: { state: 'unchanged', reasons: [] }, source_verification: 'not_checked', legal_readiness: 'not_established' }],
  coverage: { scope: 'authorized_portfolio_window_only', scanned_count: 1, returned_count: 1, locked_matter_count: 1, has_more: false, next_offset: null, pagination_limit_reached: false, priority_scope: 'current_window_only', total_count: null, source_verification: 'not_checked' },
  legal_readiness: 'not_established', qualification_granted: false });
function unknown(h: ReviewLineage, kind: 'head' | 'version') {
  if (kind === 'head') { h.current_head = null; h.head_relationship = 'unestablished'; h.context_navigation.historical_review = { state: 'unknown', id: null, recorded_at: null }; h.context_navigation.admission.review_state = 'unknown'; }
  else { h.context_navigation.analysis.current_version_id = null; h.context_navigation.version_relation = 'unknown'; h.context_navigation.tools_available = false; h.tools_available = false; }
  return h;
}

function fixture() {
  const i = intent(), r = receipt(), h = snapshot(2, 10, 4);
  h.context_navigation.analysis = { id: 'a', current_version_id: 'queue-version', revision: 5 };
  h.observed_at = h.context_navigation.observed_at = '2026-10-15T02:00:00Z';
  const p = page(h), value = reconcileComparisonReturn(i, r, p, h.context_navigation, h); let calls = 0;
  const read = vi.fn(async (_url: string) => { const v = snapshot(2, 1, 4); v.context_navigation.analysis = structuredClone(h.context_navigation.analysis);
    v.observed_at = v.context_navigation.observed_at = `2026-10-15T02:00:0${++calls}Z`; return v; });
  return { i, r, h, p, value, read };
}
const prepare = (f = fixture()) => prepareComparisonEvent(f.i, f.r, f.value, f.read, () => true);
const arrival = () => { const h = snapshot(2, 10, 4); h.context_navigation.analysis = { id: 'a', current_version_id: 'queue-version', revision: 5 };
  h.observed_at = h.context_navigation.observed_at = '2026-10-15T02:01:00Z'; return h; };

async function onwardFixture(a = arrival()) {
  const initial = fixture(), originalHandoff = await prepare(initial);
  const o = captureArrivalReturn(initial.i, originalHandoff, target(), a.context_navigation, a).observation!;
  const q = destination(5); q.observed_at = q.context_navigation.observed_at = '2026-10-15T02:02:00Z';
  const value = reconcileArrivalReturn(initial.i, o, page(q), q.context_navigation, q); let n = 0;
  const read = vi.fn(async (_url: string) => { const h = destination(5, 1); h.observed_at = h.context_navigation.observed_at = `2026-10-15T02:02:0${++n}Z`; return h; });
  return { i: initial.i, o, q, value, read };
}
function destination(head = 5, window = 10) { const h = snapshot(2, window, head); h.context_navigation.analysis = { id: 'a', current_version_id: 'onward-version', revision: 6 };
  h.observed_at = h.context_navigation.observed_at = '2026-10-15T02:03:00Z'; return h; }
const onward = (f: Awaited<ReturnType<typeof onwardFixture>>) => prepareArrivalEvent(f.i, f.o, f.value, f.read, () => true);

async function retained(d = destination()) {
  const f = await onwardFixture(), h = await onward(f);
  const observation = captureOnwardReturn(f.i, h, target(), d.context_navigation, d).observation!;
  return { ...f, h, d, observation };
}
function fresh(head = 5) { const h = destination(head); h.observed_at = h.context_navigation.observed_at = '2026-10-15T02:04:00Z'; return h; }

async function carryFixture(d = destination()) {
  const initial=await retained(d),q=nextDestination(6);q.observed_at=q.context_navigation.observed_at='2026-10-15T02:04:00Z';
  const o=initial.observation,value=reconcileOnwardReturn(initial.i,o,page(q),q.context_navigation,q);let n=0;
  const read=vi.fn(async(_url:string)=>{const h=nextDestination(6,1);h.observed_at=h.context_navigation.observed_at=`2026-10-15T02:04:0${++n}Z`;return h;});
  return {i:initial.i,o,q,value,read};
}
function nextDestination(head=6,window=10){const h=fresh(head);h.lineage=snapshot(2,window,head).lineage;h.context_navigation.analysis={id:'a',current_version_id:'carry-version',revision:7};h.observed_at=h.context_navigation.observed_at='2026-10-15T02:05:00Z';return h;}
const carry=(f:Awaited<ReturnType<typeof carryFixture>>)=>prepareOnwardEvent(f.i,f.o,f.value,f.read,()=>true);

async function captured(d=nextDestination()) { const f=await carryFixture(),h=await carry(f),observation=captureCarriedArrivalReturn(f.i,h,target(),d.context_navigation,d).observation!;return {...f,h,d,observation}; }
function arrived(head=7,window=10){const h=nextDestination(head,window);h.context_navigation.analysis={id:'a',current_version_id:'carried-next-version',revision:8};h.observed_at=h.context_navigation.observed_at='2026-10-15T02:07:00Z';return h;}
async function carriedFixture(d=nextDestination()){
  const f=await captured(d),q=arrived();q.observed_at=q.context_navigation.observed_at='2026-10-15T02:06:00Z';
  const o=f.observation,value=reconcileCarriedArrivalReturn(f.i,o,page(q),q.context_navigation,q);let n=0;
  const read=vi.fn(async(_url:string)=>{const h=arrived(7,1);h.observed_at=h.context_navigation.observed_at=`2026-10-15T02:06:0${++n}Z`;return h;});
  return {i:f.i,o,q,value,read};
}
const navigate=(f:Awaited<ReturnType<typeof carriedFixture>>)=>prepareCarriedArrivalEvent(f.i,f.o,f.value,f.read,()=>true);
async function savedDestination(d=arrived()) { const f=await carriedFixture(),h=await navigate(f),observation=captureCarriedDestinationReturn(f.i,h,target(),d.context_navigation,d).observation!;return {i:f.i,h,d,observation}; }
function freshDestination(head=7){const h=arrived(head);h.observed_at=h.context_navigation.observed_at='2026-10-15T02:08:00Z';return h;}

import { prepareCarriedDestinationEvent } from './carriedDestinationEventHandoff';
async function destinationFixture(d=arrived()) {
  const f=await savedDestination(d),q=freshDestination(8);q.context_navigation.analysis={id:'a',current_version_id:'destination-queue',revision:9};
  const o=f.observation,value=reconcileCarriedDestinationReturn(f.i,o,page(q),q.context_navigation,q);let n=0;
  const read=vi.fn(async(_url:string)=>{const h=destinationArrival(8,1);h.observed_at=h.context_navigation.observed_at=`2026-10-15T02:08:0${++n}Z`;return h;});
  return {i:f.i,o,q,value,read};
}
function destinationArrival(head=8,window=10){const h=arrived(head,window);h.context_navigation.analysis={id:'a',current_version_id:'destination-queue',revision:9};h.observed_at=h.context_navigation.observed_at='2026-10-15T02:09:00Z';return h;}
const prepareDestination=(f:Awaited<ReturnType<typeof destinationFixture>>)=>prepareCarriedDestinationEvent(f.i,f.o,f.value,f.read,()=>true);

import { captureCarriedDestinationArrivalReturn, reconcileCarriedDestinationArrivalReturn } from './carriedDestinationArrivalReturn';
async function savedArrival(d=destinationArrival()) { const f=await destinationFixture(),h=await prepareDestination(f),observation=captureCarriedDestinationArrivalReturn(f.i,h,target(),d.context_navigation,d).observation!;return {i:f.i,h,d,observation}; }
function freshArrival(head=8){const h=destinationArrival(head);h.observed_at=h.context_navigation.observed_at='2026-10-15T02:10:00Z';return h;}

import { prepareCarriedDestinationArrivalEvent } from './carriedDestinationArrivalEventHandoff';
function rootReceipt(observation: Awaited<ReturnType<typeof savedArrival>>['observation']) {
  const d=observation.handoff.observation,c=d.handoff.observation,o=c.handoff.observation,a=o.handoff.observation;return a.handoff.receipt;
}
let originalEvent: { i: ReturnIntent; o: Awaited<ReturnType<typeof savedArrival>>['observation']; q: ReviewLineage; value: ReturnType<typeof reconcileCarriedDestinationArrivalReturn> };
beforeAll(async()=>{
  const f=await savedArrival(),q=freshArrival(10);q.context_navigation.analysis={id:'a',current_version_id:'arrival-event-queue',revision:11};
  originalEvent={i:f.i,o:f.observation,q,value:reconcileCarriedDestinationArrivalReturn(f.i,f.observation,page(q),q.context_navigation,q)};
});
async function arrivalEventFixture(d?: ReviewLineage) {
  const f=structuredClone(originalEvent);
  if(d){const previous=await prepareDestination(await destinationFixture());f.o=captureCarriedDestinationArrivalReturn(f.i,previous,target(),d.context_navigation,d).observation!;f.value=reconcileCarriedDestinationArrivalReturn(f.i,f.o,page(f.q),f.q.context_navigation,f.q);}
  let n=0;const read=vi.fn(async(_url:string)=>{const h=eventDestination(10,1);h.observed_at=h.context_navigation.observed_at=`2026-10-15T02:10:0${++n}Z`;return h;});
  return {...f,read};
}
function eventDestination(head=10,window=10){const h=destinationArrival(head,window);h.context_navigation.analysis={id:'a',current_version_id:'arrival-event-queue',revision:11};h.observed_at=h.context_navigation.observed_at='2026-10-15T02:11:00Z';return h;}
const prepareLatest=(f:Awaited<ReturnType<typeof arrivalEventFixture>>)=>prepareCarriedDestinationArrivalEvent(f.i,f.o,f.value,f.read,()=>true);
import { captureArrivalHandoffDestinationReturn, reconcileArrivalHandoffDestinationReturn, validateArrivalHandoffDestinationReturn, type ArrivalHandoffDestinationReturn } from './arrivalHandoffDestinationReturn';
import HandoffDestinationReturnPanel from '../pages/HandoffDestinationReturnPanel';
let baseline: { i: ReturnIntent; h: Awaited<ReturnType<typeof prepareLatest>>; d: ReviewLineage; o: ArrivalHandoffDestinationReturn };
beforeAll(async()=>{
  const f=await arrivalEventFixture(),h=await prepareLatest(f),d=eventDestination(11);d.context_navigation.analysis={id:'a',current_version_id:'separately-saved-destination',revision:12};
  baseline={i:f.i,h,d,o:captureArrivalHandoffDestinationReturn(f.i,h,target(),d.context_navigation,d).observation!};
});
const latestFixture=()=>structuredClone(baseline);
function queueDestination(head=12){const h=eventDestination(head);h.context_navigation.analysis={id:'a',current_version_id:'fresh-queue-version',revision:13};h.observed_at=h.context_navigation.observed_at='2026-10-15T02:12:00Z';return h;}
function observeLatest(f=latestFixture(),h=queueDestination(),p=page(h)){return reconcileArrivalHandoffDestinationReturn(f.i,f.o,p,h.context_navigation,h);}
describe('guarded handoff-destination return reconciliation',()=>{
  it('captures the actual destination separately with exact unchanged history, evidence and all filters',()=>{
    const f=latestFixture(),before=structuredClone(f);const next=captureArrivalHandoffDestinationReturn(f.i,f.h,target(),f.d.context_navigation,f.d);
    expect(next.intent).toEqual(f.i);expect(next.observation).toEqual(f.o);expect(next.observation!.handoff).toEqual(f.h);expect(next.observation!.destination.head!.id).toBe(id(11));expect(next.observation!.handoff.observation.arrival.head!.id).toBe(id(8));
    expect(Object.keys(next.observation!).sort()).toEqual(['destination','handoff','recipe']);for(const word of ['PRIVATE TITLE','lineage','source_body','note'])expect(JSON.stringify(next.observation)).not.toContain(word);
    next.observation!.destination.metadata.analysis.current_version_id='mutated';next.observation!.handoff.observation.arrival.selected.packet_sha256='e'.repeat(64);expect(f).toEqual(before);
  });
  it('returns selection only when both observations are unavailable, never substitutes old metadata',()=>{
    const f=latestFixture();expect(captureArrivalHandoffDestinationReturn(f.i,f.h,target(),null,null)).toEqual({intent:f.i,observation:null});
    expect(()=>captureArrivalHandoffDestinationReturn(f.i,f.h,target(),f.d.context_navigation,null)).toThrow();expect(()=>captureArrivalHandoffDestinationReturn(f.i,f.h,target(),null,f.d)).toThrow();
  });
  it.each(['matter_id','analysis_id','context_id','review_id','prepare'] as const)('closes redirected %s before an unavailable return',key=>{
    const f=latestFixture(),t={...target(),[key]:'other'};expect(()=>captureArrivalHandoffDestinationReturn(f.i,f.h,t,null,null)).toThrow();
  });
  it('rejects disagreement between independently supplied metadata and lineage',()=>{
    const f=latestFixture(),m=structuredClone(f.d.context_navigation);m.analysis.revision++;expect(()=>captureArrivalHandoffDestinationReturn(f.i,f.h,target(),m,f.d)).toThrow();
  });
  it.each(['customer_ids','date_field','date_from','date_to','source_date_from','source_date_to','bucket'] as const)('retains original %s exactly',key=>{
    const f=latestFixture();if(key==='customer_ids')f.i.filters.customer_ids=['B'];else if(key==='date_field')f.i.filters.date_field='updated_at';else if(key==='bucket')f.i.filters.bucket='action_required';else f.i.filters[key]='2021-02-02';
    expect(()=>validateArrivalHandoffDestinationReturn(f.o,f.i)).toThrow();
  });
  it.each(['recipe','extra','recursive','destination-extra','metadata-extra','analysis-extra','selected-extra','head-extra'] as const)('rejects strict-schema %s including undefined keys',kind=>{
    const f=latestFixture();if(kind==='recipe')Object.assign(f.o,{recipe:'private-onward-return-v1'});if(kind==='extra')Object.assign(f.o,{source_body:undefined});if(kind==='recursive')Object.assign(f.o.handoff,{observation:f.o});
    if(kind==='destination-extra')Object.assign(f.o.destination,{lineage:undefined});if(kind==='metadata-extra')Object.assign(f.o.destination.metadata,{body:undefined});if(kind==='analysis-extra')Object.assign(f.o.destination.metadata.analysis,{note:undefined});if(kind==='selected-extra')Object.assign(f.o.destination.selected,{notes:undefined});if(kind==='head-extra')Object.assign(f.o.destination.head!,{notes:undefined});
    expect(()=>validateArrivalHandoffDestinationReturn(f.o,f.i)).toThrow();
  });
  it.each(['matter','analysis','context','frozen','manifest','selected','selected-packet','head-packet','revision','time','prepared-extra'] as const)('rejects changed immutable %s pins or regressive destination',kind=>{
    const f=latestFixture(),v=f.o.destination,m=v.metadata;if(kind==='matter')m.matter_id='other';if(kind==='analysis')m.analysis_id='other';if(kind==='context')m.context_id=`sac-${'e'.repeat(20)}-${'b'.repeat(32)}`;
    if(kind==='frozen')m.context.version_id='other';if(kind==='manifest')m.context.manifest_sha256='e'.repeat(64);if(kind==='selected')v.selected.id=id(1);if(kind==='selected-packet')v.selected.packet_sha256='e'.repeat(64);
    if(kind==='head-packet'){v.head=row(10);m.historical_review={id:id(10),state:row(10).state,recorded_at:stamp};v.head.packet_sha256='e'.repeat(64);}if(kind==='revision')m.analysis.revision=10;if(kind==='time')m.observed_at='2026-10-15T02:10:01Z';if(kind==='prepared-extra')Object.assign(f.o.handoff.prepared.metadata.analysis,{source_body:undefined});
    expect(()=>validateArrivalHandoffDestinationReturn(f.o,f.i)).toThrow();
  });
  it('compares new destination independently while preserving all original comparisons',()=>{
    const f=latestFixture(),before=structuredClone(f),fresh=queueDestination();const value=observeLatest(f,fresh);expect(value.state).toBe('observed');if(value.state!=='observed')throw Error();
    expect([value.head_relation,value.version_relation,value.revision_relation]).toEqual(['different','different','different']);const original=reconcileCarriedDestinationArrivalReturn(f.i,f.h.observation,page(fresh),fresh.context_navigation,fresh);expect(original.state).toBe('observed');
    const same=structuredClone(f.d);same.observed_at=same.context_navigation.observed_at='2026-10-15T02:12:00Z';const unchanged=observeLatest(f,same);if(unchanged.state!=='observed')throw Error();expect([unchanged.head_relation,unchanged.version_relation,unchanged.revision_relation]).toEqual(['same','same','same']);expect(f).toEqual(before);
    value.fresh.selected.packet_sha256='e'.repeat(64);expect(f).toEqual(before);
  });
  it.each([3,4,5,6,7,8,10,11])('checks same-head packet %s even when known only in earlier history or this destination',head=>{
    const f=latestFixture(),h=queueDestination(head);h.current_head!.packet_sha256='e'.repeat(64);expect(()=>observeLatest(f,h)).toThrow();
  });
  it.each(['queue-before-destination','metadata-before-queue','revision','queue-event-conflict','selected-packet','filters','offset','unexpected-read'] as const)('closes invalid fresh %s without a saved fallback',kind=>{
    const f=latestFixture(),h=queueDestination(),p=page(h);if(kind==='queue-before-destination')p.observed_at='2026-10-15T02:10:59Z';if(kind==='metadata-before-queue')p.observed_at='2026-10-15T02:12:01Z';if(kind==='revision')h.context_navigation.analysis.revision=11;
    if(kind==='queue-event-conflict')p.items[0].historical_review={id:id(13),state:row(13).state,recorded_at:stamp};if(kind==='selected-packet'){h.selected_review.packet_sha256='e'.repeat(64);h.lineage.items[0].packet_sha256='e'.repeat(64);}if(kind==='filters')p.filters.customer_ids=['B'];if(kind==='offset')p.coverage.scanned_count=-1;
    if(kind==='unexpected-read'){p.items=[];p.coverage.returned_count=0;}expect(()=>observeLatest(f,h,p)).toThrow();
  });
  it('reports only generic omission and rejects missing exact metadata for containing windows',()=>{
    const f=latestFixture(),p=page(queueDestination());p.items=[];p.coverage.returned_count=0;
    expect(reconcileArrivalHandoffDestinationReturn(f.i,f.o,p,null,null)).toEqual({state:'not_observed',queue_observed_at:p.observed_at});
    expect(()=>reconcileArrivalHandoffDestinationReturn(f.i,f.o,page(queueDestination()),null,null)).toThrow();
    const html=renderToStaticMarkup(<HandoffDestinationReturnPanel observation={f.o} value={{state:'not_observed',queue_observed_at:p.observed_at}}/>);expect(html).toContain('ayrıntıları açılmadı');for(const ident of [ctx,id(11),'separately-saved-destination','frozen'])expect(html).not.toContain(ident);
  });
  it('preserves saved unknowns and pending admissions without approval or inference',()=>{
    const f=latestFixture(),d=unknown(unknown(structuredClone(f.d),'head'),'version');d.selected_review.admission=d.lineage.items[0].admission='pending';d.context_navigation.admission.context_state='pending';
    f.o=captureArrivalHandoffDestinationReturn(f.i,f.h,target(),d.context_navigation,d).observation!;const value=observeLatest(f);if(value.state!=='observed')throw Error();expect(value.head_relation).toBe('unknown');expect(value.version_relation).toBe('unknown');expect(f.o.destination.selected.admission).toBe('pending');
    const h=unknown(unknown(queueDestination(),'head'),'version'),fresh=observeLatest(latestFixture(),h);if(fresh.state!=='observed')throw Error();expect(fresh.head_relation).toBe('unknown');expect(fresh.version_relation).toBe('unknown');
  });
  it('rejects invented queue flags and complete-purpose fields on every independent call',()=>{
    const f=latestFixture();f.o.handoff.queue.head_relation='same';expect(()=>validateArrivalHandoffDestinationReturn(f.o,f.i)).toThrow();expect(()=>observeLatest(f)).toThrow();
    const g=latestFixture();validateArrivalHandoffDestinationReturn(g.o,g.i);g.o.destination.selected.packet_sha256='e'.repeat(64);expect(()=>validateArrivalHandoffDestinationReturn(g.o,g.i)).toThrow();expect(()=>observeLatest(g)).toThrow();
  });
  it('validates before nonce or eviction, clones all projections in one row and keeps original return purpose separate',()=>{
    const f=latestFixture();let now=0,n=0;const nonce=vi.fn(()=>String(++n).padStart(32,'a')),book=new PortfolioReturnBook(()=>now,nonce);const token=book.putArrivalHandoffDestinationReturn(f.i,f.o);
    expect(nonce).toHaveBeenCalledTimes(1);expect(book.get(token)).toEqual(f.i);expect(book.getCarriedDestinationArrivalReturn(token)).toEqual(f.h.observation);expect(book.getCarriedDestinationReturn(token)).toEqual(f.h.observation.handoff.observation);expect(book.getCarriedArrivalReturn(token)).toEqual(f.h.observation.handoff.observation.handoff.observation);
    expect(book.getOnwardReturn(token)).toEqual(f.h.observation.handoff.observation.handoff.observation.handoff.observation);expect(book.getComparisonReturn(token)).toEqual(rootReceipt(f.h.observation));expect(book.getCarriedDestinationArrivalEvent(token)).toBeNull();expect(book.getReviewPath(token)).toBeNull();
    const saved=structuredClone(f.o);f.o.destination.selected.packet_sha256='e'.repeat(64);const read=book.getArrivalHandoffDestinationReturn(token)!;read.handoff.observation.arrival.metadata.analysis.current_version_id='mutated';expect(book.getArrivalHandoffDestinationReturn(token)).toEqual(saved);
    for(let i=0;i<7;i++)book.put(f.i);expect(()=>book.putArrivalHandoffDestinationReturn(f.i,f.o)).toThrow();expect(nonce).toHaveBeenCalledTimes(8);expect(book.getArrivalHandoffDestinationReturn(token)).toEqual(saved);book.put(f.i);expect(book.getArrivalHandoffDestinationReturn(token)).toBeNull();
    const latest=book.putArrivalHandoffDestinationReturn(f.i,saved);now=30*60*1000;expect(book.getArrivalHandoffDestinationReturn(latest)).toBeNull();expect(new PortfolioReturnBook().getArrivalHandoffDestinationReturn(latest)).toBeNull();
  });
  it('closes private receipts on principal change and reload',()=>{
    const f=latestFixture(),book=new PrincipalReturnBook();const first=book.forPrincipal('firm:one'),token=first.putArrivalHandoffDestinationReturn(f.i,f.o);expect(book.forPrincipal('firm:two').getArrivalHandoffDestinationReturn(token)).toBeNull();expect(book.forPrincipal('firm:one').getArrivalHandoffDestinationReturn(token)).toBeNull();
  });
  it('renders metadata only with independent preparation/destination/arrival comparisons and no weaker action',()=>{
    const f=latestFixture(),value=observeLatest(f);const html=renderToStaticMarkup(<HandoffDestinationReturnPanel observation={f.o} value={value}/>);
    for(const word of ['Geçiş hedefinden yeni kuyruğa','Ayrı saklanan geçiş hedefi','Geçiş hazırlığı','Korunan hedef varışı','separately-saved-destination','fresh-queue-version','frozen',id(11)])expect(html).toContain(word);
    for(const word of ['<button','<a ','PRIVATE TITLE','source-passage-text','qualification_granted'])expect(html).not.toContain(word);
  });
});
