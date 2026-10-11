import { request } from '../api';
import { comparisonHash } from './sourceComparison';
import { RELATIONSHIPS } from './SourceRelationshipPanel';

const SHA = /^[a-f0-9]{64}$/;
export const SELECTION_STATUSES = { missing: 'Görüş yok', unresolved: 'Çözümlenemedi', stale: 'Yeniden inceleme gerekiyor', resolved: 'Güncel insan görüşü var' } as const;
type Status = keyof typeof SELECTION_STATUSES;
type Classification = keyof typeof RELATIONSHIPS;
export interface SelectionPair {
  pair_id: string; source_ids: string[]; revision: number; status: Status; history_count: number; history_sha256: string;
  historical_classifications: Partial<Record<Classification, number>>; historical_classification_changes: number;
  latest: null | { id: string; revision: number; reviewer: { id: string; name: string }; created_at: string; comparison_sha256: string; event_sha256: string;
    input: { classification: Classification; rationale: string; identities: { source_id: string; work_ref: string; version_ref: string }[] } };
}
export interface SelectionHandoff {
  schema_version: 'source-selection-handoff-v1'; scope_sha256: string; source_ids: string[];
  sources: { source_id: string; title: string; source_version_id: string; review_revision: number;
    artifacts: Record<string, { sha256: string; bytes: number }>; assessments: Record<string, string | null> }[];
  pairs: SelectionPair[];
  coverage: { selected_source_count: number; expected_pair_count: number; pair_status_counts: Record<Status, number>; all_pairs_current_resolved: boolean };
  identity_conflicts: { source_id: string; declarations: { pair_id: string; work_ref: string; version_ref: string }[] }[];
  source_review_gaps: { source_id: string; categories: string[] }[];
  independent_original_count: null; independent_originals_verified: false; study_qualified: false; publication_eligible: false; current_law_verified: false;
  confidentiality: 'firm_confidential'; signed: false; limitations: string[];
}
export interface SelectionEvidence { receipt: SelectionHandoff; evidence_json: string; evidence_sha256: string }

export function selectionCanonical(value: unknown) {
  return JSON.stringify(value, (_key, item) => item && typeof item === 'object' && !Array.isArray(item)
    ? Object.fromEntries(Object.entries(item).sort(([a], [b]) => a.localeCompare(b))) : item);
}

export function selectionPayload(ids: string[]) {
  if (ids.length < 2 || ids.length > 6 || new Set(ids).size !== ids.length || ids.some(id => !SHA.test(id))) throw new Error('İki ile altı farklı kaynak paketi seçin.');
  return { source_ids: [...ids].sort() };
}

