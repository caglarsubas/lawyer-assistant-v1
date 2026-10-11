import { useEffect, useRef, useState } from 'react';
import type { PDFDocumentProxy, RenderTask } from 'pdfjs-dist';
import pdfWorkerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url';
import { ApiError, request } from '../api';
import { Loading, Notice } from '../components';
import type { PublicSourceOriginalPdf, PublicSourcePassage, PublicSourcePassages } from '../types';

const MAX_BYTES = 1024 * 1024;
const MAX_PAGES = 50;
const PDF_LOCATOR = /^PDF page ([1-9][0-9]?); extracted page code points \[0,([1-9][0-9]{0,4})\)$/;
export function mappedPdfPage(passage: PublicSourcePassage): number | null {
  const match = PDF_LOCATOR.exec(passage.locator);
  if (!match) return null;
  const page = Number(match[1]), length = Number(match[2]);
  return page <= MAX_PAGES && length <= 20000 && passage.id === `pdf_page_${String(page).padStart(4, '0')}`
    && length === passage.end - passage.start && length === Array.from(passage.text).length ? page : null;
}
export interface PdfInspection { kind: 'pdf'; binding: PublicSourceOriginalPdf; bytes: Uint8Array }
export async function fetchOriginalSourcePdf(data: PublicSourcePassages, passageId: string, signal?: AbortSignal): Promise<PdfInspection> {
  signal = AbortSignal.any([...(signal ? [signal] : []), AbortSignal.timeout(30000)]);
  const selected = data.items.find(item => item.id === passageId);
  const page = selected ? mappedPdfPage(selected) : null;
  if (!/^[a-f0-9]{64}$/.test(data.source_id) || !page || data.integrity_scope !== 'all_artifacts_verified') throw new Error('Özgün PDF konumu geçersiz.');
  const path = `/public-sources/${data.source_id}`;
  const binding = await request<PublicSourceOriginalPdf>(`${path}/original-pdf?passage_id=${encodeURIComponent(passageId)}`, { signal });
  if (!binding || binding.source_id !== data.source_id || binding.source_version_id !== data.source_version_id
    || binding.passage_id !== passageId || binding.raw_sha256 !== data.raw_sha256 || binding.text_sha256 !== data.text_sha256
    || !/^[a-f0-9]{64}$/.test(binding.raw_sha256) || binding.raw_media_type !== 'application/pdf'
    || binding.page !== page || !Number.isInteger(binding.page_count) || binding.page_count !== data.total
    || binding.page_count < page || binding.page_count > MAX_PAGES
    || !Number.isInteger(binding.raw_bytes) || binding.raw_bytes < 1 || binding.raw_bytes > MAX_BYTES
    || binding.integrity_scope !== 'all_artifacts_verified' || binding.extraction_fidelity_verified !== false
    || binding.locator_coordinate_status !== 'consistent_not_fidelity_reviewed') throw new Error('Özgün PDF yanıtı seçili kaynak ve pasajla eşleşmiyor.');
  if (signal?.aborted) throw new DOMException('Aborted', 'AbortError');
  const response = await fetch(`/api/v1${path}/original`, { credentials: 'same-origin', cache: 'no-store', signal });
  if (!response.ok) { await response.body?.cancel(); throw new ApiError('Özgün PDF erişimi veya kaynak bütünlüğü doğrulanamadı.', response.status); }
  if (response.headers.get('Content-Type')?.split(';')[0] !== 'application/octet-stream'
    || !response.headers.get('Content-Disposition')?.toLowerCase().startsWith('attachment') || !response.body) {
    await response.body?.cancel(); throw new Error('Güvenli özgün PDF eki alınamadı.');
  }
  const declared = response.headers.get('Content-Length');
  if (declared !== null && (!/^[0-9]+$/.test(declared) || Number(declared) !== binding.raw_bytes)) {
    await response.body.cancel(); throw new Error('Özgün PDF boyutu eşleşmiyor.');
  }
  const reader = response.body.getReader();
  const bytes = new Uint8Array(binding.raw_bytes);
  let size = 0;
  try {
    while (true) {
      if (signal?.aborted) throw new DOMException('Aborted', 'AbortError');
      const chunk = await reader.read();
      if (chunk.done) break;
      size += chunk.value.length;
      if (size > bytes.length) throw new Error('Özgün PDF boyutu eşleşmiyor.');
      bytes.set(chunk.value, size - chunk.value.length);
    }
  } finally { await reader.cancel(); reader.releaseLock(); }
  if (size !== bytes.length || signal?.aborted) throw new Error('Özgün PDF aktarımı tamamlanmadı.');
  const hash = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)), value => value.toString(16).padStart(2, '0')).join('');
  if (hash !== binding.raw_sha256) throw new Error('Özgün PDF içerik özeti eşleşmiyor.');
  if (signal.aborted) throw new DOMException('Aborted', 'AbortError');
  return { kind: 'pdf', binding, bytes };
}

