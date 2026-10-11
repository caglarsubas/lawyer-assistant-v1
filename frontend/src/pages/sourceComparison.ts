import { request } from '../api';
import type { PublicSourcePassage, PublicSourcePassages } from '../types';

export const COMPARISON_WINDOW = 2000;
export interface ComparisonSelection { source: PublicSourcePassages; passage: PublicSourcePassage }
export interface ComparisonWindow {
  source_id: string; source_version_id: string; title: string; source_url: string; domain: string; raw_media_type: string;
  artifacts: Record<string, { sha256: string; bytes: number }>; source_text_code_points: number;
  passage_id: string; locator: string; passage_start: number; passage_end: number; passage_sha256: string;
  start: number; end: number; text: string; window_sha256: string; next_offset: number | null; integrity_scope: string;
}
export interface SourceComparison {
  schema_version: 'public-source-comparison-v1'; left: ComparisonWindow; right: ComparisonWindow;
  offset_unit: 'unicode_code_points'; window_limit: number; raw_bytes_equal: boolean; extracted_text_equal: boolean;
  difference: { scope: 'selected_windows_only'; equal: boolean; common_prefix_code_points: number; common_suffix_code_points: number; left_range: [number, number]; right_range: [number, number]; range_unit: 'window_relative_unicode_code_points'; method: 'literal_common_edges_v1' };
  normalization: 'none'; legal_identity_status: 'unresolved'; legal_version_status: 'unresolved'; independent_originals_verified: false;
  current_law_verified: false; human_review_recorded: false; limitations: string[];
}
export interface ComparisonEvidence { receipt: SourceComparison; evidence_json: string; evidence_sha256: string }

export async function comparisonHash(text: string) {
  return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text))), byte => byte.toString(16).padStart(2, '0')).join('');
}

function selectedWindow(selection: ComparisonSelection, offset: number) {
  const { source, passage } = selection;
  if (!/^[a-f0-9]{64}$/.test(source.source_id) || !/^[A-Za-z][A-Za-z0-9_-]{0,79}$/.test(passage.id)
    || source.integrity_scope !== 'all_artifacts_verified' || source.offset_unit !== 'unicode_code_points'
    || !source.items.some(item => item.id === passage.id && item.text_sha256 === passage.text_sha256)
    || !Number.isInteger(offset) || offset < 0 || offset >= passage.end - passage.start
    || Array.from(passage.text).length !== passage.end - passage.start) throw new Error('Karşılaştırma seçimi geçersiz.');
  return Array.from(passage.text).slice(offset, offset + COMPARISON_WINDOW).join('');
}

async function validWindow(value: ComparisonWindow, selection: ComparisonSelection, offset: number, text: string) {
  const { source, passage } = selection;
  const end = passage.start + offset + Array.from(text).length;
  return value && value.source_id === source.source_id && value.source_version_id === source.source_version_id
    && value.passage_id === passage.id && value.locator === passage.locator && value.passage_start === passage.start
    && value.passage_end === passage.end && value.passage_sha256 === passage.text_sha256
    && value.start === passage.start + offset && value.end === end && value.text === text
    && value.next_offset === (end < passage.end ? end - passage.start : null)
    && value.integrity_scope === 'all_artifacts_verified' && Number.isInteger(value.source_text_code_points)
    && value.source_text_code_points >= passage.end && value.window_sha256 === await comparisonHash(text)
    && value.artifacts?.['raw.bin']?.sha256 === source.raw_sha256 && value.artifacts?.['text.txt']?.sha256 === source.text_sha256
    && ['source.json', 'locators.json', 'raw.bin', 'text.txt'].every(name => /^[a-f0-9]{64}$/.test(value.artifacts?.[name]?.sha256)
      && Number.isInteger(value.artifacts[name].bytes) && value.artifacts[name].bytes > 0)
    && ['title', 'source_url', 'domain', 'raw_media_type'].every(key => typeof value[key as keyof ComparisonWindow] === 'string');
}

