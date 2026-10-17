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
import { captureHandoffDestinationArrivalReturn, reconcileHandoffDestinationArrivalReturn, type HandoffDestinationArrivalReturn } from './handoffDestinationArrivalReturn';
import { prepareHandoffArrivalEvent } from './handoffArrivalEvent';
let latestBaseline:{i:ReturnIntent; h:Awaited<ReturnType<typeof prepareNewest>>; d:ReviewLineage; o:HandoffDestinationArrivalReturn; q:ReviewLineage; value:ReturnType<typeof reconcileHandoffDestinationArrivalReturn>};
beforeAll(async()=>{const f=await eventFixture(),h=await prepareNewest(f),d=actualDestination(),o=captureHandoffDestinationArrivalReturn(f.i,h,target(),d.context_navigation,d).observation!,q=latestQueue();latestBaseline={i:f.i,h,d,o,q,value:reconcileHandoffDestinationArrivalReturn(f.i,o,page(q),q.context_navigation,q)};});
function latestQueue(head=14,window=10){const h=actualDestination(head);h.lineage=snapshot(2,window,head).lineage;h.context_navigation.analysis={id:'a',current_version_id:'latest-arrival-queue',revision:15};h.observed_at=h.context_navigation.observed_at='2026-10-15T02:14:00Z';return h;}
async function newEventFixture(saved?:ReviewLineage){const f=structuredClone(latestBaseline);if(saved){f.o=captureHandoffDestinationArrivalReturn(f.i,f.h,target(),saved.context_navigation,saved).observation!;f.value=reconcileHandoffDestinationArrivalReturn(f.i,f.o,page(f.q),f.q.context_navigation,f.q);}let n=0;const read=vi.fn(async(_url:string)=>{const h=latestQueue(14,1);h.observed_at=h.context_navigation.observed_at=`2026-10-15T02:14:0${++n}Z`;return h;});return {...f,read};}
const prepareFinal=(f:Awaited<ReturnType<typeof newEventFixture>>)=>prepareHandoffArrivalEvent(f.i,f.o,f.value,f.read,()=>true);
function finalDestination(head=15){const h=latestQueue(head);h.context_navigation.analysis={id:'a',current_version_id:'latest-arrival-destination',revision:16};h.observed_at=h.context_navigation.observed_at='2026-10-15T02:15:00Z';return h;}
function retainedSnapshots(o:HandoffDestinationArrivalReturn){const newest=o.handoff,saved=newest.observation,purpose=saved.handoff,a=purpose.observation,d=a.handoff.observation,h=d.handoff,c=h.observation,o2=c.handoff.observation,old=o2.handoff.observation,r=old.handoff.receipt;return [r.destination,old.arrival,o2.handoff.queue.fresh,o2.handoff.prepared,o2.destination,c.handoff.queue.fresh,c.handoff.prepared,c.arrival,h.queue.fresh,h.prepared,d.destination,a.handoff.queue.fresh,a.handoff.prepared,a.arrival,purpose.queue.fresh,purpose.prepared,saved.destination,newest.queue.fresh,newest.prepared,o.arrival];}

import { captureHandoffArrivalDestinationReturn, reconcileHandoffArrivalDestinationReturn, type HandoffArrivalDestinationReturn } from './handoffArrivalDestinationReturn';
import { prepareHandoffArrivalDestinationEvent } from './handoffArrivalDestinationEvent';
let newBaseline:{i:ReturnIntent;h:Awaited<ReturnType<typeof prepareFinal>>;d:ReviewLineage;o:HandoffArrivalDestinationReturn;q:ReviewLineage;value:ReturnType<typeof reconcileHandoffArrivalDestinationReturn>};
beforeAll(async()=>{const f=await newEventFixture(),h=await prepareFinal(f),d=finalDestination(),o=captureHandoffArrivalDestinationReturn(f.i,h,target(),d.context_navigation,d).observation!,q=newQueue();newBaseline={i:f.i,h,d,o,q,value:reconcileHandoffArrivalDestinationReturn(f.i,o,page(q),q.context_navigation,q)};});
function newQueue(head=16,window=10){const h=finalDestination(head);h.lineage=snapshot(2,window,head).lineage;h.context_navigation.analysis={id:'a',current_version_id:'destination-event-queue',revision:17};h.observed_at=h.context_navigation.observed_at='2026-10-15T02:16:00Z';return h;}
async function destinationEventFixture(saved?:ReviewLineage){const f=structuredClone(newBaseline);if(saved){f.o=captureHandoffArrivalDestinationReturn(f.i,f.h,target(),saved.context_navigation,saved).observation!;f.value=reconcileHandoffArrivalDestinationReturn(f.i,f.o,page(f.q),f.q.context_navigation,f.q);}let n=0;const read=vi.fn(async(_url:string)=>{const h=newQueue(16,1);h.observed_at=h.context_navigation.observed_at=`2026-10-15T02:16:0${++n}Z`;return h;});return {...f,read};}
const prepareDestinationFinal=(f:Awaited<ReturnType<typeof destinationEventFixture>>)=>prepareHandoffArrivalDestinationEvent(f.i,f.o,f.value,f.read,()=>true);
function newFinalDestination(head=17){const h=newQueue(head);h.context_navigation.analysis={id:'a',current_version_id:'destination-event-arrival',revision:18};h.observed_at=h.context_navigation.observed_at='2026-10-15T02:17:00Z';return h;}
function newRetainedSnapshots(o:HandoffArrivalDestinationReturn){return [...retainedSnapshots(o.handoff.observation),o.handoff.queue.fresh,o.handoff.prepared,o.destination];}

