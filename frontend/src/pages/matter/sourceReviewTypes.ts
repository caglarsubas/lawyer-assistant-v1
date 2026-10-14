import { ApiError } from '../../api';
import { AUTHORITY_ROLES, type AuthorityRole } from './authorityTypes';

export const DIMENSIONS = ['quote_identity', 'target_alignment', 'temporal_limits'] as const;
export const DIMENSION_LABELS = { quote_identity: 'Özgün pasaj ve sürüm', target_alignment: 'Analiz adımları ve karşı dayanaklar', temporal_limits: 'Tarih, belirsizlik ve araştırma sınırları' };
export const OUTCOMES = { confirmed: 'İnceledim ve doğruladım', needs_change: 'Değişiklik gerekli', not_assessed: 'Henüz değerlendirmedim' };
export type Outcome = keyof typeof OUTCOMES;
export type Decision = 'reviewed_conditional' | 'changes_requested';
export interface Quote {
  passage_id: string; source_version_id: string; document_id: string; text: string; locator: string;
  quote_sha256: string; source_sha256: string; text_sha256: string; locator_map_sha256: string;
  start_offset: number; end_offset: number; offset_unit: 'unicode_codepoint'; release_id: string;
  assertion_id: null; authority_id: null; authority_resolution: 'not_performed';
  matter_applicability: 'not_assessed'; temporal_applicability: 'not_assessed'; finality: 'unknown';
}
export interface Selection { passage_id: string; source_version_id: string; quote_sha256: string; target_ids: string[]; relationship: AuthorityRole; note: string }
export type EditableSelection = Omit<Selection, 'relationship'> & { relationship: AuthorityRole | '' };
export interface Observation { dimension: typeof DIMENSIONS[number]; outcome: Outcome; note: string }
export type EditableAssessment = EditableSelection & { observations: (Omit<Observation, 'outcome'> & { outcome: Outcome | '' })[] };
export interface Assessment extends Selection { observations: Observation[] }
export interface Pin { release_id: string; serving_sha256: string; activation_sequence: number; status: 'verified' }
export interface Candidates {
  sources: Quote[]; snapshot: { recipe: string; release_id: string; serving_sha256: string; as_of: string | null };
  graph_release_pin: Pin; coverage: Record<string, unknown>; limitations: string[]; targets: Record<string, unknown>;
  current_version: boolean; private_freshness: { status: string; reasons: string[] };
}
export interface Spec {
  version_id: string; product_id: string; expected_release_id: string; expected_serving_sha256: string;
  title: string; purpose: string; selections: Selection[];
}
export interface LinkedSource { selection: Selection; evidence: Quote; target_snapshots: Record<string, unknown> }
export interface Manifest extends Spec {
  matter_id: string; analysis_id: string; sources: LinkedSource[]; graph_release_pin: Pin;
  analysis_author_id: string; analysis_owner_id: string; analysis_content_sha256: string; product_sha256: string;
  coverage: Record<string, unknown>; limitations: string[]; event_date: string | null; research_snapshot: Candidates['snapshot'];
  legal_approval: 'not_granted'; matter_applicability: 'not_assessed'; temporal_applicability: 'not_assessed'; finality: 'unknown';
}
export interface Preview { manifest: Manifest; preview_sha256: string }
export interface ReviewSpec {
  expected_manifest_sha256: string; expected_review_id: string | null; decision: Decision; sources: Assessment[]; note: string;
}
export interface ReviewEvent {
  recorded_by: string; recorded_at: string; sequence: number; previous_review_id: string | null; packet_sha256: string;
  input: ReviewSpec; dimensions: Record<typeof DIMENSIONS[number], string>; legal_approval: 'not_granted';
}
export interface ContextView {
  id: string; recorded_by?: string; recorded_at?: string; manifest_sha256?: string; packet_sha256?: string;
  manifest: Manifest | null; public_source_access: boolean; freshness: { status: string; reasons: string[] };
  review: { effective_state: string; id?: string; is_latest?: boolean; latest_review_id?: string | null; snapshot: ReviewEvent | null };
}
export interface ReviewInputs {
  manifest: Manifest; expected_manifest_sha256: string; expected_review_id: string | null;
  dimensions: Record<typeof DIMENSIONS[number], string>; independent_reviewer_required: true; can_record: boolean;
}
export interface Summary { id: string; recorded_at: string; recorded_by?: string }

