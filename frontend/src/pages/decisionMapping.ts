import { request } from '../api';
import type { PublicSourceDetail, PublicSourcePassage, PublicSourcePassages, SourceReviewDecision } from '../types';
import { sourceReviewPath } from './SourceReviewPage';
import { comparisonHash } from './sourceComparison';

export interface DecisionOccurrence {
  id: string; kind: string; rule: string; start: number; end: number; passage_start: number; passage_end: number;
  text: string; sha256: string; value_start: number; value_end: number; value_text: string;
  parsed_value: string | null; parse_status: string; status: 'machine_proposed'; identity_status: 'unresolved';
  event_role: 'unknown'; authority_treatment: 'unknown';
}
export interface DecisionOccurrences {
  schema_version: string; extraction_version: string; source_id: string; source_version_id: string;
  raw_sha256: string; text_sha256: string; passage_id: string; passage_sha256: string; passage_start: number; passage_end: number;
  locator: string; offset_unit: string; scope: string; integrity_scope: string; items: DecisionOccurrence[]; count: number;
  truncated: false; legal_identity_resolved: false; dates_promoted: false; human_review_recorded: false; graph_updated: false; limitations: string[];
}
export interface DecisionResolution {
  start: number; end: number; occurrence_role: 'own_decision' | 'cited_authority' | 'editorial' | 'unknown';
  proceeding_ref: string | null; decision_ref: string | null; institution_ref: string | null;
  target_ref: string | null; target_version_ref: string | null; event_role: 'decision' | 'publication' | 'unknown';
  event_date: string | null; authority_treatment: 'cites' | 'quotes' | 'applies' | 'distinguishes' | 'unknown';
}
export interface DecisionSnapshot {
  passage_id: string; candidate: DecisionOccurrence; status: 'machine_proposed' | SourceReviewDecision;
  resolution: DecisionResolution | null; reviewed_source_revision: number | null;
}
export interface DecisionEvent {
  id: string; revision: number; mapping_id: string; event_type: string; reviewer: { id: string; name: string };
  created_at: string; rationale: string; decision: SourceReviewDecision | null; evidence_refs: { reference: string; sha256: string }[];
  source_review_revision: number; snapshot: DecisionSnapshot;
}
export interface DecisionMapping extends DecisionSnapshot { id: string; stale: boolean; last_event: DecisionEvent }
export interface DecisionState {
  source: PublicSourceDetail; revision: number; source_review_revision: number; assigned_to: { id: string; name: string } | null;
  source_review_ready: boolean; export_allowed: boolean; items: DecisionMapping[]; history: DecisionEvent[]; history_truncated: boolean;
  handoff_ready: boolean; publication_eligible: false; limitations: string[];
}
export function decisionPath(id: string) { return `${sourceReviewPath(id)}/decision-mappings`; }
export const KIND_LABELS: Record<string, string> = { application_number: 'Başvuru numarası', case_number: 'Esas numarası', decision_number: 'Karar numarası', decision_date: 'Karar tarihi', publication_date: 'Yayım tarihi', instrument_number_reference: 'Sayılı belge anması', article_number_reference: 'Madde anması' };
export function emptyResolution(candidate: DecisionOccurrence): DecisionResolution {
  return { start: candidate.start, end: candidate.end, occurrence_role: 'unknown', proceeding_ref: null, decision_ref: null,
    institution_ref: null, target_ref: null, target_version_ref: null, event_role: 'unknown', event_date: null, authority_treatment: 'unknown' };
}
export async function fetchDecisionOccurrences(source: PublicSourcePassages, passage: PublicSourcePassage, signal?: AbortSignal) {
  if (!/^[A-Za-z][A-Za-z0-9_-]{0,79}$/.test(passage.id) || !source.items.includes(passage)) throw new Error('Pasaj seçimi geçersiz.');
  const envelope = await request<{ evidence_json: string; evidence_sha256: string }>(`${sourceReviewPath(source.source_id)}/jurisprudence-candidates?passage_id=${encodeURIComponent(passage.id)}`, { signal });
  if (typeof envelope?.evidence_json !== 'string' || new TextEncoder().encode(envelope.evidence_json).length > 256 * 1024
    || envelope.evidence_sha256 !== await comparisonHash(envelope.evidence_json)) throw new Error('Anma kanıtının içerik özeti doğrulanamadı.');
  let data: DecisionOccurrences;
  try { data = JSON.parse(envelope.evidence_json); } catch { throw new Error('Anma kanıtı okunamadı.'); }
  const chars = Array.from(passage.text);
  if (data.schema_version !== 'jurisprudence-occurrences-v1' || data.extraction_version !== 'tr-jurisprudence-occurrences-v1'
    || data.source_id !== source.source_id || data.source_version_id !== source.source_version_id || data.raw_sha256 !== source.raw_sha256
    || data.text_sha256 !== source.text_sha256 || data.passage_id !== passage.id || data.passage_sha256 !== passage.text_sha256
    || data.passage_start !== passage.start || data.passage_end !== passage.end || data.locator !== passage.locator
    || data.offset_unit !== 'unicode_code_points' || data.scope !== 'selected_passage_only' || data.integrity_scope !== 'all_artifacts_verified'
    || chars.length !== passage.end - passage.start || await comparisonHash(passage.text) !== passage.text_sha256
    || !Array.isArray(data.items) || data.items.length > 200 || data.count !== data.items.length
    || new Set(data.items.map(item => item.id)).size !== data.items.length
    || [data.truncated, data.legal_identity_resolved, data.dates_promoted, data.human_review_recorded, data.graph_updated].some(value => value !== false)) throw new Error('Anma yanıtı seçili kaynak ve pasajla eşleşmiyor.');
  for (const item of data.items) {
    const identity = [source.source_id, source.source_version_id, source.raw_sha256, source.text_sha256, passage.id, passage.text_sha256, data.extraction_version, item.rule, item.start, item.end];
    if (item.id !== await comparisonHash(JSON.stringify(identity)) || !/^[a-f0-9]{64}$/.test(item.id) || !KIND_LABELS[item.kind] || item.status !== 'machine_proposed' || item.identity_status !== 'unresolved'
      || item.event_role !== 'unknown' || item.authority_treatment !== 'unknown'
      || ![item.start, item.end, item.passage_start, item.passage_end, item.value_start, item.value_end].every(Number.isSafeInteger)
      || item.passage_start < 0 || item.passage_end <= item.passage_start || item.passage_end > chars.length
      || item.start !== passage.start + item.passage_start || item.end !== passage.start + item.passage_end
      || item.value_start < item.start || item.value_end > item.end || item.value_end <= item.value_start
      || chars.slice(item.passage_start, item.passage_end).join('') !== item.text
      || chars.slice(item.value_start - passage.start, item.value_end - passage.start).join('') !== item.value_text
      || await comparisonHash(item.text) !== item.sha256) throw new Error('Anma aralığı veya tam metni doğrulanamadı.');
  }
  signal?.throwIfAborted();
  return data;
}
export function decisionReviewPayload(state: DecisionState, decision: SourceReviewDecision, rationale: string, resolution: DecisionResolution, reference: string, sha256: string) {
  if (rationale.trim().length < 3 || rationale.length > 4000) throw new Error('Gerekçe 3–4000 karakter olmalı.');
  if ((reference || sha256) && (!reference.trim() || reference.length > 1000 || !/^[a-f0-9]{64}$/.test(sha256))) throw new Error('Dayanak referansı ve SHA256 birlikte gerekli.');
  if (decision === 'accepted' && (!state.source_review_ready || !reference.trim())) throw new Error('Kabul için dört kaynak incelemesi ve dayanak gerekir.');
  return { expected_revision: state.revision, expected_source_review_revision: state.source_review_revision, decision,
    rationale: rationale.trim(), resolution: decision === 'accepted' ? resolution : null,
    evidence_refs: reference ? [{ reference: reference.trim(), sha256 }] : [] };
}

