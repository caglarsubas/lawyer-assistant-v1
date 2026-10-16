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

import { carriedDestinationArrivalEventAvailable, prepareCarriedDestinationArrivalEvent, compareCarriedDestinationArrivalEventDestination, returnCarriedDestinationArrivalEvent, validateCarriedDestinationArrivalEventHandoff } from './carriedDestinationArrivalEventHandoff';
import CarriedDestinationArrivalEventDestinationPanel from '../pages/CarriedDestinationArrivalEventDestinationPanel';
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
describe('guarded destination-arrival-preserving exact-event handoff',()=>{
  it('uses exactly two bounded reads and retains independent fixed observations and exact intent',async()=>{
    const f=await arrivalEventFixture(),saved=structuredClone(f.o),h=await prepareLatest(f);expect(f.read).toHaveBeenCalledTimes(2);expect(f.read.mock.calls.every(([u])=>u.endsWith(`/reviews/${id(2)}/navigation-context?window=1`))).toBe(true);
    expect(h.observation).toEqual(saved);expect(h.observation.arrival.head?.id).toBe(id(8));expect(h.observation.handoff.observation.destination.head?.id).toBe(id(7));expect(h.prepared.head?.id).toBe(id(10));expect(h.observed_at).toEqual(['2026-10-15T02:10:01Z','2026-10-15T02:10:02Z']);
    expect(Object.keys(h).sort()).toEqual(['observation','observed_at','prepared','queue','recipe']);for(const word of ['lineage','PRIVATE TITLE','source_body','note'])expect(JSON.stringify(h)).not.toContain(word);
    h.observation.arrival.metadata.analysis.current_version_id='mutated';h.queue.fresh.selected.packet_sha256='e'.repeat(64);expect(f.o).toEqual(saved);
  });
  it('preserves unknown historical identities and pending arrival admissions without promoting them',async()=>{
    const d=unknown(destinationArrival(),'head');unknown(d,'version');d.context_navigation.admission.context_state='pending';const f=await arrivalEventFixture(d),h=await prepareLatest(f);
    expect(h.observation.arrival.head).toBeNull();expect(h.observation.arrival.metadata.analysis.current_version_id).toBeNull();expect(h.observation.arrival.metadata.admission.context_state).toBe('pending');expect(h.prepared.head?.id).toBe(id(10));
  });
  it.each(['context','selected','head','version','missing-head','tools'] as const)('withholds current %s before reads',async kind=>{
    const f=await arrivalEventFixture(),q=f.q;if(kind==='context')q.context_navigation.admission.context_state='pending';if(kind==='selected'){q.selected_review.admission=q.lineage.items[0].admission='pending';q.tools_available=false;}
    if(kind==='head'){q.current_head!.admission='pending';q.context_navigation.admission.review_state='pending';}if(kind==='version')unknown(q,'version');if(kind==='missing-head')unknown(q,'head');if(kind==='tools'){q.tools_available=false;q.context_navigation.tools_available=false;}
    f.value=reconcileCarriedDestinationArrivalReturn(f.i,f.o,page(q),q.context_navigation,q);expect(carriedDestinationArrivalEventAvailable(f.i,f.o,f.value)).toBe(false);await expect(prepareLatest(f)).rejects.toThrow();expect(f.read).not.toHaveBeenCalled();
  });
  it('withholds omitted windows and rejects invented comparison relations',async()=>{
    const f=await arrivalEventFixture();f.value={state:'not_observed',queue_observed_at:f.q.observed_at};expect(carriedDestinationArrivalEventAvailable(f.i,f.o,f.value)).toBe(false);await expect(prepareLatest(f)).rejects.toThrow();expect(f.read).not.toHaveBeenCalled();
    const g=await arrivalEventFixture();if(g.value.state!=='observed')throw Error();g.value.head_relation='same';await expect(prepareLatest(g)).rejects.toThrow();expect(g.read).not.toHaveBeenCalled();
  });
  it.each(['revision','version','head','selected','manifest','context','pending','window','time','extra'] as const)('rejects first-read %s before any second read',async kind=>{
    const f=await arrivalEventFixture(),normal=f.read.getMockImplementation()!;f.read.mockImplementation(async u=>{const h=await normal(u);
      if(kind==='revision')h.context_navigation.analysis.revision++;if(kind==='version')h.context_navigation.analysis.current_version_id='changed';if(kind==='head'){h.current_head=row(11);h.context_navigation.historical_review={id:id(11),state:row(11).state,recorded_at:stamp};}
      if(kind==='selected'){h.selected_review.packet_sha256='e'.repeat(64);h.lineage.items[0].packet_sha256='e'.repeat(64);}if(kind==='manifest')h.context_navigation.context.manifest_sha256='e'.repeat(64);if(kind==='context')h.context_id=`sac-${'e'.repeat(20)}-${'b'.repeat(32)}`;
      if(kind==='pending')h.context_navigation.admission.context_state='pending';if(kind==='window')h.lineage.window=2;if(kind==='time')h.observed_at=h.context_navigation.observed_at=stamp;if(kind==='extra')Object.assign(h,{source_body:'PRIVATE'});return h;});await expect(prepareLatest(f)).rejects.toThrow();expect(f.read).toHaveBeenCalledTimes(1);
  });
  it.each(['revision','time','head-packet'] as const)('rejects second-read %s without retry',async kind=>{
    const f=await arrivalEventFixture(),normal=f.read.getMockImplementation()!;let n=0;f.read.mockImplementation(async u=>{const h=await normal(u);if(++n===2){if(kind==='revision')h.context_navigation.analysis.revision++;else if(kind==='time')h.observed_at=h.context_navigation.observed_at='2026-10-15T02:10:00Z';else h.current_head!.packet_sha256='e'.repeat(64);}return h;});await expect(prepareLatest(f)).rejects.toThrow();expect(f.read).toHaveBeenCalledTimes(2);
  });
  it('retires before and after awaited reads and propagates denial once',async()=>{
    const f=await arrivalEventFixture();await expect(prepareCarriedDestinationArrivalEvent(f.i,f.o,f.value,f.read,()=>false)).rejects.toThrow();expect(f.read).not.toHaveBeenCalled();let active=true;const normal=f.read.getMockImplementation()!;f.read.mockImplementation(async u=>{const h=await normal(u);active=false;return h;});await expect(prepareCarriedDestinationArrivalEvent(f.i,f.o,f.value,f.read,()=>active)).rejects.toThrow();expect(f.read).toHaveBeenCalledTimes(1);
    const g=await arrivalEventFixture();g.read.mockRejectedValue(new Error('403'));await expect(prepareLatest(g)).rejects.toThrow('403');expect(g.read).toHaveBeenCalledTimes(1);
  });
  it.each(['extra','recursive','recipe','filters','baseline','retained-packet','retained-time','queue','prepared','prepared-packet','prepared-extra','prepared-undefined','prepared-meta-undefined','prepared-null','prepared-clock','times','order','last-time'] as const)('rejects %s before allocation or eviction',async kind=>{
    const f=await arrivalEventFixture(),h=await prepareLatest(f);if(kind==='extra')Object.assign(h,{note:'PRIVATE'});if(kind==='recursive')Object.assign(h,{previous:structuredClone(h)});if(kind==='recipe')Object.assign(h,{recipe:'private-onward-return-event-handoff-v1'});if(kind==='filters')rootReceipt(h.observation).intent.filters.source_date_from='';if(kind==='baseline')rootReceipt(h.observation).intent.target.head_id=id(4);
    if(kind==='retained-packet')h.observation.arrival.head!.packet_sha256='e'.repeat(64);if(kind==='retained-time')h.observation.arrival.metadata.observed_at=stamp;if(kind==='queue')h.queue.head_relation='same';if(kind==='prepared')h.prepared.metadata.analysis.revision++;if(kind==='prepared-packet')h.prepared.head!.packet_sha256='e'.repeat(64);if(kind==='prepared-extra')Object.assign(h.prepared,{note:'PRIVATE'});if(kind==='prepared-undefined')Object.assign(h.prepared,{unexpected:undefined});if(kind==='prepared-meta-undefined')Object.assign(h.prepared.metadata,{unexpected:undefined});if(kind==='prepared-null')Object.assign(h,{prepared:null});if(kind==='prepared-clock')h.prepared.metadata.observed_at='invalid';if(kind==='times')h.observed_at.pop();if(kind==='order')h.observed_at[0]='2026-10-15T02:12:00Z';if(kind==='last-time')h.observed_at[1]='2026-10-15T02:10:03Z';
    expect(()=>validateCarriedDestinationArrivalEventHandoff(h,f.i)).toThrow();let n=0;const b=new PortfolioReturnBook(()=>0,()=>(++n).toString(16).padStart(32,'0')),first=b.put(f.i);for(let k=0;k<7;k++)b.put(f.i);expect(()=>b.putCarriedDestinationArrivalEvent(f.i,h)).toThrow();expect(n).toBe(8);expect(b.get(first)).toEqual(f.i);
  });
  it.each(['customer_ids','date_field','date_from','date_to','source_date_from','source_date_to','bucket'] as const)('rejects changed exact %s intent before reads or allocation',async field=>{
    const f=await arrivalEventFixture(),h=await prepareLatest(f),i=structuredClone(f.i);if(field==='customer_ids')i.filters.customer_ids=['A'];else if(field==='date_field')i.filters.date_field='created_at';else if(field==='bucket')i.filters.bucket='action_required';else i.filters[field]=field.endsWith('from')?'2026-10-02':'2026-10-30';
    const read=vi.fn(async()=>eventDestination(7,1));await expect(prepareCarriedDestinationArrivalEvent(i,f.o,f.value,read,()=>true)).rejects.toThrow();expect(read).not.toHaveBeenCalled();expect(()=>validateCarriedDestinationArrivalEventHandoff(h,i)).toThrow();
  });
  it('keeps later opposing head and version separate and restores only the unchanged original destination arrival',async()=>{
    const f=await arrivalEventFixture(),h=await prepareLatest(f),d=eventDestination(11);d.context_navigation.analysis={id:'a',current_version_id:'actual-later',revision:12};const v=compareCarriedDestinationArrivalEventDestination(f.i,h,target(),d);expect(v).toMatchObject({head_relation:'different',version_relation:'different',revision_relation:'different'});
    const r=returnCarriedDestinationArrivalEvent(f.i,h,target(),d.context_navigation,d);expect(r.intent).toEqual(f.i);expect(r.observation).toEqual(f.o);expect(Object.keys(r.observation!).sort()).toEqual(['arrival','handoff','recipe']);r.observation!.arrival.metadata.analysis.current_version_id='mutated';expect(h.observation).toEqual(f.o);
  });
  it.each(['head','version'] as const)('keeps unknown destination %s explicit',async kind=>{const f=await arrivalEventFixture(),h=await prepareLatest(f);expect(compareCarriedDestinationArrivalEventDestination(f.i,h,target(),unknown(eventDestination(),kind))).toMatchObject({[kind==='head'?'head_relation':'version_relation']:'unknown'});});
  it.each(['context','selected','head'] as const)('retains pending destination %s',async kind=>{const f=await arrivalEventFixture(),h=await prepareLatest(f),d=eventDestination();if(kind==='context')d.context_navigation.admission.context_state='pending';if(kind==='selected'){d.selected_review.admission=d.lineage.items[0].admission='pending';d.tools_available=false;}if(kind==='head'){d.current_head!.admission='pending';d.context_navigation.admission.review_state='pending';}const v=compareCarriedDestinationArrivalEventDestination(f.i,h,target(),d);expect(v.fresh.metadata.admission.context_state==='pending'||v.fresh.selected.admission==='pending'||v.fresh.head?.admission==='pending').toBe(true);expect(returnCarriedDestinationArrivalEvent(f.i,h,target(),d.context_navigation,d).observation).toEqual(f.o);});
  it.each(['selected','head3','head4','head5','head6','head7','head8','head10','revision','time','evidence'] as const)('rejects substituted or regressive %s at destination',async kind=>{
    const f=await arrivalEventFixture(),h=await prepareLatest(f),d=eventDestination();if(kind==='selected'){d.selected_review.packet_sha256='e'.repeat(64);d.lineage.items[0].packet_sha256='e'.repeat(64);}if(kind.startsWith('head')){const n=Number(kind.slice(4));d.current_head=row(n);d.current_head.packet_sha256='e'.repeat(64);d.context_navigation.historical_review={id:id(n),state:row(n).state,recorded_at:stamp};}if(kind==='revision')d.context_navigation.analysis.revision--;if(kind==='time')d.observed_at=d.context_navigation.observed_at='2026-10-15T02:10:01Z';if(kind==='evidence')d.context_navigation.context.version_id='other';expect(()=>compareCarriedDestinationArrivalEventDestination(f.i,h,target(),d)).toThrow();
  });
  it.each(['review','context','foreign','prepare','renewal'] as const)('rejects %s purpose redirection even without metadata',async kind=>{const f=await arrivalEventFixture(),h=await prepareLatest(f),t=target();if(kind==='review')t.review_id=id(7);if(kind==='context')delete t.review_id;if(kind==='foreign')t.matter_id='other';if(kind==='prepare')t.prepare='review';if(kind==='renewal')t.prepare='renewal';expect(()=>compareCarriedDestinationArrivalEventDestination(f.i,h,t,eventDestination())).toThrow();expect(()=>returnCarriedDestinationArrivalEvent(f.i,h,t,null,null)).toThrow();});
  it('uses selection only when unavailable and rejects partial observations',async()=>{const f=await arrivalEventFixture(),h=await prepareLatest(f),d=eventDestination();expect(returnCarriedDestinationArrivalEvent(f.i,h,target(),null,null)).toEqual({intent:f.i,observation:null});expect(()=>returnCarriedDestinationArrivalEvent(f.i,h,target(),d.context_navigation,null)).toThrow();expect(()=>returnCarriedDestinationArrivalEvent(f.i,h,target(),null,d)).toThrow();const wrong=structuredClone(d.context_navigation);wrong.analysis.current_version_id='other';expect(()=>returnCarriedDestinationArrivalEvent(f.i,h,target(),wrong,d)).toThrow();});
  it('clones and bounds purpose storage, closing on expiry, reload or principal loss',async()=>{const f=await arrivalEventFixture(),h=await prepareLatest(f),saved=structuredClone(h);let now=0,n=0;const b=new PortfolioReturnBook(()=>now,()=>(++n).toString(16).padStart(32,'0')),t=b.putCarriedDestinationArrivalEvent(f.i,h);h.observation.arrival.metadata.analysis.current_version_id='mutated';expect(b.getCarriedDestinationArrivalEvent(t)).toEqual(saved);b.getCarriedDestinationArrivalEvent(t)!.queue.head_relation='same';expect(b.getCarriedDestinationArrivalEvent(t)).toEqual(saved);for(let k=0;k<8;k++)b.putCarriedDestinationArrivalEvent(f.i,saved);expect(b.getCarriedDestinationArrivalEvent(t)).toBeNull();const last=b.putCarriedDestinationArrivalEvent(f.i,saved);now=30*60*1000;expect(b.getCarriedDestinationArrivalEvent(last)).toBeNull();expect(new PortfolioReturnBook().getCarriedDestinationArrivalEvent(last)).toBeNull();const p=new PrincipalReturnBook(),token=p.forPrincipal('A').putCarriedDestinationArrivalEvent(f.i,saved);expect(p.forPrincipal('B').getCarriedDestinationArrivalEvent(token)).toBeNull();expect(p.forPrincipal('A').getCarriedDestinationArrivalEvent(token)).toBeNull();expect(b.getCarriedDestinationArrivalEvent(b.put(f.i))).toBeNull();expect(b.getCarriedDestinationArrivalEvent('bad')).toBeNull();expect(b.getCarriedDestinationArrivalReturn(last)).toBeNull();});
  it('renders separate metadata observations with no actions or approval',async()=>{const f=await arrivalEventFixture(),h=await prepareLatest(f),html=renderToStaticMarkup(<CarriedDestinationArrivalEventDestinationPanel handoff={h} value={compareCarriedDestinationArrivalEventDestination(f.i,h,target(),eventDestination())}/>);for(const word of [id(1),id(2),id(3),id(4),id(5),id(6),id(7),id(8),id(10),'frozen','queue-version','onward-version','carry-version','carried-next-version','özgün hedef varışını değişmeden korur','Bekleyen kabul tamamlanmadı'])expect(html).toContain(word);expect(html).not.toMatch(/<(a |button|input|textarea|form)/);expect(html).not.toContain('PRIVATE TITLE');});
  it('rejects a packet substituted for a head known only in the saved arrival',async()=>{
    const d=destinationArrival(9);d.context_navigation.analysis={id:'a',current_version_id:'arrival-only-version',revision:10};const f=await arrivalEventFixture(d),h=await prepareLatest(f),v=eventDestination(9);v.current_head!.packet_sha256='e'.repeat(64);
    expect(()=>compareCarriedDestinationArrivalEventDestination(f.i,h,target(),v)).toThrow();expect(()=>returnCarriedDestinationArrivalEvent(f.i,h,target(),v.context_navigation,v)).toThrow();
  });
  it('anchors filter/history/queue clones before either awaited read',async()=>{
    const f=await arrivalEventFixture(),i=structuredClone(f.i),o=structuredClone(f.o),q=structuredClone(f.value),normal=f.read.getMockImplementation()!;let n=0;
    f.read.mockImplementation(async u=>{const h=await normal(u);if(++n===1){f.i.filters.customer_ids=['A'];f.o.arrival.metadata.analysis.current_version_id='mutated';if(f.value.state==='observed')f.value.fresh.metadata.analysis.current_version_id='mutated';}return h;});
    const h=await prepareLatest(f);expect(h.observation).toEqual(o);expect(h.queue).toEqual(q);expect(()=>validateCarriedDestinationArrivalEventHandoff(h,i)).not.toThrow();expect(()=>validateCarriedDestinationArrivalEventHandoff(h,f.i)).toThrow();
  });
  it('copies each fresh reply before a later callback can mutate it',async()=>{
    const f=await arrivalEventFixture(),normal=f.read.getMockImplementation()!;let previous: ReviewLineage|null=null;
    f.read.mockImplementation(async u=>{if(previous)previous.observed_at=previous.context_navigation.observed_at='2026-10-15T03:00:00Z';const h=await normal(u);previous=h;return h;});
    const h=await prepareLatest(f);expect(h.observed_at).toEqual(['2026-10-15T02:10:01Z','2026-10-15T02:10:02Z']);expect(f.read).toHaveBeenCalledTimes(2);
  });
});
