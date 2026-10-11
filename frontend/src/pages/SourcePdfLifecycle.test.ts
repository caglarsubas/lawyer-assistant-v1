import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { openSourcePdf, type PdfInspection } from './SourcePdfInspection';
const mocks = vi.hoisted(() => ({ create: vi.fn(), getDocument: vi.fn() }));
vi.mock('pdfjs-dist', () => ({ PDFWorker: { create: mocks.create }, getDocument: mocks.getDocument }));
const data: PdfInspection = { kind: 'pdf', bytes: new Uint8Array([1, 2]), binding: { source_id: 'a'.repeat(64), source_version_id: 'synthetic', passage_id: 'pdf_page_0001', page: 1, page_count: 2, raw_sha256: 'b'.repeat(64), text_sha256: 'c'.repeat(64), raw_bytes: 2, raw_media_type: 'application/pdf', integrity_scope: 'all_artifacts_verified', locator_coordinate_status: 'consistent_not_fidelity_reviewed', extraction_fidelity_verified: false } };

describe('cancellable original-PDF worker lifecycle', () => {
  const terminate = vi.fn(), destroyWorker = vi.fn(), destroyTask = vi.fn();
  const WorkerMock = vi.fn(function (..._args: unknown[]) { return { terminate }; });
  beforeEach(() => { vi.useFakeTimers(); vi.stubGlobal('Worker', WorkerMock); vi.clearAllMocks(); mocks.create.mockReturnValue({ destroy: destroyWorker }); destroyTask.mockResolvedValue(undefined); });
  afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); });
  it('requires an explicit module worker and checks parsed count', async () => {
    mocks.getDocument.mockReturnValue({ promise: Promise.resolve({ numPages: 2 }), destroy: destroyTask });
    const active = openSourcePdf(data);
    await expect(active.promise).resolves.toMatchObject({ numPages: 2 });
    expect(WorkerMock).toHaveBeenCalledOnce(); expect(WorkerMock.mock.calls[0][1]).toEqual({ type: 'module' });
    expect(mocks.create).toHaveBeenCalledOnce(); expect(mocks.getDocument.mock.calls[0][0].worker).toEqual({ destroy: destroyWorker }); expect(vi.getTimerCount()).toBe(0);
    active.cancel(); active.cancel(); expect(terminate).toHaveBeenCalledOnce(); expect(destroyTask).toHaveBeenCalledOnce(); expect(destroyWorker).toHaveBeenCalledOnce();
  });
  it('rejects wrong actual count and cleans the deadline/worker', async () => {
    mocks.getDocument.mockReturnValue({ promise: Promise.resolve({ numPages: 3 }), destroy: destroyTask });
    const active = openSourcePdf(data); await expect(active.promise).rejects.toThrow('sayfa sayısı doğrulanamadı');
    expect(terminate).toHaveBeenCalledOnce(); expect(destroyTask).toHaveBeenCalledOnce(); expect(vi.getTimerCount()).toBe(0);
  });
  it('cancels during library loading without creating a worker', async () => {
    const active = openSourcePdf(data); active.cancel(); await expect(active.promise).rejects.toMatchObject({ name: 'AbortError' });
    await vi.dynamicImportSettled(); expect(WorkerMock).not.toHaveBeenCalled(); expect(mocks.getDocument).not.toHaveBeenCalled(); expect(vi.getTimerCount()).toBe(0);
  });
  it('cancels pending parse and rejects a late document', async () => {
    let release!: (value: { numPages: number }) => void;
    mocks.getDocument.mockReturnValue({ promise: new Promise(resolve => { release = resolve; }), destroy: destroyTask });
    const active = openSourcePdf(data); await vi.dynamicImportSettled(); active.cancel();
    await expect(active.promise).rejects.toMatchObject({ name: 'AbortError' }); release({ numPages: 2 }); await Promise.resolve();
    expect(terminate).toHaveBeenCalledOnce(); expect(destroyTask).toHaveBeenCalledOnce();
  });
  it('times out a hung parser without retry/fallback', async () => {
    mocks.getDocument.mockReturnValue({ promise: new Promise(() => undefined), destroy: destroyTask });
    const active = openSourcePdf(data); const result = expect(active.promise).rejects.toThrow('süresi aşıldı');
    await vi.dynamicImportSettled(); await vi.advanceTimersByTimeAsync(15000); await result;
    expect(mocks.getDocument).toHaveBeenCalledOnce(); expect(terminate).toHaveBeenCalledOnce(); expect(destroyTask).toHaveBeenCalledOnce(); expect(vi.getTimerCount()).toBe(0);
  });
  it('returns fixed diagnostics for parser errors with sensitive content', async () => {
    mocks.getDocument.mockReturnValue({ promise: Promise.reject(new Error('/private/secret source content')), destroy: destroyTask });
    const active = openSourcePdf(data); await expect(active.promise).rejects.toThrow('PDF veya sayfa sayısı doğrulanamadı'); expect(terminate).toHaveBeenCalledOnce();
  });
  it('refuses fake fallback when a real worker cannot start', async () => {
    WorkerMock.mockImplementationOnce(function () { throw new Error('blocked Worker'); });
    const active = openSourcePdf(data); await expect(active.promise).rejects.toThrow('PDF veya sayfa sayısı doğrulanamadı');
    expect(mocks.getDocument).not.toHaveBeenCalled(); expect(vi.getTimerCount()).toBe(0);
  });
});
