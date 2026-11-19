import { useEffect, useRef, useState } from 'react';
import { ApiError } from '../../api';
import { Detail, Icon, Loading, Notice } from '../../components';
import { formatDate, messageOf } from '../../utils';
import { capturePunctuationPage, loadPunctuationPage, loadPunctuationRaster, PUNCTUATION_LABELS } from './punctuationReview';
import type { PunctuationCaptureRun, PunctuationObservation, PunctuationSourcePins } from './punctuationTypes';

function mergeImmutable<T extends { id: string }>(old: T[], incoming: T[]): T[] {
  const byId = new Map(old.map(item => [item.id, item]));
  for (const item of incoming) {
    const previous = byId.get(item.id);
    if (previous && JSON.stringify(previous) !== JSON.stringify(item)) throw new ApiError('Saklanan gözlem geçmişi yeniden doğrulanmalıdır.', 409);
    byId.set(item.id, item);
  }
  return [...byId.values()];
}

function PunctuationRaster({ pins, observation }: { pins: PunctuationSourcePins; observation: PunctuationObservation }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => {
    const controller = new AbortController();
    const target = canvas.current;
    setReady(false); setError('');
    async function draw() {
      const blob = await loadPunctuationRaster(pins, observation, controller.signal);
      controller.signal.throwIfAborted();
      const image = await createImageBitmap(blob);
      try {
        controller.signal.throwIfAborted();
        if (image.width !== observation.width || image.height !== observation.height || !target) throw new ApiError('Kaydedilen OCR görüntüsünün boyutları doğrulanamadı.', 409);
        const [left, top, right, bottom] = observation.event.crop_bounds || [0, 0, observation.width, observation.height];
        target.width = right - left; target.height = bottom - top;
        const context = target.getContext('2d');
        if (!context) throw new ApiError('Bu tarayıcıda OCR görüntüsü açılamadı.', 0);
        context.drawImage(image, left, top, target.width, target.height, 0, 0, target.width, target.height);
        setReady(true);
      } finally { image.close(); }
    }
    void draw().catch(cause => { if (!controller.signal.aborted) setError(messageOf(cause)); });
    return () => {
      controller.abort();
      if (target) { target.width = 1; target.height = 1; }
    };
  }, [pins, observation]);
  return <>
    {error ? <Notice error>{error}</Notice> : !ready && <Loading label="Kaydedilen OCR görüntüsü doğrulanıyor…" />}
    <div className="image-stage" hidden={!ready || !!error}>
      <canvas ref={canvas} width={1} height={1} role="img" aria-label="Kaydedilen OCR sayfasının ilgili bölgesi"
        style={{ maxWidth: '100%', width: 'min(100%, 560px)', height: 'auto' }} />
    </div>
    {ready && !error && <PunctuationReadings observation={observation} />}
  </>;
}

export function PunctuationReadings({ observation }: { observation: PunctuationObservation }) {
  return <>
    <div className="details-content" style={{ paddingInline: 'clamp(18px, 3vw, 24px)' }}>
    <p className="small muted">{PUNCTUATION_LABELS[observation.event.status]}. Okumaları kaynak sayfasıyla karşılaştırarak inceleyin.</p>
    <div className="revision-columns" style={{ marginTop: 16 }}>{observation.event.readings.map(reading => <section key={reading.reader}>
      <h4>{reading.reader === 'raw' ? 'Ham görüntü okuması' : 'Kontrastlı görüntü okuması'}</h4>
      <blockquote className="source-quotation original">{reading.text}</blockquote>
    </section>)}</div>
    {!!observation.event.missing_readers.length && <p className="small muted">{observation.event.missing_readers.map(reader => reader === 'raw' ? 'Ham görüntü okuması' : 'Kontrastlı görüntü okuması').join(' ve ')} kaydedilemedi. Yerine alternatif okuma üretilmedi.</p>}
    </div>
    <Detail title="Gözlemin kaynak ve sürüm bilgileri" variant="technical">
      <dl className="provenance-list">
        <div><dt>Saklanan gözlem</dt><dd>{observation.id}</dd></div>
        <div><dt>Analiz sürümü</dt><dd>{observation.version_id}</dd></div>
        <div><dt>Belge sürümü</dt><dd>{observation.document_revision}</dd></div>
        <div><dt>Belge SHA-256</dt><dd>{observation.document_sha256}</dd></div>
        <div><dt>Sayfa görüntüsü SHA-256</dt><dd>{observation.raster_sha256}</dd></div>
        <div><dt>Alıntı SHA-256</dt><dd>{observation.quote_sha256}</dd></div>
        <div><dt>Gözlem SHA-256</dt><dd>{observation.observation_sha256}</dd></div>
        <div><dt>Kaynak bölgesi</dt><dd>{observation.event.crop_bounds?.join(', ') || 'Sayfanın tamamı'}</dd></div>
      </dl>
    </Detail>
  </>;
}

export default function PunctuationObservations({ pins }: { pins: PunctuationSourcePins }) {
  return <PunctuationObservationScope key={JSON.stringify(pins)} pins={pins} />;
}

