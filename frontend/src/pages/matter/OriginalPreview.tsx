import { useEffect, useRef, useState } from 'react';
import type { PDFDocumentProxy, RenderTask } from 'pdfjs-dist';
import pdfWorker from 'pdfjs-dist/build/pdf.worker.min.mjs?url';
import { fetchOriginal } from '../../api';
import { Empty, Loading, Notice } from '../../components';
import type { DocumentRecord } from '../../types';
import { messageOf } from '../../utils';

export type PreviewKind = 'pdf' | 'image' | 'docx' | 'text' | 'unsupported';
export function previewKind(document: Pick<DocumentRecord, 'name'>): PreviewKind {
  // Use the final extension: a file named contract.docx.pdf is a PDF.
  const extension = document.name.split('.').pop()?.toLowerCase();
  if (extension === 'pdf') return 'pdf';
  if (['png', 'jpg', 'jpeg', 'bmp', 'webp', 'gif'].includes(extension || '')) return 'image';
  if (extension === 'docx') return 'docx';
  if (['txt', 'md', 'csv', 'html', 'htm', 'eml'].includes(extension || '')) return 'text';
  return 'unsupported';
}

export default function OriginalPreview({ matterId, document, initialPage = 1 }: { matterId: string; document: DocumentRecord; initialPage?: number }) {
  const [blob, setBlob] = useState<Blob | null>(null);
  const [error, setError] = useState('');
  const kind = previewKind(document);
  useEffect(() => {
    if (kind === 'unsupported') return;
    const controller = new AbortController();
    setBlob(null); setError('');
    fetchOriginal(matterId, document.id, controller.signal).then((value) => {
      if (!controller.signal.aborted) setBlob(value);
    }).catch((cause) => { if (!controller.signal.aborted) setError(messageOf(cause)); });
    return () => controller.abort();
  }, [matterId, document.id, kind]);
  if (kind === 'unsupported') return <Empty title="Bu dosya türü için önizleme kullanılamıyor.">Özgün dosyayı indirerek kendi uygulamasında açabilirsiniz. Çıkarılan metin ayrı sekmede bulunur.</Empty>;
  if (error) return <Notice error>{error} Özgün dosyayı indirmeyi deneyebilir veya çıkarılan metne geçebilirsiniz.</Notice>;
  if (!blob) return <Loading label="Özgün dosya açılıyor…" />;
  return <div className="original-preview">
    {kind === 'pdf' && <PdfPreview blob={blob} name={document.name} initialPage={initialPage} />}
    {kind === 'image' && <ImagePreview blob={blob} name={document.name} />}
    {kind === 'docx' && <DocxPreview blob={blob} />}
    {kind === 'text' && <TextPreview blob={blob} />}
  </div>;
}

function PdfPreview({ blob, name, initialPage }: { blob: Blob; name: string; initialPage: number }) {
  const [pdf, setPdf] = useState<PDFDocumentProxy | null>(null);
  const [page, setPage] = useState(initialPage);
  const [zoom, setZoom] = useState(1);
  const [width, setWidth] = useState(0);
  const [rendering, setRendering] = useState(true);
  const [error, setError] = useState('');
  const stage = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    let disposed = false;
    let task: ReturnType<typeof import('pdfjs-dist').getDocument> | undefined;
    async function open() {
      try {
        const [library, data] = await Promise.all([import('pdfjs-dist'), blob.arrayBuffer()]);
        if (disposed) return;
        // A versioned URL also avoids cached octet-stream headers from older nginx builds.
        library.GlobalWorkerOptions.workerSrc = `${pdfWorker}?module=1`;
        task = library.getDocument({ data: new Uint8Array(data),
          cMapUrl: '/pdfjs-assets/cmaps/', cMapPacked: true,
          standardFontDataUrl: '/pdfjs-assets/standard_fonts/', wasmUrl: '/pdfjs-assets/wasm/',
          iccUrl: '/pdfjs-assets/iccs/' });
        const loaded = await task.promise;
        if (disposed) return;
        setPage(Math.min(Math.max(1, initialPage), loaded.numPages));
        setPdf(loaded);
      } catch { if (!disposed) { setError('PDF önizlemesi açılamadı. Özgün dosyayı indirerek inceleyebilirsiniz.'); setRendering(false); } }
    }
    void open();
    return () => { disposed = true; void task?.destroy(); };
  }, [blob, initialPage]);
  useEffect(() => {
    if (!stage.current) return;
    const observer = new ResizeObserver(([entry]) => setWidth(Math.max(1, entry.contentRect.width - 32)));
    observer.observe(stage.current);
    return () => observer.disconnect();
  }, []);
  useEffect(() => {
    if (!pdf || !canvas.current || !width) return;
    let disposed = false;
    let task: RenderTask | undefined;
    setRendering(true); setError('');
    async function render() {
      try {
        const source = await pdf!.getPage(page);
        if (disposed || !canvas.current) return;
        const natural = source.getViewport({ scale: 1 });
        // Bound oversized page dimensions and HiDPI canvas allocation.
        const outputScale = Math.min(window.devicePixelRatio || 1, 2);
        const scale = Math.min(width / natural.width * zoom, 4096 / (Math.max(natural.width, natural.height) * outputScale));
        const viewport = source.getViewport({ scale });
        const target = canvas.current;
        target.width = Math.ceil(viewport.width * outputScale);
        target.height = Math.ceil(viewport.height * outputScale);
        target.style.width = `${viewport.width}px`; target.style.height = `${viewport.height}px`;
        task = source.render({ canvas: target, viewport, transform: [outputScale, 0, 0, outputScale, 0, 0] });
        await task.promise;
      } catch { if (!disposed) setError('Bu PDF sayfası görüntülenemedi. Özgün dosyayı indirerek inceleyebilirsiniz.'); }
      finally { if (!disposed) setRendering(false); }
    }
    void render();
    return () => { disposed = true; task?.cancel(); };
  }, [pdf, page, zoom, width]);
  return <>
    <div className="preview-toolbar" aria-label="PDF sayfa kontrolleri">
      <div className="preview-pages"><button className="button secondary" disabled={!pdf || page <= 1} onClick={() => setPage(page - 1)} aria-label="Önceki sayfa">‹</button>
        <label>Sayfa <input aria-label="PDF sayfası" type="number" min={1} max={pdf?.numPages || 1} value={page} disabled={!pdf} onChange={(event) => { const value = Number(event.target.value); if (pdf && Number.isInteger(value) && value >= 1 && value <= pdf.numPages) setPage(value); }} /> / {pdf?.numPages || '…'}</label>
        <button className="button secondary" disabled={!pdf || page >= pdf.numPages} onClick={() => setPage(page + 1)} aria-label="Sonraki sayfa">›</button></div>
      <label className="preview-zoom">Görünüm <select aria-label="PDF yakınlaştırma" value={zoom} onChange={(event) => setZoom(Number(event.target.value))}><option value={1}>Genişliğe sığdır</option><option value={1.25}>%125</option><option value={1.5}>%150</option><option value={2}>%200</option></select></label>
    </div>
    {error && <Notice error>{error}</Notice>}
    <div className="pdf-stage" ref={stage} aria-busy={rendering}>
      {rendering && <Loading label="Özgün sayfa görüntüleniyor…" />}
      <canvas ref={canvas} style={{ visibility: rendering || error ? 'hidden' : 'visible' }} role="img" aria-label={`${name} · Sayfa ${page}${pdf ? ` / ${pdf.numPages}` : ''}`} />
    </div>
  </>;
}

