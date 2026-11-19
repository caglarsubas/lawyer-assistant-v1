import { ApiError, fetchPunctuationRaster, request } from '../../api';
import type { PunctuationCaptureRun, PunctuationEvent, PunctuationObservation, PunctuationPage, PunctuationSourcePins, RasterBox } from './punctuationTypes';

const READERS = ['raw', 'locally_leveled'];
const COMMON_KEYS = ['id', 'created_at', 'analysis_id', 'version_id', 'evidence_id', 'content_sha256', 'quote_sha256',
  'document_id', 'document_revision', 'document_sha256', 'page', 'page_count', 'raster_sha256', 'width', 'height',
  'producer_sha256', 'producer_recipe', 'assessment', 'run_sha256', 'scope', 'status', 'canonical_usable', 'immutable'];
const SHA256_FIELDS = ['content_sha256', 'quote_sha256', 'document_sha256', 'raster_sha256', 'producer_sha256', 'run_sha256'] as const;
export const PUNCTUATION_LABELS: Record<PunctuationEvent['status'], string> = {
  punctuation_disagreement: 'Noktalama okumaları uyuşmuyor', field_unavailable: 'Okuma bölgesi belirlenemedi',
  raw_unavailable: 'Ham görüntü okuması tamamlanamadı', contrast_unavailable: 'Kontrastlı okuma tamamlanamadı',
  page_budget: 'Okuma zaman sınırında tamamlanamadı', reader_error: 'OCR okuması tamamlanamadı',
  invalid_glyph_vector: 'Karakter konumları doğrulanamadı', source_ink_unverified: 'Kaynak görüntü bağı doğrulanamadı',
};
const isHash = (value: unknown): value is string => typeof value === 'string' && value.length === 64 && !/[^a-f0-9]/.test(value);
const positive = (value: unknown): value is number => Number.isSafeInteger(value) && Number(value) > 0;
const identifier = (value: unknown): value is string => typeof value === 'string' && value.length > 0 && value.length <= 500 && !/[\u0000-\u001f]/.test(value);
const same = (left: unknown, right: unknown): boolean => JSON.stringify(left) === JSON.stringify(right);
const contains = (outer: RasterBox, inner: RasterBox) => outer[0] <= inner[0] && outer[1] <= inner[1] && inner[2] <= outer[2] && inner[3] <= outer[3];
const unavailable = () => new ApiError('Kaydedilen noktalama gözleminin kaynak ve sürüm bağı doğrulanamadı.', 409);
function requireThat(condition: unknown): asserts condition { if (!condition) throw unavailable(); }

export function canonicalPunctuationJson(value: unknown): string {
  if (Array.isArray(value)) return '[' + value.map(canonicalPunctuationJson).join(',') + ']';
  if (value !== null && typeof value === 'object') {
    return '{' + Object.keys(value).sort().map(key => JSON.stringify(key) + ':' + canonicalPunctuationJson((value as Record<string, unknown>)[key])).join(',') + '}';
  }
  const result = JSON.stringify(value);
  requireThat(result !== undefined);
  return result;
}

export async function punctuationDigest(value: string): Promise<string> {
  requireThat(globalThis.crypto?.subtle);
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(value));
  return Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, '0')).join('');
}

export function punctuationBase(pins: PunctuationSourcePins) {
  return `/matters/${encodeURIComponent(pins.matterId)}/analyses/${encodeURIComponent(pins.analysisId)}/versions/${encodeURIComponent(pins.versionId)}/evidence/${encodeURIComponent(pins.evidenceId)}/punctuation-observations/${pins.page}`;
}
export function punctuationHeaders(pins: PunctuationSourcePins) {
  return { 'X-Analysis-Content-SHA256': pins.contentSha256, 'X-Quote-SHA256': pins.quoteSha256 };
}

function verifySource(value: PunctuationObservation | PunctuationCaptureRun, pins: PunctuationSourcePins) {
  requireThat(value && identifier(value.id) && typeof value.created_at === 'string' && Number.isFinite(Date.parse(value.created_at))
    && value.scope === 'source_page_context' && value.immutable === true && value.canonical_usable === false
    && value.analysis_id === pins.analysisId && value.version_id === pins.versionId && value.evidence_id === pins.evidenceId
    && value.content_sha256 === pins.contentSha256 && value.quote_sha256 === pins.quoteSha256
    && value.document_id === pins.documentId && value.document_revision === pins.documentRevision
    && value.document_sha256 === pins.documentSha256 && value.page === pins.page && value.page_count === pins.pageCount
    && SHA256_FIELDS.every(key => isHash(value[key])) && positive(value.width) && positive(value.height)
    && value.width * value.height <= 4_000_000
    && ['native-pdf-punctuation-v1', 'native-pdf-punctuation-v2'].includes(value.producer_recipe));
}

