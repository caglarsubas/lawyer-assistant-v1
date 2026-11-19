import { createHash, webcrypto } from 'node:crypto';
import { renderToStaticMarkup } from 'react-dom/server';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { onUnauthorized } from '../../api';
import { PdfPreview } from './OriginalPreview';
import { loadSavedAnalysisSource, type SavedAnalysisSourceSelection } from './SavedAnalysisSource';

const bytes = '%PDF-1.7\nfixture-body';
const revision = 2;
const contentSha256 = 'a'.repeat(64);
const quoteSha256 = 'b'.repeat(64);
const documentSha256 = createHash('sha256').update(bytes).digest('hex');
const selection: SavedAnalysisSourceSelection = {
  analysisId: 'analysis/1', versionId: 'previous/2', version: 2, contentSha256,
  evidence: { evidence_id: 'evidence/3', document_id: 'document-1', name: 'sentetik.PDF', locator: 'Sayfa 2',
    document_revision: revision, document_sha256: documentSha256, passage_sha256: 'c'.repeat(64),
    quote_sha256: quoteSha256, start: 10, end: 16, text: 'Satır\n' },
};

function context(overrides = {}) {
  const { evidence_id, document_id, name, locator, start, end, quote_sha256 } = selection.evidence;
  return Response.json({ version_id: selection.versionId, content_sha256: contentSha256,
    sources: [{ evidence_id, document_id, name, locator, start, end, quote_sha256 }], ...overrides });
}

function original(overrides: Record<string, string> = {}, body = bytes, status = 200) {
  return new Response(body, { status, headers: { 'Content-Type': 'application/pdf',
    'X-Analysis-Content-SHA256': contentSha256, 'X-Quote-SHA256': quoteSha256,
    'X-Source-SHA256': documentSha256, 'X-Source-Revision': String(revision),
    'X-Source-Page': '2', 'X-Source-Page-Count': '3', ...overrides } });
}

describe('saved PDF source binding', () => {
  const fetchMock = vi.fn<typeof fetch>();
  const open = (signal = new AbortController().signal) => loadSavedAnalysisSource('matter/1', selection, signal);
  beforeEach(() => { fetchMock.mockReset(); vi.stubGlobal('fetch', fetchMock); vi.stubGlobal('crypto', webcrypto); });
  afterEach(() => { vi.unstubAllGlobals(); onUnauthorized(); });

  it('requests the historical review version and serves the exact verified bytes for its saved page', async () => {
    fetchMock.mockResolvedValueOnce(context()).mockResolvedValueOnce(original());
    const result = await open();
    expect(result).toMatchObject({ page: 2, pageCount: 3 });
    expect(await result.blob.text()).toBe(bytes);
    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      '/api/v1/matters/matter%2F1/analyses/analysis%2F1/reviews/context?version_id=previous%2F2',
      '/api/v1/matters/matter%2F1/analyses/analysis%2F1/versions/previous%2F2/evidence/evidence%2F3/original/2',
    ]);
    for (const [, options] of fetchMock.mock.calls) {
      expect(options).toMatchObject({ credentials: 'same-origin', cache: 'no-store', redirect: 'error' });
    }
    const headers = new Headers(fetchMock.mock.calls[1][1]?.headers);
    expect(headers.get('X-Analysis-Content-SHA256')).toBe(contentSha256);
    expect(headers.get('X-Quote-SHA256')).toBe(quoteSha256);
  });

  it.each(['Sayfa 02', 'Sayfa 2\n', 'Paragraf 2'])('refuses the noncanonical saved locator %j before making a request', async (locator) => {
    await expect(loadSavedAnalysisSource('matter/1', { ...selection, evidence: { ...selection.evidence, locator } },
      new AbortController().signal)).rejects.toMatchObject({ status: 409 });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it.each([
    ['other version', { version_id: 'new-head' }],
    ['stale comparison', { content_sha256: 'd'.repeat(64) }],
    ['wrong quote', { sources: [{ ...selection.evidence, quote_sha256: 'e'.repeat(64) }] }],
    ['duplicate sources', { sources: [selection.evidence, selection.evidence] }],
  ])('refuses the %s without retrieving bytes', async (_, overrides) => {
    fetchMock.mockResolvedValueOnce(context(overrides));
    await expect(open()).rejects.toMatchObject({ status: 409 });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it.each([
    ['X-Analysis-Content-SHA256', 'e'.repeat(64)],
    ['X-Quote-SHA256', 'e'.repeat(64)],
    ['X-Source-SHA256', 'e'.repeat(64)],
    ['X-Source-Revision', '1'],
    ['X-Source-Page', '1'],
    ['X-Source-Page-Count', '1'],
    ['X-Source-Page-Count', '03'],
    ['Content-Type', 'application/octet-stream'],
  ])('refuses a mismatched response %s (%s)', async (name, value) => {
    fetchMock.mockResolvedValueOnce(context()).mockResolvedValueOnce(original({ [name]: value }));
    await expect(open()).rejects.toMatchObject({ status: 409 });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('refuses a partial response and rejects changed bytes even with matching headers', async () => {
    fetchMock.mockResolvedValueOnce(context()).mockResolvedValueOnce(original({}, bytes, 206));
    await expect(open()).rejects.toMatchObject({ status: 409 });
    fetchMock.mockResolvedValueOnce(context()).mockResolvedValueOnce(original({}, bytes + 'altered'));
    await expect(open()).rejects.toMatchObject({ status: 409 });
  });

  it('propagates loss of access without falling back to the live document', async () => {
    const logout = vi.fn();
    onUnauthorized(logout);
    fetchMock.mockResolvedValueOnce(context()).mockResolvedValueOnce(Response.json({}, { status: 401 }));
    await expect(open()).rejects.toMatchObject({ status: 401 });
    expect(logout).toHaveBeenCalledOnce();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('discards a body that finishes reading after the viewer is closed', async () => {
    const controller = new AbortController();
    const response = original();
    vi.spyOn(response, 'arrayBuffer').mockImplementation(async () => {
      controller.abort();
      return new TextEncoder().encode(bytes).buffer as ArrayBuffer;
    });
    fetchMock.mockResolvedValueOnce(context()).mockResolvedValueOnce(response);
    await expect(open(controller.signal)).rejects.toMatchObject({ name: 'AbortError' });
  });

  it('offers no neighboring page controls for an exact saved page', () => {
    const markup = renderToStaticMarkup(<PdfPreview blob={new Blob([bytes])} name="sentetik.PDF" initialPage={2} exactPageCount={3} />);
    expect(markup).toContain('Sayfa 2');
    expect(markup).not.toContain('Sonraki sayfa');
    expect(markup).not.toContain('Önceki sayfa');
    expect(markup).toContain('visibility:hidden');
  });
});
