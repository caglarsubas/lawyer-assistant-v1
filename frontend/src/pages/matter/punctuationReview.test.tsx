import { createHash, webcrypto } from 'node:crypto';
import { renderToStaticMarkup } from 'react-dom/server';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { onUnauthorized, setCsrfToken } from '../../api';
import { PunctuationReadings, PunctuationRunSummary, PunctuationRunWarning } from './PunctuationObservations';
import { canonicalPunctuationJson, capturePunctuationPage, loadPunctuationPage, loadPunctuationRaster, verifyPunctuationObservation, verifyPunctuationRun } from './punctuationReview';
import type { PunctuationAssessment, PunctuationCaptureRun, PunctuationEvent, PunctuationObservation, PunctuationSourcePins } from './punctuationTypes';

const sha = (data: string | Uint8Array) => createHash('sha256').update(data).digest('hex');
const quote = 'Saklanan alıntı değişmez.';
const pins: PunctuationSourcePins = { matterId: 'matter/1', analysisId: 'analysis/1', versionId: 'version/2', evidenceId: 'evidence/3',
  documentId: 'document-1', documentRevision: 4, documentSha256: 'a'.repeat(64), contentSha256: 'b'.repeat(64),
  quoteSha256: sha(quote), page: 2, pageCount: 3, quote };
