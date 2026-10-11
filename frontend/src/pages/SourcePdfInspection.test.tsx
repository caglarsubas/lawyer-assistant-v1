import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import type { PublicSourceOriginalPdf, PublicSourcePassages } from '../types';
import { SourcePassageList } from './SourceReviewPage';
import SourcePdfView, { fetchOriginalSourcePdf, mappedPdfPage, sourcePdfOptions, sourcePdfViewport } from './SourcePdfInspection';

const raw = new TextEncoder().encode('%PDF-1.4 SYNTHETIC original fixture');
const hash = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', raw)), value => value.toString(16).padStart(2, '0')).join('');
const sourceId = 'a'.repeat(64), text = 'SYNTHETIC İ😀 <script>untrusted</script>', length = Array.from(text).length;
const passage = { id: 'pdf_page_0002', locator: `PDF page 2; extracted page code points [0,${length})`, start: 10, end: 10 + length, text, text_sha256: 'b'.repeat(64) };
const data: PublicSourcePassages = { source_id: sourceId, source_version_id: 'fixture-version', raw_sha256: hash, text_sha256: 'c'.repeat(64), total: 2, items: [passage], next_offset: null, offset_unit: 'unicode_code_points', integrity_scope: 'all_artifacts_verified' };
const binding: PublicSourceOriginalPdf = { source_id: sourceId, source_version_id: data.source_version_id, passage_id: passage.id, raw_sha256: hash, text_sha256: data.text_sha256, raw_bytes: raw.length, raw_media_type: 'application/pdf', page: 2, page_count: 2, integrity_scope: 'all_artifacts_verified', locator_coordinate_status: 'consistent_not_fidelity_reviewed', extraction_fidelity_verified: false };
const attachment = (bytes = raw, headers = {}) => new Response(bytes, { headers: { 'Content-Type': 'application/octet-stream', 'Content-Disposition': 'attachment; filename="original.bin"', ...headers } });