// Strict data-only loading; all PDF.js dependencies are bundled same-origin assets.
export function sourcePdfOptions(bytes: Uint8Array) {
  return { data: bytes.slice(), cMapUrl: '/pdfjs-assets/cmaps/', cMapPacked: true,
    standardFontDataUrl: '/pdfjs-assets/standard_fonts/', wasmUrl: '/pdfjs-assets/wasm/', iccUrl: '/pdfjs-assets/iccs/',
    useSystemFonts: false, stopAtErrors: true, enableXfa: false, useWasm: false,
    maxImageSize: 4 * 1024 * 1024, canvasMaxAreaInBytes: 16 * 1024 * 1024,
    isImageDecoderSupported: false, isOffscreenCanvasSupported: false,
    disableAutoFetch: true, disableRange: true, disableStream: true, verbosity: 0 };
}
export function sourcePdfViewport(width: number, height: number, available: number, zoom: number, ratio: number) {
  if (![width, height, available, zoom, ratio].every(value => Number.isFinite(value) && value > 0)
    || ![1, 1.5, 2].includes(zoom)) throw new Error('PDF sayfa boyutları geçersiz.');
  const pixelRatio = Math.min(ratio, 2);
  const scale = Math.min(available / width * zoom, 4096 / (Math.max(width, height) * pixelRatio));
  if (!Number.isFinite(scale) || scale <= 0) throw new Error('PDF sayfa boyutları geçersiz.');
  return { scale, pixelRatio };
}

export function openSourcePdf(data: PdfInspection) {
  let closed = false, port: Worker | undefined, isolated: import('pdfjs-dist').PDFWorker | undefined;
  let task: ReturnType<typeof import('pdfjs-dist').getDocument> | undefined;
  let rejectPending: (reason: unknown) => void;
  let timeout: ReturnType<typeof setTimeout>;
  function destroy() {
    if (closed) return;
    closed = true; clearTimeout(timeout); port?.terminate(); isolated?.destroy();
    void task?.destroy().catch(() => undefined);
  }
  const promise = new Promise<PDFDocumentProxy>((resolve, reject) => {
    rejectPending = reject;
    timeout = setTimeout(() => { destroy(); reject(new Error('PDF açma süresi aşıldı. Özgün dosyayı bağımsız olarak inceleyin.')); }, 15000);
    void import('pdfjs-dist').then(async library => {
      if (closed) return;
      // Explicit real worker: no fake-worker fallback on the page's main thread.
      port = new Worker(`${pdfWorkerUrl}?module=1`, { type: 'module' });
      isolated = library.PDFWorker.create({ port });
      task = library.getDocument({ ...sourcePdfOptions(data.bytes), worker: isolated });
      const document = await task.promise;
      if (closed) return;
      if (document.numPages !== data.binding.page_count) throw new Error('page count');
      clearTimeout(timeout); resolve(document);
    }).catch(() => {
      if (!closed) { destroy(); reject(new Error('PDF veya sayfa sayısı doğrulanamadı. Özgün dosyayı bağımsız olarak inceleyin.')); }
    });
  });
  return { promise, cancel: () => { destroy(); rejectPending(new DOMException('Aborted', 'AbortError')); } };
}