function verifyAssessment(value: PunctuationObservation | PunctuationCaptureRun, eventCount: number, event?: PunctuationEvent) {
  if (value.producer_recipe === 'native-pdf-punctuation-v1') {
    requireThat(!Object.hasOwn(value, 'assessment'));
    return;
  }
  const assessment = value.assessment;
  requireThat(assessment && typeof assessment === 'object' && !Array.isArray(assessment)
    && same(Object.keys(assessment).sort(), ['reason', 'stage', 'status'])
    && ['nomination_raw', 'nomination_contrast', 'currency_fields'].includes(assessment.stage)
    && (eventCount === 0 || assessment.stage === 'currency_fields'));
  if (assessment.status === 'complete') {
    requireThat(assessment.stage === 'currency_fields'
      && ['checked', 'no_currency_scope'].includes(assessment.reason)
      && (assessment.reason !== 'no_currency_scope' || eventCount === 0)
      && (!event || event.status === 'punctuation_disagreement'));
  } else {
    requireThat(assessment.status === 'incomplete'
      && ['page_budget', 'reader_error', 'reader_unavailable', 'source_scope_unverified'].includes(assessment.reason)
      && (assessment.reason !== 'source_scope_unverified' || assessment.stage === 'currency_fields'));
  }
}

export function verifyPunctuationEvent(event: PunctuationEvent, width: number, height: number): void {
  const validBox = (value: unknown): value is RasterBox => Array.isArray(value) && value.length === 4 && value.every(Number.isSafeInteger)
    && 0 <= value[0] && value[0] < value[2] && value[2] <= width && 0 <= value[1] && value[1] < value[3] && value[3] <= height;
  requireThat(event && event.canonical_usable === false && event.coordinate_frame === 'original_raster_top_left_half_open'
    && Object.keys(event).every(key => ['status', 'field_bounds', 'crop_bounds', 'coordinate_frame', 'readings', 'missing_readers', 'canonical_usable', 'region'].includes(key))
    && Array.isArray(event.readings) && event.readings.length <= 2);
  if (event.region !== undefined) requireThat(validBox(event.region));
  if (event.status === 'field_unavailable') {
    requireThat(event.field_bounds === null && event.crop_bounds === null && event.readings.length === 0 && same(event.missing_readers, READERS));
    return;
  }
  requireThat(validBox(event.crop_bounds) && validBox(event.field_bounds) && contains(event.crop_bounds, event.field_bounds)
    && event.crop_bounds[2] - event.crop_bounds[0] <= 640 && event.crop_bounds[3] - event.crop_bounds[1] <= 150);
  const readers = new Set<string>();
  for (const reading of event.readings) {
    requireThat(reading && Object.keys(reading).every(key => ['reader', 'text', 'glyphs'].includes(key))
      && READERS.includes(reading.reader) && !readers.has(reading.reader)
      && typeof reading.text === 'string' && reading.text.length > 0 && reading.text.length <= 40
      && Array.isArray(reading.glyphs) && reading.glyphs.length > 0 && reading.glyphs.length <= 20);
    for (const glyph of reading.glyphs) {
      requireThat(Array.isArray(glyph) && glyph.length === 2 && typeof glyph[0] === 'string'
        && /^[0-9.,−–-]$/.test(glyph[0]) && validBox(glyph[1]) && contains(event.crop_bounds, glyph[1]));
    }
    requireThat(reading.text === reading.glyphs.map(glyph => glyph[0]).join(''));
    readers.add(reading.reader);
  }
  requireThat(same(event.missing_readers, READERS.filter(reader => !readers.has(reader))));
  if (event.status === 'punctuation_disagreement') {
    requireThat(readers.size === 2 && event.readings.every(reading => /^[-−–]?[0-9][0-9.,]*$/.test(reading.text)));
    const marks = event.readings.map(reading => [...reading.text.replace(/^[-−–]/, '')]
      .flatMap((char, index) => char === '.' || char === ',' ? [[index, char]] : []));
    requireThat(!same(marks[0], marks[1]));
  } else {
    requireThat(Object.hasOwn(PUNCTUATION_LABELS, event.status));
  }
}

export async function verifyPunctuationObservation(value: PunctuationObservation, pins: PunctuationSourcePins, signal: AbortSignal) {
  verifySource(value, pins);
  requireThat(Object.keys(value).every(key => [...COMMON_KEYS, 'event', 'event_sha256', 'run_id', 'observation_sha256'].includes(key))
    && /^pco-[a-f0-9]{60}$/.test(value.id) && value.status === 'review_required' && /^pcr-[a-f0-9]{60}$/.test(value.run_id)
    && isHash(value.event_sha256) && isHash(value.observation_sha256));
  verifyPunctuationEvent(value.event, value.width, value.height);
  verifyAssessment(value, 1, value.event);
  const { id: _id, created_at: _created, observation_sha256: _digest, ...metadata } = value;
  const [observationDigest, eventDigest, quoteDigest] = await Promise.all([
    punctuationDigest(canonicalPunctuationJson(metadata)), punctuationDigest(canonicalPunctuationJson(value.event)), punctuationDigest(pins.quote),
  ]);
  signal.throwIfAborted();
  requireThat(observationDigest === value.observation_sha256 && eventDigest === value.event_sha256 && quoteDigest === pins.quoteSha256);
  return value;
}

