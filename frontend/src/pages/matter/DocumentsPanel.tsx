import { lazy, Suspense, useCallback, useEffect, useId, useRef, useState } from 'react';
import { downloadOriginal, request } from '../../api';
import { Badge, Detail, Empty, Icon, Loading, Notice } from '../../components';
import { IntakeReadinessDetails, ReadinessIssues, uploadAllowed } from '../../readiness';
import type { DocumentRecord, IntakeReadiness, Matter } from '../../types';
import { formatDate, locatorText, messageOf, slugId } from '../../utils';

const OriginalPreview = lazy(() => import('./OriginalPreview'));

export default function DocumentsPanel({ matter, onChange, selectedDocumentId, demo = false }: { matter: Matter; onChange: () => Promise<void>; selectedDocumentId?: string | null; demo?: boolean }) {
  const [selectedId, setSelectedId] = useState<string | null>(matter.documents?.[0]?.id || null);
  const [busy, setBusy] = useState(false); const [error, setError] = useState(''); const [message, setMessage] = useState(''); const [dragging, setDragging] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const readinessId = useId();
  const [intake, setIntake] = useState<IntakeReadiness | null>(null);
  const [checking, setChecking] = useState(!demo);
  const [readinessError, setReadinessError] = useState('');
  const canUpload = uploadAllowed(demo, intake, checking);
  const checkIntake = useCallback(async (signal?: AbortSignal) => {
    setChecking(true); setReadinessError(''); setIntake(null);
    try {
      const result = await request<IntakeReadiness>('/intake/readiness', { signal });
      if (!signal?.aborted) setIntake(result);
    } catch (cause) {
      if (!signal?.aborted) setReadinessError(messageOf(cause));
    } finally {
      if (!signal?.aborted) setChecking(false);
    }
  }, []);
  useEffect(() => {
    if (demo) return;
    const controller = new AbortController();
    void checkIntake(controller.signal);
    return () => controller.abort();
  }, [demo, checkIntake]);
  useEffect(() => { if (selectedDocumentId && matter.documents?.some(document => document.id === selectedDocumentId)) setSelectedId(selectedDocumentId); }, [selectedDocumentId, matter.documents]);
  async function upload(files: FileList | File[] | null) {
    if (!files?.length || busy || !canUpload) return;
    setBusy(true); setError(''); setMessage(''); const uploaded: DocumentRecord[] = []; const failures: string[] = [];
    for (const file of Array.from(files)) {
      try { const body = new FormData(); body.append('file', file); uploaded.push(await request<DocumentRecord>(`/matters/${encodeURIComponent(matter.id)}/documents`, { method: 'POST', body })); }
      catch (cause) { failures.push(`${file.name}: ${messageOf(cause)}`); }
    }
    try { await onChange(); } catch (cause) { failures.push(messageOf(cause)); }
    if (uploaded.length) { setSelectedId(uploaded[uploaded.length - 1].id); setMessage(`${uploaded.length} belge yüklendi. Çıkarılan metni ve uyarıları inceleyin.`); }
    if (failures.length) setError(failures.join(' · '));
    setBusy(false); if (input.current) input.current.value = '';
  }
  return <section><div className="section-heading"><div><h2>Dosyalar ve dayanaklar</h2><p className="muted small">Yüklediğiniz dosyalar bu çalışma alanına aittir. Özgün belge ve çıkarılan pasajlar birlikte tutulur.</p></div><button className="button secondary" disabled={busy || !canUpload} aria-describedby={readinessId} onClick={() => input.current?.click()}><Icon name="upload" size={17} />{busy ? 'Yükleniyor…' : 'Dosya yükle'}</button></div>
    <input ref={input} type="file" multiple disabled={busy || !canUpload} accept=".pdf,.docx,.doc,.xlsx,.xls,.csv,.txt,.md,.png,.jpg,.jpeg,.tif,.tiff,.bmp,.webp,.gif,.pptx,.odt,.ods,.odp,.html,.htm,.eml,.msg,.rtf" className="visually-hidden" tabIndex={-1} onChange={(event) => void upload(event.target.files)} aria-label="Çalışma alanına dosya yükle" aria-describedby={readinessId} />
    <div id={readinessId} className="intake-readiness" aria-live="polite">
      {demo ? <Notice><strong>Sentetik demo ortamı.</strong> Yükleme yalnızca geliştirme içindir; gerçek müvekkil belgesi yüklemeyin. Üretim güvenlik kontrolleri burada doğrulanmaz.</Notice> : <>
        <div className="section-heading compact"><span className="small">{checking ? 'Belge kabulü denetleniyor…' : canUpload ? 'Belge kabulü kullanılabilir.' : 'Belge yükleme şu anda kapalı.'}</span><button className="text-button" disabled={checking || busy} onClick={() => void checkIntake()}>{checking ? 'Denetleniyor…' : 'Yeniden denetle'}</button></div>
        {readinessError && <Notice error>{readinessError} Belge kabulü doğrulanamadığı için yükleme kapalı tutuluyor.</Notice>}
        {intake && <>
          {intake.status !== 'ready' && <p className="small">{intake.issues[0]?.message || 'Zararlı içerik tarayıcısı ve belge çıkarım hizmeti erişilebilir olmalıdır.'} Hizmetler düzeltildikten sonra yeniden denetleyin.</p>}
          {intake.checked_at && <p className="small muted">Son denetim: {formatDate(intake.checked_at, true)}</p>}
          <ReadinessIssues issues={intake.issues} /><IntakeReadinessDetails intake={intake} />
        </>}
      </>}
    </div>
    {error && <Notice error>{error}</Notice>}{message && <Notice>{message}</Notice>}
    <div className={`upload-zone ${dragging ? 'dragging' : ''} ${busy || !canUpload ? 'busy' : ''}`} aria-disabled={busy || !canUpload} onDragOver={(event) => { event.preventDefault(); if (canUpload && !busy) setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={(event) => { event.preventDefault(); setDragging(false); void upload(event.dataTransfer.files); }}><Icon name="upload" size={22} /><div><button className="text-button" disabled={busy || !canUpload} aria-describedby={readinessId} onClick={() => input.current?.click()}>{busy ? 'Belgeler yükleniyor…' : 'Dosya seçin veya buraya bırakın'}</button><p>PDF, Office, OpenDocument, görsel, e-posta, HTML, RTF, Markdown ve metin. Çıkarım kısmi olabilir; uyarıları kontrol edin. UDF henüz desteklenmiyor.</p></div></div>
    {!matter.documents?.length ? <Empty title="Henüz bir dayanak eklenmedi.">Belge yükleyerek başlayın. Düşük kalitede veya çıkarılamayan içerikler ayrıca işaretlenir.</Empty> : <div className="document-workspace"><div className="document-list" aria-label="Çalışma alanındaki dosyalar">{matter.documents.map((document) => <button key={document.id} className={`document-item ${selectedId === document.id ? 'selected' : ''}`} onClick={() => setSelectedId(document.id)} aria-pressed={selectedId === document.id}><Icon name="file" size={20} /><span><strong>{document.name}</strong><span className="document-item-meta">{document.page_count ? `${document.page_count} sayfa · ` : ''}{formatDate(document.created_at)}</span><Badge status={document.status} /></span><Icon name="chevron" size={16} /></button>)}</div>{selectedId && <DocumentViewer key={selectedId} matterId={matter.id} documentId={selectedId} />}</div>}
  </section>;
}

export function DocumentViewer({ matterId, documentId, highlightPassageId }: { matterId: string; documentId: string; highlightPassageId?: string }) {
  const [document, setDocument] = useState<DocumentRecord | null>(null); const [error, setError] = useState(''); const [loading, setLoading] = useState(true);
  const [view, setView] = useState<'original' | 'text'>(highlightPassageId ? 'text' : 'original');
  const viewId = useId();
  const [downloading, setDownloading] = useState(false); const [downloadError, setDownloadError] = useState('');
  async function original() { if (!document) return; setDownloading(true); setDownloadError(''); try { await downloadOriginal(matterId, documentId, document.name); } catch (cause) { setDownloadError(messageOf(cause)); } finally { setDownloading(false); } }
  useEffect(() => {
    const controller = new AbortController();
    setDocument(null); setLoading(true); setError(''); setDownloadError('');
    request<DocumentRecord>(`/matters/${encodeURIComponent(matterId)}/documents/${encodeURIComponent(documentId)}`, { signal: controller.signal }).then((value) => {
      if (!controller.signal.aborted) setDocument(value);
    }).catch((cause) => { if (!controller.signal.aborted) setError(messageOf(cause)); }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [matterId, documentId]);
  useEffect(() => { setView(highlightPassageId ? 'text' : 'original'); }, [matterId, documentId, highlightPassageId]);
  useEffect(() => { if (document && highlightPassageId && view === 'text') window.document.getElementById(`passage-${slugId(highlightPassageId)}`)?.scrollIntoView({ block: 'nearest' }); }, [document, highlightPassageId, view]);
  const selectedPassage = document?.passages?.find(passage => passage.id === highlightPassageId);
  const locator = selectedPassage?.locator;
  const locatorPage = typeof locator === 'string' ? Number(/^(?:Sayfa|Page)\s+(\d+)$/i.exec(locator)?.[1]) : locator ? Number(locator.page) : 1;
  const initialPage = Number.isInteger(locatorPage) && locatorPage > 0 ? locatorPage : 1;
  return <div className="document-viewer">{loading ? <Loading label="Belge açılıyor…" /> : error ? <Notice error>{error}</Notice> : document && <>
    <header className="viewer-heading"><span className="eyebrow">KAYNAK GÖRÜNÜMÜ</span><h3>{document.name}</h3><div className="viewer-actions"><Badge status={document.status} />{!document.synthetic && <button className="text-button" disabled={downloading} onClick={() => void original()}><Icon name="download" size={15} />{downloading ? 'İndiriliyor…' : 'Özgün dosyayı indir'}</button>}</div></header>
    {downloadError && <Notice error>{downloadError}</Notice>}
    <div className="source-view-switch" role="group" aria-label="Kaynak görünümü seçimi">
      <button id={`${viewId}-original`} aria-pressed={view === 'original'} aria-controls={`${viewId}-content`} onClick={() => setView('original')}>Özgün belge</button>
      <button id={`${viewId}-text`} aria-pressed={view === 'text'} aria-controls={`${viewId}-content`} onClick={() => setView('text')}>Çıkarılan metin</button>
    </div>
    <div id={`${viewId}-content`} role="region" aria-labelledby={`${viewId}-${view}`}>
      {view === 'original' ? document.synthetic ? <Empty title="Bu örneğin özgün dosyası yok.">Sentetik örnek pasajlarını Çıkarılan metin sekmesinde inceleyebilirsiniz.</Empty> : <Suspense fallback={<Loading label="Özgün dosya açılıyor…" />}><OriginalPreview key={`${matterId}/${documentId}`} matterId={matterId} document={document} initialPage={initialPage} /></Suspense> : <>
        <p className="preview-caption">Analiz için çıkarılan metin. Belgenin sayfa düzenini ve görsellerini Özgün belge sekmesinde inceleyebilirsiniz.</p>
        {document.extraction_warnings?.length > 0 && <Notice><strong>Çıkarım uyarıları</strong><ul>{document.extraction_warnings.map((warning, index) => <li key={index}>{warning}</li>)}</ul></Notice>}
        {document.passages?.length ? <div className="passages">{document.passages.map((passage) => <article key={passage.id} id={`passage-${slugId(passage.id)}`} className={`passage ${passage.id === highlightPassageId ? 'highlighted' : ''}`}><div className="passage-label">{locatorText(passage.locator)}{passage.id === highlightPassageId && <Badge>Seçili dayanak</Badge>}</div><p>{passage.text}</p><Detail title="Pasaj kimliği"><span className="reference-id">{passage.id}</span></Detail></article>)}</div> : <Empty title="Görüntülenebilir metin yok.">Belgenin çıkarım durumunu ve uyarılarını kontrol edin. Metin olmadan belge içeriği doğrulanmış sayılmaz.</Empty>}
      </>}
    </div>
  </>}</div>;
}
