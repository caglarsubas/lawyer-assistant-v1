import { useEffect, useRef, useState } from 'react';
import { request } from '../api';
import { Detail, Notice, PageHeader } from '../components';
import { formatDate, messageOf } from '../utils';
import { usePortfolio, workspaceQuery } from '../workbench/portfolio';
import { captureReturn, portfolioPart, queueReturnHref, reconcileReturn, type ReturnIntent, type ReturnReconciliation } from '../workbench/portfolioReturn';
import { canonicalJson, SourceReadFence } from './matter/sourceReviewTypes';
import { verifyNavigation, type NavigationMetadata, type SourceTarget } from './sourceContextNavigationTypes';
import { returnComparisonLinks } from '../workbench/returnComparison';
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
function ReturnWorkspace({ intent, token }: { intent: ReturnIntent; token: string }) {
  const { filters, setFilters, revision, loading, error: scopeError, refresh, returns } = usePortfolio();
  const [prepared, setPrepared] = useState(false); const [preparedRevision, setPreparedRevision] = useState(-1);
  const [page, setPage] = useState<PortfolioQueuePage | null>(null); const [comparison, setComparison] = useState<ReturnReconciliation | null>(null);
  const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  const fence = useRef(new SourceReadFence()); const matching = canonicalJson(filters) === canonicalJson(portfolioPart(intent.filters));
  const visible = prepared && matching && revision === preparedRevision && !loading && !scopeError;
  const key = `${workspaceQuery(filters)}:${revision}`;
  useEffect(() => { const gate = fence.current; return () => gate.invalidate(); }, []);
  useEffect(() => { fence.current.invalidate(); setPage(null); setComparison(null); setBusy(false); if (prepared && (!matching || revision !== preparedRevision)) setPrepared(false); }, [key, matching]);
  useEffect(() => { if (loading || scopeError) { fence.current.invalidate(); setPage(null); setComparison(null); setBusy(false); } }, [loading, scopeError]);
  function prepare() {
    fence.current.invalidate(); setPage(null); setComparison(null); setError(''); setBusy(false);
    setFilters(portfolioPart(intent.filters)); setPreparedRevision(revision + 1); refresh(); setPrepared(true);
  }
  async function observe(offset: number) {
    if (!prepared || !matching || loading || scopeError || !returns.get(token)) return;
    const task = fence.current.begin(); setBusy(true); setError(''); setPage(null); setComparison(null);
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
      if (task.current() && returns.get(token)) { setPage(result); setComparison(value); }
    } catch (cause) { if (task.current()) { fence.current.invalidate(); setPage(null); setComparison(null); setBusy(false); setError(messageOf(cause)); } }
    finally { if (task.current()) setBusy(false); }
  }
  return <><PageHeader eyebrow="PORTFÖYE GÜVENLİ DÖNÜŞ" title="Kaynak incelemelerine dön" description="Tam filtre niyetini yeniden hazırlayın; mevcut yetkilerinizle yeni ve sınırlı bir gözlem yapın." />
    <ReturnFilterSummary intent={intent} />
    {error && <Notice error>{error}</Notice>}{scopeError && <Notice error>{scopeError}</Notice>}
    {!prepared || !matching ? <button className="button secondary" disabled={busy} onClick={prepare}>Dönüş filtrelerini uygula ve hazırla</button> : <><p className="small muted">Tam müvekkil ve çalışma alanı tarih filtreleri soldaki portföye uygulandı. Kaynak kayıt tarihleri yukarıdaki niyette ayrı korunur.</p><button className="button secondary" disabled={busy || loading || !!scopeError} onClick={() => void observe(0)}>Aynı filtrelerle yeni portföy gözlemi yap</button></>}
    {comparison && visible && <ReturnReconciliationPanel value={comparison} links={returnComparisonLinks(intent, comparison, token)} renew={captureRenewalHandoff(intent, comparison) ? () => {
      try { const handoff = captureRenewalHandoff(intent, comparison); if (!handoff || !returns.get(token)) throw new Error('Yeni karşılaştırma gözlemi gerekli.');
        const next = returns.put(intent, handoff); window.location.hash = renewalHandoffHref(intent, next)!;
      } catch (cause) { fence.current.invalidate(); setPage(null); setComparison(null); setError(messageOf(cause)); }
    } : undefined} />}
    {page && visible && <PortfolioQueueResults page={page} busy={busy} next={() => void observe(page.coverage.next_offset!)} open={(item, event) => { event.preventDefault(); if (busy) return; try { const next = returns.put(captureReturn(page, item)); window.location.hash = sourceQueueHref(item, next)!; } catch (cause) { setPage(null); setComparison(null); setError(messageOf(cause)); } }} />}
    <p><a className="text-link" href={queueReturnHref()!}>Yeni filtrelerle ayrı kaynak kuyruğu hazırla</a></p>
  </>;
}
export default function PortfolioReturnQueue({ token }: { token: string }) {
  const { returns } = usePortfolio(); const [expired, setExpired] = useState(false);
  useEffect(() => { setExpired(false); const timer = setTimeout(() => setExpired(true), returns.remaining(token)); return () => clearTimeout(timer); }, [token, returns]);
  const intent = returns.get(token);
  if (expired || !intent) return <Notice error>Dönüş bağı yok veya süresi doldu. Tam filtreler tahmin edilmedi; kaynak kuyruğu okunmadı. <a href={queueReturnHref()!}>Yeni kaynak kuyruğunu açıkça hazırla</a></Notice>;
  return <ReturnWorkspace key={token} token={token} intent={intent} />;
}