export interface DecisionDossier {
  schema_version: 'decision-review-dossier-v1'; confidentiality: 'firm_confidential'; firm_id: string;
  exported_by: { id: string; name: string }; exported_at: string; signed: false; publication_eligible: false;
  source_binding: { source_id: string; artifacts: PublicSourceDetail['artifacts'] };
  mappings: DecisionState; history_complete: true;
  source_review: { revision: number; history: { revision: number }[]; history_complete: true };
  supporting_passages: { id: string; start: number; end: number; text: string; sha256: string; locator: string }[];
  handoff_checks: { independent_review_ready: boolean; canonical_identity_resolved: false; legal_effect_verified: false;
    publication_eligible: false; unresolved_mapping_ids: string[]; identity_conflicts: { decision_ref: string; field: string; alternatives: { value: string; mapping_ids: string[] }[] }[] };
  limitations: string[];
}
export async function fetchDecisionDossier(state: DecisionState, user: { id: string; firm_id: string }, signal?: AbortSignal) {
  const envelope = await request<{ evidence_json: string; evidence_sha256: string }>(`${decisionPath(state.source.id)}/dossier`, {
    method: 'POST', body: JSON.stringify({ expected_revision: state.revision, expected_source_review_revision: state.source_review_revision }), signal,
  });
  if (typeof envelope?.evidence_json !== 'string' || new TextEncoder().encode(envelope.evidence_json).length > 4 * 1024 * 1024
    || envelope.evidence_sha256 !== await comparisonHash(envelope.evidence_json)) throw new Error('İnceleme dosyasının içerik özeti doğrulanamadı.');
  let data: DecisionDossier;
  try { data = JSON.parse(envelope.evidence_json); } catch { throw new Error('İnceleme dosyası okunamadı.'); }
  const artifacts = data?.source_binding?.artifacts;
  if (data.schema_version !== 'decision-review-dossier-v1' || data.confidentiality !== 'firm_confidential' || data.firm_id !== user.firm_id
    || data.exported_by?.id !== user.id || data.signed !== false || data.publication_eligible !== false
    || data.source_binding.source_id !== state.source.id || data.mappings?.source.id !== state.source.id
    || data.mappings.source.source_version_id !== state.source.source_version_id || data.mappings.revision !== state.revision
    || data.mappings.source_review_revision !== state.source_review_revision || data.source_review?.revision !== state.source_review_revision
    || data.history_complete !== true || data.source_review.history_complete !== true || data.mappings.history_truncated !== false
    || data.mappings.publication_eligible !== false || data.mappings.export_allowed !== true
    || data.handoff_checks?.publication_eligible !== false || data.handoff_checks.canonical_identity_resolved !== false || data.handoff_checks.legal_effect_verified !== false
    || !artifacts || Object.keys(artifacts).sort().join(',') !== Object.keys(state.source.artifacts).sort().join(',')
    || Object.entries(state.source.artifacts).some(([key, value]) => artifacts[key]?.sha256 !== value.sha256 || artifacts[key]?.bytes !== value.bytes)
    || !Array.isArray(data.mappings.history) || data.mappings.history.length !== state.revision
    || data.mappings.history.some((event, index) => event.revision !== state.revision - index)
    || !Array.isArray(data.source_review.history) || data.source_review.history.length !== state.source_review_revision
    || data.source_review.history.some((event, index) => event.revision !== state.source_review_revision - index)
    || !Array.isArray(data.supporting_passages) || data.supporting_passages.length > 5000
    || new Set(data.supporting_passages.map(passage => passage.id)).size !== data.supporting_passages.length) throw new Error('İnceleme dosyası seçili büro, kaynak ve güncel revizyonlarla eşleşmiyor.');
  for (const passage of data.supporting_passages) {
    if (!Number.isSafeInteger(passage.start) || !Number.isSafeInteger(passage.end) || passage.start < 0 || passage.end <= passage.start
      || passage.end - passage.start > 20000 || typeof passage.text !== 'string' || Array.from(passage.text).length !== passage.end - passage.start
      || await comparisonHash(passage.text) !== passage.sha256) throw new Error('Dosyadaki dayanak pasajı doğrulanamadı.');
  }
  signal?.throwIfAborted();
  return { data, evidence_json: envelope.evidence_json, evidence_sha256: envelope.evidence_sha256 };
}
