import { afterEach, describe, expect, it, vi } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import type { User } from '../types';
import { EquivalenceHandoffSummary } from './DecisionEquivalenceReview';
import type { EquivalenceState } from './decisionEquivalence';
import { sortedJson } from './decisionIdentity';
import { fetchEquivalenceHandoff, type EquivalenceHandoff } from './equivalenceHandoff';
import { comparisonHash } from './sourceComparison';

const ids = ['a', 'b', 'c'].map(value => value.repeat(64));
const selection = { peer: ids[1], register: ids[2] }; const user = { id: 'reviewer', firm_id: 'firm' } as User;
async function fixture() {
  const original = 'Synthetic original'; const hash = await comparisonHash(original);
  const artifacts = { 'source.bin': { sha256: hash, bytes: original.length } };
  const pins = { source_revisions: Object.fromEntries(ids.map(id => [id, 6])), mapping_revisions: { [ids[0]]: 2, [ids[1]]: 2, [ids[2]]: 0 }, identity_revisions: { [ids[0]]: 2, [ids[1]]: 2 } };
  const decisions = Object.fromEntries(ids.slice(0, 2).map((id, i) => [id, { decision_id: `urn:tr-law:decision:${i}`, proceeding_id: 'urn:tr-law:proceeding:one', institution_id: 'urn:tr-law:institution:one', version_id: `urn:tr-law:decision-version:${id}` }]));
  const current = { revision: 2, decision: 'accepted', proposal: { claims: { relation: 'same_decision', canonical_decision_id: decisions[ids[0]].decision_id }, decisions } };
  const state = { firm_id: user.firm_id, context_id: 'd'.repeat(64), revision: 2, pins, current, history: [current, { ...current, revision: 1, decision: null }],
    sources: Object.fromEntries(ids.map(id => [id, { id, artifacts }])), decisions, decision_source_ids: ids.slice(0,2), register_source_id: ids[2],
    inputs_ready: true, stale: false, export_allowed: true, same_decision_supported: true } as unknown as EquivalenceState;
  const files: EquivalenceHandoff['files'] = {};
  const names = ['candidate/jurisprudence.nt', ...ids.flatMap(id => [`original/${id}/source.bin`, `candidate/${id}/locators.json`])];
  for (const name of names) files[name] = { sha256: hash, bytes: original.length, encoding: 'base64', data: btoa(original) };
  const data = { schema_version: 'decision-equivalence-graph-b-handoff-v1', compiler_version: 'decision-equivalence-graph-b-handoff-v1', confidentiality: 'firm_confidential', firm_id: user.firm_id,
    context_id: state.context_id, equivalence_revision: 2, pins, decision_source_ids: state.decision_source_ids, register_source_id: ids[2], canonical_candidate: decisions[ids[0]].decision_id, original_decisions: decisions,
    source_bindings: Object.fromEntries(ids.map(id => [id,{ source_id: id, artifacts }])), ontology_sha256: 'e'.repeat(64), equivalence_history: state.history.slice().reverse(),
    identity_histories: Object.fromEntries(ids.slice(0,2).map(id => [id,[1,2].map(revision => ({ revision, decision: revision === 2 ? 'accepted' : null, proposal: { identity: decisions[id], version_id: decisions[id].version_id } }))])),
    source_review_histories: Object.fromEntries(ids.map(id => [id,[6,5,4,3,2,1].map(revision => ({ revision }))])),
    mapping_histories: Object.fromEntries(ids.map((id, i) => [id, (i < 2 ? [2,1] : []).map(revision => ({ revision }))])), history_complete: true, files,
    structural_validation: { conforms: true, assertion_count: 6, legal_truth_verified: false }, omitted_mapping_ids: Object.fromEntries(ids.map(id => [id,[]])),
    scope: 'reviewed_equivalence_identity_candidates_only', signed: false, graph_updated: false, identity_reservations_changed: false, global_registry_qualified: false,
    legal_effect_verified: false, institutional_competence_verified: false, publication_eligible: false, limitations: ['<script>synthetic fixture</script>'] } as unknown as EquivalenceHandoff;
  return {state, data};
}
async function envelope(data: EquivalenceHandoff) {
  const { packet_id: _, ...core } = data;
  core.files = Object.fromEntries(Object.entries(data.files).map(([name, {data: _, ...entry}]) => [name, entry])) as EquivalenceHandoff['files'];
  data.packet_id = await comparisonHash(sortedJson(core));
  const evidence_json = sortedJson(data); return { evidence_json, evidence_sha256: await comparisonHash(evidence_json) };
}
afterEach(() => vi.unstubAllGlobals());
describe('multi-source staged Graph B handoff', () => {
  it('verifies all retained bytes and complete private histories before download', async () => {
    const {state,data}=await fixture(); const value=await envelope(data);
    const mock=vi.fn().mockResolvedValue(new Response(JSON.stringify(value)));vi.stubGlobal('fetch',mock);
    expect((await fetchEquivalenceHandoff(state,ids[0],selection,user)).data).toEqual(data);
    expect(mock.mock.calls[0][0]).toContain('/decision-equivalence/graph-b-handoff?');
    expect(JSON.parse(mock.mock.calls[0][1].body)).toEqual({expected_revision:2,pins:state.pins});
  });
  it.each(['firm','context','pin','anchor','original-id','source','history','identity-history','mapping-history','source-history','publication','competence','count','files','bytes','hash'])('rejects rehashed tampered %s',async change=>{
    const {state,data}=await fixture();
    if(change==='firm')data.firm_id='another';if(change==='context')data.context_id='a'.repeat(64);
    if(change==='pin')data.pins=structuredClone(data.pins),data.pins.source_revisions[ids[2]]++;
    if(change==='anchor')data.canonical_candidate='urn:tr-law:decision:other';
    if(change==='original-id')data.original_decisions=structuredClone(data.original_decisions),data.original_decisions[ids[1]].version_id='wrong';
    if(change==='source')data.source_bindings[ids[2]].source_id=ids[1];
    if(change==='history')data.equivalence_history=data.equivalence_history.slice(1);
    if(change==='identity-history')data.identity_histories[ids[0]]=data.identity_histories[ids[0]].slice(1);
    if(change==='mapping-history')data.mapping_histories[ids[0]]=[];if(change==='source-history')data.source_review_histories[ids[2]]=[];
    if(change==='publication')Object.assign(data,{publication_eligible:true});if(change==='competence')Object.assign(data,{institutional_competence_verified:true});
    if(change==='count')Object.assign(data.structural_validation,{assertion_count:3});if(change==='files')delete data.files[`original/${ids[2]}/source.bin`];
    if(change==='bytes')data.files[`original/${ids[2]}/source.bin`].bytes++;
    if(change==='hash'){const entry=data.files[`original/${ids[2]}/source.bin`];entry.data=btoa('Different bytes');entry.bytes=15;entry.sha256=await comparisonHash('Different bytes');}
    vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response(JSON.stringify(await envelope(data)))));
    await expect(fetchEquivalenceHandoff(state,ids[0],selection,user)).rejects.toThrow();
  });
  it('withholds stale, unaccepted or nonexportable contexts before requesting a packet',async()=>{
    const {state}=await fixture();const mock=vi.fn();vi.stubGlobal('fetch',mock);
    for(const change of [{stale:true},{export_allowed:false},{same_decision_supported:false}]) await expect(fetchEquivalenceHandoff({...state,...change},ids[0],selection,user)).rejects.toThrow();
    expect(mock).not.toHaveBeenCalled();
  });
  it('rejects envelope hash mismatch and cancellation after byte verification',async()=>{
    const {state,data}=await fixture();const value=await envelope(data);vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response(JSON.stringify({...value,evidence_sha256:'f'.repeat(64)}))));
    await expect(fetchEquivalenceHandoff(state,ids[0],selection,user)).rejects.toThrow();
    vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response(JSON.stringify(value))));const operation=new AbortController();operation.abort();
    await expect(fetchEquivalenceHandoff(state,ids[0],selection,user,operation.signal)).rejects.toThrow();
  });
  it('exposes private unpublished candidates and escapes limitations',async()=>{
    const {data}=await fixture();const markup=renderToStaticMarkup(<EquivalenceHandoffSummary data={data}/>);
    expect(markup).toContain('Altı yapı doğrulanmış kimlik adayı');expect(markup).toContain('Graf yayımlanmadı');expect(markup).toContain('Kimlik rezervasyonları korunuyor');expect(markup).not.toContain('<script>');
  });
});