const hash = (value: unknown): value is string => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value);
const ident = (value: unknown): value is string => typeof value === 'string' && value.length > 0 && value.length <= 512 && !/[\s\x00-\x1f\x7f]/.test(value);
const boundedNote = (value: string, max = 2000) => value.trim().length >= 3 && value.length <= max;
export function canonicalJson(value: unknown): string {
  const ordered = (item: unknown): unknown => Array.isArray(item) ? item.map(ordered) : item !== null && typeof item === 'object'
    ? Object.fromEntries(Object.entries(item).sort(([left], [right]) => left < right ? -1 : left > right ? 1 : 0).map(([key, entry]) => [key, ordered(entry)])) : item;
  return JSON.stringify(ordered(value));
}
export function sourceIdentity(value: Pick<Quote, 'passage_id' | 'source_version_id' | 'quote_sha256'>) {
  return { passage_id: value.passage_id, source_version_id: value.source_version_id, quote_sha256: value.quote_sha256 };
}
export function occurrenceKey(value: Pick<Selection, 'passage_id' | 'source_version_id' | 'quote_sha256'>) { return JSON.stringify(Object.values(sourceIdentity(value))); }
export function selectionsPayload(rows: EditableSelection[], allowedTargets: string[]): Selection[] | null {
  if (!rows.length || rows.length > 8 || new Set(rows.map(row => row.passage_id)).size !== rows.length) return null;
  if (rows.some(row => !ident(row.passage_id) || !ident(row.source_version_id) || !hash(row.quote_sha256)
    || !Object.hasOwn(AUTHORITY_ROLES, row.relationship) || !boundedNote(row.note) || !row.target_ids.length || row.target_ids.length > 12
    || new Set(row.target_ids).size !== row.target_ids.length || row.target_ids.some(id => !allowedTargets.includes(id)))) return null;
  return rows.map(row => ({ ...sourceIdentity(row), target_ids: [...row.target_ids], relationship: row.relationship as AuthorityRole, note: row.note }));
}
export function reviewPayload(rows: EditableAssessment[], note: string, decision: Decision, inputs: ReviewInputs): ReviewSpec | null {
  const expected = inputs.manifest.sources.map(source => source.selection);
  const selections = selectionsPayload(rows, expected.flatMap(source => source.target_ids));
  if (!selections || !boundedNote(note) || rows.length !== expected.length) return null;
  const sources: Assessment[] = [];
  for (let index = 0; index < rows.length; index++) {
    const row = rows[index]; const selected = selections[index]; const original = expected.find(item => occurrenceKey(item) === occurrenceKey(selected));
    if (!original || [...row.target_ids].sort().join('\0') !== [...original.target_ids].sort().join('\0')
      || row.observations.length !== 3 || new Set(row.observations.map(item => item.dimension)).size !== 3
      || row.observations.some(item => !DIMENSIONS.includes(item.dimension) || !Object.hasOwn(OUTCOMES, item.outcome) || !boundedNote(item.note))) return null;
    sources.push({ ...selected, observations: row.observations.map(item => ({ ...item, outcome: item.outcome as Outcome })) });
  }
  const outcomes = sources.flatMap(source => source.observations.map(item => item.outcome));
  if ((decision === 'reviewed_conditional' && outcomes.some(value => value !== 'confirmed'))
    || (decision === 'changes_requested' && !outcomes.includes('needs_change'))) return null;
  const value = { expected_manifest_sha256: inputs.expected_manifest_sha256, expected_review_id: inputs.expected_review_id, decision, sources, note };
  return new TextEncoder().encode(JSON.stringify({ ...value, request_id: '0'.repeat(32) })).length > 128 * 1024 ? null : value;
}
export function currentView(value: ContextView) { return value.public_source_access === true && value.freshness.status === 'current' && value.manifest !== null; }
export function canExport(value: ContextView) { return currentView(value) && value.review.is_latest === true && value.review.effective_state === 'reviewed_conditional' && value.review.snapshot !== null; }
export function pendingReceipt(cause: unknown, kind: 'context' | 'review'): string | null {
  if (!(cause instanceof ApiError) || cause.status !== 409 || !cause.data || typeof cause.data !== 'object') return null;
  const value = cause.data as Record<string, unknown>;
  return value.outcome === 'committed_needs_revalidation' && typeof value.id === 'string'
    && new RegExp(`^${kind === 'context' ? 'sac' : 'sar'}-[a-f0-9]{20}-[a-f0-9]{32}$`).test(value.id) ? value.id : null;
}

