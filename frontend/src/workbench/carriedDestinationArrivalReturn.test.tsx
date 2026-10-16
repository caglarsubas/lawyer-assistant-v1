import { captureCarriedDestinationReturn, reconcileCarriedDestinationReturn } from './carriedDestinationReturn';
import { describe, expect, it, vi } from 'vitest';
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

import CarriedDestinationArrivalReturnPanel from '../pages/CarriedDestinationArrivalReturnPanel';
import { captureCarriedDestinationArrivalReturn, reconcileCarriedDestinationArrivalReturn, validateCarriedDestinationArrivalReturn } from './carriedDestinationArrivalReturn';
async function savedArrival(d=destinationArrival()) { const f=await destinationFixture(),h=await prepareDestination(f),observation=captureCarriedDestinationArrivalReturn(f.i,h,target(),d.context_navigation,d).observation!;return {i:f.i,h,d,observation}; }
function freshArrival(head=8){const h=destinationArrival(head);h.observed_at=h.context_navigation.observed_at='2026-10-15T02:10:00Z';return h;}
function reconcile(f:Awaited<ReturnType<typeof savedArrival>>,h=freshArrival(),p=page(h)){return reconcileCarriedDestinationArrivalReturn(f.i,f.observation,p,h.context_navigation,h);}
describe('guarded destination-arrival return reconciliation',()=>{
  it('captures a distinct destination without changing intent, original destination or preparations',async()=>{
    const f=await savedArrival(),original=structuredClone(f.h);expect(f.observation.handoff).toEqual(original);expect(f.observation.arrival.head?.id).toBe(id(8));expect(f.observation.handoff.observation.destination.head?.id).toBe(id(7));expect(f.observation.handoff.observation.handoff.observation.arrival.head?.id).toBe(id(6));
    expect(Object.keys(f.observation).sort()).toEqual(['arrival','handoff','recipe']);for(const word of ['lineage','PRIVATE TITLE','source_body','note'])expect(JSON.stringify(f.observation)).not.toContain(word);f.d.current_head!.packet_sha256='e'.repeat(64);f.h.prepared.metadata.analysis.current_version_id='mutated';expect(f.observation.handoff).toEqual(original);
  });
  it('compares retained destination independently with stable and later opposing heads and versions',async()=>{
    const d=destinationArrival(9);d.context_navigation.analysis={id:'a',current_version_id:'retained-arrival',revision:10};const f=await savedArrival(d),h=freshArrival(9);h.context_navigation.analysis=structuredClone(d.context_navigation.analysis);const saved=structuredClone(f.observation),v=reconcile(f,h);expect(v).toMatchObject({state:'observed',head_relation:'same',version_relation:'same',revision_relation:'same'});
    const later=freshArrival(10);later.context_navigation.analysis={id:'a',current_version_id:'later-version',revision:11};expect(reconcile(f,later)).toMatchObject({head_relation:'different',version_relation:'different',revision_relation:'different'});if(v.state!=='observed')throw Error();v.fresh.selected.packet_sha256='e'.repeat(64);expect(f.observation).toEqual(saved);
  });
  it.each(['head','version'] as const)('retains unknown saved or current %s without inference',async kind=>{const f=await savedArrival(unknown(destinationArrival(),kind));expect(reconcile(f)).toMatchObject({[kind==='head'?'head_relation':'version_relation']:'unknown'});const g=await savedArrival();expect(reconcile(g,unknown(freshArrival(),kind))).toMatchObject({[kind==='head'?'head_relation':'version_relation']:'unknown'});});
  it('preserves pending destination and current admissions without completing them',async()=>{
    const d=destinationArrival();d.context_navigation.admission.context_state='pending';d.selected_review.admission=d.lineage.items[0].admission='pending';d.tools_available=false;const f=await savedArrival(d),q=freshArrival();q.context_navigation.admission={context_state:'pending',review_state:'pending'};q.selected_review.admission=q.lineage.items[0].admission='pending';q.current_head!.admission='pending';q.tools_available=false;const v=reconcile(f,q);if(v.state!=='observed')throw Error();expect(v.fresh.selected.admission).toBe('pending');expect(v.fresh.metadata.admission).toEqual({context_state:'pending',review_state:'pending'});expect(f.observation.arrival.selected.admission).toBe('pending');
  });
  it('returns selection only when unavailable and rejects partial, conflicting or redirected metadata',async()=>{
    const f=await savedArrival();expect(captureCarriedDestinationArrivalReturn(f.i,f.h,target(),null,null)).toEqual({intent:f.i,observation:null});expect(()=>captureCarriedDestinationArrivalReturn(f.i,f.h,target(),f.d.context_navigation,null)).toThrow();expect(()=>captureCarriedDestinationArrivalReturn(f.i,f.h,target(),null,f.d)).toThrow();const wrong=structuredClone(f.d.context_navigation);wrong.analysis.current_version_id='wrong';expect(()=>captureCarriedDestinationArrivalReturn(f.i,f.h,target(),wrong,f.d)).toThrow();
    for(const t of [{...target(),review_id:id(8)},{...target(),matter_id:'other'},{...target(),prepare:'review' as const},{...target(),prepare:'renewal' as const},{...target(),review_id:undefined}])expect(()=>captureCarriedDestinationArrivalReturn(f.i,f.h,t,null,null)).toThrow();
  });
  it.each(['extra','recursive','recipe','filters','baseline','evidence','selected','head3','head4','head5','head6','head7','head8','time','revision','extra-destination'] as const)('rejects retained %s forgery before nonce allocation or eviction',async kind=>{
    const f=await savedArrival(),o=f.observation,r=o.handoff.observation.handoff.observation.handoff.observation.handoff.observation.handoff.receipt;if(kind==='extra')Object.assign(o,{note:'PRIVATE'});if(kind==='recursive')Object.assign(o,{previous:structuredClone(o)});if(kind==='recipe')Object.assign(o,{recipe:'other'});if(kind==='filters')r.intent.filters.source_date_from='';if(kind==='baseline')r.intent.target.head_id=id(4);
    if(kind==='evidence')o.arrival.metadata.context.version_id='other';if(kind==='selected')o.arrival.selected.packet_sha256='e'.repeat(64);if(kind.startsWith('head')){const n=Number(kind.slice(4));o.arrival.head=row(n);o.arrival.head.packet_sha256='e'.repeat(64);o.arrival.metadata.historical_review={id:id(n),state:row(n).state,recorded_at:stamp};}if(kind==='time')o.arrival.metadata.observed_at=stamp;if(kind==='revision')o.arrival.metadata.analysis.revision=8;if(kind==='extra-destination')Object.assign(o.arrival,{source_body:'PRIVATE'});
    expect(()=>validateCarriedDestinationArrivalReturn(o,f.i)).toThrow();let n=0;const b=new PortfolioReturnBook(()=>0,()=>(++n).toString(16).padStart(32,'0')),first=b.put(f.i);for(let k=0;k<7;k++)b.put(f.i);expect(()=>b.putCarriedDestinationArrivalReturn(f.i,o)).toThrow();expect(n).toBe(8);expect(b.get(first)).toEqual(f.i);
  });
  it.each(['customer_ids','date_field','date_from','date_to','source_date_from','source_date_to','bucket'] as const)('rejects changed exact %s filter',async kind=>{const f=await savedArrival(),h=freshArrival(),p=page(h);if(kind==='customer_ids')p.filters.customer_ids=['A'];else if(kind==='date_field')p.filters.date_field='created_at';else if(kind==='bucket')p.filters.bucket='action_required';else p.filters[kind]='';expect(()=>reconcile(f,h,p)).toThrow();});
  it.each(['selected','head3','head4','head5','head6','head7','head8','head9','revision','time','manifest','version','scope','extra'] as const)('rejects fresh immutable or regressive %s',async kind=>{
    const d=destinationArrival(9);d.context_navigation.analysis.revision=10;const f=await savedArrival(d),h=freshArrival(9);h.context_navigation.analysis.revision=10;if(kind==='selected'){h.selected_review.packet_sha256='e'.repeat(64);h.lineage.items[0].packet_sha256='e'.repeat(64);}if(kind.startsWith('head')){const n=Number(kind.slice(4));h.current_head=row(n);h.current_head.packet_sha256='e'.repeat(64);h.context_navigation.historical_review={id:id(n),state:row(n).state,recorded_at:stamp};}
    if(kind==='revision')h.context_navigation.analysis.revision=9;if(kind==='time')h.observed_at=h.context_navigation.observed_at='2026-10-15T02:08:30Z';if(kind==='manifest')h.context_navigation.context.manifest_sha256='e'.repeat(64);if(kind==='version')h.context_navigation.context.version_id='other';if(kind==='scope')h.matter_id='foreign';if(kind==='extra')Object.assign(h,{source_body:'PRIVATE'});expect(()=>reconcile(f,h)).toThrow();
  });
  it('keeps bounded omissions private and rejects fallback metadata or regressive queue clocks',async()=>{
    const f=await savedArrival(),p=page(freshArrival());p.items=[];p.coverage.returned_count=0;const v=reconcileCarriedDestinationArrivalReturn(f.i,f.observation,p,null,null);expect(v).toEqual({state:'not_observed',queue_observed_at:p.observed_at});const html=renderToStaticMarkup(<CarriedDestinationArrivalReturnPanel observation={f.observation} value={v}/>);expect(html).toContain('bu pencerede gözlenmedi');for(const word of [ctx,id(2),'frozen','carried-next-version'])expect(html).not.toContain(word);expect(()=>reconcileCarriedDestinationArrivalReturn(f.i,f.observation,p,f.d.context_navigation,f.d)).toThrow();const old=structuredClone(p);old.observed_at='2026-10-15T02:08:30Z';expect(()=>reconcileCarriedDestinationArrivalReturn(f.i,f.observation,old,null,null)).toThrow();
  });
  it('clones bounded principal memory and preserves unchanged earlier projections',async()=>{
    const f=await savedArrival(),saved=structuredClone(f.observation);let now=0,n=0;const b=new PortfolioReturnBook(()=>now,()=>(++n).toString(16).padStart(32,'0')),t=b.putCarriedDestinationArrivalReturn(f.i,f.observation);f.observation.arrival.metadata.analysis.current_version_id='mutated';expect(b.getCarriedDestinationArrivalReturn(t)).toEqual(saved);b.getCarriedDestinationArrivalReturn(t)!.handoff.observed_at[0]=stamp;expect(b.getCarriedDestinationArrivalReturn(t)).toEqual(saved);
    const prior=saved.handoff.observation;expect(b.getCarriedDestinationReturn(t)).toEqual(prior);const c=prior.handoff.observation;expect(b.getCarriedArrivalReturn(t)).toEqual(c);expect(b.getOnwardReturn(t)).toEqual(c.handoff.observation);expect(b.getArrivalReturn(t)).toEqual(c.handoff.observation.handoff.observation);expect(b.getComparisonReturn(t)).toEqual(c.handoff.observation.handoff.observation.handoff.receipt);expect(b.getCarriedArrivalEvent(t)).toBeNull();for(let k=0;k<8;k++)b.putCarriedDestinationArrivalReturn(f.i,saved);expect(b.getCarriedDestinationArrivalReturn(t)).toBeNull();const last=b.putCarriedDestinationArrivalReturn(f.i,saved);now=30*60*1000;expect(b.getCarriedDestinationArrivalReturn(last)).toBeNull();expect(new PortfolioReturnBook().getCarriedDestinationArrivalReturn(last)).toBeNull();const p=new PrincipalReturnBook(),token=p.forPrincipal('A').putCarriedDestinationArrivalReturn(f.i,saved);expect(p.forPrincipal('B').getCarriedDestinationArrivalReturn(token)).toBeNull();expect(p.forPrincipal('A').getCarriedDestinationArrivalReturn(token)).toBeNull();expect(b.getCarriedDestinationArrivalReturn(b.put(f.i))).toBeNull();expect(b.getCarriedDestinationArrivalReturn('bad')).toBeNull();
  });
  it('renders independent metadata observations without actions, source bodies or inherited approval',async()=>{const f=await savedArrival(),html=renderToStaticMarkup(<CarriedDestinationArrivalReturnPanel observation={f.observation} value={reconcile(f)}/>);for(const word of [id(1),id(2),id(3),id(4),id(5),id(6),id(7),id(8),'frozen','queue-version','onward-version','carry-version','carried-next-version','önceki onay taşınmaz','Bekleyen kabul tamamlanmadı'])expect(html).toContain(word);expect(html).not.toMatch(/<(a |button|input|textarea|form)/);expect(html).not.toContain('PRIVATE TITLE');});
});