function ImagePreview({ blob, name }: { blob: Blob; name: string }) {
  const [url, setUrl] = useState('');
  const [error, setError] = useState(false);
  useEffect(() => {
    // Original download uses octet-stream; assign only an admitted image type.
    const extension = name.split('.').pop()?.toLowerCase();
    const type = extension === 'jpg' || extension === 'jpeg' ? 'image/jpeg' : `image/${extension}`;
    const source = URL.createObjectURL(new Blob([blob], { type }));
    setUrl(source); setError(false);
    return () => URL.revokeObjectURL(source);
  }, [blob, name]);
  return error ? <Notice error>Görsel önizlemesi açılamadı. Özgün dosyayı indirerek inceleyebilirsiniz.</Notice> : <div className="image-stage">{url && <img src={url} alt={`Özgün belge: ${name}`} onError={() => setError(true)} />}</div>;
}

function TextPreview({ blob }: { blob: Blob }) {
  const [text, setText] = useState('');
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let disposed = false;
    blob.arrayBuffer().then((buffer) => {
      if (!disposed) setText(new TextDecoder('utf-8', { fatal: true }).decode(buffer));
    }).catch(() => { if (!disposed) setError(true); }).finally(() => { if (!disposed) setLoading(false); });
    return () => { disposed = true; };
  }, [blob]);
  if (loading) return <Loading label="Özgün metin açılıyor…" />;
  if (error) return <Notice error>Dosyanın metin kodlaması görüntülenemiyor. Özgün dosyayı indirerek açabilirsiniz.</Notice>;
  // React escapes markup. HTML and Markdown are source text, never executable content.
  return <pre className="original-text">{text}</pre>;
}

function DocxPreview({ blob }: { blob: Blob }) {
  const host = useRef<HTMLDivElement>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  useEffect(() => {
    let disposed = false;
    // Detached rendering prevents a late result from overwriting another selection.
    const body = window.document.createElement('div');
    const styles = window.document.createElement('div');
    async function render() {
      try {
        const { renderAsync } = await import('docx-preview');
        if (disposed) return;
        await renderAsync(await blob.arrayBuffer(), body, styles, {
          className: 'original-docx', renderAltChunks: false, useBase64URL: true,
          ignoreLastRenderedPageBreak: false, renderChanges: true,
        });
        // Document hyperlinks are displayed as text and cannot navigate or run scripts.
        body.querySelectorAll('a').forEach((link) => { link.removeAttribute('href'); link.removeAttribute('target'); });
        if (!disposed) host.current?.replaceChildren(styles, body);
      } catch { if (!disposed) setError(true); }
      finally { if (!disposed) setLoading(false); }
    }
    void render();
    return () => { disposed = true; body.replaceChildren(); styles.replaceChildren(); };
  }, [blob]);
  return <>
    <p className="preview-caption">Word dosyasının önizlemesi. Sayfa düzeni ve yazı tipleri Word uygulamasından farklı görünebilir.</p>
    {loading && <Loading label="Özgün Word belgesi açılıyor…" />}
    {error && <Notice error>Word önizlemesi açılamadı. Özgün dosyayı indirerek inceleyebilirsiniz.</Notice>}
    <div className="docx-stage" ref={host} hidden={loading || error} />
  </>;
}
