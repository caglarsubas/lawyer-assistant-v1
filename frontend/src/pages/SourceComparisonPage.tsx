import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiError, request } from '../api';
import { Detail, Field, Loading, Notice, PageHeader } from '../components';
import type { PublicSourceCatalog, PublicSourcePassages, User } from '../types';
import { messageOf } from '../utils';
import { canReviewSource } from './SourceReviewPage';
import SourceRelationshipPanel from './SourceRelationshipPanel';
import { COMPARISON_WINDOW, fetchSourceComparison, type ComparisonEvidence, type ComparisonSelection, type ComparisonWindow } from './sourceComparison';

export default function SourceComparisonPage({ sourceId, user }: { sourceId: string; user: User }) {
  if (!canReviewSource(user)) return <Notice error>Kaynak karşılaştırması için küratör yetkisi gerekiyor.</Notice>;
  if (!/^[a-f0-9]{64}$/.test(sourceId)) return <Notice error>Kaynak kimliği geçersiz.</Notice>;
  return <ComparisonWorkspace key={`${sourceId}:${user.id}`} sourceId={sourceId} />;
}

function ComparisonWorkspace({ sourceId }: { sourceId: string }) {
  const [catalog, setCatalog] = useState<(PublicSourceCatalog & { next_cursor: string | null }) | null>(null);
  const [refresh, setRefresh] = useState(0);
  const [catalogLoading, setCatalogLoading] = useState(false); const [catalogCursor, setCatalogCursor] = useState<string | null>(null);
  const [other, setOther] = useState(''); const [left, setLeft] = useState<ComparisonSelection | null>(null); const [right, setRight] = useState<ComparisonSelection | null>(null);
  const [offset, setOffset] = useState(0); const [otherOffset, setOtherOffset] = useState(0);
  const [result, setResult] = useState<ComparisonEvidence | null>(null); const [busy, setBusy] = useState(false); const [error, setError] = useState(''); const [denied, setDenied] = useState(false);
  const operation = useRef<AbortController | null>(null), catalogOperation = useRef<AbortController | null>(null);
  const urls = useRef(new Set<string>());
  const clearResult = useCallback(() => { operation.current?.abort(); setResult(null); setBusy(false); urls.current.forEach(URL.revokeObjectURL); urls.current.clear(); }, []);
  const fail = useCallback((cause: unknown) => {
    clearResult(); setError(messageOf(cause));
    if (cause instanceof ApiError && [401, 403].includes(cause.status)) { catalogOperation.current?.abort(); setDenied(true); setCatalog(null); setLeft(null); setRight(null); }
  }, [clearResult]);
  useEffect(() => {
    const controller = new AbortController(); catalogOperation.current = controller; setCatalog(null); setCatalogLoading(true);
    void request<PublicSourceCatalog & { next_cursor: string | null }>(`/public-sources?limit=100${catalogCursor ? `&after=${catalogCursor}` : ''}`, { signal: controller.signal }).then(value => {
      if (!controller.signal.aborted) { setCatalog(value); setCatalogLoading(false); }
    }).catch(cause => { if (!controller.signal.aborted) { setCatalogLoading(false); fail(cause); } });
    return () => controller.abort();
  }, [catalogCursor, fail, refresh]);
  useEffect(() => { const savedUrls = urls.current; return () => { operation.current?.abort(); catalogOperation.current?.abort(); savedUrls.forEach(URL.revokeObjectURL); savedUrls.clear(); }; }, []);
  const selectLeft = useCallback((value: ComparisonSelection | null) => { clearResult(); setLeft(value); setOffset(0); }, [clearResult]);
  const selectRight = useCallback((value: ComparisonSelection | null) => { clearResult(); setRight(value); setOtherOffset(0); }, [clearResult]);
  async function compare(download = false) {
    if (!left || !right || busy || denied) return;
    operation.current?.abort(); const controller = new AbortController(); operation.current = controller; setBusy(true); setError('');
    const previous = result; if (!download) setResult(null);
    try {
      const evidence = await fetchSourceComparison(left, right, offset, otherOffset, controller.signal);
      if (controller.signal.aborted) return;
      if (download) {
        if (!previous || previous.evidence_sha256 !== evidence.evidence_sha256) throw new Error('Karşılaştırma değişti; yeniden inceleyin.');
        const url = URL.createObjectURL(new Blob([evidence.evidence_json], { type: 'application/json' })); urls.current.add(url);
        const link = document.createElement('a'); link.href = url; link.download = `kaynak-karsilastirmasi-${evidence.evidence_sha256.slice(0, 16)}.json`; document.body.append(link); link.click(); link.remove();
        window.setTimeout(() => { URL.revokeObjectURL(url); urls.current.delete(url); }, 1000);
      }
      setResult(evidence);
    } catch (cause) { if (!controller.signal.aborted) fail(cause); }
    finally { if (!controller.signal.aborted) setBusy(false); }
  }
  if (denied) return <Notice error>Erişim doğrulanamadı. Kaynak karşılaştırmasını yeniden açın.</Notice>;
  return <div className="source-review-page">
    <a className="text-link" href={`#/sources/${sourceId}`}>Kaynak incelemesine dön</a>
    <button className="text-button" onClick={() => { clearResult(); setLeft(null); setRight(null); setOther(''); setOffset(0); setOtherOffset(0); setError(''); setCatalogCursor(null); setRefresh(value => value + 1); }}>Kaynakları yeniden doğrula</button>
    <PageHeader eyebrow="KAYNAK UZLAŞTIRMA" title="İki kaynak temsilini karşılaştırın." description="Karşılıklı pasajları kendiniz seçin; tam metnin değiştirilmeden nasıl farklılaştığını inceleyin." />
    <Notice>Bu karşılaştırma kaynakları birleştirmez, aynı hukuki sürümü veya bağımsız iki çalışma örneğini doğrulamaz. Kaynak kimliği ve sürüm kararını dayanaklarıyla ayrı insan incelemesinde kaydedin.</Notice>
    {error && <Notice error>{error}</Notice>}
    <section className="source-review-section"><h2>Karşılaştırılacak ikinci kaynak</h2>
      {catalogLoading ? <Loading label="Kaynak listesi yükleniyor…" /> : catalog && <>
        <Field label="Kayıtlı kaynak paketi">{id => <select id={id} value={catalog.items.some(item => item.id === other) ? other : ''} onChange={event => { clearResult(); setOther(event.target.value); setRight(null); setOtherOffset(0); }}><option value="">Kaynak seçin</option>{catalog.items.filter(item => item.id !== sourceId).map(item => <option key={item.id} value={item.id}>{item.title} · {item.id.slice(0, 12)}</option>)}</select>}</Field>
        <p className="small muted">Liste paket bildirimlerini gösterir; karşılaştırmada her iki paketin tüm dosyaları ayrıca doğrulanır. Aynı kanun numarası eşleşme kararı değildir.</p>
        {other && <p className="small reference-id">Seçili ikinci paket: {other}</p>}
        <div className="button-group"><button className="text-button" disabled={!catalogCursor} onClick={() => { clearResult(); setOther(''); setRight(null); setCatalogCursor(null); }}>İlk kaynak sayfası</button>{catalog.next_cursor && <button className="text-button" onClick={() => { clearResult(); setOther(''); setRight(null); setCatalogCursor(catalog.next_cursor); }}>Sonraki kaynak sayfası</button>}</div>
      </>}
    </section>
    <div className="source-comparison"><PassageSelector key={`left:${sourceId}:${refresh}`} sourceId={sourceId} label="Birinci kaynak" onSelect={selectLeft} onError={fail} />{other ? <PassageSelector key={`right:${other}`} sourceId={other} label="İkinci kaynak" onSelect={selectRight} onError={fail} /> : <p className="muted">İkinci kaynağı seçerek devam edin.</p>}</div>
    {left && right && <section className="source-review-section"><h2>Seçili pasaj pencereleri</h2><p className="small muted">Her tarafta en fazla {COMPARISON_WINDOW} Unicode karakteri gösterilir. Hizalama veya metin düzeltmesi yapılmaz.</p>
      <div className="form-grid"><Field label="Birinci pasaj başlangıcı">{id => <input id={id} type="number" min={0} max={left.passage.end - left.passage.start - 1} value={offset} onChange={event => { clearResult(); setOffset(event.target.value === '' ? -1 : Number(event.target.value)); }} />}</Field><Field label="İkinci pasaj başlangıcı">{id => <input id={id} type="number" min={0} max={right.passage.end - right.passage.start - 1} value={otherOffset} onChange={event => { clearResult(); setOtherOffset(event.target.value === '' ? -1 : Number(event.target.value)); }} />}</Field></div>
      <button className="button primary" disabled={busy} onClick={() => void compare()}>{busy ? 'Doğrulanıyor…' : 'Seçili pasajları karşılaştır'}</button>
    </section>}
    {result && <><ComparisonResult value={result} /><button className="button secondary" disabled={busy} onClick={() => void compare(true)}>Kanıt kaydını yeniden doğrula ve indir (JSON)</button><p className="small muted">İndirme kaynakları yeniden doğrular. Dosya özeti kimlik incelemesinde dayanak olarak kullanılabilir; insan kararı yerine geçmez.</p><SourceRelationshipPanel key={result.evidence_sha256} evidence={result} onError={fail} /></>}
  </div>;
}

