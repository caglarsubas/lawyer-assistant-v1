import { afterEach, describe, expect, it, vi } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { IdentitySummary } from './DecisionIdentityReview';
import { evidence, fetchIdentities, identityProposalPayload, mayIndependentlyReview, validateIdentityState, type IdentityState } from './decisionIdentity';
import type { DecisionState } from './decisionMapping';
import type { User } from '../types';
const id = 'a'.repeat(64);
const source = { source: { id, source_version_id: 'v1' }, revision: 2, source_review_revision: 5 } as DecisionState;
const identity = { institution_id: 'urn:tr-law:institution:test', proceeding_id: 'urn:tr-law:proceeding:test', decision_id: 'urn:tr-law:decision:test',
  identity_evidence: evidence('Synthetic identity register', 'b'.repeat(64)), institution_evidence: evidence('Synthetic institution register', 'c'.repeat(64)) };
function fixture() {
  const event = { id: 'event', revision: 1, action: 'propose' as const, actor: { id: 'owner', name: '<script>synthetic</script>' }, created_at: '2026-10-11T12:00:00Z', rationale: '<img src=x>', decision: null, evidence_refs: [],
    proposal: { identity, version_id: 'urn:tr-law:decision-version:' + 'd'.repeat(64), proposer: { id: 'owner', name: 'Synthetic owner' }, mapping_revision: 2, source_review_revision: 5,
      snapshot_sha256: 'e'.repeat(64), contributors: ['historical-contributor'], own_mapping_ids: ['mapping'], local_references: { decision_ref: 'd', proceeding_ref: 'p', institution_ref: 'i' } } };
  return { schema_version: 'decision-identity-review-v1', source: source.source, revision: 1, mapping_revision: 2, source_review_revision: 5, assigned_to: event.actor,
    current: event, history: [event], stale: false, source_review_ready: true, export_allowed: false, can_independently_review: true, canonical_identity_reviewed: false,
    staged_handoff_ready: false, global_registry_qualified: false, legal_effect_verified: false, publication_eligible: false } as IdentityState;
}
afterEach(() => vi.unstubAllGlobals());
describe('canonical identity review', () => {
  it('pins all three review versions and requires explicit typed IDs and evidence', () => {
    expect(identityProposalPayload(fixture(), identity, 'Synthetic rationale')).toMatchObject({ expected_revision: 1, expected_mapping_revision: 2, expected_source_review_revision: 5, identity });
    expect(() => identityProposalPayload(fixture(), { ...identity, decision_id: '2020/5' }, 'Synthetic rationale')).toThrow();
    expect(() => identityProposalPayload(fixture(), { ...identity, institution_evidence: [] }, 'Synthetic rationale')).toThrow();
    expect(() => evidence('Synthetic', 'bad')).toThrow();
  });
  it('blocks proposer, historical contributors and stale reviews', () => {
    const state = fixture(); expect(mayIndependentlyReview(state, { id: 'owner' } as User)).toBe(false);
    expect(mayIndependentlyReview(state, { id: 'historical-contributor' } as User)).toBe(false);
    expect(mayIndependentlyReview(state, { id: 'independent' } as User)).toBe(true);
    expect(mayIndependentlyReview({ ...state, stale: true }, { id: 'independent' } as User)).toBe(false);
  });
  it('fetches only the validated selected source', async () => {
    const mock = vi.fn().mockResolvedValue(new Response(JSON.stringify(fixture()))); vi.stubGlobal('fetch', mock);
    expect(await fetchIdentities(source)).toEqual(fixture()); expect(mock.mock.calls[0][0]).toContain(`${id}/decision-identities`);
  });
  it.each(['source', 'mapping', 'review', 'publication', 'history', 'head'])('withholds mismatched %s state', change => {
    const state = structuredClone(fixture());
    if (change === 'source') state.source.id = 'f'.repeat(64); if (change === 'mapping') state.mapping_revision++; if (change === 'review') state.source_review_revision++;
    if (change === 'publication') Object.assign(state, { publication_eligible: true }); if (change === 'history') state.history = []; if (change === 'head') state.current = { ...state.current!, rationale: 'forged' };
    expect(() => validateIdentityState(state, source)).toThrow();
  });
  it('escapes all historical evidence and exposes unqualified legal effects', () => {
    const markup = renderToStaticMarkup(<IdentitySummary state={{ ...fixture(), stale: true }} />);
    expect(markup).toContain('Yeniden inceleme gerekli'); expect(markup).toContain('Graf yayımlanmadı'); expect(markup).toContain('Hukuki etki ve kesinleşme bilinmiyor');
    expect(markup).not.toContain('<script>'); expect(markup).not.toContain('<img'); expect(markup).toContain('Tam kimlik inceleme geçmişi');
  });
});