describe('exact local original-PDF inspection', () => {
  const fetchMock = vi.fn<typeof fetch>();
  beforeEach(() => { vi.stubGlobal('fetch', fetchMock); fetchMock.mockReset(); });
  afterEach(() => { vi.unstubAllGlobals(); });
  it('checks the selected binding before fresh same-origin attachment bytes', async () => {
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify(binding))).mockResolvedValueOnce(attachment());
    const result = await fetchOriginalSourcePdf(data, passage.id, new AbortController().signal);
    expect(result).toEqual({ kind: 'pdf', binding, bytes: raw });
    expect(fetchMock.mock.calls.map(call => call[0])).toEqual([`/api/v1/public-sources/${sourceId}/original-pdf?passage_id=pdf_page_0002`, `/api/v1/public-sources/${sourceId}/original`]);
    for (const [, options] of fetchMock.mock.calls) { expect(options?.credentials).toBe('same-origin'); expect(options?.body).toBeUndefined(); expect(options?.signal).toBeInstanceOf(AbortSignal); }
    expect(fetchMock.mock.calls[1][1]?.cache).toBe('no-store');
  });
  it.each([{ source_id: 'x' }, { source_version_id: 'other' }, { passage_id: 'pdf_page_0001' }, { raw_sha256: 'f'.repeat(64) }, { text_sha256: 'f'.repeat(64) }, { raw_media_type: 'text/html' }, { page: 1 }, { page_count: 1 }, { page_count: 51 }, { page_count: 2.1 }, { raw_bytes: 0 }, { raw_bytes: 1048577 }, { raw_bytes: 2.2 }, { integrity_scope: 'manifest_only' }, { extraction_fidelity_verified: true }, { locator_coordinate_status: 'reviewed' }])('rejects mismatched binding before bytes: %j', async change => {
    fetchMock.mockResolvedValue(new Response(JSON.stringify({ ...binding, ...change })));
    await expect(fetchOriginalSourcePdf(data, passage.id)).rejects.toThrow('eşleşmiyor'); expect(fetchMock).toHaveBeenCalledOnce();
  });
  it.each(['page 2', 'PDF page 51; extracted page code points [0,20)', 'PDF page 2; extracted page code points [1,20)', `PDF page 2; extracted page code points [0,${length + 1})`])('does not guess inconsistent page: %s', async locator => {
    const item = { ...passage, locator }; expect(mappedPdfPage(item)).toBeNull();
    await expect(fetchOriginalSourcePdf({ ...data, items: [item] }, item.id)).rejects.toThrow('konumu geçersiz'); expect(fetchMock).not.toHaveBeenCalled();
  });
  it('rejects absent passage/wrong package before fetching', async () => {
    await expect(fetchOriginalSourcePdf(data, 'pdf_page_0001')).rejects.toThrow('konumu geçersiz');
    await expect(fetchOriginalSourcePdf({ ...data, source_id: '../private' }, passage.id)).rejects.toThrow('konumu geçersiz');
    expect(fetchMock).not.toHaveBeenCalled();
  });
  it.each([401, 403, 409])('does not fallback or retry denied bytes: %i', async status => {
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify(binding))).mockResolvedValueOnce(new Response('{}', { status }));
    await expect(fetchOriginalSourcePdf(data, passage.id)).rejects.toMatchObject({ status }); expect(fetchMock).toHaveBeenCalledTimes(2);
  });
  it.each([{ 'Content-Type': 'application/pdf' }, { 'Content-Disposition': 'inline' }, { 'Content-Length': String(raw.length + 1) }])('rejects unsafe headers: %j', async headers => {
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify(binding))).mockResolvedValueOnce(attachment(raw, headers));
    await expect(fetchOriginalSourcePdf(data, passage.id)).rejects.toThrow();
  });
  it.each([raw.slice(0, -1), new Uint8Array([...raw, 32])])('rejects incomplete/oversized bytes', async bytes => {
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify(binding))).mockResolvedValueOnce(attachment(bytes));
    await expect(fetchOriginalSourcePdf(data, passage.id)).rejects.toThrow();
  });
  it('detects same-length tampering with SHA256', async () => {
    const changed = raw.slice(); changed[changed.length - 1] ^= 1;
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify(binding))).mockResolvedValueOnce(attachment(changed));
    await expect(fetchOriginalSourcePdf(data, passage.id)).rejects.toThrow('içerik özeti');
  });
  it('cancels after binding if selection changed', async () => {
    const controller = new AbortController();
    fetchMock.mockImplementationOnce(async () => { controller.abort(); return new Response(JSON.stringify(binding)); });
    await expect(fetchOriginalSourcePdf(data, passage.id, controller.signal)).rejects.toMatchObject({ name: 'AbortError' }); expect(fetchMock).toHaveBeenCalledOnce();
  });
  it('compares independently of review acceptance without URLs/frames/forms', () => {
    const markup = renderToStaticMarkup(<SourcePassageList data={data} offset={0} selected={[]} canSelect={false} onSelect={() => undefined} onPage={() => undefined} onOriginal={() => undefined} original={{ passageId: passage.id, offset: 0, state: { status: 'loaded', value: { kind: 'pdf', binding, bytes: raw } } }} />);
    expect(markup).toContain('Özgün PDF sayfasıyla karşılaştır'); expect(markup).toContain('Sayfa 2 / 2'); expect(markup).toContain('source-comparison'); expect(markup).toContain('insan incelemesi gerektirir');
    for (const value of ['checkbox', '<iframe', '<object', '<script>', 'blob:']) expect(markup).not.toContain(value);
    expect(markup).toContain('&lt;script&gt;untrusted&lt;/script&gt;');
    expect(renderToStaticMarkup(<SourcePdfView data={{ kind: 'pdf', binding, bytes: raw }} onClose={() => undefined} />)).toContain('inceleme kabulü değildir');
  });
  it('never displays another passage\'s prior PDF', () => {
    const markup = renderToStaticMarkup(<SourcePassageList data={data} offset={0} selected={[]} canSelect={false} onSelect={() => undefined} onPage={() => undefined} original={{ passageId: 'pdf_page_0001', offset: 0, state: { status: 'loaded', value: { kind: 'pdf', binding, bytes: raw } } }} />);
    expect(markup).not.toContain('<canvas');
  });
  it('loads data with bundled paths and strict parser options', () => {
    const options = sourcePdfOptions(raw); expect(options.data).toEqual(raw); expect(options.data).not.toBe(raw);
    for (const key of ['url', 'docBaseUrl', 'password']) expect(options).not.toHaveProperty(key);
    expect(options.enableXfa).toBe(false); expect(options.stopAtErrors).toBe(true); expect(options.useSystemFonts).toBe(false);
    for (const key of ['cMapUrl', 'standardFontDataUrl', 'wasmUrl', 'iccUrl'] as const) expect(options[key]).toMatch(/^\/pdfjs-assets\//);
  });
  it('caps high-DPI canvas and rejects invalid geometry', () => {
    for (const [width, height] of [[612, 792], [1, 200000], [200000, 1]]) { const { scale, pixelRatio } = sourcePdfViewport(width, height, 4000, 2, 4); expect(pixelRatio).toBe(2); expect(Math.ceil(Math.max(width, height) * scale * pixelRatio)).toBeLessThanOrEqual(4096); }
    for (const invalid of [0, -1, Infinity, Number.NaN]) expect(() => sourcePdfViewport(invalid, 792, 500, 1, 1)).toThrow();
    expect(() => sourcePdfViewport(612, 792, 500, 3, 1)).toThrow();
  });
});
