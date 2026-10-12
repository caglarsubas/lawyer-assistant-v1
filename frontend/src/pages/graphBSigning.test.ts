import { describe, expect, it } from 'vitest';
import type { User } from '../types';
import { sortedJson } from './decisionIdentity';
import type { EquivalenceState } from './decisionEquivalence';
import { validateSigningPacket, type GraphBSigningPacket } from './graphBSigning';
import type { SignedGraphBState } from './signedGraphBReview';
import { comparisonHash } from './sourceComparison';

const state = { context_id: 'c'.repeat(64), revision: 2, same_decision_supported: true, export_allowed: true, stale: false, inputs_ready: true,
  pins: { source_revisions: {['a'.repeat(64)]: 6}, mapping_revisions: {}, identity_revisions: {} } } as EquivalenceState;
const user = {firm_id: 'firm'} as User;
function review(): SignedGraphBState {
  const event = { id: 'event', revision: 1, actor: {id:'reviewer',name:'Test reviewer'}, envelope: { algorithm: 'Ed25519', signature: 'TEST-ONLY', body: { firm_id:'firm',context_id:state.context_id,reviewer_id:'reviewer',decision: 'approve', expected_review_revision: 0,
    equivalence_revision: 2, ontology_sha256: 'd'.repeat(64), qualifications: {decision_on:'2021-01-12'}, public_reviewer: 'TEST-ONLY PUBLIC EDITOR', reviewed_at: '2026-10-12T00:00:00Z' } } };
  return {schema_version:'signed-graph-b-review-v1',confidentiality:'firm_confidential',firm_id:'firm',context_id:state.context_id,revision:1,
    history_complete:true,history:[event],current:event,stale:false,trust_configured:true,signed_review_current:true,
    graph_updated:false,publication_eligible:false,legal_truth_verified:false,institutional_competence_verified:false,finality_verified:false} as SignedGraphBState;
}
async function fixture() {
  const signed = review(); const files: GraphBSigningPacket['files'] = {};
  async function add(name: string, text: string) { const bytes = new TextEncoder().encode(text); files[name] = {sha256: await comparisonHash(text),bytes: bytes.length,encoding:'base64',data:btoa(String.fromCharCode(...bytes))}; }
  await add('inputs/structure.ttl','\n'); await add('inputs/jurisprudence.ttl','# invented Turkish Unicode ıİğĞ\n');
  for (const text of ['raw fixture bytes','text fixture ıİğĞ','locator fixture']) await add(`evidence/${await comparisonHash(text)}.bin`,text);
  await add('public-review-body.json',sortedJson({reviewer:signed.current!.envelope.body.public_reviewer,reviewed_at:signed.current!.envelope.body.reviewed_at,decision:'approve',scope:'national_ontology_and_assertions',ontology_sha256:'d'.repeat(64),input_graphs_sha256:{structure:files['inputs/structure.ttl'].sha256,jurisprudence:files['inputs/jurisprudence.ttl'].sha256}}));
  await add('NOTICE.json',sortedJson({signed:false,publication_eligible:false}));
  const data = {schema_version:'qualified-graph-b-signing-inputs-v1',confidentiality:'firm_confidential',firm_id:'firm',context_id:state.context_id,
    signed_review_revision:1,equivalence_revision:2,pins:state.pins,signed_review_sha256:await comparisonHash(sortedJson(signed.current!.envelope)),ontology_sha256:'d'.repeat(64),
    public_input_paths:Object.keys(files).filter(name=>name!=='NOTICE.json').sort(),files,structural_preflight:{conforms:true,assertion_count:6,legal_truth_verified:false},signed:false,publication_eligible:false,graph_updated:false,identity_reservations_changed:false,institutional_competence_verified:false,finality_verified:false} as Omit<GraphBSigningPacket,'packet_id'>;
  const metadata = Object.fromEntries(Object.entries(files).map(([name,{data:unused,...entry}])=>[name,entry]));
  return {signed,data:{...data,packet_id:await comparisonHash(sortedJson({...data,files:metadata}))}};
}
async function envelope(data: unknown) { const evidence_json=sortedJson(data);return {evidence_json,evidence_sha256:await comparisonHash(evidence_json)}; }

describe('qualified Graph B signing inputs',()=>{
  it('checks exact signed-review, packet and every Unicode file before download',async()=>{
    const f=await fixture();expect(await validateSigningPacket(await envelope(f.data),state,f.signed,user)).toEqual(f.data);
  });
  it.each(['firm','context','review-revision','equivalence','pins','review-hash','ontology','publication','competence','preflight','missing-file','extra-private-file','public-notice','raw-hash','raw-bytes','raw-data','raw-name','packet'])('withholds mismatched %s inputs',async change=>{
    const f=await fixture(); const value=f.data;
    if(change==='firm')value.firm_id='other';if(change==='context')value.context_id='e'.repeat(64);
    if(change==='review-revision')value.signed_review_revision=2;if(change==='equivalence')value.equivalence_revision=1;
    if(change==='pins')value.pins={...value.pins,source_revisions:{}};if(change==='review-hash')value.signed_review_sha256='e'.repeat(64);
    if(change==='ontology')value.ontology_sha256='e'.repeat(64);if(change==='publication')Object.assign(value,{publication_eligible:true});
    if(change==='competence')Object.assign(value,{institutional_competence_verified:true});if(change==='preflight')Object.assign(value.structural_preflight,{assertion_count:3});
    if(change==='missing-file')delete value.files['inputs/structure.ttl'];if(change==='extra-private-file')value.files['private-credential.bin']=value.files['NOTICE.json'];
    if(change==='public-notice')value.public_input_paths.push('NOTICE.json');
    if(change==='raw-hash')value.files['inputs/jurisprudence.ttl'].sha256='f'.repeat(64);
    if(change==='raw-bytes')value.files['inputs/jurisprudence.ttl'].bytes+=1;
    if(change==='raw-data')value.files['inputs/jurisprudence.ttl'].data=btoa('tampered');
    if(change==='raw-name'){const name=value.public_input_paths.find(name=>name.startsWith('evidence/'))!;value.files[`evidence/${'f'.repeat(64)}.bin`]=value.files[name];delete value.files[name];value.public_input_paths=Object.keys(value.files).filter(name=>name!=='NOTICE.json').sort();}
    if(change==='packet')value.packet_id='f'.repeat(64);
    await expect(validateSigningPacket(await envelope(value),state,f.signed,user)).rejects.toThrow();
  });
  it.each(['stale','missing-trust','negative','no-export','wrong-envelope'])('withholds invalid live %s context',async change=>{
    const f=await fixture(); const current={...state}; const encoded=await envelope(f.data);
    if(change==='stale')f.signed.stale=true;if(change==='missing-trust')f.signed.trust_configured=false;
    if(change==='negative')f.signed.signed_review_current=false;if(change==='no-export')current.export_allowed=false;
    if(change==='wrong-envelope')encoded.evidence_sha256='f'.repeat(64);
    await expect(validateSigningPacket(encoded,current,f.signed,user)).rejects.toThrow();
  });
});