export function commonEdges(left: string, right: string) {
  const a = Array.from(left), b = Array.from(right); const shortest = Math.min(a.length, b.length);
  let prefix = 0, suffix = 0;
  while (prefix < shortest && a[prefix] === b[prefix]) prefix++;
  while (suffix < shortest - prefix && a[a.length - 1 - suffix] === b[b.length - 1 - suffix]) suffix++;
  return { prefix, suffix, left: [prefix, a.length - suffix], right: [prefix, b.length - suffix] };
}

export async function fetchSourceComparison(left: ComparisonSelection, right: ComparisonSelection, offset = 0, otherOffset = 0, signal?: AbortSignal): Promise<ComparisonEvidence> {
  const a = selectedWindow(left, offset), b = selectedWindow(right, otherOffset);
  if (left.source.source_id === right.source.source_id) throw new Error('İki farklı kaynak paketi seçin.');
  const controller = new AbortController(); const abort = () => controller.abort();
  signal?.addEventListener('abort', abort, { once: true }); if (signal?.aborted) controller.abort();
  const timeout = setTimeout(abort, 30000);
  try {
    controller.signal.throwIfAborted();
    const params = new URLSearchParams({ other_source_id: right.source.source_id, passage_id: left.passage.id, other_passage_id: right.passage.id, offset: String(offset), other_offset: String(otherOffset), limit: String(COMPARISON_WINDOW) });
    const envelope = await request<{ evidence_json: string; evidence_sha256: string }>(`/public-sources/${left.source.source_id}/comparison?${params}`, { signal: controller.signal });
    controller.signal.throwIfAborted();
    if (!envelope || typeof envelope.evidence_json !== 'string' || envelope.evidence_json.length > 100000
      || !/^[a-f0-9]{64}$/.test(envelope.evidence_sha256) || await comparisonHash(envelope.evidence_json) !== envelope.evidence_sha256) throw new Error('Karşılaştırma kanıtının içerik özeti doğrulanamadı.');
    let value: SourceComparison;
    try { value = JSON.parse(envelope.evidence_json); } catch { throw new Error('Karşılaştırma kanıtı okunamadı.'); }
    const edges = commonEdges(a, b), diff = value?.difference;
    if (!value || value.schema_version !== 'public-source-comparison-v1' || value.offset_unit !== 'unicode_code_points'
      || value.window_limit !== COMPARISON_WINDOW || value.normalization !== 'none' || value.legal_identity_status !== 'unresolved'
      || value.legal_version_status !== 'unresolved' || value.independent_originals_verified !== false
      || value.current_law_verified !== false || value.human_review_recorded !== false
      || value.raw_bytes_equal !== (left.source.raw_sha256 === right.source.raw_sha256)
      || value.extracted_text_equal !== (left.source.text_sha256 === right.source.text_sha256)
      || !Array.isArray(value.limitations) || !value.limitations.every(item => typeof item === 'string')
      || !diff || diff.scope !== 'selected_windows_only' || diff.equal !== (a === b) || diff.method !== 'literal_common_edges_v1'
      || diff.range_unit !== 'window_relative_unicode_code_points' || diff.common_prefix_code_points !== edges.prefix
      || diff.common_suffix_code_points !== edges.suffix || JSON.stringify(diff.left_range) !== JSON.stringify(edges.left)
      || JSON.stringify(diff.right_range) !== JSON.stringify(edges.right)
      || !await validWindow(value.left, left, offset, a) || !await validWindow(value.right, right, otherOffset, b)) throw new Error('Karşılaştırma yanıtı seçili kaynak ve pasajlarla eşleşmiyor.');
    controller.signal.throwIfAborted();
    return { receipt: value, evidence_json: envelope.evidence_json, evidence_sha256: envelope.evidence_sha256 };
  } finally { clearTimeout(timeout); signal?.removeEventListener('abort', abort); }
}
