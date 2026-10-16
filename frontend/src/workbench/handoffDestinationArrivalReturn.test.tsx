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
import { captureArrivalHandoffDestinationReturn, reconcileArrivalHandoffDestinationReturn, type ArrivalHandoffDestinationReturn } from './arrivalHandoffDestinationReturn';
let baseline: { i: ReturnIntent; h: Awaited<ReturnType<typeof prepareLatest>>; d: ReviewLineage; o: ArrivalHandoffDestinationReturn };
beforeAll(async()=>{
  const f=await arrivalEventFixture(),h=await prepareLatest(f),d=eventDestination(11);d.context_navigation.analysis={id:'a',current_version_id:'separately-saved-destination',revision:12};
  baseline={i:f.i,h,d,o:captureArrivalHandoffDestinationReturn(f.i,h,target(),d.context_navigation,d).observation!};
});
const latestFixture=()=>structuredClone(baseline);
function queueDestination(head=12){const h=eventDestination(head);h.context_navigation.analysis={id:'a',current_version_id:'fresh-queue-version',revision:13};h.observed_at=h.context_navigation.observed_at='2026-10-15T02:12:00Z';return h;}
import { prepareHandoffDestinationEvent } from './handoffDestinationEvent';
let nextBaseline: {i: ReturnIntent; o: ArrivalHandoffDestinationReturn; q: ReviewLineage; value: ReturnType<typeof reconcileArrivalHandoffDestinationReturn>};
beforeAll(()=>{const f=latestFixture(),q=queueDestination();nextBaseline={i:f.i,o:f.o,q,value:reconcileArrivalHandoffDestinationReturn(f.i,f.o,page(q),q.context_navigation,q)};});
function nextDestinationEvent(head=12,window=10){const h=queueDestination(head);h.lineage=snapshot(2,window,head).lineage;return h;}
async function eventFixture(saved?:ReviewLineage){
  const f=structuredClone(nextBaseline);if(saved){f.o=captureArrivalHandoffDestinationReturn(f.i,baseline.h,target(),saved.context_navigation,saved).observation!;f.value=reconcileArrivalHandoffDestinationReturn(f.i,f.o,page(f.q),f.q.context_navigation,f.q);}
  let n=0;const read=vi.fn(async(_url:string)=>{const h=nextDestinationEvent(12,1);h.observed_at=h.context_navigation.observed_at=`2026-10-15T02:12:0${++n}Z`;return h;});return {...f,read};
}
const prepareNewest=(f:Awaited<ReturnType<typeof eventFixture>>)=>prepareHandoffDestinationEvent(f.i,f.o,f.value,f.read,()=>true);
function actualDestination(head=13){const h=nextDestinationEvent(head);h.context_navigation.analysis={id:'a',current_version_id:'later-handoff-destination',revision:14};h.observed_at=h.context_navigation.observed_at='2026-10-15T02:13:00Z';return h;}
import { captureHandoffDestinationArrivalReturn, reconcileHandoffDestinationArrivalReturn, validateHandoffDestinationArrivalReturn, type HandoffDestinationArrivalReturn } from './handoffDestinationArrivalReturn';
import HandoffDestinationArrivalReturnPanel from '../pages/HandoffDestinationArrivalReturnPanel';
let newest: {i:ReturnIntent; h:Awaited<ReturnType<typeof prepareNewest>>; d:ReviewLineage; o:HandoffDestinationArrivalReturn};
beforeAll(async()=>{const f=await eventFixture(),h=await prepareNewest(f),d=actualDestination();newest={i:f.i,h,d,o:captureHandoffDestinationArrivalReturn(f.i,h,target(),d.context_navigation,d).observation!};});
const saved=()=>structuredClone(newest);
function finalDestination(head=14){const h=actualDestination(head);h.context_navigation.analysis={id:'a',current_version_id:'fresh-final-queue',revision:15};h.observed_at=h.context_navigation.observed_at='2026-10-15T02:14:00Z';return h;}
function observe(f=saved(),h=finalDestination(),p=page(h)){return reconcileHandoffDestinationArrivalReturn(f.i,f.o,p,h.context_navigation,h);}
function snapshots(o:HandoffDestinationArrivalReturn){
  const latest=o.handoff,purpose=latest.observation.handoff,a=purpose.observation,d=a.handoff.observation,h=d.handoff,c=h.observation,o2=c.handoff.observation,old=o2.handoff.observation,r=old.handoff.receipt;
  return [r.destination,old.arrival,o2.handoff.queue.fresh,o2.handoff.prepared,o2.destination,c.handoff.queue.fresh,c.handoff.prepared,c.arrival,h.queue.fresh,h.prepared,d.destination,a.handoff.queue.fresh,a.handoff.prepared,a.arrival,purpose.queue.fresh,purpose.prepared,latest.observation.destination,latest.queue.fresh,latest.prepared];
}
describe('guarded handoff-destination-arrival return reconciliation',()=>{
  it('captures one separate metadata arrival and retains the complete handoff and exact original intent unchanged',()=>{
    const f=saved(),next=captureHandoffDestinationArrivalReturn(f.i,f.h,target(),f.d.context_navigation,f.d);expect(next).toEqual({intent:f.i,observation:f.o});expect(Object.keys(f.o).sort()).toEqual(['arrival','handoff','recipe']);
    expect(f.o.handoff.observation.destination.head?.id).toBe(id(11));expect(f.o.handoff.prepared.head?.id).toBe(id(12));expect(f.o.arrival.head?.id).toBe(id(13));
    for(const word of ['lineage','PRIVATE TITLE','source_body','note'])expect(JSON.stringify(next)).not.toContain(word);
    next.observation!.arrival.selected.packet_sha256='e'.repeat(64);next.observation!.handoff.observation.destination.metadata.analysis.current_version_id='mutated';expect(f).toEqual(saved());
  });
  it('returns selection only for both unavailable observations, rejects partial/conflicting observations',()=>{
    const f=saved();expect(captureHandoffDestinationArrivalReturn(f.i,f.h,target(),null,null)).toEqual({intent:f.i,observation:null});
    expect(()=>captureHandoffDestinationArrivalReturn(f.i,f.h,target(),f.d.context_navigation,null)).toThrow();expect(()=>captureHandoffDestinationArrivalReturn(f.i,f.h,target(),null,f.d)).toThrow();const m=structuredClone(f.d.context_navigation);m.analysis.revision++;expect(()=>captureHandoffDestinationArrivalReturn(f.i,f.h,target(),m,f.d)).toThrow();
  });
  it.each(['kind','matter_id','analysis_id','context_id','review_id'] as const)('rejects redirected %s even with unavailable metadata',key=>{
    const f=saved();expect(()=>captureHandoffDestinationArrivalReturn(f.i,f.h,{...target(),[key]:'other'},null,null)).toThrow();
  });
  it.each(['customer_ids','date_field','date_from','date_to','source_date_from','source_date_to','bucket'] as const)('binds exact original %s before allocation',key=>{
    const f=saved(),nonce=vi.fn(()=>'a'.repeat(32)),b=new PortfolioReturnBook(()=>0,nonce);if(key==='customer_ids')f.i.filters.customer_ids=['B'];else if(key==='date_field')f.i.filters.date_field='updated_at';else if(key==='bucket')f.i.filters.bucket='action_required';else f.i.filters[key]='2021-02-02';expect(()=>b.putHandoffDestinationArrivalReturn(f.i,f.o)).toThrow();expect(nonce).not.toHaveBeenCalled();
  });
  it.each(['recipe','extra','recursive','arrival-extra','analysis-extra','selected','manifest','version','queue','times','time','revision'] as const)('rejects %s at both validation and fresh reconciliation',kind=>{
    const f=saved();if(kind==='recipe')Object.assign(f.o,{recipe:'private-arrival-return-v1'});if(kind==='extra')Object.assign(f.o,{note:undefined});if(kind==='recursive')Object.assign(f.o,{previous:f.o});if(kind==='arrival-extra')Object.assign(f.o.arrival,{lineage:undefined});if(kind==='analysis-extra')Object.assign(f.o.arrival.metadata.analysis,{note:undefined});if(kind==='selected')f.o.arrival.selected.packet_sha256='e'.repeat(64);if(kind==='manifest')f.o.arrival.metadata.context.manifest_sha256='e'.repeat(64);if(kind==='version')f.o.arrival.metadata.context.version_id='other';if(kind==='queue')f.o.handoff.queue.head_relation='same';if(kind==='times')f.o.handoff.observed_at.reverse();if(kind==='time')f.o.arrival.metadata.observed_at=stamp;if(kind==='revision')f.o.arrival.metadata.analysis.revision=2;
    expect(()=>validateHandoffDestinationArrivalReturn(f.o,f.i)).toThrow();expect(()=>observe(f)).toThrow();
  });
  it.each(Array.from({length:19},(_,i)=>i))('rejects a changed selected packet in retained observation %s',n=>{
    const f=saved();snapshots(f.o)[n].selected.packet_sha256='e'.repeat(64);expect(()=>validateHandoffDestinationArrivalReturn(f.o,f.i)).toThrow();expect(()=>observe(f)).toThrow();
  });
  it.each([3,4,5,6,7,8,10,11,12,13])('checks known head %s including newly saved arrival-only packets',head=>{
    const f=saved(),h=finalDestination(head);h.current_head!.packet_sha256='e'.repeat(64);expect(()=>observe(f,h)).toThrow();
  });
  it('compares arrival independently without changing older destination, preparation or relation flags',()=>{
    const f=saved(),before=structuredClone(f),h=finalDestination(),value=observe(f,h),old=reconcileArrivalHandoffDestinationReturn(f.i,f.o.handoff.observation,page(h),h.context_navigation,h);
    expect(value.state).toBe('observed');if(value.state!=='observed'||old.state!=='observed')throw Error();expect([value.head_relation,value.version_relation,value.revision_relation]).toEqual(['different','different','different']);
    expect({...value,head_relation:old.head_relation,version_relation:old.version_relation,revision_relation:old.revision_relation}).toEqual(old);expect(f).toEqual(before);value.fresh.selected.packet_sha256='e'.repeat(64);expect(f).toEqual(before);
    const same=observe(f,structuredClone(f.d));if(same.state!=='observed')throw Error();expect([same.head_relation,same.version_relation,same.revision_relation]).toEqual(['same','same','same']);
  });
  it.each(['queue-head','packet','filters','page-time','event-time','revision','unexpected-read','offset'] as const)('fails closed on fresh %s',kind=>{
    const f=saved(),h=finalDestination(),p=page(h);if(kind==='queue-head')p.items[0].historical_review.id=id(15);if(kind==='packet'){h.selected_review.packet_sha256=h.lineage.items[0].packet_sha256='e'.repeat(64);}if(kind==='filters')p.filters.customer_ids=['B'];if(kind==='page-time')p.observed_at=stamp;if(kind==='event-time')h.observed_at=h.context_navigation.observed_at=stamp;if(kind==='revision')h.context_navigation.analysis.revision=2;if(kind==='unexpected-read'){p.items=[];p.coverage.returned_count=0;}if(kind==='offset')p.coverage.scanned_count=-1;expect(()=>observe(f,h,p)).toThrow();
  });
  it('omission is generic, requires no target metadata and never reveals saved identities',()=>{
    const f=saved(),p=page(finalDestination());p.items=[];p.coverage.returned_count=0;const value=reconcileHandoffDestinationArrivalReturn(f.i,f.o,p,null,null);expect(value).toEqual({state:'not_observed',queue_observed_at:p.observed_at});expect(()=>reconcileHandoffDestinationArrivalReturn(f.i,f.o,page(finalDestination()),null,null)).toThrow();
    const html=renderToStaticMarkup(<HandoffDestinationArrivalReturnPanel observation={f.o} value={value}/>);expect(html).toContain('ayrıntıları açılmadı');for(const word of [ctx,id(13),'frozen','later-handoff-destination'])expect(html).not.toContain(word);
  });
  it('preserves unknown/pending saved and fresh admissions with no permission or approval inference',()=>{
    const f=saved(),d=unknown(unknown(structuredClone(f.d),'head'),'version');d.selected_review.admission=d.lineage.items[0].admission='pending';d.context_navigation.admission.context_state='pending';f.o=captureHandoffDestinationArrivalReturn(f.i,f.h,target(),d.context_navigation,d).observation!;
    const value=observe(f);if(value.state!=='observed')throw Error();expect(value.head_relation).toBe('unknown');expect(value.version_relation).toBe('unknown');expect(f.o.arrival.selected.admission).toBe('pending');const v=observe(saved(),unknown(unknown(finalDestination(),'head'),'version'));if(v.state!=='observed')throw Error();expect(v.head_relation).toBe('unknown');expect(v.version_relation).toBe('unknown');
  });
  it('validates every public call after an earlier success; no persistent verdict',()=>{
    const f=saved();validateHandoffDestinationArrivalReturn(f.o,f.i);f.o.arrival.selected.packet_sha256='e'.repeat(64);expect(()=>validateHandoffDestinationArrivalReturn(f.o,f.i)).toThrow();expect(()=>observe(f)).toThrow();expect(()=>captureHandoffDestinationArrivalReturn(f.i,f.o.handoff,target(),null,null)).not.toThrow();
  });
  it('stores one row, clones all earlier projections and validates before nonce or eviction',()=>{
    const f=saved();let now=0,n=0;const nonce=vi.fn(()=>String(++n).padStart(32,'a')),book=new PortfolioReturnBook(()=>now,nonce),token=book.putHandoffDestinationArrivalReturn(f.i,f.o);expect(nonce).toHaveBeenCalledTimes(1);expect(book.get(token)).toEqual(f.i);expect(book.getHandoffDestinationArrivalReturn(token)).toEqual(f.o);expect(book.getArrivalHandoffDestinationReturn(token)).toEqual(f.h.observation);expect(book.getCarriedDestinationArrivalReturn(token)).toEqual(f.h.observation.handoff.observation);expect(book.getCarriedDestinationReturn(token)).toEqual(f.h.observation.handoff.observation.handoff.observation);
    expect(book.getCarriedArrivalReturn(token)).toEqual(f.h.observation.handoff.observation.handoff.observation.handoff.observation);expect(book.getOnwardReturn(token)).toEqual(f.h.observation.handoff.observation.handoff.observation.handoff.observation.handoff.observation);expect(book.getArrivalReturn(token)).not.toBeNull();expect(book.getComparisonReturn(token)).not.toBeNull();expect(book.getHandoffDestinationEvent(token)).toBeNull();expect(book.getReviewPath(token)).toBeNull();
    const original=structuredClone(f.o);f.o.arrival.selected.packet_sha256='e'.repeat(64);book.getHandoffDestinationArrivalReturn(token)!.handoff.prepared.selected.packet_sha256='e'.repeat(64);expect(book.getHandoffDestinationArrivalReturn(token)).toEqual(original);for(let i=0;i<7;i++)book.put(f.i);expect(()=>book.putHandoffDestinationArrivalReturn(f.i,f.o)).toThrow();expect(nonce).toHaveBeenCalledTimes(8);expect(book.getHandoffDestinationArrivalReturn(token)).toEqual(original);book.put(f.i);expect(book.getHandoffDestinationArrivalReturn(token)).toBeNull();const latest=book.putHandoffDestinationArrivalReturn(f.i,original);now=30*60*1000;expect(book.getHandoffDestinationArrivalReturn(latest)).toBeNull();expect(new PortfolioReturnBook().getHandoffDestinationArrivalReturn(latest)).toBeNull();
    const principal=new PrincipalReturnBook(),old=principal.forPrincipal('firm:one'),key=old.putHandoffDestinationArrivalReturn(f.i,original);expect(principal.forPrincipal('firm:two').getHandoffDestinationArrivalReturn(key)).toBeNull();expect(principal.forPrincipal('firm:one').getHandoffDestinationArrivalReturn(key)).toBeNull();
  });
  it('renders independent metadata comparisons and withholds every weaker action',()=>{
    const f=saved(),html=renderToStaticMarkup(<HandoffDestinationArrivalReturnPanel observation={f.o} value={observe(f)}/>);for(const word of ['Geçiş varışından yeni kuyruğa','Ayrı saklanan geçiş varışı','Korunan geçiş hedefi','Yeni geçiş hazırlığı','fresh-final-queue','later-handoff-destination','frozen',id(11),id(12),id(13)])expect(html).toContain(word);for(const word of ['<button','<a ','PRIVATE TITLE','source-passage-text','qualification_granted'])expect(html).not.toContain(word);
  });
  it('clones the older handoff baseline before awaited callbacks mutate caller-owned history and filters',async()=>{
    const f=await destinationFixture(),original=structuredClone(f.o),read=f.read.getMockImplementation()!;f.read.mockImplementation(async u=>{f.i.filters.customer_ids=['B'];f.o.destination.selected.packet_sha256='e'.repeat(64);return read(u);});const h=await prepareDestination(f);expect(h.observation).toEqual(original);
    const c=await carriedFixture(),before=structuredClone(c.o),read2=c.read.getMockImplementation()!;c.read.mockImplementation(async u=>{c.i.filters.customer_ids=['B'];c.o.arrival.selected.packet_sha256='e'.repeat(64);return read2(u);});expect((await navigate(c)).observation).toEqual(before);
  });
});
