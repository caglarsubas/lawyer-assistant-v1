import { reconcileCarriedDestinationReturn, type CarriedDestinationReturn } from '../workbench/carriedDestinationReturn';
import CarriedDestinationReturnPanel from './CarriedDestinationReturnPanel';
import { carriedArrivalEventAvailable, prepareCarriedArrivalEvent } from '../workbench/carriedArrivalEventHandoff';
import { useEffect, useRef, useState } from 'react';
import { onwardEventAvailable, prepareOnwardEvent } from '../workbench/onwardEventHandoff';
import { request } from '../api';
import { Detail, Notice, PageHeader } from '../components';
import { formatDate, messageOf } from '../utils';
import { usePortfolio, workspaceQuery } from '../workbench/portfolio';
import { captureReturn, portfolioPart, queueReturnHref, reconcileReturn, type ReturnIntent, type ReturnReconciliation } from '../workbench/portfolioReturn';
import { canonicalJson, SourceReadFence } from './matter/sourceReviewTypes';
import { sourceContextHref, verifyNavigation, type NavigationMetadata, type SourceTarget } from './sourceContextNavigationTypes';
import { returnComparisonLinks } from '../workbench/returnComparison';
import { captureReturnedLineage, observeReturnedLineage, prepareReturnedEvent, type ReturnedLineageObservation } from '../workbench/returnedReviewLineage';
import ReturnedReviewLineagePanel from './ReturnedReviewLineagePanel';
import { reconcileComparisonReturn, type ComparisonReturnReceipt, type ComparisonQueueReconciliation } from '../workbench/comparisonReturn';
import { reconcileArrivalReturn, type ArrivalReturn } from '../workbench/arrivalReturn';
import { arrivalEventAvailable, prepareArrivalEvent } from '../workbench/arrivalEventHandoff';
import { reconcileOnwardReturn, type OnwardReturn } from '../workbench/onwardReturn';
import { reconcileCarriedArrivalReturn, type CarriedArrivalReturn } from '../workbench/carriedArrivalReturn';
import CarriedArrivalReturnPanel from './CarriedArrivalReturnPanel';
import OnwardReturnPanel from './OnwardReturnPanel';
import ArrivalReturnPanel from './ArrivalReturnPanel';
import ComparisonReturnPanel from './ComparisonReturnPanel';
import { comparisonEventAvailable, prepareComparisonEvent } from '../workbench/comparisonEventHandoff';
import ReturnIdentityComparison, { type ReturnLinks } from './ReturnIdentityComparison';
import { captureRenewalHandoff, renewalHandoffHref } from '../workbench/renewalHandoff';
import { verifyReviewLineage, type ReviewLineage } from './sourceReviewLineageTypes';
import { queueFilters, queueQuery, sourceQueueHref, verifyPortfolioQueue, type PortfolioQueuePage } from './portfolioSourceQueueTypes';
import { PortfolioQueueResults } from './PortfolioSourceReviewQueue';

