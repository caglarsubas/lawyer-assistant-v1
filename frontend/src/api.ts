const BASE = '/api/v1';
let csrfToken = '';
let unauthorizedHandler: (() => void) | undefined;

export class ApiError extends Error {
  constructor(message: string, public status: number, public data?: unknown) { super(message); this.name = 'ApiError'; }
}
export function setCsrfToken(token: string) { csrfToken = token; }
export function onUnauthorized(handler?: () => void) { unauthorizedHandler = handler; }

function errorText(data: unknown): string {
  if (typeof data === 'string') return data;
  if (data && typeof data === 'object') {
    const item = data as { detail?: unknown; message?: unknown };
    const value = item.detail ?? item.message;
    if (typeof value === 'string') return value;
    if (Array.isArray(value)) return value.map((entry) => typeof entry === 'object' && entry !== null && 'msg' in entry ? String(entry.msg) : String(entry)).join(' · ');
  }
  return 'İşlem tamamlanamadı. Lütfen yeniden deneyin.';
}

export async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  const method = options.method?.toUpperCase() || 'GET';
  if (options.body && !(options.body instanceof FormData)) headers.set('Content-Type', 'application/json');
  if (!['GET', 'HEAD', 'OPTIONS'].includes(method) && csrfToken) headers.set('X-CSRF-Token', csrfToken);
  let response: Response;
  try {
    response = await fetch(`${BASE}${path}`, { ...options, headers, credentials: 'same-origin' });
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error;
    throw new ApiError('Sunucuya ulaşılamıyor. Yerel hizmetin çalıştığını kontrol edin.', 0);
  }
  if (!response.ok) {
    const data: unknown = await response.json().catch(() => null);
    if (response.status === 401 && path !== '/auth/login' && path !== '/auth/me') unauthorizedHandler?.();
    throw new ApiError(errorText(data), response.status, data);
  }
  if (!['GET', 'HEAD', 'OPTIONS'].includes(method) && !path.startsWith('/auth/') && !path.startsWith('/assistant/') && !path.startsWith('/public-sources/') && !path.endsWith('/analyses/check') && typeof window !== 'undefined') window.dispatchEvent(new Event('portfolio-updated'));
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}
export const post = <T,>(path: string, body: unknown) => request<T>(path, { method: 'POST', body: JSON.stringify(body) });
export const patch = <T,>(path: string, body: unknown) => request<T>(path, { method: 'PATCH', body: JSON.stringify(body) });

export async function fetchOriginal(matterId: string, documentId: string, signal?: AbortSignal): Promise<Blob> {
  let response: Response;
  try { response = await fetch(`${BASE}/matters/${encodeURIComponent(matterId)}/documents/${encodeURIComponent(documentId)}/original`, { credentials: 'same-origin', signal }); }
  catch (cause) {
    if (cause instanceof DOMException && cause.name === 'AbortError') throw cause;
    throw new ApiError('Özgün dosya açılamadı. Yerel hizmete bağlantıyı kontrol edin.', 0);
  }
  if (!response.ok) {
    if (response.status === 401) unauthorizedHandler?.();
    throw new ApiError(errorText(await response.json().catch(() => null)), response.status);
  }
  return response.blob();
}

