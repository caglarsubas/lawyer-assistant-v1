import { afterEach, describe, expect, it, vi } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { EquivalenceSummary } from './DecisionEquivalenceReview';
import { equivalencePayload, fetchEquivalence, mayReviewEquivalence, validateEquivalence, validateSelection, type EquivalenceState } from './decisionEquivalence';
import type { IdentityState } from './decisionIdentity';
import type { User } from '../types';
const ids = ['a', 'b', 'c'].map(char => char.repeat(64));
const selection = { peer: ids[1], register: ids[2] };
const user = { id: 'independent', firm_id: 'firm' } as User;
const identity = { source: { id: ids[0], source_version_id: 'v1', artifacts: {} }, revision: 2, mapping_revision: 2, source_review_revision: 6 } as unknown as IdentityState;
function fixture(): EquivalenceState {
  const pins = { source_revisions: Object.fromEntries(ids.map(id => [id, 6])), mapping_revisions: { [ids[0]]: 2, [ids[1]]: 2, [ids[2]]: 0 }, identity_revisions: { [ids[0]]: 2, [ids[1]]: 2 } };
  const claims = { relation: 'same_decision' as const, canonical_decision_id: 'urn:tr-law:decision:one', institution_id: 'urn:tr-law:institution:test', registered_name: '<script>court</script>', register_record_id: 'register 7', evidence: ids.map(id => ({ source_id: id, passage_id: 'p2', sha256: 'd'.repeat(64) })) };
  const decisions = Object.fromEntries(ids.slice(0,2).map((id, i) => [id,{decision_id: i ? 'urn:tr-law:decision:two' : 'urn:tr-law:decision:one', proceeding_id: 'urn:tr-law:proceeding:one', institution_id: claims.institution_id, version_id: 'urn:tr-law:decision-version:'+id}]));
  const event = { id: 'synthetic-event', revision: 1, action: 'propose' as const, actor: { id: 'owner', name: '<img src=x>' }, created_at: '2026-10-12T00:00:00Z', rationale: 'Synthetic rationale', decision: null, evidence: [],
    proposal: { claims, decisions, pins, snapshot_sha256: 'e'.repeat(64), contributors: ['identity-reviewer', 'register-owner'], proposer: { id: 'owner', name: 'Synthetic owner' } } };
  return { schema_version: 'decision-equivalence-review-v1', confidentiality: 'firm_confidential', firm_id: 'firm', context_id: 'f'.repeat(64), decision_source_ids: ids.slice(0, 2), register_source_id: ids[2],
    sources: Object.fromEntries(ids.map(id => [id, { id, title: 'Synthetic source', source_version_id: 'v1', artifacts: {} }])), decisions, revision: 1, pins, current: event, history: [event], history_complete: true,
    stale: false, inputs_ready: true, export_allowed: true, can_propose: false, can_independently_review: true, review_accepted: false, same_decision_supported: false,
    identity_reservations_changed: false, global_registry_qualified: false, legal_effect_verified: false, institutional_competence_verified: false, publication_eligible: false } as unknown as EquivalenceState;
}
afterEach(() => vi.unstubAllGlobals());
describe('reviewed cross-source identity claims', () => {
  it('requires two decision sources and a separate retained register', () => {
    expect(validateSelection(ids[0], selection)).toEqual(selection);
    expect(() => validateSelection(ids[0], { ...selection, register: ids[0] })).toThrow();
    expect(() => validateSelection(ids[0], { ...selection, peer: 'https://court.gov.tr' })).toThrow();
  });
  it('fetches the exact selected context without provider or graph mutations', async () => {
    const mock = vi.fn().mockResolvedValue(new Response(JSON.stringify(fixture()))); vi.stubGlobal('fetch', mock);
    expect(await fetchEquivalence(identity, user, selection)).toEqual(fixture());
    expect(mock).toHaveBeenCalledTimes(1); expect(mock.mock.calls[0][0]).toContain(`/decision-equivalence?peer_source_id=${ids[1]}&register_source_id=${ids[2]}`);
  });
  it.each(['firm', 'source', 'peer', 'register', 'identity', 'mapping', 'review', 'publication', 'institution', 'history', 'head', 'stale-acceptance'])('rejects mismatched %s state', change => {
    const state = structuredClone(fixture());
    if (change === 'firm') state.firm_id = 'other'; if (change === 'source') state.sources[ids[0]].source_version_id = 'changed';
    if (change === 'peer') state.decision_source_ids = [ids[0], 'e'.repeat(64)]; if (change === 'register') state.register_source_id = ids[1];
    if (change === 'identity') state.pins.identity_revisions[ids[0]]++; if (change === 'mapping') state.pins.mapping_revisions[ids[0]]++; if (change === 'review') state.pins.source_revisions[ids[0]]++;
    if (change === 'publication') Object.assign(state, { publication_eligible: true }); if (change === 'institution') Object.assign(state, { institutional_competence_verified: true });
    if (change === 'history') state.history = []; if (change === 'head') state.current = { ...state.current!, rationale: 'forged' }; if (change === 'stale-acceptance') Object.assign(state, { stale: true, review_accepted: true });
    expect(() => validateEquivalence(state, identity, user, selection)).toThrow();
  });
  it('excludes source, register and prior identity contributors, plus proposer and stale context', () => {
    expect(mayReviewEquivalence(fixture(), user)).toBe(true);
    for (const id of ['owner', 'identity-reviewer', 'register-owner']) expect(mayReviewEquivalence(fixture(), { ...user, id })).toBe(false);
    expect(mayReviewEquivalence({ ...fixture(), stale: true }, user)).toBe(false);
  });
  it('pins all source, mapping and identity revisions and requires exact proofs from three sources', () => {
    const state = fixture(); const claims = state.current!.proposal.claims;
    expect(equivalencePayload(state, 'Synthetic rationale', claims.evidence, claims)).toMatchObject({ expected_revision: 1, pins: state.pins, claims });
    expect(() => equivalencePayload(state, 'Synthetic rationale', claims.evidence.slice(0, 2), claims)).toThrow();
    expect(() => equivalencePayload(state, 'Synthetic rationale', claims.evidence.map((p, i) => i ? p : { ...p, sha256: 'wrong' }), claims)).toThrow();
    expect(() => equivalencePayload(state, 'no', claims.evidence, claims)).toThrow();
  });
  it('escapes complete preserved opinions and exposes institutional and legal limits', () => {
    const markup = renderToStaticMarkup(<EquivalenceSummary state={{ ...fixture(), stale: true }} />);
    expect(markup).not.toContain('<script>'); expect(markup).not.toContain('<img'); expect(markup).toContain('Yeniden inceleme gerekli');
    expect(markup).toContain('Kimlikler birleştirilmedi'); expect(markup).toContain('tarihsel geçerlilik doğrulanmadı'); expect(markup).toContain('Tam eşdeğerlik ve sicil inceleme geçmişi');
  });
});