export function ReturnFilterSummary({ intent }: { intent: ReturnIntent }) {
  const f = intent.filters;
  return <section aria-label="Dönüşün tam portföy filtreleri"><Detail title="İncelemeye giderken seçilen filtreler" open>
    <p className="reference-id">Müvekkil kimlikleri: {f.customer_ids.join(', ') || 'Tüm yetkili müvekkiller'} · Seçimler OR eşleşir; erişim ayrıca doğrulanır.</p>
    <p>Çalışma alanı tarihi: {f.date_field === 'created_at' ? 'Oluşturulma' : f.date_field === 'updated_at' ? 'Son güncelleme' : 'Hukuken ilgili tarih'} · {f.date_from || 'Açık başlangıç'} — {f.date_to || 'Açık bitiş'}</p>
    <p>Kaynak kaydının tarihi: {f.source_date_from || 'Açık başlangıç'} — {f.source_date_to || 'Açık bitiş'} · Türkiye takvim günleri.</p>
    <p>Kaynak inceleme durumu: {f.bucket === 'all' ? 'Tüm kayıtlar' : 'Karar, yenileme veya düzeltme bekleyen'}</p>
    <p className="small muted">Bu seçim yalnızca dönüş niyetidir. Önceki sonuçlar, alıntılar, yorumlar, inceleme onayı ve kaynak izinleri geri yüklenmez.</p>
  </Detail></section>;
}
export function ReturnReconciliationPanel({ value, links, renew }: { value: ReturnReconciliation; links: ReturnLinks; renew?: () => void }) {
  return <section aria-label="Seçilen kaydın yeni portföy gözlemi">
    <h3>Seçilen kaydın yeni gözlemi</h3><p className="small muted">Kuyruk gözlemi: {formatDate(value.queue_observed_at, true)}{value.state === 'observed' && ` · Kayıt kimliği gözlemi: ${formatDate(value.target_observed_at, true)}`}. Ayrı gözlemler tek bir atomik an değildir; kaynaklar kontrol edilmedi.</p>
    {value.state === 'not_observed' ? <Notice>Seçilen kayıt bu sınırlı pencerede gözlenmedi. Silindiği, erişimin kaybolduğu veya tüm portföyün incelendiği sonucuna varılmaz. Pencereler kendiliğinden taranmaz.</Notice> : <>
      <p>Sabit bağlam ve kanıt sürümü kimlikleri eşleşiyor. Bu eşleşme içerik güncelliği veya hukuki hazır olma değildir.</p>
      <p>Özel dayanak gözlemi: {value.private_state === 'unchanged' ? 'Değişiklik gözlenmedi' : value.private_state === 'changed' ? 'Değişiklik gözlendi' : 'Bilinmiyor'} · Bağlam kabulü: {value.context_state === 'complete' ? 'Tamamlandı' : value.context_state === 'pending' ? 'Bekliyor' : 'Doğrulanamadı'} · Karar kabulü: {value.review_state === 'complete' ? 'Tamamlandı' : value.review_state === 'pending' ? 'Bekliyor' : 'Karar yok veya doğrulanamadı'}</p>
      {value.selected_review_state && <p>Seçilen tarihsel inceleme: {value.selected_review_state === 'reviewed_conditional' ? 'Koşullu inceleme kaydedildi' : value.selected_review_state === 'changes_requested' ? 'Değişiklik istendi' : 'Doğrulanamadı'}. Güncel kararın veya kaynak izninin yerine geçmez.</p>}
      <ReturnIdentityComparison value={value.comparison} links={links} renew={renew} />
    </>}
  </section>;
}
function ReturnWorkspace({ intent, token, receipt, arrival, onward, carried, destination }: { destination: CarriedDestinationReturn | null; carried: CarriedArrivalReturn | null; onward: OnwardReturn | null; intent: ReturnIntent; token: string; receipt: ComparisonReturnReceipt | null; arrival: ArrivalReturn | null }) {
  const { filters, setFilters, revision, loading, error: scopeError, refresh, returns } = usePortfolio();
  const [prepared, setPrepared] = useState(false); const [preparedRevision, setPreparedRevision] = useState(-1);
  const [page, setPage] = useState<PortfolioQueuePage | null>(null); const [comparison, setComparison] = useState<ReturnReconciliation | null>(null);
  const [destinationComparison, setDestinationComparison] = useState<ComparisonQueueReconciliation | null>(null);
  const [carriedComparison, setCarriedComparison] = useState<ComparisonQueueReconciliation | null>(null);
  const [onwardComparison, setOnwardComparison] = useState<ComparisonQueueReconciliation | null>(null);
  const [arrivalComparison, setArrivalComparison] = useState<ComparisonQueueReconciliation | null>(null);
  const [receiptComparison, setReceiptComparison] = useState<ComparisonQueueReconciliation | null>(null);
  const [history, setHistory] = useState<ReviewLineage | null>(null); const [path, setPath] = useState<ReturnedLineageObservation | null>(null);
  const [comparisonLink, setComparisonLink] = useState<string | null>(null);
  const [eventLink, setEventLink] = useState<{ href: string; id: string } | null>(null);
  const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  const fence = useRef(new SourceReadFence()); const matching = canonicalJson(filters) === canonicalJson(portfolioPart(intent.filters));
  const visible = prepared && matching && revision === preparedRevision && !loading && !scopeError;
  const key = `${workspaceQuery(filters)}:${revision}`;
  useEffect(() => { const gate = fence.current; return () => gate.invalidate(); }, []);
  useEffect(() => { fence.current.invalidate(); setPage(null); setComparison(null); setReceiptComparison(null); setArrivalComparison(null); setOnwardComparison(null); setCarriedComparison(null); setDestinationComparison(null); setHistory(null); setPath(null); setEventLink(null); setComparisonLink(null); setBusy(false); if (prepared && (!matching || revision !== preparedRevision)) setPrepared(false); }, [key, matching]);
  useEffect(() => { if (loading || scopeError) { fence.current.invalidate(); setPage(null); setComparison(null); setReceiptComparison(null); setArrivalComparison(null); setOnwardComparison(null); setCarriedComparison(null); setDestinationComparison(null); setHistory(null); setPath(null); setEventLink(null); setComparisonLink(null); setBusy(false); } }, [loading, scopeError]);
  function prepare() {
    fence.current.invalidate(); setPage(null); setComparison(null); setReceiptComparison(null); setArrivalComparison(null); setOnwardComparison(null); setCarriedComparison(null); setDestinationComparison(null); setHistory(null); setPath(null); setEventLink(null); setComparisonLink(null); setError(''); setBusy(false);
    setFilters(portfolioPart(intent.filters)); setPreparedRevision(revision + 1); refresh(); setPrepared(true);
  }
  async function observe(offset: number) {
    if (!prepared || !matching || loading || scopeError || !returns.get(token)) return;
    const task = fence.current.begin(); setBusy(true); setError(''); setPage(null); setComparison(null); setReceiptComparison(null); setArrivalComparison(null); setOnwardComparison(null); setCarriedComparison(null); setDestinationComparison(null); setHistory(null); setPath(null); setEventLink(null); setComparisonLink(null);
    const target: SourceTarget = { kind: 'selected', matter_id: intent.target.matter_id, analysis_id: intent.target.analysis_id, context_id: intent.target.context_id, ...(intent.target.review_id ? { review_id: intent.target.review_id } : {}) };
    try {
      const expected = queueFilters(filters, intent.filters);
      const result = await request<PortfolioQueuePage>(`/work/source-reviews?${queueQuery(expected, offset)}`, { signal: task.signal }); verifyPortfolioQueue(result, expected, offset);
      if (!task.current() || !returns.get(token)) return;
      let meta: NavigationMetadata | null = null, lineage: ReviewLineage | null = null;
      if (result.items.some(item => item.id === target.context_id)) {
        const base = `/matters/${encodeURIComponent(target.matter_id)}/analyses/${encodeURIComponent(target.analysis_id)}/source-contexts/${encodeURIComponent(target.context_id)}`;
        if (target.review_id) { lineage = await request<ReviewLineage>(`${base}/reviews/${encodeURIComponent(target.review_id)}/navigation-context`, { signal: task.signal }); verifyReviewLineage(lineage, target); meta = lineage.context_navigation; }
        else { meta = await request<NavigationMetadata>(`${base}/navigation-context`, { signal: task.signal }); verifyNavigation(meta, target); }
      }
      const value = reconcileReturn(intent, result, meta, lineage);
      const receiptValue = receipt ? reconcileComparisonReturn(intent, receipt, result, meta, lineage, offset) : null;
      const arrivalValue = arrival ? reconcileArrivalReturn(intent, arrival, result, meta, lineage, offset) : null;
      const onwardValue = onward ? reconcileOnwardReturn(intent, onward, result, meta, lineage, offset) : null;
      const carriedValue = carried ? reconcileCarriedArrivalReturn(intent, carried, result, meta, lineage, offset) : null;
      const destinationValue = destination ? reconcileCarriedDestinationReturn(intent, destination, result, meta, lineage, offset) : null;
      if (task.current() && returns.get(token)) { setDestinationComparison(destinationValue); setCarriedComparison(carriedValue); setOnwardComparison(onwardValue); setArrivalComparison(arrivalValue); setPage(result); setComparison(value); setReceiptComparison(receiptValue); setHistory(lineage); }
    } catch (cause) { if (task.current()) { fence.current.invalidate(); setPage(null); setComparison(null); setReceiptComparison(null); setArrivalComparison(null); setOnwardComparison(null); setCarriedComparison(null); setDestinationComparison(null); setHistory(null); setPath(null); setEventLink(null); setComparisonLink(null); setBusy(false); setError(messageOf(cause)); } }
    finally { if (task.current()) setBusy(false); }
  }
  const basis = comparison && history ? captureReturnedLineage(intent, comparison, history) : null;
  async function observePath() {
    if (!visible || busy || !basis || !returns.get(token)) return;
    const task = fence.current.begin(); setBusy(true); setError(''); setPath(null); setEventLink(null); setComparisonLink(null);
    try {
      const value = await observeReturnedLineage(basis, url => request<ReviewLineage>(url, { signal: task.signal }), () => task.current() && !!returns.get(token));
      if (task.current() && returns.get(token)) setPath(value);
    } catch (cause) {
      if (task.current()) { fence.current.invalidate(); setPage(null); setComparison(null); setReceiptComparison(null); setArrivalComparison(null); setOnwardComparison(null); setCarriedComparison(null); setDestinationComparison(null); setHistory(null); setPath(null); setEventLink(null); setComparisonLink(null); setBusy(false); setError(messageOf(cause)); }
    } finally { if (task.current()) setBusy(false); }
  }
  async function prepareComparedEvent() {
    if (!visible || busy || destination || carried && !carriedComparison || onward && !onwardComparison || !receipt || !receiptComparison || arrival && !arrivalComparison || !returns.get(token)) return;
    const task = fence.current.begin(); setBusy(true); setError(''); setComparisonLink(null); setEventLink(null); setPath(null);
    try {
      const read = (url: string) => request<ReviewLineage>(url, { signal: task.signal }), current = () => task.current() && !!returns.get(token);
      const preparedCarried = carried ? await prepareCarriedArrivalEvent(intent, carried, carriedComparison!, read, current) : null;
      const preparedOnward = !carried && onward ? await prepareOnwardEvent(intent, onward, onwardComparison!, read, current) : null;
      const preparedArrival = !carried && !onward && arrival ? await prepareArrivalEvent(intent, arrival, arrivalComparison!, read, current) : null;
      const preparedComparison = !carried && !onward && !arrival ? await prepareComparisonEvent(intent, receipt, receiptComparison, read, current) : null;
      if (!current()) return;
      const next = preparedCarried ? returns.putCarriedArrivalEvent(intent, preparedCarried) : preparedOnward ? returns.putOnwardEvent(intent, preparedOnward) : preparedArrival ? returns.putArrivalEvent(intent, preparedArrival) : returns.putComparisonEvent(intent, preparedComparison!), t = intent.target;
      const href = sourceContextHref(t.matter_id, t.analysis_id, t.context_id, t.review_id!, next);
      if (!href) throw new Error('Tam karşılaştırma bağlantısı kurulamadı.');
      setComparisonLink(href);
    } catch (cause) {
      if (task.current()) { fence.current.invalidate(); setPage(null); setComparison(null); setReceiptComparison(null); setArrivalComparison(null); setOnwardComparison(null); setCarriedComparison(null); setDestinationComparison(null); setHistory(null); setPath(null); setEventLink(null); setComparisonLink(null); setBusy(false); setError(messageOf(cause)); }
    } finally { if (task.current()) setBusy(false); }
  }
  async function prepareEvent(id: string) {
    if (!visible || busy || !basis || !path || !returns.get(token)) return;
    const task = fence.current.begin(); setBusy(true); setError(''); setEventLink(null); setComparisonLink(null);
    try {
      const preparedEvent = await prepareReturnedEvent(basis, path, id, url => request<ReviewLineage>(url, { signal: task.signal }), () => task.current() && !!returns.get(token));
      if (!task.current() || !returns.get(token)) return;
      const { intent: next, handoff } = preparedEvent;
      const nextToken = returns.putReviewPath(next, handoff);
      const href = sourceContextHref(next.target.matter_id, next.target.analysis_id, next.target.context_id, next.target.review_id!, nextToken);
      if (!href) throw new Error('Tam tarihsel karar bağlantısı kurulamadı.');
      setEventLink({ href, id: next.target.review_id! });
    } catch (cause) {
      if (task.current()) { fence.current.invalidate(); setPage(null); setComparison(null); setReceiptComparison(null); setArrivalComparison(null); setOnwardComparison(null); setCarriedComparison(null); setDestinationComparison(null); setHistory(null); setPath(null); setEventLink(null); setComparisonLink(null); setBusy(false); setError(messageOf(cause)); }
    } finally { if (task.current()) setBusy(false); }
  }
  return <><PageHeader eyebrow="PORTFÖYE GÜVENLİ DÖNÜŞ" title="Kaynak incelemelerine dön" description="Tam filtre niyetini yeniden hazırlayın; mevcut yetkilerinizle yeni ve sınırlı bir gözlem yapın." />
    <ReturnFilterSummary intent={intent} />
    {error && <Notice error>{error}</Notice>}{scopeError && <Notice error>{scopeError}</Notice>}
    {!prepared || !matching ? <button className="button secondary" disabled={busy} onClick={prepare}>Dönüş filtrelerini uygula ve hazırla</button> : <><p className="small muted">Tam müvekkil ve çalışma alanı tarih filtreleri soldaki portföye uygulandı. Kaynak kayıt tarihleri yukarıdaki niyette ayrı korunur.</p><button className="button secondary" disabled={busy || loading || !!scopeError} onClick={() => void observe(0)}>Aynı filtrelerle yeni portföy gözlemi yap</button></>}
    {receipt && receiptComparison && visible && <ComparisonReturnPanel receipt={receipt} value={receiptComparison} prepare={!arrival && comparisonEventAvailable(intent, receipt, receiptComparison) ? () => void prepareComparedEvent() : undefined} busy={busy} />}
    {arrival && arrivalComparison && visible && <ArrivalReturnPanel observation={arrival} value={arrivalComparison} prepare={!onward && arrivalEventAvailable(intent, arrival, arrivalComparison) ? () => void prepareComparedEvent() : undefined} busy={busy} />}
    {onward && onwardComparison && visible && <OnwardReturnPanel observation={onward} value={onwardComparison} prepare={!carried && onwardEventAvailable(intent, onward, onwardComparison) ? () => void prepareComparedEvent() : undefined} busy={busy} />}
    {carried && carriedComparison && visible && <CarriedArrivalReturnPanel observation={carried} value={carriedComparison} prepare={!destination && carriedArrivalEventAvailable(intent, carried, carriedComparison) ? () => void prepareComparedEvent() : undefined} busy={busy} />}
    {destination && destinationComparison && visible && <CarriedDestinationReturnPanel observation={destination} value={destinationComparison} />}
    {comparisonLink && visible && <section aria-label={carried ? "Taşınan varışı koruyan seçilen karara güvenli geçiş" : onward ? "İleri dönüşü koruyan seçilen karara güvenli geçiş" : arrival ? "Varışı koruyan seçilen karara güvenli geçiş" : "Karşılaştırmadan seçilen karara güvenli geçiş"}>
      <p className="small muted">Tam seçilen karar iki yeni kimlik gözlemiyle doğrulandı. İlk filtreler, kanıt ve ayrı karşılaştırma gözlemleri korundu. Kaynak içeriği veya onay açılmaz.</p>
      <a className="button secondary" href={comparisonLink}>{carried ? "Taşınan varışı koruyan doğrulanmış tam kararı aç" : onward ? "İleri dönüşü koruyan doğrulanmış tam kararı aç" : arrival ? "Varışı koruyan doğrulanmış tam kararı aç" : "Karşılaştırmadan doğrulanan tam kararı aç"}</a>
    </section>}
    {comparison && visible && <ReturnReconciliationPanel value={comparison} links={returnComparisonLinks(intent, comparison, token)} renew={captureRenewalHandoff(intent, comparison) ? () => {
      try { const handoff = captureRenewalHandoff(intent, comparison); if (!handoff || !returns.get(token)) throw new Error('Yeni karşılaştırma gözlemi gerekli.');
        const next = returns.put(intent, handoff); window.location.hash = renewalHandoffHref(intent, next)!;
      } catch (cause) { fence.current.invalidate(); setPage(null); setComparison(null); setReceiptComparison(null); setArrivalComparison(null); setOnwardComparison(null); setCarriedComparison(null); setDestinationComparison(null); setHistory(null); setPath(null); setEventLink(null); setComparisonLink(null); setError(messageOf(cause)); }
    } : undefined} />}
    {comparison?.state === 'observed' && visible && <section aria-label="Sınırlı karar zinciri kontrolü">
      <p className="small muted">Bu karşılaştırmadaki karar başından seçilen tarihsel incelemeye kayıt bağlantısını ayrıca gözlemleyin. Seçilen kaydın iki kimlik gözlemi arasında, baştan başlayan tek ve en çok 10 kayıtlık geçmiş penceresi okunur.</p>
      {basis ? <button className="button secondary" disabled={busy} onClick={() => void observePath()}>Baştan seçilen incelemeye sınırlı zinciri kontrol et</button>
        : <Notice>Tam seçilen karar, güncel baş, sürüm veya kabuller doğrulanamadı. Zincir kontrolü için yeni ve tamamlanmış bir portföy gözlemi gerekli.</Notice>}
      {path && <ReturnedReviewLineagePanel value={path} busy={busy} choose={id => void prepareEvent(id)} />}
      {eventLink && <section aria-label="Doğrulanan zincir kaydına güvenli geçiş"><p className="reference-id">Ayrıca seçilen kayıt: {eventLink.id}</p>
        <p className="small muted">İlk filtreler ve karşılaştırma gözlemleri korundu. Bağlantı yeni tam kimlik gözlemi yapar; kaynak metni veya onay açmaz.</p>
        <a className="button secondary" href={eventLink.href}>Doğrulanan zincir kaydının tam kimliğini aç</a></section>}
    </section>}
    {page && visible && <PortfolioQueueResults page={page} busy={busy} next={() => void observe(page.coverage.next_offset!)} open={(item, event) => { event.preventDefault(); if (busy) return; try { const next = returns.put(captureReturn(page, item)); window.location.hash = sourceQueueHref(item, next)!; } catch (cause) { setPage(null); setComparison(null); setReceiptComparison(null); setArrivalComparison(null); setOnwardComparison(null); setCarriedComparison(null); setDestinationComparison(null); setHistory(null); setPath(null); setEventLink(null); setComparisonLink(null); setError(messageOf(cause)); } }} />}
    <p><a className="text-link" href={queueReturnHref()!}>Yeni filtrelerle ayrı kaynak kuyruğu hazırla</a></p>
  </>;
}
export default function PortfolioReturnQueue({ token }: { token: string }) {
  const { returns } = usePortfolio(); const [expired, setExpired] = useState(false);
  useEffect(() => { setExpired(false); const timer = setTimeout(() => setExpired(true), returns.remaining(token)); return () => clearTimeout(timer); }, [token, returns]);
  const intent = returns.get(token);
  if (expired || !intent) return <Notice error>Dönüş bağı yok veya süresi doldu. Tam filtreler tahmin edilmedi; kaynak kuyruğu okunmadı. <a href={queueReturnHref()!}>Yeni kaynak kuyruğunu açıkça hazırla</a></Notice>;
  return <ReturnWorkspace key={token} token={token} intent={intent} receipt={returns.getComparisonReturn(token)} arrival={returns.getArrivalReturn(token)} onward={returns.getOnwardReturn(token)} carried={returns.getCarriedArrivalReturn(token)} destination={returns.getCarriedDestinationReturn(token)} />;
}