export default function SourcePdfView({ data, onClose }: { data: PdfInspection; onClose: () => void }) {
  const [pdf, setPdf] = useState<PDFDocumentProxy | null>(null);
  const [error, setError] = useState('');
  const [rendering, setRendering] = useState(true);
  const [zoom, setZoom] = useState(1);
  const [width, setWidth] = useState(0);
  const stage = useRef<HTMLDivElement>(null), canvas = useRef<HTMLCanvasElement>(null);
  const session = useRef<ReturnType<typeof openSourcePdf> | null>(null);
  useEffect(() => {
    let disposed = false;
    const active = openSourcePdf(data); session.current = active;
    setPdf(null); setError(''); setRendering(true);
    void active.promise.then(document => { if (!disposed) setPdf(document); }).catch(cause => {
      if (!disposed) { setError(cause instanceof Error ? cause.message : 'Özgün PDF açılamadı.'); setRendering(false); }
    });
    return () => { disposed = true; active.cancel(); session.current = null; };
  }, [data]);
  useEffect(() => {
    if (!stage.current) return;
    const observer = new ResizeObserver(([entry]) => setWidth(Math.max(1, entry.contentRect.width - 32)));
    observer.observe(stage.current);
    return () => observer.disconnect();
  }, []);
  useEffect(() => {
    if (!pdf || !canvas.current || !width) return;
    let disposed = false, task: RenderTask | undefined;
    const target = canvas.current;
    setRendering(true); setError(''); target.width = 0; target.height = 0;
    const timeout = window.setTimeout(() => {
      if (!disposed) { setError('PDF sayfasını gösterme süresi aşıldı. Özgün dosyayı bağımsız olarak inceleyin.'); setRendering(false); task?.cancel(); session.current?.cancel(); }
    }, 15000);
    async function render() {
      try {
        const source = await pdf!.getPage(data.binding.page);
        if (disposed) return;
        const natural = source.getViewport({ scale: 1 });
        const { scale, pixelRatio } = sourcePdfViewport(natural.width, natural.height, width, zoom, window.devicePixelRatio || 1);
        const viewport = source.getViewport({ scale });
        target.width = Math.min(4096, Math.ceil(viewport.width * pixelRatio)); target.height = Math.min(4096, Math.ceil(viewport.height * pixelRatio));
        target.style.width = `${viewport.width}px`; target.style.height = `${viewport.height}px`;
        task = source.render({ canvas: target, viewport, transform: [pixelRatio, 0, 0, pixelRatio, 0, 0], annotationMode: 0 });
        await task.promise;
        if (!disposed) { window.clearTimeout(timeout); setRendering(false); }
      } catch {
        if (!disposed) { window.clearTimeout(timeout); setError('Özgün PDF sayfası görüntülenemedi. Dosyayı bağımsız olarak inceleyin.'); setRendering(false); target.width = 0; target.height = 0; }
      }
    }
    void render();
    return () => { disposed = true; window.clearTimeout(timeout); task?.cancel(); target.width = 0; target.height = 0; };
  }, [pdf, data, width, zoom]);
  return <section className="source-original-view" aria-label={`${data.binding.passage_id} özgün PDF sayfası`}>
    <div className="source-passage-heading"><h4>Özgün PDF · Sayfa {data.binding.page} / {data.binding.page_count}</h4><button className="text-button" onClick={onClose}>Kaynak görünümünü kapat</button></div>
    <p className="small muted">Tam özgün dosyanın içerik özeti doğrulandı. Yerel sayfa görünümü; çıkarım doğruluğu, yazı tipleri ve eksik içerik insan incelemesi gerektirir. Bu görünümü açmak inceleme kabulü değildir.</p>
    <div className="preview-toolbar"><label>Görünüm <select aria-label="Özgün PDF yakınlaştırma" value={zoom} disabled={!pdf || Boolean(error)} onChange={event => setZoom(Number(event.target.value))}><option value={1}>Genişliğe sığdır</option><option value={1.5}>%150</option><option value={2}>%200</option></select></label></div>
    {error && <Notice error>{error}</Notice>}
    <div className="pdf-stage" ref={stage} aria-busy={rendering}>
      {rendering && <Loading label="Özgün PDF sayfası yükleniyor…" />}
      <canvas ref={canvas} style={{ visibility: rendering || error ? 'hidden' : 'visible' }} role="img" aria-label={`Özgün PDF · Sayfa ${data.binding.page}`} />
    </div>
    <p className="small muted">Bağlantılar, ekler, formlar ve belge betikleri açılmaz. Diğer sayfayı ilgili pasajdan açın. Sayfa konumu hukuki madde kimliği değildir.</p>
  </section>;
}
