import { request } from '../api';
import type { SourceReviewDecision, User } from '../types';
import type { DecisionState } from './decisionMapping';
import { sourceReviewPath } from './SourceReviewPage';

type Reviewer = { id: string; name: string };
export type IdentityEvidence = { reference: string; sha256: string };
export interface CanonicalDecisionIdentity {
  institution_id: string; proceeding_id: string; decision_id: string;
  identity_evidence: IdentityEvidence[]; institution_evidence: IdentityEvidence[];
}
export interface IdentityEvent {
  id: string; revision: number; action: 'propose' | 'review'; actor: Reviewer; created_at: string;
  rationale: string; decision: SourceReviewDecision | null; evidence_refs: IdentityEvidence[];
  proposal: { identity: CanonicalDecisionIdentity; version_id: string; proposer: Reviewer;
    mapping_revision: number; source_review_revision: number; snapshot_sha256: string;
    contributors: string[]; own_mapping_ids: string[];
    local_references: { decision_ref: string; proceeding_ref: string; institution_ref: string } };
}
export interface IdentityState {
  schema_version: 'decision-identity-review-v1'; source: DecisionState['source']; revision: number;
  mapping_revision: number; source_review_revision: number; assigned_to: Reviewer | null;
  current: IdentityEvent | null; history: IdentityEvent[]; stale: boolean; source_review_ready: boolean;
  export_allowed: boolean; can_independently_review: boolean; canonical_identity_reviewed: boolean;
  staged_handoff_ready: boolean; global_registry_qualified: false; legal_effect_verified: false; publication_eligible: false;
}
export function identityPath(id: string) { return `${sourceReviewPath(id)}/decision-identities`; }
export function evidence(reference: string, sha256: string): IdentityEvidence[] {
  if (!reference.trim() || reference.length > 1000 || !/^[a-f0-9]{64}$/.test(sha256)) throw new Error('Dayanak referansı ve 64 karakter SHA256 gerekli.');
  return [{ reference: reference.trim(), sha256 }];
}
export function identityPins(state: IdentityState, rationale: string) {
  if (rationale.trim().length < 3 || rationale.length > 4000) throw new Error('Gerekçe 3–4000 karakter olmalı.');
  return { expected_revision: state.revision, expected_mapping_revision: state.mapping_revision,
    expected_source_review_revision: state.source_review_revision, rationale: rationale.trim() };
}
export function identityProposalPayload(state: IdentityState, identity: CanonicalDecisionIdentity, rationale: string) {
  for (const kind of ['institution', 'proceeding', 'decision'] as const) {
    if (!new RegExp(`^urn:tr-law:${kind}:[a-z0-9][a-z0-9.-]{0,119}$`).test(identity[`${kind}_id`])) throw new Error('Kurum, yargılama ve karar için açık kanonik kimlik gerekli.');
  }
  for (const refs of [identity.identity_evidence, identity.institution_evidence]) {
    if (!Array.isArray(refs) || refs.length < 1 || refs.length > 10 || new Set(refs.map(ref => `${ref.reference}:${ref.sha256}`)).size !== refs.length) throw new Error('Kimlik ve kurum dayanakları gerekli.');
    refs.forEach(ref => evidence(ref.reference, ref.sha256));
  }
  return { ...identityPins(state, rationale), identity };
}
export async function fetchIdentities(source: DecisionState, signal?: AbortSignal) {
  const state = await request<IdentityState>(identityPath(source.source.id), { signal });
  return validateIdentityState(state, source);
}
export function validateIdentityState(state: IdentityState, source: DecisionState) {
  if (state.schema_version !== 'decision-identity-review-v1' || state.source?.id !== source.source.id
    || state.source.source_version_id !== source.source.source_version_id
    || state.mapping_revision !== source.revision || state.source_review_revision !== source.source_review_revision
    || [state.global_registry_qualified, state.legal_effect_verified, state.publication_eligible].some(value => value !== false)
    || !Number.isSafeInteger(state.revision) || state.revision < 0 || state.revision > 100
    || !Array.isArray(state.history) || state.history.length !== state.revision
    || state.history.some((event, index) => event.revision !== state.revision - index)
    || (state.revision === 0 ? state.current !== null : JSON.stringify(state.current) !== JSON.stringify(state.history[0]))) throw new Error('Kimlik incelemesi seçili kaynak ve güncel revizyonlarla eşleşmiyor. Yenileyin.');
  return state;
}
export function mayIndependentlyReview(state: IdentityState, user: User) {
  const proposal = state.current?.proposal;
  return !!proposal && state.can_independently_review && !state.stale && user.id !== proposal.proposer.id && !proposal.contributors.includes(user.id);
}