function PassageSelector({ sourceId, label, onSelect, onError }: { sourceId: string; label: string; onSelect: (value: ComparisonSelection | null) => void; onError: (cause: unknown) => void }) {
  const [data, setData] = useState<PublicSourcePassages | null>(null), [offset, setOffset] = useState(0), [selected, setSelected] = useState('');
  const [error, setError] = useState(''), [refresh, setRefresh] = useState(0);
  useEffect(() => {
    const controller = new AbortController(); setData(null); setError('');
    void request<PublicSourcePassages>(`/public-sources/${sourceId}/passages?offset=${offset}&limit=20`, { signal: controller.signal }).then(value => {
      if (!controller.signal.aborted) {
        if (value.source_id !== sourceId || value.integrity_scope !== 'all_artifacts_verified') throw new Error('Kaynak pasajları seçili paketle eşleşmiyor.');
        setData(value);
      }
    }).catch(cause => { if (!controller.signal.aborted) { setError(messageOf(cause)); onError(cause); } });
    return () => controller.abort();
  }, [sourceId, offset, onError, refresh]);
  function page(value: number) { setSelected(''); onSelect(null); setOffset(value); }
  return <section className="source-original-view"><h2>{label}</h2><p className="small reference-id">{sourceId}</p>{error ? <><Notice error>{error}</Notice><button className="text-button" onClick={() => { setSelected(''); onSelect(null); setRefresh(value => value + 1); }}>Pasajları yeniden doğrula</button></> : !data ? <Loading label="Pasajlar yükleniyor…" /> : <>
    <Field label={`${label} pasajı`}>{id => <select id={id} value={selected} onChange={event => { setSelected(event.target.value); const passage = data.items.find(item => item.id === event.target.value); onSelect(passage ? { source: data, passage } : null); }}><option value="">Pasaj seçin</option>{data.items.map(passage => <option key={passage.id} value={passage.id}>{passage.id} · {passage.locator}</option>)}</select>}</Field>
    <p className="small muted">{offset + (data.items.length ? 1 : 0)}–{offset + data.items.length} / {data.total} pasaj. Otomatik eşleştirme yapılmaz.</p>
    <div className="button-group"><button className="text-button" disabled={!offset} onClick={() => page(Math.max(0, offset - 20))}>Önceki pasajlar</button><button className="text-button" disabled={data.next_offset === null} onClick={() => page(data.next_offset!)}>Sonraki pasajlar</button></div>
  </>}</section>;
}

