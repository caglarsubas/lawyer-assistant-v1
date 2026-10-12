import { request } from '../api';
import type { User } from '../types';
import { sortedJson } from './decisionIdentity';
import { comparisonHash } from './sourceComparison';
import { equivalencePath, type EquivalencePins, type EquivalenceState, type EvidenceSelection } from './decisionEquivalence';
import { validateSignedReview, type SignedGraphBState } from './signedGraphBReview';

export interface GraphBSigningPacket {
  schema_version: 'qualified-graph-b-signing-inputs-v1'; confidentiality: 'firm_confidential'; packet_id: string;
  firm_id: string; context_id: string; signed_review_revision: number; equivalence_revision: number; pins: EquivalencePins;
  signed_review_sha256: string; ontology_sha256: string; public_input_paths: string[];
  files: Record<string, { sha256: string; bytes: number; encoding: 'base64'; data: string }>;
  structural_preflight: { conforms: true; assertion_count: 6; legal_truth_verified: false };
  signed: false; publication_eligible: false; graph_updated: false; identity_reservations_changed: false;
  institutional_competence_verified: false; finality_verified: false;
}
export async function validateSigningPacket(envelope: { evidence_json: string; evidence_sha256: string }, state: EquivalenceState, review: SignedGraphBState, user: User) {
  validateSignedReview(review, state, user);
  if (!review.signed_review_current || !state.same_decision_supported || !state.export_allowed || state.stale || !state.inputs_ready
    || typeof envelope?.evidence_json !== 'string' || new TextEncoder().encode(envelope.evidence_json).length > 16 * 1024 * 1024
    || envelope.evidence_sha256 !== await comparisonHash(envelope.evidence_json)) throw new Error('Güncel imzalı inceleme ve tam paket özeti gerekli.');
  const data = JSON.parse(envelope.evidence_json) as GraphBSigningPacket;
  const same = (a: unknown, b: unknown) => sortedJson(a) === sortedJson(b);
  if (data?.schema_version !== 'qualified-graph-b-signing-inputs-v1' || data.confidentiality !== 'firm_confidential' || data.firm_id !== user.firm_id
    || data.context_id !== state.context_id || data.equivalence_revision !== state.revision || data.signed_review_revision !== review.revision || !same(data.pins, state.pins)
    || data.signed_review_sha256 !== await comparisonHash(sortedJson(review.current!.envelope)) || !/^[a-f0-9]{64}$/.test(data.ontology_sha256)
    || data.ontology_sha256 !== review.current!.envelope.body.ontology_sha256
    || [data.signed, data.publication_eligible, data.graph_updated, data.identity_reservations_changed, data.institutional_competence_verified, data.finality_verified,
      data.structural_preflight?.legal_truth_verified].some(value => value !== false) || data.structural_preflight?.conforms !== true || data.structural_preflight.assertion_count !== 6
    || !data.files || !Array.isArray(data.public_input_paths)) throw new Error('İmza girdileri seçili güncel incelemeyle eşleşmiyor.');
  const names = Object.keys(data.files).sort();
  if (names.length < 7 || names.length > 16 || !['NOTICE.json', 'inputs/structure.ttl', 'inputs/jurisprudence.ttl', 'public-review-body.json'].every(name => names.includes(name))
    || names.some(name => !['NOTICE.json', 'inputs/structure.ttl', 'inputs/jurisprudence.ttl', 'public-review-body.json'].includes(name) && !/^evidence\/[a-f0-9]{64}\.bin$/.test(name))
    || !same(data.public_input_paths, names.filter(name => name !== 'NOTICE.json'))) throw new Error('İmza girdilerinin tam dosya envanteri geçersiz.');
  const metadata: Record<string, Omit<GraphBSigningPacket['files'][string], 'data'>> = {}; const raw: Record<string, Uint8Array> = {}; let total = 0;
  for (const name of names) {
    const entry = data.files[name];
    if (!Number.isSafeInteger(entry.bytes) || entry.bytes < 1 || entry.bytes > 8 * 1024 * 1024 || entry.encoding !== 'base64'
      || typeof entry.data !== 'string' || !/^[A-Za-z0-9+/]*={0,2}$/.test(entry.data) || !/^[a-f0-9]{64}$/.test(entry.sha256)) throw new Error('İmza dosyasının boyutu veya özeti geçersiz.');
    const bytes = Uint8Array.from(atob(entry.data), char => char.charCodeAt(0)); total += bytes.length;
    const hash = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)), value => value.toString(16).padStart(2, '0')).join('');
    if (total > 12 * 1024 * 1024 || hash !== entry.sha256 || bytes.length !== entry.bytes || (name.startsWith('evidence/') && name !== `evidence/${hash}.bin`)) throw new Error('Fiziksel imza girdisi doğrulanamadı.');
    metadata[name] = { sha256: hash, bytes: entry.bytes, encoding: 'base64' }; raw[name] = bytes;
  }
  const body = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(raw['public-review-body.json']));
  if (!same(Object.keys(body).sort(), ['decision', 'input_graphs_sha256', 'ontology_sha256', 'reviewed_at', 'reviewer', 'scope']) || body.decision !== 'approve'
    || body.scope !== 'national_ontology_and_assertions' || body.ontology_sha256 !== data.ontology_sha256 || body.reviewer !== review.current!.envelope.body.public_reviewer
    || body.reviewed_at !== review.current!.envelope.body.reviewed_at || !same(body.input_graphs_sha256, { structure: metadata['inputs/structure.ttl'].sha256, jurisprudence: metadata['inputs/jurisprudence.ttl'].sha256 })) throw new Error('Kamu inceleme gövdesi dosya özetleriyle eşleşmiyor.');
  const { packet_id, ...core } = data;
  if (packet_id !== await comparisonHash(sortedJson({ ...core, files: metadata }))) throw new Error('İmza paketi kimliği doğrulanamadı.');
  return data;
}
export async function fetchGraphBSigning(state: EquivalenceState, review: SignedGraphBState, source: string, selection: EvidenceSelection, user: User, signal?: AbortSignal) {
  const path = equivalencePath(source, selection).replace('/decision-equivalence?', '/graph-b-review/signing-inputs?');
  const envelope = await request<{ evidence_json: string; evidence_sha256: string }>(path, { method: 'POST', signal, body: JSON.stringify({
    expected_review_revision: review.revision, expected_equivalence_revision: state.revision, pins: state.pins }) });
  const data = await validateSigningPacket(envelope, state, review, user); signal?.throwIfAborted(); return { data, evidence_json: envelope.evidence_json };
}