export async function verifyPunctuationRun(value: PunctuationCaptureRun, pins: PunctuationSourcePins, signal: AbortSignal) {
  verifySource(value, pins);
  requireThat(Object.keys(value).every(key => [...COMMON_KEYS, 'event_count', 'receipt_sha256'].includes(key))
    && /^pcr-[a-f0-9]{60}$/.test(value.id) && Number.isSafeInteger(value.event_count) && value.event_count >= 0 && value.event_count <= 8 && isHash(value.receipt_sha256)
    && value.status === (value.assessment?.status === 'incomplete' ? 'captured_incomplete'
      : value.event_count === 0 ? 'captured_no_alternatives' : 'captured_review_observations'));
  verifyAssessment(value, value.event_count);
  const { id: _id, created_at: _created, receipt_sha256: _digest, ...metadata } = value;
  const [digest, quoteDigest] = await Promise.all([punctuationDigest(canonicalPunctuationJson(metadata)), punctuationDigest(pins.quote)]);
  signal.throwIfAborted();
  requireThat(digest === value.receipt_sha256 && quoteDigest === pins.quoteSha256);
  return value;
}

export async function capturePunctuationPage(pins: PunctuationSourcePins, signal: AbortSignal) {
  await request(punctuationBase(pins), { method: 'POST', headers: punctuationHeaders(pins), signal, refreshPortfolio: false, redirect: 'error' });
  signal.throwIfAborted();
}

export async function loadPunctuationPage(pins: PunctuationSourcePins, offset: number, runOffset: number, signal: AbortSignal): Promise<PunctuationPage> {
  const page = await request<PunctuationPage>(`${punctuationBase(pins)}?limit=20&offset=${offset}&run_offset=${runOffset}`, {
    headers: punctuationHeaders(pins), signal, redirect: 'error',
  });
  signal.throwIfAborted();
  requireThat(page && Array.isArray(page.items) && page.items.length <= 20 && Array.isArray(page.runs) && page.runs.length <= 20
    && typeof page.has_more === 'boolean' && typeof page.runs_has_more === 'boolean'
    && page.items.every(item => item && identifier(item.id)) && page.runs.every(run => run && identifier(run.id))
    && new Set(page.items.map(item => item.id)).size === page.items.length && new Set(page.runs.map(run => run.id)).size === page.runs.length);
  const [items, runs] = await Promise.all([
    Promise.all(page.items.map(item => verifyPunctuationObservation(item, pins, signal))),
    Promise.all(page.runs.map(run => verifyPunctuationRun(run, pins, signal))),
  ]);
  signal.throwIfAborted();
  for (const item of items) {
    const run = runs.find(candidate => candidate.id === item.run_id);
    if (run) requireThat(run.producer_recipe === item.producer_recipe
      && canonicalPunctuationJson(run.assessment ?? null) === canonicalPunctuationJson(item.assessment ?? null));
  }
  return { items, runs, has_more: page.has_more, runs_has_more: page.runs_has_more };
}

export async function loadPunctuationRaster(pins: PunctuationSourcePins, selected: PunctuationObservation, signal: AbortSignal) {
  await verifyPunctuationObservation(selected, pins, signal);
  const blob = await fetchPunctuationRaster(`${punctuationBase(pins)}/${encodeURIComponent(selected.id)}/raster`, {
    ...punctuationHeaders(pins), 'X-Source-SHA256': pins.documentSha256, 'X-Source-Revision': String(pins.documentRevision),
    'X-Source-Page': String(pins.page), 'X-Source-Page-Count': String(pins.pageCount),
    'X-Punctuation-Observation-SHA256': selected.observation_sha256, 'X-Punctuation-Event-SHA256': selected.event_sha256,
    'X-Source-Raster-SHA256': selected.raster_sha256,
  }, signal);
  const bytes = await blob.arrayBuffer();
  signal.throwIfAborted();
  requireThat(bytes.byteLength >= 33);
  const view = new DataView(bytes);
  requireThat(view.getBigUint64(0) === 0x89504e470d0a1a0an && view.getUint32(8) === 13 && view.getUint32(12) === 0x49484452
    && view.getUint32(16) === selected.width && view.getUint32(20) === selected.height);
  return blob;
}
