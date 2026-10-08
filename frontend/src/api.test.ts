import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError, downloadAuthorityContext, downloadAuthorityReview, fetchOriginal, onUnauthorized, post, request, setCsrfToken } from './api';

describe('session and request boundaries', () => {
  const fetchMock = vi.fn<typeof fetch>();
  beforeEach(() => { vi.stubGlobal('fetch', fetchMock); setCsrfToken(''); onUnauthorized(); fetchMock.mockReset(); });
  afterEach(() => { vi.unstubAllGlobals(); setCsrfToken(''); onUnauthorized(); });

  it('uses same-origin session cookies and attaches the current CSRF token to mutations', async () => {
    fetchMock.mockResolvedValue(new Response(JSON.stringify({ id: 'matter-1' }), { status: 201 }));
    setCsrfToken('session-specific-token');
    await post('/matters', { title: 'Dosya' });
    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toBe('/api/v1/matters');
    expect(options?.credentials).toBe('same-origin');
    expect(new Headers(options?.headers).get('X-CSRF-Token')).toBe('session-specific-token');
    expect(new Headers(options?.headers).get('Content-Type')).toBe('application/json');
  });

  it('does not forward a previous session token after logout clears it', async () => {
    fetchMock.mockResolvedValue(new Response('{}'));
    setCsrfToken('previous-session'); setCsrfToken('');
    await post('/auth/login', { username: 'demo', password: 'demo-local-only' });
    expect(new Headers(fetchMock.mock.calls[0][1]?.headers).has('X-CSRF-Token')).toBe(false);
  });

  it('allows the browser to construct multipart boundaries for document intake', async () => {
    fetchMock.mockResolvedValue(new Response('{}'));
    const body = new FormData(); body.append('file', new Blob(['Örnek belge']), 'ornek.txt');
    setCsrfToken('upload-token');
    await request('/matters/m1/documents', { method: 'POST', body });
    const headers = new Headers(fetchMock.mock.calls[0][1]?.headers);
    expect(headers.has('Content-Type')).toBe(false);
    expect(headers.get('X-CSRF-Token')).toBe('upload-token');
  });

  it('does not include CSRF tokens on reads', async () => {
    fetchMock.mockResolvedValue(new Response('{}')); setCsrfToken('private-token');
    await request('/matters');
    expect(new Headers(fetchMock.mock.calls[0][1]?.headers).has('X-CSRF-Token')).toBe(false);
  });

  it('ends the UI session when an authenticated resource rejects the session', async () => {
    const expire = vi.fn(); onUnauthorized(expire);
    fetchMock.mockResolvedValue(new Response(JSON.stringify({ detail: 'Oturum geçersiz' }), { status: 401 }));
    await expect(request('/matters')).rejects.toMatchObject({ status: 401, message: 'Oturum geçersiz' });
    expect(expire).toHaveBeenCalledOnce();
  });

  it('does not announce an expired session for anonymous restoration or an invalid login', async () => {
    const expire = vi.fn(); onUnauthorized(expire);
    fetchMock.mockImplementation(async () => new Response(JSON.stringify({ detail: 'Giriş gerekli' }), { status: 401 }));
    await expect(request('/auth/me')).rejects.toBeInstanceOf(ApiError);
    await expect(post('/auth/login', {})).rejects.toBeInstanceOf(ApiError);
    expect(expire).not.toHaveBeenCalled();
  });

  it('surfaces server-side policy denials and never converts them to success', async () => {
    fetchMock.mockResolvedValue(new Response(JSON.stringify({ detail: 'Dış ağ erişimi kapalı' }), { status: 403 }));
    await expect(post('/matters/m1/gateway/execute', { request_id: 'r1' })).rejects.toMatchObject({ status: 403, message: 'Dış ağ erişimi kapalı' });
  });

  it('retains a structured committed receipt while keeping the request failed for explicit UI handling', async () => {
    const data = { detail: 'Kayıt saklandı; son izin denetimi tamamlanamadı.', outcome: 'committed_needs_revalidation', needs_revalidation: true, id: 'aac-' + 'a'.repeat(20) + '-' + 'b'.repeat(32) };
    fetchMock.mockResolvedValue(new Response(JSON.stringify(data), { status: 409 }));
    await expect(post('/matters/m1/analyses/a1/authority-contexts', {})).rejects.toMatchObject({ status: 409, message: data.detail, data });
  });

  it('rechecks attachment access using encoded same-origin paths and never turns a denied export into a download', async () => {
    fetchMock.mockResolvedValue(new Response(JSON.stringify({ detail: 'Kaynak izni bekletiliyor.' }), { status: 409 }));
    await expect(downloadAuthorityContext('matter/1', 'analysis/2', 'context/3', 'docx')).rejects.toMatchObject({ status: 409 });
    expect(fetchMock.mock.calls[0]).toEqual(['/api/v1/matters/matter%2F1/analyses/analysis%2F2/authority-contexts/context%2F3/export?format=docx', { credentials: 'same-origin', cache: 'no-store' }]);
  });

  it('preserves cancellation instead of reporting a network failure', async () => {
    fetchMock.mockRejectedValue(new DOMException('Aborted', 'AbortError'));
    await expect(request('/matters', { signal: new AbortController().signal })).rejects.toMatchObject({ name: 'AbortError' });
  });

  it('never downloads a withheld authority review and rechecks its exact same-origin identity', async () => {
    fetchMock.mockResolvedValue(new Response(JSON.stringify({ detail: 'İnceleme aktarımı kapalı.' }), { status: 409 }));
    await expect(downloadAuthorityReview('matter/1', 'analysis/2', 'context/3', 'review/4', 'pdf')).rejects.toMatchObject({ status: 409 });
    expect(fetchMock.mock.calls[0]).toEqual(['/api/v1/matters/matter%2F1/analyses/analysis%2F2/authority-contexts/context%2F3/reviews/review%2F4/export?format=pdf', { credentials: 'same-origin', cache: 'no-store' }]);
  });

  it('converts an unreachable local service into an actionable error without provider details', async () => {
    fetchMock.mockRejectedValue(new TypeError('Failed to fetch'));
    await expect(request('/status')).rejects.toMatchObject({ status: 0, message: 'Sunucuya ulaşılamıyor. Yerel hizmetin çalıştığını kontrol edin.' });
  });

  it('loads original bytes with authorization cookies and cancellable, encoded document paths', async () => {
    const source = new Uint8Array([37, 80, 68, 70, 0, 255]);
    fetchMock.mockResolvedValue(new Response(source, { headers: { 'Content-Type': 'application/octet-stream' } }));
    const controller = new AbortController();
    const original = await fetchOriginal('matter/1', 'document/2', controller.signal);
    expect(new Uint8Array(await original.arrayBuffer())).toEqual(source);
    expect(fetchMock.mock.calls[0]).toEqual(['/api/v1/matters/matter%2F1/documents/document%2F2/original', { credentials: 'same-origin', signal: controller.signal }]);
  });

  it('never previews authorization failures as document content and expires rejected sessions', async () => {
    const expire = vi.fn(); onUnauthorized(expire);
    fetchMock.mockResolvedValue(new Response(JSON.stringify({ detail: 'Giriş gerekli' }), { status: 401 }));
    await expect(fetchOriginal('m1', 'd1')).rejects.toMatchObject({ status: 401 });
    expect(expire).toHaveBeenCalledOnce();
    fetchMock.mockResolvedValue(new Response(JSON.stringify({ detail: 'Bulunamadı' }), { status: 404 }));
    await expect(fetchOriginal('m1', 'foreign-document')).rejects.toMatchObject({ status: 404 });
  });

  it('preserves cancellation when the source selection changes', async () => {
    fetchMock.mockRejectedValue(new DOMException('Aborted', 'AbortError'));
    await expect(fetchOriginal('m1', 'd1', new AbortController().signal)).rejects.toMatchObject({ name: 'AbortError' });
  });
});