export async function verifyQuotes(sources: Quote[], pin: Pin): Promise<void> {
  if (!hash(pin.release_id) || !hash(pin.serving_sha256) || pin.status !== 'verified' || !Number.isSafeInteger(pin.activation_sequence) || pin.activation_sequence < 1
    || sources.length > 50 || new Set(sources.map(item => item.passage_id)).size !== sources.length) throw new Error('Kaynak sürümü doğrulanamadı; içerik bekletiliyor.');
  for (const source of sources) {
    if (!ident(source.passage_id) || !ident(source.source_version_id) || !ident(source.document_id)
      || ![source.source_sha256, source.text_sha256, source.locator_map_sha256, source.quote_sha256].every(hash)
      || typeof source.text !== 'string' || source.text.length > 2 * 1024 * 1024 || typeof source.locator !== 'string'
      || !Number.isSafeInteger(source.start_offset) || !Number.isSafeInteger(source.end_offset) || source.start_offset < 0
      || source.end_offset - source.start_offset !== Array.from(source.text).length || source.offset_unit !== 'unicode_codepoint'
      || source.release_id !== pin.release_id || source.assertion_id !== null || source.authority_id !== null
      || source.authority_resolution !== 'not_performed' || source.matter_applicability !== 'not_assessed'
      || source.temporal_applicability !== 'not_assessed' || source.finality !== 'unknown') throw new Error('Tam kaynak ve alıntı bağı doğrulanamadı; içerik bekletiliyor.');
    const bytes = new TextEncoder().encode(source.text);
    const actual = [...new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))].map(value => value.toString(16).padStart(2, '0')).join('');
    if (actual !== source.quote_sha256) throw new Error('Alıntı özeti eşleşmiyor; içerik bekletiliyor.');
  }
}
export async function verifyManifest(manifest: Manifest, matterId: string, analysisId: string): Promise<void> {
  if (manifest.matter_id !== matterId || manifest.analysis_id !== analysisId || manifest.sources.length < 1 || manifest.sources.length > 8
    || manifest.expected_release_id !== manifest.graph_release_pin.release_id || manifest.expected_serving_sha256 !== manifest.graph_release_pin.serving_sha256
    || manifest.legal_approval !== 'not_granted') throw new Error('Özel çalışma alanı veya kaynak sürümü eşleşmiyor.');
  await verifyQuotes(manifest.sources.map(source => source.evidence), manifest.graph_release_pin);
  const selected = selectionsPayload(manifest.selections, manifest.sources.flatMap(source => Object.keys(source.target_snapshots)));
  if (!selected || selected.length !== manifest.sources.length || manifest.sources.some(source => !selected.some(item => occurrenceKey(item) === occurrenceKey(source.evidence)
    && occurrenceKey(source.selection) === occurrenceKey(item) && source.selection.note === item.note && source.selection.relationship === item.relationship
    && JSON.stringify(source.selection.target_ids) === JSON.stringify(item.target_ids)))) throw new Error('Seçilen tam pasaj ve analiz adımları eşleşmiyor.');
}

export async function verifyView(value: ContextView, matterId: string, analysisId: string): Promise<void> {
  if (!currentView(value) || !hash(value.manifest_sha256)) throw new Error('Kaynak veya özel dayanaklar güncel değil; alıntılar ve notlar bekletiliyor.');
  await verifyManifest(value.manifest!, matterId, analysisId);
  const event = value.review.snapshot;
  if (event) {
    const inputs: ReviewInputs = { manifest: value.manifest!, expected_manifest_sha256: value.manifest_sha256!, expected_review_id: event.input.expected_review_id,
      dimensions: event.dimensions, independent_reviewer_required: true, can_record: false };
    if (event.input.expected_manifest_sha256 !== value.manifest_sha256 || event.legal_approval !== 'not_granted'
      || !reviewPayload(event.input.sources, event.input.note, event.input.decision, inputs)
      || [value.manifest!.analysis_author_id, value.manifest!.analysis_owner_id, value.recorded_by].includes(event.recorded_by)) throw new Error('Bağımsız inceleme ve tam kaynak bağları doğrulanamadı.');
  }
}

/** A source/permission failure retires all in-flight responses for this scope. */
export class SourceReadFence {
  private generation = 0;
  private controller?: AbortController;
  invalidate() { this.generation++; this.controller?.abort(); }
  begin() {
    this.invalidate(); const generation = this.generation; const controller = new AbortController(); this.controller = controller;
    return { signal: controller.signal, current: () => generation === this.generation && !controller.signal.aborted };
  }
}
