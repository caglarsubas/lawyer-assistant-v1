import { canonicalJson, occurrenceKey, type Manifest, type Pin, type Quote, type Selection } from './sourceReviewTypes';

export const DISPOSITIONS = { retained: 'Aynı tam pasajı koru', replaced: 'Açıkça başka seçimle değiştir', omitted: 'Yeni seçimden çıkar', unresolved: 'Eşleme belirsiz' };
export type Disposition = keyof typeof DISPOSITIONS;
export interface RenewalMapping { parent_passage_id: string; new_passage_ids: string[]; disposition: Disposition; note: string }
export type EditableMapping = Omit<RenewalMapping, 'disposition'> & { disposition: Disposition | '' };
export type EvidenceIdentity = Pick<Quote, 'passage_id' | 'source_version_id' | 'document_id' | 'quote_sha256' | 'source_sha256' | 'text_sha256' | 'locator_map_sha256' | 'start_offset' | 'end_offset' | 'offset_unit'>;
export interface RenewalMetadata {
  id: string; matter_id: string; analysis_id: string; manifest_sha256: string; review_id: string | null;
  admission_completed: boolean; can_record: boolean; version_id: string; product_id: string; graph_release_pin: Pin; recorded_by: string;
  sources: { identity: EvidenceIdentity; targets: Record<string, string> }[];
  old_quotes_and_notes: 'withheld_use_original_guarded_context'; review_inheritance: 'none'; legal_equivalence: 'not_assessed';
}
export interface Renewal {
  parent_context_id: string; expected_parent_manifest_sha256: string; expected_parent_review_id: string | null;
  reason: string; mappings: RenewalMapping[]; added_passage_ids: string[];
}
export interface RenewalAssessment { expected_comparison_sha256: string; outcome: 'confirmed' | 'needs_change' | 'not_assessed'; note: string }
export interface RenewalComparison {
  recipe: 'private-source-context-renewal-v1'; depth: number; parent_context_id: string;
  parent_manifest_sha256: string; parent_packet_sha256: string; parent_review_id: string | null;
  parent_version_id: string; parent_product_id: string; parent_graph_release_pin: Pin;
  release_changed: boolean; analysis_changed: boolean; research_changed: boolean;
  entries: { parent_identity: EvidenceIdentity; parent_targets: Record<string, string>; disposition: Disposition; note: string;
    successors: { identity: EvidenceIdentity; targets: Record<string, string>; exact_evidence_same: boolean; exact_targets_same: boolean }[] }[];
  added_passage_ids: string[]; old_quotes_and_notes: 'withheld_use_original_guarded_context'; review_inheritance: 'none';
  original_dependencies: 'retained_in_immutable_parent_not_reauthorized'; legal_equivalence: 'not_assessed';
}
const isHash = (value: string) => /^[a-f0-9]{64}$/.test(value);
const explained = (value: string, max: number) => value.trim().length >= 3 && value.length <= max;
const contextId = (value: string) => /^sac-[a-f0-9]{20}-[a-f0-9]{32}$/.test(value);
const keys = ['passage_id', 'source_version_id', 'document_id', 'quote_sha256', 'source_sha256', 'text_sha256', 'locator_map_sha256', 'start_offset', 'end_offset', 'offset_unit'] as const;
function closed(value: object, expected: readonly string[]) { return canonicalJson(Object.keys(value).sort()) === canonicalJson([...expected].sort()); }
function identity(value: EvidenceIdentity): EvidenceIdentity { return Object.fromEntries(keys.map(key => [key, value[key]])) as unknown as EvidenceIdentity; }
function validateIdentity(value: EvidenceIdentity) {
  if (!closed(value, keys) || ['passage_id', 'source_version_id', 'document_id'].some(key => typeof value[key as keyof EvidenceIdentity] !== 'string'
      || !String(value[key as keyof EvidenceIdentity]).length || String(value[key as keyof EvidenceIdentity]).length > 512)
    || ![value.quote_sha256, value.source_sha256, value.text_sha256, value.locator_map_sha256].every(isHash)
    || !Number.isSafeInteger(value.start_offset) || !Number.isSafeInteger(value.end_offset) || value.start_offset < 0 || value.end_offset <= value.start_offset
    || value.offset_unit !== 'unicode_codepoint') throw new Error('Önceki tam kaynak kimliği doğrulanamadı.');
}
function validateTargets(targets: Record<string, string>) {
  const rows = Object.entries(targets);
  if (!rows.length || rows.length > 12 || rows.some(([id, hash]) => !id.length || id.length > 129 || !isHash(hash))) throw new Error('Tam analiz adımı özeti doğrulanamadı.');
}
export function verifyRenewalMetadata(value: RenewalMetadata, matterId: string, analysisId: string, id: string) {
  if (!value || !closed(value, ['id', 'matter_id', 'analysis_id', 'manifest_sha256', 'review_id', 'admission_completed', 'can_record', 'version_id', 'product_id', 'graph_release_pin', 'recorded_by', 'sources', 'old_quotes_and_notes', 'review_inheritance', 'legal_equivalence'])
    || value.id !== id || !contextId(id) || value.matter_id !== matterId || value.analysis_id !== analysisId || !isHash(value.manifest_sha256)
    || typeof value.admission_completed !== 'boolean' || typeof value.can_record !== 'boolean'
    || typeof value.version_id !== 'string' || !/^[a-zA-Z0-9_-]{1,64}$/.test(value.version_id) || typeof value.product_id !== 'string' || !/^[a-zA-Z0-9_-]{1,64}$/.test(value.product_id)
    || typeof value.recorded_by !== 'string' || !/^[a-zA-Z0-9_-]{1,64}$/.test(value.recorded_by) || value.review_id !== null && !/^sar-[a-f0-9]{20}-[a-f0-9]{32}$/.test(value.review_id)
    || !value.graph_release_pin || !closed(value.graph_release_pin, ['release_id', 'serving_sha256', 'activation_sequence', 'status']) || value.graph_release_pin.status !== 'verified'
    || !isHash(value.graph_release_pin.release_id) || !isHash(value.graph_release_pin.serving_sha256) || !Number.isSafeInteger(value.graph_release_pin.activation_sequence) || value.graph_release_pin.activation_sequence < 1
    || !Array.isArray(value.sources) || value.sources.length < 1 || value.sources.length > 8 || new Set(value.sources.map(row => row.identity.passage_id)).size !== value.sources.length
    || value.old_quotes_and_notes !== 'withheld_use_original_guarded_context' || value.review_inheritance !== 'none' || value.legal_equivalence !== 'not_assessed') throw new Error('Özel yenileme kaydı doğrulanamadı.');
  value.sources.forEach(row => { if (!closed(row, ['identity', 'targets'])) throw new Error('Önceki içerik yerine yalnız kimlik ve özet gerekli.'); validateIdentity(row.identity); validateTargets(row.targets); });
}
export function renewalPayload(meta: RenewalMetadata, rows: EditableMapping[], reason: string, added: string[], selections: Selection[]): Renewal | null {
  if (!meta.admission_completed || !meta.can_record || !explained(reason, 2000) || rows.length !== meta.sources.length
    || new Set(rows.map(row => row.parent_passage_id)).size !== rows.length || new Set(added).size !== added.length) return null;
  const before = new Map(meta.sources.map(row => [row.identity.passage_id, row.identity])); const after = new Map(selections.map(row => [row.passage_id, row]));
  for (const row of rows) {
    const parent = before.get(row.parent_passage_id);
    if (!parent || !Object.hasOwn(DISPOSITIONS, row.disposition) || !explained(row.note, 1000) || row.new_passage_ids.length > 8
      || new Set(row.new_passage_ids).size !== row.new_passage_ids.length || row.new_passage_ids.some(id => !after.has(id))
      || (['retained', 'replaced'].includes(row.disposition) && !row.new_passage_ids.length)
      || (row.disposition === 'omitted' && row.new_passage_ids.length)) return null;
    if (row.disposition === 'retained' && (row.new_passage_ids.length !== 1 || occurrenceKey(parent) !== occurrenceKey(after.get(row.new_passage_ids[0])!))) return null;
  }
  const linked = new Set(rows.flatMap(row => row.new_passage_ids));
  if (added.some(id => linked.has(id) || !after.has(id)) || new Set([...linked, ...added]).size !== after.size) return null;
  return { parent_context_id: meta.id, expected_parent_manifest_sha256: meta.manifest_sha256, expected_parent_review_id: meta.review_id,
    reason, mappings: rows.map(row => ({ ...row, disposition: row.disposition as Disposition })), added_passage_ids: [...added] };
}
export function verifyRenewalComparison(manifest: Manifest) {
  const spec = manifest.renewal; const value = manifest.renewal_comparison;
  if (!spec && !value) return;
  if (!spec || !value || value.recipe !== 'private-source-context-renewal-v1' || value.parent_context_id !== spec.parent_context_id
    || !contextId(value.parent_context_id) || !isHash(manifest.renewal_comparison_sha256 || '') || value.parent_manifest_sha256 !== spec.expected_parent_manifest_sha256
    || value.parent_review_id !== spec.expected_parent_review_id || !isHash(value.parent_manifest_sha256) || !isHash(value.parent_packet_sha256)
    || !Number.isSafeInteger(value.depth) || value.depth < 1 || value.depth > 8 || value.entries.length !== spec.mappings.length
    || value.review_inheritance !== 'none' || value.legal_equivalence !== 'not_assessed' || value.old_quotes_and_notes !== 'withheld_use_original_guarded_context'
    || value.original_dependencies !== 'retained_in_immutable_parent_not_reauthorized' || canonicalJson(value.added_passage_ids) !== canonicalJson(spec.added_passage_ids)) throw new Error('Tam yenileme ve geçmiş bağı doğrulanamadı.');
  const meta = { id: value.parent_context_id, manifest_sha256: value.parent_manifest_sha256, review_id: value.parent_review_id,
    admission_completed: true, can_record: true, sources: value.entries.map(row => ({ identity: row.parent_identity, targets: row.parent_targets })) } as RenewalMetadata;
  if (!renewalPayload(meta, spec.mappings, spec.reason, spec.added_passage_ids, manifest.selections)) throw new Error('Eksiksiz kaynak yenileme eşlemesi gerekli.');
  for (const entry of value.entries) {
    if (!closed(entry, ['parent_identity', 'parent_targets', 'disposition', 'note', 'successors'])) throw new Error('Önceki alıntı ve notlar karşılaştırmaya aktarılamaz.');
    validateIdentity(entry.parent_identity); validateTargets(entry.parent_targets);
    const mapping = spec.mappings.find(row => row.parent_passage_id === entry.parent_identity.passage_id)!;
    if (mapping.disposition !== entry.disposition || mapping.note !== entry.note || canonicalJson(mapping.new_passage_ids) !== canonicalJson(entry.successors.map(row => row.identity.passage_id))) throw new Error('Beyan edilen kaynak eşlemesi değişti.');
    for (const successor of entry.successors) {
      if (!closed(successor, ['identity', 'targets', 'exact_evidence_same', 'exact_targets_same'])) throw new Error('Tam karşılaştırma alanları değişti.');
      const source = manifest.sources.find(row => row.evidence.passage_id === successor.identity.passage_id);
      validateTargets(successor.targets);
      if (!source || canonicalJson(identity(source.evidence)) !== canonicalJson(successor.identity)
        || canonicalJson([...source.selection.target_ids].sort()) !== canonicalJson(Object.keys(successor.targets).sort())
        || successor.exact_evidence_same !== (canonicalJson(entry.parent_identity) === canonicalJson(successor.identity))
        || successor.exact_targets_same !== (canonicalJson(entry.parent_targets) === canonicalJson(successor.targets))) throw new Error('Karşılaştırılan tam sürüm veya analiz adımları eşleşmiyor.');
    }
    if (entry.disposition === 'retained' && (entry.successors.length !== 1 || !entry.successors[0].exact_evidence_same)) throw new Error('Korunan pasajın tam kimliği değişti.');
  }
}