function PunctuationObservationScope({ pins }: { pins: PunctuationSourcePins }) {
  const [items, setItems] = useState<PunctuationObservation[]>([]);
  const [runs, setRuns] = useState<PunctuationCaptureRun[]>([]);
  const [more, setMore] = useState(false);
  const [moreRuns, setMoreRuns] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const active = useRef<AbortController | null>(null);
  const generation = useRef(0);
  const selected = items.find(item => item.id === selectedId);

  async function load(offset = 0, runOffset = 0, append: 'items' | 'runs' | null = null) {
    active.current?.abort();
    const controller = new AbortController(); active.current = controller;
    const turn = ++generation.current;
    setBusy(true); setError('');
    if (!append) { setItems([]); setRuns([]); setSelectedId(null); setLoaded(false); }
    try {
      const page = await loadPunctuationPage(pins, offset, runOffset, controller.signal);
      if (controller.signal.aborted || turn !== generation.current) return;
      if (append === 'items') setItems(mergeImmutable(items, page.items));
      else if (append !== 'runs') setItems(page.items);
      if (append === 'runs') setRuns(mergeImmutable(runs, page.runs));
      else if (append !== 'items') setRuns(page.runs);
      if (append !== 'runs') setMore(page.has_more);
      if (append !== 'items') setMoreRuns(page.runs_has_more);
      setLoaded(true);
    } catch (cause) {
      if (!controller.signal.aborted && turn === generation.current) {
        setError(messageOf(cause)); setItems([]); setRuns([]); setSelectedId(null); setLoaded(false);
      }
    } finally { if (turn === generation.current) setBusy(false); }
  }

  useEffect(() => {
    void load();
    return () => { generation.current++; active.current?.abort(); };
  }, []);

  async function capture() {
    active.current?.abort();
    const controller = new AbortController(); active.current = controller;
    const turn = ++generation.current;
    setBusy(true); setError(''); setNotice(''); setSelectedId(null);
    try {
      await capturePunctuationPage(pins, controller.signal);
      if (controller.signal.aborted || turn !== generation.current) return;
      setNotice('Denetim kaydı saklandı. Okumaları özgün sayfayla birlikte inceleyin.');
      await load();
    } catch (cause) {
      if (!controller.signal.aborted && turn === generation.current) setError(messageOf(cause));
    } finally { if (turn === generation.current) setBusy(false); }
  }

  return <section className="analysis-source" aria-label="Sayfadaki OCR noktalama okumaları">
    <div className="analysis-source-heading"><Icon name="file" size={20} /><div>
      <h4>Sayfadaki OCR noktalama okumaları</h4>
      <p className="small muted">Tutar alanlarındaki ham ve kontrastlı OCR okumaları karşılaştırılır. Gözlemler bu kaynak sayfasına aittir; alıntıyla ilişkisini özgün sayfada inceleyin. Belge ve kayıtlı alıntı değiştirilmez.</p>
    </div></div>
    <div className="button-group">
      <button type="button" className="button secondary" disabled={busy} onClick={() => void capture()}>Noktalama okumalarını denetle</button>
      <button type="button" className="text-button" disabled={busy} onClick={() => void load()}>Saklanan okumaları yenile</button>
    </div>
    {notice && <Notice>{notice}</Notice>}{error && <Notice error>{error}</Notice>}
    {busy && <Loading label="Sayfaya bağlı noktalama kayıtları açılıyor…" />}
    {loaded && !items.length && <p className="small muted">Bu sayfa için saklanan noktalama gözlemi yok. Bu durum, sayfadaki tüm noktalamanın doğru olduğunu göstermez; özgün sayfayı inceleyin.</p>}
    {items.map(item => <button key={item.id} type="button" className={`document-item${selectedId === item.id ? ' selected' : ''}`}
      aria-pressed={selectedId === item.id} disabled={busy} onClick={() => setSelectedId(item.id)}>
      <span><strong>{PUNCTUATION_LABELS[item.event.status]}</strong><span className="document-item-meta">{formatDate(item.created_at, true)} · Sayfa {item.page}</span></span><Icon name="chevron" size={16} />
    </button>)}
    {more && <button type="button" className="text-button" disabled={busy} onClick={() => void load(items.length, 0, 'items')}>Diğer gözlemleri getir</button>}
    {selected && <article className="source-excerpt"><header className="source-excerpt-header"><div>
      <h4>İnceleme için saklanan OCR okumaları</h4><p>{formatDate(selected.created_at, true)} · Sayfa {selected.page}</p>
    </div></header><PunctuationRaster key={selected.observation_sha256} pins={pins} observation={selected} /></article>}
    {!!runs.length && <Detail title="Noktalama denetim geçmişi">
      <p className="small muted">Her kayıt yalnız bu analiz sürümü ve kaynak sayfasındaki denetimi gösterir.</p>
      <ul>{runs.map(run => <li key={run.id}>{formatDate(run.created_at, true)} · {run.event_count === 0 ? 'Hedeflenen tutar alanlarında yeni gözlem oluşmadı' : `${run.event_count} inceleme gözlemi saklandı`}</li>)}</ul>
      {moreRuns && <button type="button" className="text-button" disabled={busy} onClick={() => void load(0, runs.length, 'runs')}>Diğer denetimleri getir</button>}
    </Detail>}
  </section>;
}