const signal = () => new AbortController().signal;
function event(): PunctuationEvent {
  const reading = (reader: 'raw' | 'locally_leveled', text: string) => ({ reader, text,
    glyphs: [...text].map((char, index) => [char, [20 + index * 8, 25, 26 + index * 8, 40]] as [string, [number, number, number, number]]) });
  return { status: 'punctuation_disagreement', field_bounds: [20, 25, 70, 40], crop_bounds: [10, 10, 100, 50],
    coordinate_frame: 'original_raster_top_left_half_open', readings: [reading('raw', '16500.'), reading('locally_leveled', '16,500')],
    missing_readers: [], canonical_usable: false };
}
function seal(value: PunctuationObservation): PunctuationObservation {
  value.event_sha256 = sha(canonicalPunctuationJson(value.event));
  const { id: _id, created_at: _created, observation_sha256: _sha, ...metadata } = value;
  return { ...value, observation_sha256: sha(canonicalPunctuationJson(metadata)) };
}
function fixture(overrides = {}): PunctuationObservation {
  return seal({ id: 'pco-' + 'c'.repeat(60), created_at: '2026-11-19T01:00:00Z',
    analysis_id: pins.analysisId, version_id: pins.versionId, evidence_id: pins.evidenceId,
    content_sha256: pins.contentSha256, quote_sha256: pins.quoteSha256, document_id: pins.documentId,
    document_revision: pins.documentRevision, document_sha256: pins.documentSha256, page: pins.page, page_count: pins.pageCount,
    width: 200, height: 100, raster_sha256: 'd'.repeat(64), event: event(), event_sha256: '',
    producer_recipe: 'native-pdf-punctuation-v1', producer_sha256: 'e'.repeat(64), run_sha256: 'f'.repeat(64), run_id: 'pcr-' + '1'.repeat(60),
    scope: 'source_page_context', status: 'review_required', canonical_usable: false, immutable: true, observation_sha256: '', ...overrides });
}
function sealRun(value: PunctuationCaptureRun): PunctuationCaptureRun {
  const { id: _id, created_at: _created, receipt_sha256: _receipt, ...body } = value;
  return { ...value, receipt_sha256: sha(canonicalPunctuationJson(body)) };
}
function assessedFixture(assessment: PunctuationAssessment = { status: 'complete', reason: 'checked', stage: 'currency_fields' }) {
  return fixture({ producer_recipe: 'native-pdf-punctuation-v2', assessment });
}
function run(observation = fixture(), count = 1): PunctuationCaptureRun {
  const { event: _event, event_sha256: _eventSha, run_id, observation_sha256: _sha, ...metadata } = observation;
  const value = { ...metadata, id: run_id, event_count: count,
    status: observation.assessment?.status === 'incomplete' ? 'captured_incomplete'
      : count ? 'captured_review_observations' : 'captured_no_alternatives', receipt_sha256: '' } as PunctuationCaptureRun;
  return sealRun(value);
}
const png = new Uint8Array(Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/ScLbtAAAAABJRU5ErkJggg==', 'base64'));
function rasterFixture() {
  return fixture({ width: 1, height: 1, raster_sha256: sha(png), event: {
    status: 'field_unavailable', field_bounds: null, crop_bounds: null, coordinate_frame: 'original_raster_top_left_half_open',
    readings: [], missing_readers: ['raw', 'locally_leveled'], canonical_usable: false } });
}
function rasterResponse(observation: PunctuationObservation, overrides = {}, bytes = png, status = 200) {
  return new Response(new Uint8Array(bytes), { status, headers: { 'Content-Type': 'image/png',
    'X-Analysis-Content-SHA256': pins.contentSha256, 'X-Quote-SHA256': pins.quoteSha256,
    'X-Source-SHA256': pins.documentSha256, 'X-Source-Revision': String(pins.documentRevision),
    'X-Source-Page': String(pins.page), 'X-Source-Page-Count': String(pins.pageCount),
    'X-Punctuation-Observation-SHA256': observation.observation_sha256, 'X-Punctuation-Event-SHA256': observation.event_sha256,
    'X-Source-Raster-SHA256': observation.raster_sha256, ...overrides } });
}

describe('immutable source-page punctuation review', () => {
  const fetchMock = vi.fn<typeof fetch>();
  beforeEach(() => { fetchMock.mockReset(); vi.stubGlobal('fetch', fetchMock); vi.stubGlobal('crypto', webcrypto); });
  afterEach(() => { vi.unstubAllGlobals(); onUnauthorized(); setCsrfToken(''); });

  it('accepts exact immutable source pins and retains literal glyph readings', async () => {
    const observation = fixture();
    expect(await verifyPunctuationObservation(observation, pins, signal())).toBe(observation);
    const html = renderToStaticMarkup(<PunctuationReadings observation={observation} />);
    expect(html).toContain('16500.'); expect(html).toContain('16,500');
    expect(html).toContain('Ham görüntü okuması'); expect(html).toContain('Kontrastlı görüntü okuması');
    expect(html).toContain(pins.documentSha256); expect(html).not.toContain('Doğru okuma');
  });

  it.each(['analysis_id', 'version_id', 'evidence_id', 'document_id', 'content_sha256', 'quote_sha256', 'document_sha256', 'document_revision', 'page', 'page_count'] as const)(
    'refuses a re-hashed observation bound to another %s', async key => {
      const value = fixture();
      Object.assign(value, { [key]: typeof value[key] === 'number' ? 9 : '0'.repeat(64) });
      await expect(verifyPunctuationObservation(seal(value), pins, signal())).rejects.toMatchObject({ status: 409 });
    });

  it('rejects changed metadata, invented claim fields and changed saved quote text', async () => {
    const observation = fixture();
    await expect(verifyPunctuationObservation({ ...observation, width: 201 }, pins, signal())).rejects.toMatchObject({ status: 409 });
    await expect(verifyPunctuationObservation(seal(Object.assign(fixture(), { approved_text: '16500' })), pins, signal())).rejects.toMatchObject({ status: 409 });
    await expect(verifyPunctuationObservation(observation, { ...pins, quote: quote + ' ' }, signal())).rejects.toMatchObject({ status: 409 });
  });

  it.each([
    ['text not backed by glyphs', (value: PunctuationObservation) => { value.event.readings[0].text += '.'; }],
    ['glyph outside source crop', (value: PunctuationObservation) => { value.event.readings[0].glyphs[0][1] = [1, 1, 4, 4]; }],
    ['missing reader replaced by a claim', (value: PunctuationObservation) => { value.event.readings.pop(); }],
    ['matching readers relabeled disagreement', (value: PunctuationObservation) => { value.event.readings[1] = { ...value.event.readings[0], reader: 'locally_leveled' }; }],
    ['unbounded crop', (value: PunctuationObservation) => { value.event.crop_bounds = [0, 0, 201, 100]; }],
    ['canonical replacement permission', (value: PunctuationObservation) => { Object.assign(value.event, { canonical_usable: true }); }],
  ])('refuses %s even with recomputed digests', async (_label, modify) => {
    const value = fixture(); modify(value);
    await expect(verifyPunctuationObservation(seal(value), pins, signal())).rejects.toMatchObject({ status: 409 });
  });

  it('shows only a captured reader when the other is unavailable; creates no alternative', async () => {
    const value = fixture(); value.event.status = 'contrast_unavailable';
    value.event.readings.pop(); value.event.missing_readers = ['locally_leveled'];
    await verifyPunctuationObservation(seal(value), pins, signal());
    const html = renderToStaticMarkup(<PunctuationReadings observation={value} />);
    expect(html.match(/<blockquote/g)).toHaveLength(1);
    expect(html).toContain('16500.'); expect(html).not.toContain('16,500');
    expect(html).toContain('Yerine alternatif okuma üretilmedi.');
  });

  it('retains a genuine zero-event receipt without asserting source correctness', async () => {
    const receipt = run(fixture(), 0);
    expect(await verifyPunctuationRun(receipt, pins, signal())).toBe(receipt);
    await expect(verifyPunctuationRun(run(fixture(), 9), pins, signal())).rejects.toMatchObject({ status: 409 });
    await expect(verifyPunctuationRun(receipt, { ...pins, versionId: 'current' }, signal())).rejects.toMatchObject({ status: 409 });
  });

  it('keeps historical completion unknown without rewriting its metadata or readings', async () => {
    const observation = fixture(); const before = canonicalPunctuationJson(observation);
    const receipt = run(observation, 0);
    await verifyPunctuationObservation(observation, pins, signal());
    await verifyPunctuationRun(receipt, pins, signal());
    const html = renderToStaticMarkup(<PunctuationRunSummary run={receipt} />);
    expect(html).toContain('denetimin tamamlanma durumu bilinmiyor');
    expect(html).not.toContain('tamamlandı'); expect(html).not.toContain('noktalama farkı kaydedilmedi');
    expect(canonicalPunctuationJson(observation)).toBe(before);
    expect(Object.hasOwn(observation, 'assessment')).toBe(false);
  });

  it('binds the complete v2 assessment into observation and run digests', async () => {
    const observation = assessedFixture(); const receipt = run(observation);
    expect(await verifyPunctuationObservation(observation, pins, signal())).toBe(observation);
    expect(await verifyPunctuationRun(receipt, pins, signal())).toBe(receipt);
    const changed = { status: 'incomplete', reason: 'page_budget', stage: 'currency_fields' } as const;
    await expect(verifyPunctuationObservation({ ...observation, assessment: changed }, pins, signal())).rejects.toMatchObject({ status: 409 });
    await expect(verifyPunctuationRun({ ...receipt, assessment: changed, status: 'captured_incomplete' }, pins, signal())).rejects.toMatchObject({ status: 409 });
    expect(renderToStaticMarkup(<PunctuationRunSummary run={receipt} />)).toContain('Hedeflenen tutar denetimi tamamlandı.');
  });

  it('requires v2 assessment and forbids adding a completion verdict to legacy records', async () => {
    for (const observation of [fixture({ producer_recipe: 'native-pdf-punctuation-v2' }),
      fixture({ producer_recipe: 'unknown-v1' }), fixture({ assessment: assessedFixture().assessment })]) {
      await expect(verifyPunctuationObservation(observation, pins, signal())).rejects.toMatchObject({ status: 409 });
      await expect(verifyPunctuationRun(run(observation, 0), pins, signal())).rejects.toMatchObject({ status: 409 });
    }
  });

  it.each([
    ['extra assertion', { status: 'complete', reason: 'checked', stage: 'currency_fields', approved: true }],
    ['missing stage', { status: 'complete', reason: 'checked' }],
    ['unknown status', { status: 'accepted', reason: 'checked', stage: 'currency_fields' }],
    ['unknown reason', { status: 'incomplete', reason: 'other', stage: 'currency_fields' }],
    ['unknown stage', { status: 'incomplete', reason: 'page_budget', stage: 'other' }],
    ['complete nomination', { status: 'complete', reason: 'checked', stage: 'nomination_raw' }],
    ['complete error', { status: 'complete', reason: 'reader_error', stage: 'currency_fields' }],
    ['incomplete checked', { status: 'incomplete', reason: 'checked', stage: 'currency_fields' }],
    ['unverified nomination scope', { status: 'incomplete', reason: 'source_scope_unverified', stage: 'nomination_contrast' }],
    ['null assessment', null],
    ['array assessment', []],
  ])('refuses re-hashed assessment with %s', async (_label, assessment) => {
    const observation = fixture({ producer_recipe: 'native-pdf-punctuation-v2', assessment });
    await expect(verifyPunctuationObservation(observation, pins, signal())).rejects.toMatchObject({ status: 409 });
    await expect(verifyPunctuationRun(run(observation, 0), pins, signal())).rejects.toMatchObject({ status: 409 });
  });

  it('accepts no currency scope only for an empty completed run', async () => {
    const observation = assessedFixture({ status: 'complete', reason: 'no_currency_scope', stage: 'currency_fields' });
    const receipt = run(observation, 0);
    await verifyPunctuationRun(receipt, pins, signal());
    await expect(verifyPunctuationRun(run(observation, 1), pins, signal())).rejects.toMatchObject({ status: 409 });
    await expect(verifyPunctuationObservation(observation, pins, signal())).rejects.toMatchObject({ status: 409 });
    expect(renderToStaticMarkup(<PunctuationRunSummary run={receipt} />)).toContain('Sınırlı taramada desteklenen bir tutar alanı belirlenemedi.');
  });

  it.each(['page_budget', 'reader_error', 'reader_unavailable', 'source_scope_unverified'] as const)(
    'shows zero-event %s as incomplete and rejects a successful status relabel', async reason => {
      const receipt = run(assessedFixture({ status: 'incomplete', reason, stage: 'currency_fields' }), 0);
      await verifyPunctuationRun(receipt, pins, signal());
      const html = renderToStaticMarkup(<PunctuationRunSummary run={receipt} />);
      expect(html).toContain('Denetim tamamlanmadı'); expect(html).toContain('İnceleme gözlemi saklanmadı.');
      expect(html).not.toContain('noktalama farkı kaydedilmedi'); expect(html).not.toContain('denetimi tamamlandı');
      await expect(verifyPunctuationRun(sealRun({ ...receipt, status: 'captured_no_alternatives' }), pins, signal())).rejects.toMatchObject({ status: 409 });
    });

  it.each(['nomination_raw', 'nomination_contrast', 'currency_fields'] as const)(
    'accepts bounded interruption during %s without promoting the run', async stage => {
      const receipt = run(assessedFixture({ status: 'incomplete', reason: 'page_budget', stage }), 0);
      expect(await verifyPunctuationRun(receipt, pins, signal())).toBe(receipt);
    });

  it.each(['nomination_raw', 'nomination_contrast'] as const)(
    'rejects re-hashed field observations attributed to unfinished %s', async stage => {
      const observation = assessedFixture({ status: 'incomplete', reason: 'page_budget', stage });
      await expect(verifyPunctuationObservation(observation, pins, signal())).rejects.toMatchObject({ status: 409 });
      await expect(verifyPunctuationRun(run(observation), pins, signal())).rejects.toMatchObject({ status: 409 });
    });

  it('surfaces incomplete visible history above the accordion without claiming it is the latest run', () => {
    const incomplete = run(assessedFixture({ status: 'incomplete', reason: 'page_budget', stage: 'nomination_raw' }), 0);
    const html = renderToStaticMarkup(<PunctuationRunWarning runs={[incomplete, run(assessedFixture(), 0)]} />);
    expect(html).toContain('role="status"');
    expect(html).toContain('Gösterilen denetimler arasında tamamlanmayan kayıt var.');
    expect(html).toContain('Gözlem kaydı bulunmaması, denetimin tamamlandığını göstermez');
    expect(html).not.toContain('son denetim');
    expect(renderToStaticMarkup(<PunctuationRunWarning runs={[run(fixture(), 0)]} />)).toBe('');
    expect(renderToStaticMarkup(<PunctuationRunWarning runs={[run(assessedFixture(), 0)]} />)).toBe('');
  });

  it('retains a partial raw reading, labels it and rejects a complete diagnostic event', async () => {
    const observation = assessedFixture({ status: 'incomplete', reason: 'reader_unavailable', stage: 'currency_fields' });
    observation.event.status = 'contrast_unavailable'; observation.event.readings.pop();
    observation.event.missing_readers = ['locally_leveled'];
    const value = seal(observation); const before = canonicalPunctuationJson(value);
    await verifyPunctuationObservation(value, pins, signal());
    await verifyPunctuationRun(run(value), pins, signal());
    const html = renderToStaticMarkup(<PunctuationReadings observation={value} />);
    expect(html).toContain('Kısmi okuma.'); expect(html).toContain('Denetim tamamlanmadı');
    expect(html).toContain('16500.'); expect(html).not.toContain('16,500');
    expect(html.match(/<blockquote/g)).toHaveLength(1);
    expect(canonicalPunctuationJson(value)).toBe(before);
    await expect(verifyPunctuationObservation(seal({ ...value, assessment: {
      status: 'complete', reason: 'checked', stage: 'currency_fields',
    } }), pins, signal())).rejects.toMatchObject({ status: 409 });
  });

  it('rejects different re-hashed assessments on an observation and its returned run', async () => {
    const item = assessedFixture(); const receipt = run(assessedFixture({ status: 'incomplete', reason: 'page_budget', stage: 'currency_fields' }));
    fetchMock.mockResolvedValueOnce(Response.json({ items: [item], runs: [receipt], has_more: false, runs_has_more: false }));
    await expect(loadPunctuationPage(pins, 0, 0, signal())).rejects.toMatchObject({ status: 409 });
  });

  it('lists historical records using bounded independent offsets and refuses duplicate record identities', async () => {
    const item = fixture(); const receipt = run(item);
    fetchMock.mockResolvedValueOnce(Response.json({ items: [item], runs: [receipt], has_more: true, runs_has_more: false }));
    expect(await loadPunctuationPage(pins, 20, 40, signal())).toEqual({ items: [item], runs: [receipt], has_more: true, runs_has_more: false });
    expect(fetchMock.mock.calls[0][0]).toBe('/api/v1/matters/matter%2F1/analyses/analysis%2F1/versions/version%2F2/evidence/evidence%2F3/punctuation-observations/2?limit=20&offset=20&run_offset=40');
    expect(fetchMock.mock.calls[0][1]).toMatchObject({ credentials: 'same-origin', cache: 'no-store', redirect: 'error' });
    fetchMock.mockResolvedValueOnce(Response.json({ items: [item, item], runs: [receipt], has_more: false, runs_has_more: false }));
    await expect(loadPunctuationPage(pins, 0, 0, signal())).rejects.toMatchObject({ status: 409 });
  });

  it('triggers only server capture with exact pins and CSRF; sends no events, pixels or content body', async () => {
    setCsrfToken('disposable-csrf'); fetchMock.mockResolvedValueOnce(Response.json({}));
    await capturePunctuationPage(pins, signal());
    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toBe('/api/v1/matters/matter%2F1/analyses/analysis%2F1/versions/version%2F2/evidence/evidence%2F3/punctuation-observations/2');
    expect(options).toMatchObject({ method: 'POST', credentials: 'same-origin', cache: 'no-store', redirect: 'error' });
    expect(options?.body).toBeUndefined();
    const headers = new Headers(options?.headers);
    expect(headers.get('X-CSRF-Token')).toBe('disposable-csrf');
    expect(headers.get('X-Analysis-Content-SHA256')).toBe(pins.contentSha256);
    expect(headers.get('X-Quote-SHA256')).toBe(pins.quoteSha256);
  });

  it('retrieves bytes only for the chosen record and validates PNG identity and dimensions', async () => {
    const value = rasterFixture(); fetchMock.mockResolvedValueOnce(rasterResponse(value));
    const blob = await loadPunctuationRaster(pins, value, signal());
    expect(new Uint8Array(await blob.arrayBuffer())).toEqual(png);
    expect(fetchMock.mock.calls[0][0]).toContain(`/punctuation-observations/2/${value.id}/raster`);
    expect(fetchMock.mock.calls[0][1]).toMatchObject({ credentials: 'same-origin', cache: 'no-store', redirect: 'error' });
  });

  it.each(['X-Analysis-Content-SHA256', 'X-Quote-SHA256', 'X-Source-SHA256', 'X-Source-Revision', 'X-Source-Page',
    'X-Source-Page-Count', 'X-Punctuation-Observation-SHA256', 'X-Punctuation-Event-SHA256', 'X-Source-Raster-SHA256', 'Content-Type'])(
    'refuses wrong raster echo %s', async header => {
      const value = rasterFixture(); fetchMock.mockResolvedValueOnce(rasterResponse(value, { [header]: 'wrong' }));
      await expect(loadPunctuationRaster(pins, value, signal())).rejects.toMatchObject({ status: 409 });
    });

  it('rejects altered bytes and a re-hashed PNG whose dimensions disagree', async () => {
    const value = rasterFixture(); const altered = png.slice(); altered[altered.length - 1] ^= 1;
    fetchMock.mockResolvedValueOnce(rasterResponse(value, {}, altered));
    await expect(loadPunctuationRaster(pins, value, signal())).rejects.toMatchObject({ status: 409 });
    const wrongSize = fixture({ ...value, width: 2 });
    fetchMock.mockResolvedValueOnce(rasterResponse(wrongSize));
    await expect(loadPunctuationRaster(pins, wrongSize, signal())).rejects.toMatchObject({ status: 409 });
  });

  it('revokes the local session on lost access and never falls back to a newer source', async () => {
    const logout = vi.fn(); onUnauthorized(logout); const value = rasterFixture();
    fetchMock.mockResolvedValueOnce(Response.json({}, { status: 401 }));
    await expect(loadPunctuationRaster(pins, value, signal())).rejects.toMatchObject({ status: 401 });
    expect(logout).toHaveBeenCalledOnce(); expect(fetchMock).toHaveBeenCalledOnce();
  });

  it('discards PNG bytes that finish after selection closure', async () => {
    const controller = new AbortController(); const value = rasterFixture(); const response = rasterResponse(value);
    vi.spyOn(response, 'arrayBuffer').mockImplementation(async () => { controller.abort(); return png.slice().buffer; });
    fetchMock.mockResolvedValueOnce(response);
    await expect(loadPunctuationRaster(pins, value, controller.signal)).rejects.toMatchObject({ name: 'AbortError' });
  });
});