export function ComparisonResult({ value }: { value: ComparisonEvidence }) {
  const { receipt } = value;
  function window(item: ComparisonWindow, range: [number, number], label: string) {
    const points = Array.from(item.text);
    return <article className="source-original-view"><h3>{label}: {item.title}</h3><p className="small reference-id">{item.passage_id} · {item.locator}</p><p className="small muted">Kaynak metninde [{item.start}, {item.end}) · {item.next_offset === null ? 'Pasaj sonuna ulaşıldı.' : `Pasajın devamı var; sonraki başlangıç: ${item.next_offset}.`}</p>
      <pre className="source-original-code">{points.slice(0, range[0]).join('')}{range[1] > range[0] && <mark>{points.slice(range[0], range[1]).join('')}</mark>}{points.slice(range[1]).join('')}</pre><a className="text-link" href={`#/sources/${item.source_id}`}>Bu kaynağın özgün belge incelemesini aç</a></article>;
  }
  return <section className="source-review-section"><h2>Değiştirilmemiş metin karşılaştırması</h2>
    <p>{receipt.difference.equal ? 'Seçili pencerelerin metni birebir aynı.' : 'Seçili pencerelerde ortak başlangıç ve son arasında kalan bölümler işaretlendi.'}</p>
    <p className="small muted">İşaretler tüm değişiklikleri tek tek hizalamaz. Pencere uzunluğu veya kesim farkı da işaret oluşturabilir. Tam kaynak metinleri: {receipt.extracted_text_equal ? 'birebir aynı' : 'birebir aynı değil'}. Özgün dosya baytları: {receipt.raw_bytes_equal ? 'birebir aynı' : 'birebir aynı değil'}.</p>
    <div className="source-comparison">{window(receipt.left, receipt.difference.left_range, 'Birinci kaynak')}{window(receipt.right, receipt.difference.right_range, 'İkinci kaynak')}</div>
    <Notice>Hukuki kimlik ve sürüm henüz çözümlenmedi. Aynı metin aynı hukuki otoriteyi; farklı metin de bir mevzuat değişikliğini kanıtlamaz. Bu işlem inceleme kabulü veya bağımsızlık kararı kaydetmez.</Notice>
    <Detail title="Kanıt kimliği ve kaynak bağları"><dl className="coverage-fields"><div><dt>Kanıt SHA256</dt><dd className="reference-id">{value.evidence_sha256}</dd></div>{[receipt.left, receipt.right].map(item => <div key={item.source_id}><dt>{item.title}</dt><dd className="reference-id">{item.source_version_id} · pasaj: {item.passage_sha256} · pencere: {item.window_sha256}</dd></div>)}</dl><p className="small">İmzalanmamış teknik kayıt. Kaynak adresleri yalnızca köken bilgisidir; dış bağlantı kurulmaz. Tam paket bağları indirilen JSON içinde korunur.</p></Detail>
  </section>;
}