import { captureHandoffArrivalDestinationArrivalReturn, reconcileHandoffArrivalDestinationArrivalReturn, type HandoffArrivalDestinationArrivalReturn } from './handoffArrivalDestinationArrivalReturn';
let returnBaseline:{i:ReturnIntent;h:Awaited<ReturnType<typeof prepareDestinationFinal>>;d:ReviewLineage;o:HandoffArrivalDestinationArrivalReturn};
beforeAll(async()=>{const f=await destinationEventFixture(),h=await prepareDestinationFinal(f),d=newFinalDestination();returnBaseline={i:f.i,h,d,o:captureHandoffArrivalDestinationArrivalReturn(f.i,h,target(),d.context_navigation,d).observation!};});
const savedReturn=()=>structuredClone(returnBaseline);
function freshReturn(head=18){const h=newFinalDestination(head);h.context_navigation.analysis={id:'a',current_version_id:'fresh-destination-arrival-return-queue',revision:19};h.observed_at=h.context_navigation.observed_at='2026-10-15T02:18:00Z';return h;}
import { prepareHandoffArrivalDestinationArrivalEvent } from './handoffArrivalDestinationArrivalEvent';
let arrivalEventBaseline:{i:ReturnIntent;o:HandoffArrivalDestinationArrivalReturn;q:ReviewLineage;value:ReturnType<typeof reconcileHandoffArrivalDestinationArrivalReturn>};
beforeAll(()=>{const f=savedReturn(),q=freshReturn();arrivalEventBaseline={i:f.i,o:f.o,q,value:reconcileHandoffArrivalDestinationArrivalReturn(f.i,f.o,page(q),q.context_navigation,q)};});
async function newestEventFixture(saved?:ReviewLineage){const f=structuredClone(arrivalEventBaseline);if(saved){f.o=captureHandoffArrivalDestinationArrivalReturn(f.i,returnBaseline.h,target(),saved.context_navigation,saved).observation!;f.value=reconcileHandoffArrivalDestinationArrivalReturn(f.i,f.o,page(f.q),f.q.context_navigation,f.q);}let n=0;const read=vi.fn(async(_url:string)=>{const h=freshReturn();h.lineage=snapshot(2,1,18).lineage;h.observed_at=h.context_navigation.observed_at=`2026-10-15T02:18:0${++n}Z`;return h;});return {...f,read};}
const prepareCurrent=(f:Awaited<ReturnType<typeof newestEventFixture>>)=>prepareHandoffArrivalDestinationArrivalEvent(f.i,f.o,f.value,f.read,()=>true);
function currentDestination(head=19){const h=freshReturn(head);h.context_navigation.analysis={id:'a',current_version_id:'new-arrival-preserving-destination',revision:20};h.observed_at=h.context_navigation.observed_at='2026-10-15T02:19:00Z';return h;}
function currentPins(o:HandoffArrivalDestinationArrivalReturn){return [...newRetainedSnapshots(o.handoff.observation),o.handoff.queue.fresh,o.handoff.prepared,o.arrival];}
import { captureHandoffArrivalDestinationArrivalDestinationReturn, reconcileHandoffArrivalDestinationArrivalDestinationReturn, type HandoffArrivalDestinationArrivalDestinationReturn } from './handoffArrivalDestinationArrivalDestinationReturn';
let destinationReturnBaseline:{i:ReturnIntent;h:Awaited<ReturnType<typeof prepareCurrent>>;d:ReviewLineage;o:HandoffArrivalDestinationArrivalDestinationReturn};
beforeAll(async()=>{const f=await newestEventFixture(),h=await prepareCurrent(f),d=currentDestination();destinationReturnBaseline={i:f.i,h,d,o:captureHandoffArrivalDestinationArrivalDestinationReturn(f.i,h,target(),d.context_navigation,d).observation!};});
const currentSavedReturn=()=>structuredClone(destinationReturnBaseline);
function newestFreshReturn(head=20){const h=currentDestination(head);h.context_navigation.analysis={id:'a',current_version_id:'fresh-arrival-destination-return-queue',revision:21};h.observed_at=h.context_navigation.observed_at='2026-10-15T02:20:00Z';return h;}
import { prepareHandoffArrivalDestinationArrivalDestinationEvent } from './handoffArrivalDestinationArrivalDestinationEvent';
let destinationEventBaseline:{i:ReturnIntent;o:HandoffArrivalDestinationArrivalDestinationReturn;q:ReviewLineage;value:ReturnType<typeof reconcileHandoffArrivalDestinationArrivalDestinationReturn>};
beforeAll(()=>{const f=currentSavedReturn(),q=newestFreshReturn();destinationEventBaseline={i:f.i,o:f.o,q,value:reconcileHandoffArrivalDestinationArrivalDestinationReturn(f.i,f.o,page(q),q.context_navigation,q)};});
async function lastEventFixture(saved?:ReviewLineage){const f=structuredClone(destinationEventBaseline);if(saved){f.o=captureHandoffArrivalDestinationArrivalDestinationReturn(f.i,destinationReturnBaseline.h,target(),saved.context_navigation,saved).observation!;f.value=reconcileHandoffArrivalDestinationArrivalDestinationReturn(f.i,f.o,page(f.q),f.q.context_navigation,f.q);}let n=0;const read=vi.fn(async(_url:string)=>{const h=newestFreshReturn();h.lineage=snapshot(2,1,20).lineage;h.observed_at=h.context_navigation.observed_at=`2026-10-15T02:20:0${++n}Z`;return h;});return {...f,read};}
const prepareLast=(f:Awaited<ReturnType<typeof lastEventFixture>>)=>prepareHandoffArrivalDestinationArrivalDestinationEvent(f.i,f.o,f.value,f.read,()=>true);
function lastDestination(head=21){const h=newestFreshReturn(head);h.context_navigation.analysis={id:'a',current_version_id:'new-destination-preserving-arrival',revision:22};h.observed_at=h.context_navigation.observed_at='2026-10-15T02:21:00Z';return h;}
function lastPins(o:HandoffArrivalDestinationArrivalDestinationReturn){return [...currentPins(o.handoff.observation),o.handoff.queue.fresh,o.handoff.prepared,o.destination];}
import { captureHandoffArrivalDestinationArrivalDestinationArrivalReturn, reconcileHandoffArrivalDestinationArrivalDestinationArrivalReturn, type HandoffArrivalDestinationArrivalDestinationArrivalReturn } from './handoffArrivalDestinationArrivalDestinationArrivalReturn';
let finalReturnBaseline:{i:ReturnIntent;h:Awaited<ReturnType<typeof prepareLast>>;d:ReviewLineage;o:HandoffArrivalDestinationArrivalDestinationArrivalReturn};
beforeAll(async()=>{const f=await lastEventFixture(),h=await prepareLast(f),d=lastDestination();finalReturnBaseline={i:f.i,h,d,o:captureHandoffArrivalDestinationArrivalDestinationArrivalReturn(f.i,h,target(),d.context_navigation,d).observation!};});
const finalSavedReturn=()=>structuredClone(finalReturnBaseline);
function finalFreshReturn(head=22){const h=lastDestination(head);h.context_navigation.analysis={id:'a',current_version_id:'fresh-destination-preserving-arrival-return-queue',revision:23};h.observed_at=h.context_navigation.observed_at='2026-10-15T02:22:00Z';return h;}
import { prepareHandoffArrivalDestinationArrivalDestinationArrivalEvent } from './handoffArrivalDestinationArrivalDestinationArrivalEvent';
let fullEventBaseline:{i:ReturnIntent;o:HandoffArrivalDestinationArrivalDestinationArrivalReturn;q:ReviewLineage;value:ReturnType<typeof reconcileHandoffArrivalDestinationArrivalDestinationArrivalReturn>};
beforeAll(()=>{const f=finalSavedReturn(),q=finalFreshReturn();fullEventBaseline={i:f.i,o:f.o,q,value:reconcileHandoffArrivalDestinationArrivalDestinationArrivalReturn(f.i,f.o,page(q),q.context_navigation,q)};});
async function fullEventFixture(saved?:ReviewLineage){const f=structuredClone(fullEventBaseline);if(saved){f.o=captureHandoffArrivalDestinationArrivalDestinationArrivalReturn(f.i,finalReturnBaseline.h,target(),saved.context_navigation,saved).observation!;f.value=reconcileHandoffArrivalDestinationArrivalDestinationArrivalReturn(f.i,f.o,page(f.q),f.q.context_navigation,f.q);}let n=0;const read=vi.fn(async(_url:string)=>{const h=finalFreshReturn();h.lineage=snapshot(2,1,22).lineage;h.observed_at=h.context_navigation.observed_at=`2026-10-15T02:22:0${++n}Z`;return h;});return {...f,read};}
const prepareComplete=(f:Awaited<ReturnType<typeof fullEventFixture>>)=>prepareHandoffArrivalDestinationArrivalDestinationArrivalEvent(f.i,f.o,f.value,f.read,()=>true);
function fullDestination(head=23){const h=finalFreshReturn(head);h.context_navigation.analysis={id:'a',current_version_id:'new-arrival-preserving-complete-destination',revision:24};h.observed_at=h.context_navigation.observed_at='2026-10-15T02:23:00Z';return h;}
function completePins(o:HandoffArrivalDestinationArrivalDestinationArrivalReturn){return [...lastPins(o.handoff.observation),o.handoff.queue.fresh,o.handoff.prepared,o.arrival];}
import { captureHandoffArrivalDestinationArrivalDestinationArrivalDestinationReturn, reconcileHandoffArrivalDestinationArrivalDestinationArrivalDestinationReturn, type HandoffArrivalDestinationArrivalDestinationArrivalDestinationReturn } from './handoffArrivalDestinationArrivalDestinationArrivalDestinationReturn';
let newestReturnBaseline:{i:ReturnIntent;h:Awaited<ReturnType<typeof prepareComplete>>;d:ReviewLineage;o:HandoffArrivalDestinationArrivalDestinationArrivalDestinationReturn};
beforeAll(async()=>{const f=await fullEventFixture(),h=await prepareComplete(f),d=fullDestination();newestReturnBaseline={i:f.i,h,d,o:captureHandoffArrivalDestinationArrivalDestinationArrivalDestinationReturn(f.i,h,target(),d.context_navigation,d).observation!};});
const destinationSavedReturn=()=>structuredClone(newestReturnBaseline);
function destinationFresh(head=24){const h=fullDestination(head);h.context_navigation.analysis={id:'a',current_version_id:'fresh-complete-destination-return-queue',revision:25};h.observed_at=h.context_navigation.observed_at='2026-10-15T02:24:00Z';return h;}
import { prepareHandoffArrivalDestinationArrivalDestinationArrivalDestinationEvent } from './handoffArrivalDestinationArrivalDestinationArrivalDestinationEvent';
let completeDestinationBaseline:{i:ReturnIntent;o:HandoffArrivalDestinationArrivalDestinationArrivalDestinationReturn;q:ReviewLineage;value:ReturnType<typeof reconcileHandoffArrivalDestinationArrivalDestinationArrivalDestinationReturn>};
beforeAll(()=>{const f=destinationSavedReturn(),q=destinationFresh();completeDestinationBaseline={i:f.i,o:f.o,q,value:reconcileHandoffArrivalDestinationArrivalDestinationArrivalDestinationReturn(f.i,f.o,page(q),q.context_navigation,q)};});
async function completeDestinationFixture(saved?:ReviewLineage){const f=structuredClone(completeDestinationBaseline);if(saved){f.o=captureHandoffArrivalDestinationArrivalDestinationArrivalDestinationReturn(f.i,newestReturnBaseline.h,target(),saved.context_navigation,saved).observation!;f.value=reconcileHandoffArrivalDestinationArrivalDestinationArrivalDestinationReturn(f.i,f.o,page(f.q),f.q.context_navigation,f.q);}let n=0;const read=vi.fn(async(_url:string)=>{const h=destinationFresh();h.lineage=snapshot(2,1,24).lineage;h.observed_at=h.context_navigation.observed_at=`2026-10-15T02:24:0${++n}Z`;return h;});return {...f,read};}
const prepareCompleteDestinationEvent=(f:Awaited<ReturnType<typeof completeDestinationFixture>>)=>prepareHandoffArrivalDestinationArrivalDestinationArrivalDestinationEvent(f.i,f.o,f.value,f.read,()=>true);
function newestDestination(head=25){const h=destinationFresh(head);h.context_navigation.analysis={id:'a',current_version_id:'complete-destination-preserving-event-arrival',revision:26};h.observed_at=h.context_navigation.observed_at='2026-10-15T02:25:00Z';return h;}
function allRetainedPins(o:HandoffArrivalDestinationArrivalDestinationArrivalDestinationReturn){return [...completePins(o.handoff.observation),o.handoff.queue.fresh,o.handoff.prepared,o.destination];}
import { captureHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalReturn, reconcileHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalReturn, type HandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalReturn } from './handoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalReturn';
let completeArrivalBaseline:{i:ReturnIntent;h:Awaited<ReturnType<typeof prepareCompleteDestinationEvent>>;d:ReviewLineage;o:HandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalReturn};
beforeAll(async()=>{const f=await completeDestinationFixture(),h=await prepareCompleteDestinationEvent(f),d=newestDestination();completeArrivalBaseline={i:f.i,h,d,o:captureHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalReturn(f.i,h,target(),d.context_navigation,d).observation!};});
const completeArrivalSavedReturn=()=>structuredClone(completeArrivalBaseline);
function completeArrivalFresh(head=26){const h=newestDestination(head);h.context_navigation.analysis={id:'a',current_version_id:'fresh-complete-handoff-arrival-return-queue',revision:27};h.observed_at=h.context_navigation.observed_at='2026-10-15T02:26:00Z';return h;}
import { prepareHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalEvent, returnHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalEvent } from './handoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalEvent';
let completeArrivalEventBaseline:{i:ReturnIntent;o:HandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalReturn;q:ReviewLineage;value:ReturnType<typeof reconcileHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalReturn>};
beforeAll(()=>{const f=completeArrivalSavedReturn(),q=completeArrivalFresh();completeArrivalEventBaseline={i:f.i,o:f.o,q,value:reconcileHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalReturn(f.i,f.o,page(q),q.context_navigation,q)};});
async function retainedArrivalEventFixture(saved?:ReviewLineage){const f=structuredClone(completeArrivalEventBaseline);if(saved){f.o=captureHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalReturn(f.i,completeArrivalBaseline.h,target(),saved.context_navigation,saved).observation!;f.value=reconcileHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalReturn(f.i,f.o,page(f.q),f.q.context_navigation,f.q);}let n=0;const read=vi.fn(async(_url:string)=>{const h=completeArrivalFresh();h.lineage=snapshot(2,1,26).lineage;h.observed_at=h.context_navigation.observed_at=`2026-10-15T02:26:0${++n}Z`;return h;});return {...f,read};}
const prepareRetainedArrivalEvent=(f:Awaited<ReturnType<typeof retainedArrivalEventFixture>>)=>prepareHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalEvent(f.i,f.o,f.value,f.read,()=>true);
function retainedArrivalDestination(head=27){const h=completeArrivalFresh(head);h.context_navigation.analysis={id:'a',current_version_id:'complete-arrival-preserving-event-destination',revision:28};h.observed_at=h.context_navigation.observed_at='2026-10-15T02:27:00Z';return h;}
function completeRetainedArrivalPins(o:HandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalReturn){return [...allRetainedPins(o.handoff.observation),o.handoff.queue.fresh,o.handoff.prepared,o.arrival];}
import { captureHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationReturn, reconcileHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationReturn, validateHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationReturn, type HandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationReturn } from './handoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationReturn';
import HandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationReturnPanel from '../pages/HandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationReturnPanel';
let completeDestinationReturnBaseline:{i:ReturnIntent;h:Awaited<ReturnType<typeof prepareRetainedArrivalEvent>>;d:ReviewLineage;o:HandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationReturn};
beforeAll(async()=>{const f=await retainedArrivalEventFixture(),h=await prepareRetainedArrivalEvent(f),d=retainedArrivalDestination();completeDestinationReturnBaseline={i:f.i,h,d,o:captureHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationReturn(f.i,h,target(),d.context_navigation,d).observation!};});
const completeDestinationReturnSaved=()=>structuredClone(completeDestinationReturnBaseline);
function completeDestinationReturnFresh(head=28){const h=retainedArrivalDestination(head);h.context_navigation.analysis={id:'a',current_version_id:'fresh-complete-arrival-handoff-destination-return-queue',revision:29};h.observed_at=h.context_navigation.observed_at='2026-10-15T02:28:00Z';return h;}
function observeReturn(f=completeDestinationReturnSaved(),h=completeDestinationReturnFresh(),p=page(h)){return reconcileHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationReturn(f.i,f.o,p,h.context_navigation,h);}
function allNewPins(o:HandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationReturn){return [...completeRetainedArrivalPins(o.handoff.observation),o.handoff.queue.fresh,o.handoff.prepared];}
describe('guarded handoff-arrival-destination-arrival-destination-arrival-destination-arrival-destination return reconciliation',()=>{
  it('captures one reduced destination separately while keeping the entire original handoff and intent unchanged',()=>{
    const f=completeDestinationReturnSaved(),before=structuredClone(f),next=captureHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationReturn(f.i,f.h,target(),f.d.context_navigation,f.d);expect(next).toEqual({intent:f.i,observation:f.o});expect(Object.keys(f.o).sort()).toEqual(['destination','handoff','recipe']);expect(f.o.destination.head?.id).toBe(id(27));expect(f.o.handoff.prepared.head?.id).toBe(id(26));expect(f.o.handoff.observation.arrival.head?.id).toBe(id(25));
    for(const word of ['lineage','PRIVATE TITLE','source_body','note'])expect(JSON.stringify(next)).not.toContain(word);next.observation!.destination.selected.packet_sha256='e'.repeat(64);next.observation!.handoff.observation.arrival.metadata.analysis.current_version_id='mutated';expect(f).toEqual(before);
  });
  it('preserves the original exact-event return projection without another arrival',()=>{const f=completeDestinationReturnSaved();expect(returnHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalEvent(f.i,f.h,target(),f.d.context_navigation,f.d)).toEqual({intent:f.i,observation:f.h.observation});expect(returnHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalEvent(f.i,f.h,target(),null,null)).toEqual({intent:f.i,observation:null});});
  it('returns selection only for both unavailable inputs and rejects partial/conflicting observations',()=>{
    const f=completeDestinationReturnSaved();expect(captureHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationReturn(f.i,f.h,target(),null,null)).toEqual({intent:f.i,observation:null});expect(()=>captureHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationReturn(f.i,f.h,target(),f.d.context_navigation,null)).toThrow();expect(()=>captureHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationReturn(f.i,f.h,target(),null,f.d)).toThrow();const m=structuredClone(f.d.context_navigation);m.analysis.revision++;expect(()=>captureHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationReturn(f.i,f.h,target(),m,f.d)).toThrow();
  });
  it.each(['kind','matter_id','analysis_id','context_id','review_id','prepare'] as const)('rejects redirected %s even when observations are unavailable',key=>{
    const f=completeDestinationReturnSaved();expect(()=>captureHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationReturn(f.i,f.h,{...target(),[key]:'other'},null,null)).toThrow();
  });
  it.each(['customer_ids','date_field','date_from','date_to','source_date_from','source_date_to','bucket'] as const)('binds original %s before allocation',key=>{
    const f=completeDestinationReturnSaved(),nonce=vi.fn(()=>'a'.repeat(32)),b=new PortfolioReturnBook(()=>0,nonce);if(key==='customer_ids')f.i.filters.customer_ids=['B'];else if(key==='date_field')f.i.filters.date_field='updated_at';else if(key==='bucket')f.i.filters.bucket='action_required';else f.i.filters[key]='2021-02-02';expect(()=>b.putHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationReturn(f.i,f.o)).toThrow();expect(nonce).not.toHaveBeenCalled();
  });
  it.each(['recipe','extra','recursive','destination-extra','analysis-extra','selected','manifest','version','queue','times','time','revision'] as const)('rejects %s at validation and fresh reconciliation',kind=>{
    const f=completeDestinationReturnSaved();if(kind==='recipe')Object.assign(f.o,{recipe:'private-arrival-return-v1'});if(kind==='extra')Object.assign(f.o,{note:undefined});if(kind==='recursive')Object.assign(f.o,{previous:f.o});if(kind==='destination-extra')Object.assign(f.o.destination,{lineage:undefined});if(kind==='analysis-extra')Object.assign(f.o.destination.metadata.analysis,{note:undefined});if(kind==='selected')f.o.destination.selected.packet_sha256='e'.repeat(64);if(kind==='manifest')f.o.destination.metadata.context.manifest_sha256='e'.repeat(64);if(kind==='version')f.o.destination.metadata.context.version_id='other';if(kind==='queue')f.o.handoff.queue.head_relation='same';if(kind==='times')f.o.handoff.observed_at.reverse();if(kind==='time')f.o.destination.metadata.observed_at=stamp;if(kind==='revision')f.o.destination.metadata.analysis.revision=2;expect(()=>validateHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationReturn(f.o,f.i)).toThrow();expect(()=>observeReturn(f)).toThrow();
  });
  it.each(Array.from({length:40},(_,i)=>i))('rejects a changed selected packet in retained snapshot %s',n=>{
    const f=completeDestinationReturnSaved();allNewPins(f.o)[n].selected.packet_sha256='e'.repeat(64);expect(()=>validateHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationReturn(f.o,f.i)).toThrow();expect(()=>observeReturn(f)).toThrow();
  });
  it.each([3,4,5,6,7,8,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27])('checks known head %s including the destination-only head',head=>{
    const f=completeDestinationReturnSaved(),h=completeDestinationReturnFresh(head);h.current_head!.packet_sha256='e'.repeat(64);expect(()=>observeReturn(f,h)).toThrow();
  });
  it('checks a head known only to the separately captured destination',()=>{
    const f=completeDestinationReturnSaved(),d=structuredClone(f.d);d.current_head=row(9);d.context_navigation.historical_review={id:id(9),state:row(9).state,recorded_at:stamp};f.o=captureHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationReturn(f.i,f.h,target(),d.context_navigation,d).observation!;
    const h=completeDestinationReturnFresh(9);h.current_head!.packet_sha256='e'.repeat(64);expect(()=>observeReturn(f,h)).toThrow();
  });
  it('compares the destination independently and leaves all earlier observations and relation flags unchanged',()=>{
    const f=completeDestinationReturnSaved(),before=structuredClone(f),h=completeDestinationReturnFresh(),value=observeReturn(f,h),old=reconcileHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalReturn(f.i,f.h.observation,page(h),h.context_navigation,h);if(value.state!=='observed'||old.state!=='observed')throw Error();expect([value.head_relation,value.version_relation,value.revision_relation]).toEqual(['different','different','different']);expect({...value,head_relation:old.head_relation,version_relation:old.version_relation,revision_relation:old.revision_relation}).toEqual(old);expect(f).toEqual(before);value.fresh.selected.packet_sha256='e'.repeat(64);expect(f).toEqual(before);const same=observeReturn(f,structuredClone(f.d));if(same.state!=='observed')throw Error();expect([same.head_relation,same.version_relation,same.revision_relation]).toEqual(['same','same','same']);
  });
  it.each(['queue-head','packet','filters','page-time','event-time','revision','unexpected-read','offset'] as const)('closes on fresh %s disagreement',kind=>{
    const f=completeDestinationReturnSaved(),h=completeDestinationReturnFresh(),p=page(h);if(kind==='queue-head')p.items[0].historical_review.id=id(25);if(kind==='packet')h.selected_review.packet_sha256=h.lineage.items[0].packet_sha256='e'.repeat(64);if(kind==='filters')p.filters.customer_ids=['B'];if(kind==='page-time')p.observed_at='2026-10-15T02:16:30Z';if(kind==='event-time')h.observed_at=h.context_navigation.observed_at=stamp;if(kind==='revision')h.context_navigation.analysis=structuredClone(f.h.prepared.metadata.analysis);if(kind==='unexpected-read'){p.items=[];p.coverage.returned_count=0;}if(kind==='offset')p.coverage.scanned_count=-1;expect(()=>observeReturn(f,h,p)).toThrow();
  });
  it('exposes only generic omission, rejects target metadata outside the window and requires it inside',()=>{
    const f=completeDestinationReturnSaved(),p=page(completeDestinationReturnFresh());p.items=[];p.coverage.returned_count=0;const value=reconcileHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationReturn(f.i,f.o,p,null,null);expect(value).toEqual({state:'not_observed',queue_observed_at:p.observed_at});expect(()=>reconcileHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationReturn(f.i,f.o,page(completeDestinationReturnFresh()),null,null)).toThrow();const html=renderToStaticMarkup(<HandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationReturnPanel observation={f.o} value={value}/>);expect(html).toContain('ayrıntıları açılmadı');for(const word of [ctx,id(25),'frozen','complete-arrival-preserving-event-destination'])expect(html).not.toContain(word);
  });
  it('retains unknown/pending saved and fresh observations explicitly without granting authority',()=>{
    const f=completeDestinationReturnSaved(),d=unknown(unknown(structuredClone(f.d),'head'),'version');d.selected_review.admission=d.lineage.items[0].admission='pending';d.context_navigation.admission.context_state='pending';f.o=captureHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationReturn(f.i,f.h,target(),d.context_navigation,d).observation!;const value=observeReturn(f);if(value.state!=='observed')throw Error();expect(value.head_relation).toBe('unknown');expect(value.version_relation).toBe('unknown');expect(f.o.destination.selected.admission).toBe('pending');const v=observeReturn(completeDestinationReturnSaved(),unknown(unknown(completeDestinationReturnFresh(),'head'),'version'));if(v.state!=='observed')throw Error();expect(v.head_relation).toBe('unknown');expect(v.version_relation).toBe('unknown');
  });
  it('validates complete history on every public call after earlier success',()=>{
    const f=completeDestinationReturnSaved();validateHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationReturn(f.o,f.i);f.o.destination.selected.packet_sha256='e'.repeat(64);expect(()=>validateHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationReturn(f.o,f.i)).toThrow();expect(()=>observeReturn(f)).toThrow();f.o=structuredClone(completeDestinationReturnBaseline.o);validateHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationReturn(f.o,f.i);f.o.handoff.observation.arrival.selected.packet_sha256='e'.repeat(64);expect(()=>captureHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationReturn(f.i,f.o.handoff,target(),null,null)).toThrow();
  });
  it('keeps one cloned row of unchanged return projections, validates before nonce/eviction and enforces eight entries/TTL',()=>{
    const f=completeDestinationReturnSaved();let now=0,n=0;const nonce=vi.fn(()=>String(++n).padStart(32,'a')),book=new PortfolioReturnBook(()=>now,nonce),token=book.putHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationReturn(f.i,f.o);const originalCompleteArrival=f.h.observation,originalDestination=originalCompleteArrival.handoff.observation,originalArrival=originalDestination.handoff.observation,destination=originalArrival.handoff.observation,preceding=destination.handoff.observation,parent=preceding.handoff.observation,arrival=parent.handoff.observation,prior=arrival.handoff.observation,sourceArrival=prior.handoff.observation,sourceDest=sourceArrival.handoff.observation,carried=sourceDest.handoff.observation,onward=carried.handoff.observation,original=onward.handoff.observation;
    expect(nonce).toHaveBeenCalledTimes(1);expect(book.get(token)).toEqual(f.i);expect(book.getHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationReturn(token)).toEqual(f.o);expect(book.getHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalReturn(token)).toEqual(originalCompleteArrival);expect(book.getHandoffArrivalDestinationArrivalDestinationArrivalDestinationReturn(token)).toEqual(originalDestination);expect(book.getHandoffArrivalDestinationArrivalDestinationArrivalReturn(token)).toEqual(originalArrival);expect(book.getHandoffArrivalDestinationArrivalDestinationReturn(token)).toEqual(destination);expect(book.getHandoffArrivalDestinationArrivalReturn(token)).toEqual(preceding);expect(book.getHandoffArrivalDestinationReturn(token)).toEqual(parent);expect(book.getHandoffDestinationArrivalReturn(token)).toEqual(arrival);expect(book.getArrivalHandoffDestinationReturn(token)).toEqual(prior);expect(book.getCarriedDestinationArrivalReturn(token)).toEqual(sourceArrival);expect(book.getCarriedDestinationReturn(token)).toEqual(sourceDest);expect(book.getCarriedArrivalReturn(token)).toEqual(carried);expect(book.getOnwardReturn(token)).toEqual(onward);expect(book.getArrivalReturn(token)).toEqual(original);expect(book.getComparisonReturn(token)).toEqual(original.handoff.receipt);expect(book.getHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalEvent(token)).toBeNull();expect(book.getHandoffArrivalDestinationArrivalDestinationArrivalDestinationEvent(token)).toBeNull();expect(book.getHandoffArrivalDestinationArrivalDestinationArrivalEvent(token)).toBeNull();expect(book.getHandoffArrivalDestinationArrivalDestinationEvent(token)).toBeNull();expect(book.getHandoffArrivalDestinationArrivalEvent(token)).toBeNull();expect(book.getHandoffArrivalDestinationEvent(token)).toBeNull();expect(book.getHandoffArrivalEvent(token)).toBeNull();expect(book.getHandoffDestinationEvent(token)).toBeNull();expect(book.getReviewPath(token)).toBeNull();
    const before=structuredClone(f.o);f.o.destination.selected.packet_sha256='e'.repeat(64);book.getHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationReturn(token)!.handoff.prepared.selected.packet_sha256='e'.repeat(64);expect(book.getHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationReturn(token)).toEqual(before);for(let i=0;i<7;i++)book.put(f.i);expect(()=>book.putHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationReturn(f.i,f.o)).toThrow();expect(nonce).toHaveBeenCalledTimes(8);expect(book.getHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationReturn(token)).toEqual(before);book.put(f.i);expect(book.getHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationReturn(token)).toBeNull();const last=book.putHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationReturn(f.i,before);now=30*60*1000;expect(book.getHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationReturn(last)).toBeNull();expect(new PortfolioReturnBook().getHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationReturn(last)).toBeNull();
  });
  it('closes private records on principal change and reload',()=>{
    const f=completeDestinationReturnSaved(),principal=new PrincipalReturnBook(),old=principal.forPrincipal('firm:one'),key=old.putHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationReturn(f.i,f.o);expect(principal.forPrincipal('firm:two').getHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationReturn(key)).toBeNull();expect(principal.forPrincipal('firm:one').getHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationReturn(key)).toBeNull();
  });
  it('renders metadata-only independent identities and withholds weaker navigation actions',()=>{
    const f=completeDestinationReturnSaved(),html=renderToStaticMarkup(<HandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationReturnPanel observation={f.o} value={observeReturn(f)}/>);for(const word of ['Tam geçiş hedefinden yeni kuyruğa','Korunan tam varış','Tam varışı koruyan hazırlık','Ayrı saklanan tam hedef','fresh-complete-arrival-handoff-destination-return-queue','complete-arrival-preserving-event-destination','frozen',id(25),id(26),id(27),id(28)])expect(html).toContain(word);for(const word of ['<button','<a ','PRIVATE TITLE','source-passage-text','qualification_granted'])expect(html).not.toContain(word);
  });
});
