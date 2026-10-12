import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { SignedGraphBSummary, signedReviewPath, validateSignedReview, type SignedGraphBState } from './GraphBReviewStatus';
import type { EquivalenceState } from './decisionEquivalence';
import type { User } from '../types';

const ids = ['a', 'b', 'c'].map(value => value.repeat(64));
const source = { context_id: 'd'.repeat(64), revision: 2 } as EquivalenceState;
const user = { firm_id: 'firm' } as User;
function state(): SignedGraphBState {
  const event = { id: 'test-event', revision: 1, created_at: '2026-10-12T00:00:00Z', actor: { id: 'reviewer', name: '<script>reviewer</script>' }, envelope: {
    algorithm: 'Ed25519', signature: 's', body: { firm_id: 'firm', context_id: source.context_id, decision: 'approve', public_reviewer: 'TEST-ONLY', reviewed_at: '2026-10-12T00:00:00Z', reviewer_id: 'reviewer', equivalence_revision: 2, expected_review_revision: 0, ontology_sha256: 'e'.repeat(64),
      qualifications: { decision_on: '2021-01-12', institution: { scope: 'historical_identity_only', registered_name: 'TEST-ONLY court', register_record_id: 'register 7', identity_window: { valid_from: '2020-01-01', valid_until: '2022-01-01', checked_through: null } },
        relations: ids.slice(0,2).flatMap(id => ['decidedIn','issuedBy','hasDecisionVersion'].map(relation => ({ source_id: id, relation, end_status: 'unknown', valid_from: null, valid_until: null, checked_through: null, rationale: 'Unknown applicability' }))) },
      appointment: { scope: 'TR_decision_identity_institution_temporal_review', valid_from: '2026-01-01', valid_until: '2027-01-01', statement: 'TEST-ONLY appointment' } } } };
  return { schema_version: 'signed-graph-b-review-v1', confidentiality: 'firm_confidential', firm_id: 'firm', context_id: source.context_id,
    revision: 1, history_complete: true, history: [event], current: event, stale: false, trust_configured: true, signed_review_current: true,
    graph_updated: false, publication_eligible: false, legal_truth_verified: false, institutional_competence_verified: false, finality_verified: false } as SignedGraphBState;
}
describe('signed qualification review disclosure', () => {
  it('selects the exact three-source review context', () => {
    expect(signedReviewPath(ids[0], {peer: ids[1],register: ids[2]})).toContain(`/graph-b-review?peer_source_id=${ids[1]}&register_source_id=${ids[2]}`);
    expect(validateSignedReview(state(),source,user)).toEqual(state());
  });
  it.each(['firm','context','history','head','stale','trust','equivalence','publication','credential','key'])('withholds mismatched or sensitive %s state', change => {
    const value = structuredClone(state());
    if(change==='firm')value.firm_id='other';if(change==='context')value.context_id='e'.repeat(64);
    if(change==='history')value.history=[];if(change==='head')value.current={...value.current!,revision:0};
    if(change==='stale')value.stale=true;if(change==='trust')value.trust_configured=false;
    if(change==='equivalence')value.current!.envelope.body.equivalence_revision=1;
    if(change==='publication')Object.assign(value,{publication_eligible:true});
    if(change==='credential')Object.assign(value.history[0],{credential_data:'PRIVATE credential bytes'});
    if(change==='key')Object.assign(value.history[0],{accepted_key:'PRIVATE historical PEM'});
    expect(()=>validateSignedReview(value,source,user)).toThrow();
  });
  it('escapes reviewer text and distinguishes signature, scope, dates and actual legal truth', () => {
    const html=renderToStaticMarkup(<SignedGraphBSummary state={state()}/>);
    expect(html).not.toContain('<script>');expect(html).toContain('Güncel bağımsız imza doğrulandı');
    expect(html).toContain('Graf yayımlanmadı');expect(html).toContain('Zamansal uygulanabilirlik bilinmiyor');
    expect(html).toContain('mesleki yeterliği veya hukuki doğruluğu tek başına kanıtlamaz');
  });
});

describe('negative qualification review', () => {
  it('retains explicit unknown dates on a negative opinion without an approval', () => {
    const value=state();value.signed_review_current=false;value.current!.envelope.body.decision='needs_changes';value.current!.envelope.body.qualifications.decision_on=null;
    expect(validateSignedReview(value,source,user)).toEqual(value);
    const html=renderToStaticMarkup(<SignedGraphBSummary state={value}/>);expect(html).toContain('Bilinmiyor; hukuki kabul yok');expect(html).toContain('Düzeltme gerekli');
  });
  it('withholds an approval claiming an unknown decision date', () => {
    const value=state();value.current!.envelope.body.qualifications.decision_on=null;
    expect(()=>validateSignedReview(value,source,user)).toThrow();
  });
});
