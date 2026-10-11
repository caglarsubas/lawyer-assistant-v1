import { request } from '../api';
import type { User } from '../types';
import { sortedJson, type IdentityEvent } from './decisionIdentity';
import { equivalencePath, type DecisionSummary, type EquivalenceEvent, type EquivalencePins, type EquivalenceState, type EvidenceSelection } from './decisionEquivalence';
import { comparisonHash } from './sourceComparison';

export interface EquivalenceHandoff {
  schema_version: 'decision-equivalence-graph-b-handoff-v1'; compiler_version: string; packet_id: string;
  confidentiality: 'firm_confidential'; firm_id: string; context_id: string; equivalence_revision: number; pins: EquivalencePins;
  decision_source_ids: string[]; register_source_id: string; canonical_candidate: string; original_decisions: Record<string, DecisionSummary>;
  source_bindings: Record<string, { source_id: string; artifacts: EquivalenceState['sources'][string]['artifacts'] }>;
  ontology_sha256: string; equivalence_history: EquivalenceEvent[]; identity_histories: Record<string, IdentityEvent[]>;
  source_review_histories: Record<string, { revision: number }[]>; mapping_histories: Record<string, { revision: number }[]>; history_complete: true;
  files: Record<string, { sha256: string; bytes: number; encoding: 'base64'; data: string }>;
  structural_validation: { conforms: true; assertion_count: 6; legal_truth_verified: false };
  omitted_mapping_ids: Record<string, string[]>; scope: 'reviewed_equivalence_identity_candidates_only';
  signed: false; graph_updated: false; identity_reservations_changed: false; global_registry_qualified: false;
  legal_effect_verified: false; institutional_competence_verified: false; publication_eligible: false; limitations: string[];
}
export async function fetchEquivalenceHandoff(state: EquivalenceState, source: string, selection: EvidenceSelection, user: User, signal?: AbortSignal) {
  if (!state.same_decision_supported || !state.export_allowed || state.stale || !state.inputs_ready || state.firm_id !== user.firm_id) throw new Error('Güncel aynı-karar kabulü ve üç kaynak için dışa aktarma izni gerekli.');
  const path = equivalencePath(source, selection).replace('/decision-equivalence?', '/decision-equivalence/graph-b-handoff?');
  const envelope = await request<{ evidence_json: string; evidence_sha256: string }>(path, { method: 'POST', body: JSON.stringify({ expected_revision: state.revision, pins: state.pins }), signal });
  if (typeof envelope?.evidence_json !== 'string' || new TextEncoder().encode(envelope.evidence_json).length > 16 * 1024 * 1024
    || envelope.evidence_sha256 !== await comparisonHash(envelope.evidence_json)) throw new Error('Çok kaynaklı Graph B paketinin içerik özeti doğrulanamadı.');
  let data: EquivalenceHandoff;
  try { data = JSON.parse(envelope.evidence_json); } catch { throw new Error('Çok kaynaklı paket okunamadı.'); }
  const ids = Object.keys(state.sources).sort(); const decisions = state.decision_source_ids.slice().sort();
  const same = (a: unknown, b: unknown) => sortedJson(a) === sortedJson(b);
  const keys = (value: object | undefined, expected: string[]) => !!value && same(Object.keys(value).sort(), expected);
  if (data?.schema_version !== 'decision-equivalence-graph-b-handoff-v1' || data.compiler_version !== data.schema_version
    || data.scope !== 'reviewed_equivalence_identity_candidates_only' || data.confidentiality !== 'firm_confidential' || data.firm_id !== user.firm_id
    || data.context_id !== state.context_id || data.equivalence_revision !== state.revision || !same(data.pins, state.pins)
    || !same(data.decision_source_ids, state.decision_source_ids) || data.register_source_id !== state.register_source_id
    || data.canonical_candidate !== state.current?.proposal.claims.canonical_decision_id || !same(data.original_decisions, state.current.proposal.decisions)
    || data.history_complete !== true || !/^[a-f0-9]{64}$/.test(data.ontology_sha256)
    || [data.signed, data.graph_updated, data.identity_reservations_changed, data.global_registry_qualified, data.legal_effect_verified, data.institutional_competence_verified, data.publication_eligible, data.structural_validation?.legal_truth_verified].some(value => value !== false)
    || data.structural_validation?.conforms !== true || data.structural_validation.assertion_count !== 6
    || !same(data.equivalence_history, state.history.slice().reverse()) || !keys(data.source_bindings, ids)
    || !keys(data.source_review_histories, ids) || !keys(data.mapping_histories, ids) || !keys(data.identity_histories, decisions)
    || ids.some(id => data.source_bindings[id].source_id !== id || !same(data.source_bindings[id].artifacts, state.sources[id].artifacts))
    || ids.some(id => !Array.isArray(data.source_review_histories[id]) || data.source_review_histories[id].length !== state.pins.source_revisions[id]
      || data.source_review_histories[id].some((event, index) => event.revision !== state.pins.source_revisions[id] - index)
      || !Array.isArray(data.mapping_histories[id]) || data.mapping_histories[id].length !== state.pins.mapping_revisions[id]
      || data.mapping_histories[id].some((event, index) => event.revision !== state.pins.mapping_revisions[id] - index))
    || decisions.some(id => !Array.isArray(data.identity_histories[id]) || data.identity_histories[id].length !== state.pins.identity_revisions[id]
      || data.identity_histories[id].some((event, index) => event.revision !== index + 1)
      || data.identity_histories[id].at(-1)?.decision !== 'accepted'
      || data.identity_histories[id].at(-1)?.proposal.identity.decision_id !== data.original_decisions[id].decision_id
      || data.identity_histories[id].at(-1)?.proposal.identity.proceeding_id !== data.original_decisions[id].proceeding_id
      || data.identity_histories[id].at(-1)?.proposal.identity.institution_id !== data.original_decisions[id].institution_id
      || data.identity_histories[id].at(-1)?.proposal.version_id !== data.original_decisions[id].version_id)) throw new Error('Paket seçili büro, üç kaynak ve tam inceleme geçmişleriyle eşleşmiyor.');
  const expected = ['candidate/jurisprudence.nt', ...ids.flatMap(id => [`candidate/${id}/locators.json`, ...Object.keys(state.sources[id].artifacts).map(name => `original/${id}/${name}`)])].sort();
  if (!keys(data.files, expected)) throw new Error('Tam fiziksel dosya envanteri eşleşmiyor.');
  const metadata: Record<string, Omit<EquivalenceHandoff['files'][string], 'data'>> = {}; let bytesTotal = 0;
  for (const [name, entry] of Object.entries(data.files)) {
    if (!Number.isSafeInteger(entry.bytes) || entry.bytes < 1 || entry.bytes > 12 * 1024 * 1024 || entry.encoding !== 'base64'
      || typeof entry.data !== 'string' || !/^[A-Za-z0-9+/]*={0,2}$/.test(entry.data) || !/^[a-f0-9]{64}$/.test(entry.sha256)) throw new Error('Fiziksel dosya sözleşmesi geçersiz.');
    const bytes = Uint8Array.from(atob(entry.data), char => char.charCodeAt(0)); bytesTotal += bytes.length;
    const hash = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)), value => value.toString(16).padStart(2, '0')).join('');
    const [, id, artifact] = name.split('/'); const original = name.startsWith('original/') ? state.sources[id].artifacts[artifact] : null;
    if (bytesTotal > 12 * 1024 * 1024 || bytes.length !== entry.bytes || hash !== entry.sha256
      || (original && (original.sha256 !== hash || original.bytes !== bytes.length))) throw new Error('Fiziksel dosyanın özeti veya özgün kaynak bağı doğrulanamadı.');
    metadata[name] = { sha256: entry.sha256, bytes: entry.bytes, encoding: entry.encoding };
  }
  const { packet_id, ...core } = data;
  if (packet_id !== await comparisonHash(sortedJson({ ...core, files: metadata }))) throw new Error('Çok kaynaklı paket kimliği doğrulanamadı.');
  signal?.throwIfAborted();
  return { data, evidence_json: envelope.evidence_json, evidence_sha256: envelope.evidence_sha256 };
}