export async function validateSelection(envelope: { evidence_json: string; evidence_sha256: string }, ids: string[]): Promise<SelectionEvidence> {
  const selected = selectionPayload(ids).source_ids;
  const invalid = () => { throw new Error('Seçim dosyası kaynaklarla veya inceleme kapsamıyla eşleşmiyor.'); };
  if (!envelope || typeof envelope.evidence_json !== 'string' || new TextEncoder().encode(envelope.evidence_json).length > 512 * 1024
    || !SHA.test(envelope.evidence_sha256) || await comparisonHash(envelope.evidence_json) !== envelope.evidence_sha256) invalid();
  const value: SelectionHandoff = JSON.parse(envelope.evidence_json);
  const same = (a: unknown, b: unknown) => selectionCanonical(a) === selectionCanonical(b);
  const categories = ['rights', 'source_identity', 'extraction', 'legal'];
  if (!value || value.schema_version !== 'source-selection-handoff-v1' || !same(value.source_ids, selected) || !SHA.test(value.scope_sha256)
    || value.confidentiality !== 'firm_confidential' || value.signed !== false || value.independent_original_count !== null
    || value.independent_originals_verified !== false || value.study_qualified !== false || value.publication_eligible !== false || value.current_law_verified !== false
    || !Array.isArray(value.sources) || !same(value.sources.map(source => source?.source_id), selected)
    || !Array.isArray(value.pairs) || value.pairs.length !== selected.length * (selected.length - 1) / 2
    || !Array.isArray(value.identity_conflicts) || !Array.isArray(value.source_review_gaps)
    || !Array.isArray(value.limitations) || !value.limitations.every(item => typeof item === 'string')) invalid();
  for (const source of value.sources) {
    if (typeof source.title !== 'string' || typeof source.source_version_id !== 'string' || !Number.isInteger(source.review_revision)
      || source.review_revision < 0 || source.review_revision > 1000 || !same(Object.keys(source.assessments ?? {}).sort(), [...categories].sort())
      || categories.some(category => ![null, 'accepted', 'needs_changes', 'rejected'].includes(source.assessments[category]))
      || ['raw.bin', 'text.txt', 'locators.json', 'source.json'].some(name => !Object.hasOwn(source.artifacts ?? {}, name))
      || Object.keys(source.artifacts ?? {}).some(name => !['raw.bin', 'text.txt', 'locators.json', 'source.json', 'rights-review.json', 'identity-review.json'].includes(name))
      || Object.values(source.artifacts).some(artifact => !SHA.test(artifact?.sha256) || !Number.isInteger(artifact.bytes) || artifact.bytes < 1)) invalid();
  }
  let index = 0, totalEvents = 0;
  for (let a = 0; a < selected.length; a++) for (let b = a + 1; b < selected.length; b++) {
    const pair = value.pairs[index++], pairIds = [selected[a], selected[b]];
    if (!pair || !same(pair.source_ids, pairIds) || pair.pair_id !== await comparisonHash(JSON.stringify(pairIds))
      || !Object.hasOwn(SELECTION_STATUSES, pair.status) || !Number.isInteger(pair.revision) || pair.revision < 0 || pair.revision > 200
      || pair.history_count !== pair.revision || !SHA.test(pair.history_sha256) || !Number.isInteger(pair.historical_classification_changes)
      || pair.historical_classification_changes < 0 || pair.historical_classification_changes > Math.max(0, pair.revision - 1)
      || !pair.historical_classifications || Object.entries(pair.historical_classifications).some(([key, count]) => !Object.hasOwn(RELATIONSHIPS, key) || !Number.isInteger(count) || count! < 1)
      || Object.values(pair.historical_classifications).reduce((sum, count) => sum + count!, 0) !== pair.revision) invalid();
    if (pair.latest === null) { if (pair.status !== 'missing' || pair.revision !== 0) invalid(); }
    else {
      const latest = pair.latest;
      if (pair.revision < 1 || latest.revision !== pair.revision || pair.status === 'missing' || !SHA.test(latest.event_sha256)
        || !SHA.test(latest.comparison_sha256) || typeof latest.reviewer?.name !== 'string' || typeof latest.created_at !== 'string'
        || typeof latest.input?.rationale !== 'string' || !Object.hasOwn(RELATIONSHIPS, latest.input.classification)
        || !Array.isArray(latest.input.identities) || (pair.status === 'unresolved' && latest.input.classification !== 'unresolved')
        || (pair.status === 'resolved' && latest.input.classification === 'unresolved')) invalid();
      const identities = latest.input.identities;
      if (latest.input.classification === 'unresolved' ? identities.length !== 0 : identities.length !== 2
        || !same(identities.map(item => item.source_id).sort(), pairIds)
        || identities.some(item => typeof item.work_ref !== 'string' || typeof item.version_ref !== 'string')) invalid();
    }
    totalEvents += pair.history_count;
  }
  const counts = Object.fromEntries(Object.keys(SELECTION_STATUSES).map(status => [status, value.pairs.filter(pair => pair.status === status).length]));
  if (totalEvents > 200 || value.coverage?.selected_source_count !== selected.length || value.coverage.expected_pair_count !== value.pairs.length
    || !same(Object.entries(value.coverage.pair_status_counts).sort(), Object.entries(counts).sort())
    || value.coverage.all_pairs_current_resolved !== (counts.resolved === value.pairs.length)) invalid();
  const declarations = new Map<string, { pair_id: string; work_ref: string; version_ref: string }[]>();
  for (const pair of value.pairs.filter(item => item.status === 'resolved')) for (const item of pair.latest!.input.identities) {
    declarations.set(item.source_id, [...(declarations.get(item.source_id) ?? []), { pair_id: pair.pair_id, work_ref: item.work_ref, version_ref: item.version_ref }]);
  }
  const conflicts = [...declarations].sort(([a], [b]) => a.localeCompare(b)).filter(([, items]) => new Set(items.map(item => JSON.stringify([item.work_ref, item.version_ref]))).size > 1)
    .map(([source_id, items]) => ({ source_id, declarations: items }));
  const gaps = value.sources.filter(source => categories.some(category => source.assessments[category] !== 'accepted'))
    .map(source => ({ source_id: source.source_id, categories: categories.filter(category => source.assessments[category] !== 'accepted') }));
  if (!same(value.identity_conflicts, conflicts) || !same(value.source_review_gaps, gaps)) invalid();
  return { receipt: value, evidence_json: envelope.evidence_json, evidence_sha256: envelope.evidence_sha256 };
}

export async function fetchSelection(ids: string[], signal: AbortSignal, download = false) {
  const response = await request<{ schema_version?: string; evidence_json: string; evidence_sha256: string }>(`/public-sources/selection-review${download ? '/export' : ''}`, {
    method: 'POST', body: JSON.stringify(selectionPayload(ids)), signal,
  });
  signal.throwIfAborted();
  if (download && response.schema_version !== 'source-selection-dossier-v1') throw new Error('Seçim dosyası doğrulanamadı.');
  const value = await validateSelection(response, ids); signal.throwIfAborted(); return value;
}
