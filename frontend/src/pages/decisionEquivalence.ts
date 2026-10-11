import { request } from '../api';
import type { PublicSourceDetail, SourceReviewDecision, User } from '../types';
import type { IdentityState } from './decisionIdentity';
import { identityPath } from './decisionIdentity';

export type EvidenceProof = { source_id: string; passage_id: string; sha256: string };
export type EquivalencePins = { source_revisions: Record<string, number>; mapping_revisions: Record<string, number>; identity_revisions: Record<string, number> };
export type DecisionSummary = { decision_id: string; proceeding_id: string; institution_id: string; version_id: string };
export type EquivalenceClaims = { relation: 'same_decision' | 'different_decision' | 'undetermined'; canonical_decision_id: string | null; institution_id: string; registered_name: string; register_record_id: string; evidence: EvidenceProof[] };
export type EquivalenceEvent = { id: string; revision: number; action: 'propose' | 'review'; actor: { id: string; name: string }; created_at: string; rationale: string; decision: SourceReviewDecision | null; evidence: EvidenceProof[];
  proposal: { claims: EquivalenceClaims; decisions: Record<string, DecisionSummary>; pins: EquivalencePins; snapshot_sha256: string; contributors: string[]; proposer: { id: string; name: string } } };
export interface EquivalenceState {
  schema_version: 'decision-equivalence-review-v1'; confidentiality: 'firm_confidential'; firm_id: string; context_id: string;
  decision_source_ids: string[]; register_source_id: string; sources: Record<string, PublicSourceDetail>;
  decisions: Record<string, DecisionSummary | null>;
  revision: number; pins: EquivalencePins; current: EquivalenceEvent | null; history: EquivalenceEvent[]; history_complete: true;
  stale: boolean; inputs_ready: boolean; export_allowed: boolean; can_propose: boolean; can_independently_review: boolean; review_accepted: boolean; same_decision_supported: boolean;
  identity_reservations_changed: false; global_registry_qualified: false; legal_effect_verified: false; institutional_competence_verified: false; publication_eligible: false;
}
export type EvidenceSelection = { peer: string; register: string };
export function validateSelection(source: string, selection: EvidenceSelection) {
  if (![source, selection.peer, selection.register].every(id => /^[a-f0-9]{64}$/.test(id)) || new Set([source, selection.peer, selection.register]).size !== 3) throw new Error('İki karar kaynağı ve ayrı sicil kaynağı için üç geçerli kaynak kimliği gerekli.');
  return selection;
}
export function equivalencePath(source: string, selection: EvidenceSelection, review = false) {
  validateSelection(source, selection);
  return `${identityPath(source).replace('/decision-identities', '/decision-equivalence')}${review ? '/review' : ''}?peer_source_id=${selection.peer}&register_source_id=${selection.register}`;
}
export function validateEquivalence(state: EquivalenceState, identity: IdentityState, user: User, selection: EvidenceSelection) {
  validateSelection(identity.source.id, selection);
  const ids = [identity.source.id, selection.peer, selection.register].sort().join(',');
  if (state?.schema_version !== 'decision-equivalence-review-v1' || state.confidentiality !== 'firm_confidential' || state.firm_id !== user.firm_id
    || state.register_source_id !== selection.register || state.decision_source_ids?.slice().sort().join(',') !== [identity.source.id, selection.peer].sort().join(',')
    || !/^[a-f0-9]{64}$/.test(state.context_id) || !state.sources || Object.keys(state.sources).sort().join(',') !== ids
    || Object.entries(state.sources).some(([key, value]) => value.id !== key)
    || state.sources[identity.source.id].source_version_id !== identity.source.source_version_id
    || JSON.stringify(state.sources[identity.source.id].artifacts) !== JSON.stringify(identity.source.artifacts)
    || !state.pins || Object.keys(state.pins.source_revisions).sort().join(',') !== ids || Object.keys(state.pins.mapping_revisions).sort().join(',') !== ids
    || Object.keys(state.pins.identity_revisions).sort().join(',') !== state.decision_source_ids.slice().sort().join(',')
    || state.pins.identity_revisions[identity.source.id] !== identity.revision || state.pins.mapping_revisions[identity.source.id] !== identity.mapping_revision || state.pins.source_revisions[identity.source.id] !== identity.source_review_revision
    || [state.identity_reservations_changed, state.global_registry_qualified, state.legal_effect_verified, state.institutional_competence_verified, state.publication_eligible].some(value => value !== false)
    || !state.decisions || Object.keys(state.decisions).sort().join(',') !== state.decision_source_ids.slice().sort().join(',')
    || !Number.isSafeInteger(state.revision) || state.revision < 0 || state.revision > 50 || !Array.isArray(state.history) || state.history.length !== state.revision
    || state.history_complete !== true || state.history.some((event, i) => event.revision !== state.revision - i)
    || (state.revision === 0 ? state.current !== null : JSON.stringify(state.current) !== JSON.stringify(state.history[0]))
    || (state.review_accepted && (state.stale || !state.inputs_ready || state.current?.decision !== 'accepted'))
    || (state.same_decision_supported && (!state.review_accepted || state.current?.proposal.claims.relation !== 'same_decision'))) throw new Error('Eşdeğerlik kaydı seçili büro, kaynaklar ve kimlik revizyonlarıyla eşleşmiyor. Yenileyin.');
  return state;
}
export async function fetchEquivalence(identity: IdentityState, user: User, selection: EvidenceSelection, signal?: AbortSignal) {
  const result = await request<EquivalenceState>(equivalencePath(identity.source.id, selection), { signal });
  return validateEquivalence(result, identity, user, selection);
}
export function mayReviewEquivalence(state: EquivalenceState, user: User) {
  return !!state.current && state.can_independently_review && state.inputs_ready && !state.stale
    && user.id !== state.current.proposal.proposer.id && !state.current.proposal.contributors.includes(user.id);
}
export function validateProofs(state: EquivalenceState, proofs: EvidenceProof[]) {
  if (proofs.length < 3 || proofs.length > 30 || new Set(proofs.map(p => `${p.source_id}:${p.passage_id}`)).size !== proofs.length
    || [...new Set(proofs.map(p => p.source_id))].sort().join(',') !== Object.keys(state.sources).sort().join(',')
    || proofs.some(p => !/^[A-Za-z][A-Za-z0-9_-]{0,79}$/.test(p.passage_id) || !/^[a-f0-9]{64}$/.test(p.sha256))) throw new Error('Her karar ve sicil kaynağından ayrı pasaj kimliği ve SHA256 gerekli.');
  return proofs;
}
export function equivalencePayload(state: EquivalenceState, rationale: string, proofs: EvidenceProof[], claims?: Omit<EquivalenceClaims, 'evidence'>, decision?: SourceReviewDecision) {
  if (rationale.trim().length < 3 || rationale.length > 4000) throw new Error('Gerekçe 3–4000 karakter olmalı.');
  validateProofs(state, proofs);
  const pins = { expected_revision: state.revision, pins: state.pins, rationale: rationale.trim() };
  if (claims) {
    if (!/^(same_decision|different_decision|undetermined)$/.test(claims.relation) || !/^urn:tr-law:institution:[a-z0-9][a-z0-9.-]{0,119}$/.test(claims.institution_id)
      || [claims.registered_name, claims.register_record_id].some(value => value.trim().length < 3 || value.length > 300 || /[\x00-\x1f]/.test(value))) throw new Error('Açık kurum kimliği, sicil kaydı ve karşılaştırma sonucu gerekli.');
    if (claims.relation === 'same_decision' ? !Object.values(state.decisions).some(value => value?.decision_id === claims.canonical_decision_id) : claims.canonical_decision_id !== null) throw new Error('Aynı karar için incelenmiş iki kimlikten kanonik aday seçin.');
    return { ...pins, claims: { ...claims, registered_name: claims.registered_name.trim(), register_record_id: claims.register_record_id.trim(), evidence: proofs } };
  }
  if (!decision) throw new Error('Bağımsız inceleme kararı gerekli.');
  return { ...pins, decision, evidence: proofs };
}