export async function downloadOriginal(matterId: string, documentId: string, filename: string) {
  const url = URL.createObjectURL(await fetchOriginal(matterId, documentId));
  const link = document.createElement('a'); link.href = url; link.download = filename;
  document.body.append(link); link.click(); link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export async function downloadPracticeDraft(matterId: string, recordId: string, versionId: string, format: 'docx' | 'pdf') {
  const params = new URLSearchParams({ format, version_id: versionId });
  let response: Response;
  try { response = await fetch(`${BASE}/matters/${encodeURIComponent(matterId)}/practice/drafts/${encodeURIComponent(recordId)}/export?${params}`, { credentials: 'same-origin' }); }
  catch { throw new ApiError('Taslak indirilemedi. Yerel hizmete bağlantıyı kontrol edin.', 0); }
  if (!response.ok) {
    if (response.status === 401) unauthorizedHandler?.();
    throw new ApiError(errorText(await response.json().catch(() => null)), response.status);
  }
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement('a'); link.href = url; link.download = `avukat-taslagi-${recordId}-${versionId}.${format}`;
  document.body.append(link); link.click(); link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export async function downloadAnalysis(matterId: string, recordId: string, versionId: string, format: 'docx' | 'pdf') {
  const params = new URLSearchParams({ version_id: versionId, format });
  let response: Response;
  try { response = await fetch(`${BASE}/matters/${encodeURIComponent(matterId)}/analyses/${encodeURIComponent(recordId)}/export?${params}`, { credentials: 'same-origin' }); }
  catch { throw new ApiError('Analiz indirilemedi. Yerel hizmete bağlantıyı kontrol edin.', 0); }
  if (!response.ok) {
    if (response.status === 401) unauthorizedHandler?.();
    throw new ApiError(errorText(await response.json().catch(() => null)), response.status);
  }
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement('a'); link.href = url; link.download = `analiz-taslagi-${recordId}-${versionId}.${format}`;
  document.body.append(link); link.click(); link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export async function downloadAuthorityContext(matterId: string, analysisId: string, contextId: string, format: 'json' | 'docx' | 'pdf') {
  const path = [matterId, analysisId, contextId].map(encodeURIComponent);
  let response: Response;
  try { response = await fetch(`${BASE}/matters/${path[0]}/analyses/${path[1]}/authority-contexts/${path[2]}/export?format=${format}`, { credentials: 'same-origin', cache: 'no-store' }); }
  catch { throw new ApiError('Bağlam indirilemedi. Yerel hizmete bağlantıyı kontrol edin.', 0); }
  if (!response.ok) {
    if (response.status === 401) unauthorizedHandler?.();
    throw new ApiError(errorText(await response.json().catch(() => null)), response.status);
  }
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement('a'); link.href = url; link.download = `ozel-dayanak-baglami-${contextId}.${format}`;
  document.body.append(link); link.click(); link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export async function downloadAuthorityReview(matterId: string, analysisId: string, contextId: string, reviewId: string, format: 'json' | 'docx' | 'pdf') {
  const path = [matterId, analysisId, contextId, reviewId].map(encodeURIComponent);
  let response: Response;
  try { response = await fetch(`${BASE}/matters/${path[0]}/analyses/${path[1]}/authority-contexts/${path[2]}/reviews/${path[3]}/export?format=${format}`, { credentials: 'same-origin', cache: 'no-store' }); }
  catch { throw new ApiError('İnceleme indirilemedi. Yerel hizmete bağlantıyı kontrol edin.', 0); }
  if (!response.ok) {
    if (response.status === 401) unauthorizedHandler?.();
    throw new ApiError(errorText(await response.json().catch(() => null)), response.status);
  }
  const url = URL.createObjectURL(await response.blob()); const link = document.createElement('a');
  link.href = url; link.download = `ozel-dayanak-incelemesi-${reviewId}.${format}`;
  document.body.append(link); link.click(); link.remove(); window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export async function downloadAuthorityComparison(matterId: string, analysisId: string, contextId: string, reviewId: string, comparisonId: string, format: 'json' | 'docx' | 'pdf') {
  const path = [matterId, analysisId, contextId, reviewId, comparisonId].map(encodeURIComponent);
  let response: Response;
  try { response = await fetch(`${BASE}/matters/${path[0]}/analyses/${path[1]}/authority-contexts/${path[2]}/reviews/${path[3]}/comparisons/${path[4]}/export?format=${format}`, { credentials: 'same-origin', cache: 'no-store' }); }
  catch { throw new ApiError('Karşılaştırma indirilemedi. Yerel hizmete bağlantıyı kontrol edin.', 0); }
  if (!response.ok) {
    if (response.status === 401) unauthorizedHandler?.();
    throw new ApiError(errorText(await response.json().catch(() => null)), response.status);
  }
  const url = URL.createObjectURL(await response.blob()); const link = document.createElement('a');
  link.href = url; link.download = `ozel-dayanak-karsilastirmasi-${comparisonId}.${format}`;
  document.body.append(link); link.click(); link.remove(); window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export async function downloadProduct(matterId: string, productId: string, format: 'docx' | 'pdf') {
  let response: Response;
  try {
    response = await fetch(`${BASE}/matters/${encodeURIComponent(matterId)}/products/${encodeURIComponent(productId)}/export?format=${format}`, { credentials: 'same-origin' });
  } catch {
    throw new ApiError('Dosya indirilemedi. Yerel hizmete bağlantıyı kontrol edin.', 0);
  }
  if (!response.ok) {
    if (response.status === 401) unauthorizedHandler?.();
    throw new ApiError(errorText(await response.json().catch(() => null)), response.status);
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url; link.download = `hazirlik-paketi-${productId}.${format}`;
  document.body.append(link); link.click(); link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export async function downloadAuthorityAdjudication(base: string, id: string, format: 'json' | 'docx' | 'pdf') {
  let response: Response;
  try { response = await fetch(`${BASE}${base}/${encodeURIComponent(id)}/export?format=${format}`, { credentials: 'same-origin', cache: 'no-store' }); }
  catch { throw new ApiError('Değerlendirme indirilemedi. Yerel bağlantıyı kontrol edin.', 0); }
  if (!response.ok) {
    if (response.status === 401) unauthorizedHandler?.();
    throw new ApiError(errorText(await response.json().catch(() => null)), response.status);
  }
  const url = URL.createObjectURL(await response.blob()); const link = document.createElement('a');
  link.href = url; link.download = `ozel-dayanak-degerlendirmesi-${id}.${format}`;
  document.body.append(link); link.click(); link.remove(); window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export async function downloadAuthorityTrial(base: string, id: string) {
  return downloadAuthorityTrialPacket(base, id, 'ozel-dayanak-denemesi');
}

export async function downloadAuthorityTrialCohort(base: string, id: string) {
  return downloadAuthorityTrialPacket(`${base}/${encodeURIComponent(id)}`, id, 'ozel-dayanak-grubu');
}

async function downloadAuthorityTrialPacket(base: string, id: string, prefix: string) {
  let response: Response;
  try { response = await fetch(`${BASE}${base}/export`, { credentials: 'same-origin', cache: 'no-store' }); }
  catch { throw new ApiError('Deneme paketi indirilemedi. Yerel bağlantıyı kontrol edin.', 0); }
  if (!response.ok) {
    if (response.status === 401) unauthorizedHandler?.();
    throw new ApiError(errorText(await response.json().catch(() => null)), response.status);
  }
  const url = URL.createObjectURL(await response.blob()); const link = document.createElement('a');
  link.href = url; link.download = `${prefix}-${id}.json`;
  document.body.append(link); link.click(); link.remove(); window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}
