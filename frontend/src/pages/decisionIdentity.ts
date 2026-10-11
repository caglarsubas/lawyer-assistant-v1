import { request } from '../api';
import type { SourceReviewDecision, User } from '../types';
import type { DecisionState } from './decisionMapping';
import { sourceReviewPath } from './SourceReviewPage';
import { comparisonHash } from './sourceComparison';

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

export interface GraphBHandoff {
  schema_version: 'decision-graph-b-handoff-v1'; packet_id: string; confidentiality: 'firm_confidential'; firm_id: string;
  source_binding: { source_id: string; artifacts: IdentityState['source']['artifacts'] };
  identity_revision: number; mapping_revision: number; source_review_revision: number; ontology_sha256: string;
  compiler_version: string; identity_history: IdentityEvent[]; history_complete: true;
  source_review_history: { revision: number }[]; mapping_history: { revision: number }[];
  files: Record<string, { sha256: string; bytes: number; encoding: 'base64'; data: string }>;
  structural_validation: { conforms: true; assertion_count: 3; legal_truth_verified: false };
  scope: 'own_decision_identity_candidates_only'; omitted_mapping_ids: string[];
  signed: false; graph_updated: false; global_registry_qualified: false; legal_effect_verified: false; publication_eligible: false;
  limitations: string[];
}
function sortedJson(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(sortedJson).join(',')}]`;
  if (value !== null && typeof value === 'object') return `{${Object.entries(value).sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0).map(([key, item]) => `${JSON.stringify(key)}:${sortedJson(item)}`).join(',')}}`;
  return JSON.stringify(value);
}
export async function fetchGraphBHandoff(state: IdentityState, user: User, signal?: AbortSignal) {
  const envelope = await request<{ evidence_json: string; evidence_sha256: string }>(`${identityPath(state.source.id)}/graph-b-handoff`, {
    method: 'POST', body: JSON.stringify({ expected_revision: state.revision, expected_mapping_revision: state.mapping_revision,
      expected_source_review_revision: state.source_review_revision }), signal,
  });
  if (typeof envelope?.evidence_json !== 'string' || new TextEncoder().encode(envelope.evidence_json).length > 8 * 1024 * 1024
    || envelope.evidence_sha256 !== await comparisonHash(envelope.evidence_json)) throw new Error('Graph B paketinin içerik özeti doğrulanamadı.');
  let data: GraphBHandoff;
  try { data = JSON.parse(envelope.evidence_json); } catch { throw new Error('Graph B paketi okunamadı.'); }
  const files = data?.files;
  if (data.schema_version !== 'decision-graph-b-handoff-v1' || data.compiler_version !== data.schema_version || data.scope !== 'own_decision_identity_candidates_only'
    || data.confidentiality !== 'firm_confidential' || data.firm_id !== user.firm_id || data.source_binding?.source_id !== state.source.id
    || data.identity_revision !== state.revision || data.mapping_revision !== state.mapping_revision || data.source_review_revision !== state.source_review_revision
    || data.history_complete !== true || !/^[a-f0-9]{64}$/.test(data.ontology_sha256)
    || [data.signed, data.graph_updated, data.global_registry_qualified, data.legal_effect_verified, data.publication_eligible, data.structural_validation?.legal_truth_verified].some(value => value !== false)
    || data.structural_validation?.conforms !== true || data.structural_validation.assertion_count !== 3
    || !Array.isArray(data.identity_history) || data.identity_history.length !== state.revision
    || data.identity_history.some((event, index) => event.revision !== index + 1)
    || sortedJson(data.identity_history.at(-1)) !== sortedJson(state.current)
    || !Array.isArray(data.mapping_history) || data.mapping_history.length !== state.mapping_revision
    || data.mapping_history.some((event, index) => event.revision !== state.mapping_revision - index)
    || !Array.isArray(data.source_review_history) || data.source_review_history.length !== state.source_review_revision
    || data.source_review_history.some((event, index) => event.revision !== state.source_review_revision - index)
    || sortedJson(data.source_binding.artifacts) !== sortedJson(state.source.artifacts)
    || !files || Object.keys(files).sort().join(',') !== [...Object.keys(state.source.artifacts).map(name => `original/${name}`), 'candidate/locators.json', 'candidate/jurisprudence.nt'].sort().join(',')) throw new Error('Graph B paketi seçili büro, kaynak ve inceleme revizyonlarıyla eşleşmiyor.');
  const metadata: Record<string, Omit<GraphBHandoff['files'][string], 'data'>> = {};
  for (const [name, entry] of Object.entries(files)) {
    if (!Number.isSafeInteger(entry.bytes) || entry.bytes < 1 || entry.bytes > 2 * 1024 * 1024 || entry.encoding !== 'base64'
      || typeof entry.data !== 'string' || !/^[A-Za-z0-9+/]*={0,2}$/.test(entry.data) || !/^[a-f0-9]{64}$/.test(entry.sha256)) throw new Error('Graph B fiziksel dosya sözleşmesi geçersiz.');
    const bytes = Uint8Array.from(atob(entry.data), char => char.charCodeAt(0));
    const hash = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)), value => value.toString(16).padStart(2, '0')).join('');
    const original = name.startsWith('original/') ? state.source.artifacts[name.slice(9)] : null;
    if (bytes.length !== entry.bytes || hash !== entry.sha256 || (original && (entry.sha256 !== original.sha256 || entry.bytes !== original.bytes))) throw new Error('Graph B fiziksel dosya özeti veya kaynak bağı doğrulanamadı.');
    metadata[name] = { sha256: entry.sha256, bytes: entry.bytes, encoding: entry.encoding };
  }
  const { packet_id, ...core } = data;
  if (packet_id !== await comparisonHash(sortedJson({ ...core, files: metadata }))) throw new Error('Graph B paket kimliği doğrulanamadı.');
  signal?.throwIfAborted();
  return { data, evidence_json: envelope.evidence_json, evidence_sha256: envelope.evidence_sha256 };
}
