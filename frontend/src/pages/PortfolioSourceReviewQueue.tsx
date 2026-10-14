import { useEffect, useRef, useState, type MouseEvent } from 'react';
import { request } from '../api';
import { Detail, Field, Notice, PageHeader } from '../components';
import type { PortfolioFilters } from '../types';
import { formatDate, messageOf } from '../utils';
import { usePortfolio, workspaceQuery } from '../workbench/portfolio';
import { SourceReviewSummary } from './matter/SourceReviewQueue';
import { READINESS_STATES } from './matter/sourceReadinessTypes';
import { SourceReadFence } from './matter/sourceReviewTypes';
import PortfolioReturnQueue from './PortfolioReturnQueue';
import { captureReturn } from '../workbench/portfolioReturn';
import { queueFilters, queueQuery, sourceQueueHref, verifyPortfolioQueue, type PortfolioQueuePage, type QueueFilters } from './portfolioSourceQueueTypes';

export function PortfolioQueueResults({ page, busy, next, open }: { page: PortfolioQueuePage; busy: boolean; next: () => void; open?: (item: PortfolioQueuePage['items'][number], event: MouseEvent<HTMLAnchorElement>) => void }) {
  return <section aria-label="Portföy kaynak inceleme sonuçları">
    <p className="small muted">Gözlem: {formatDate(page.observed_at, true)} · Bu pencerede {page.coverage.scanned_count} kayıt gözlendi, {page.coverage.returned_count} kayıt gösteriliyor.
      Öncelik yalnızca bu pencereye aittir; toplam kapsam bilinmiyor. Kamu kaynakları kontrol edilmedi.</p>
    {!page.items.length && <Notice>Bu pencerede filtreye uygun kayıt yok. Tüm portföyün incelendiği veya incelemelerin tamamlandığı anlamına gelmez.</Notice>}
    <div className="work-register">{page.items.map(item => <article key={item.id}><div>
      <p className="small-label">{item.matter_title}</p><h3>{READINESS_STATES[item.state]}</h3><p className="small">Kayıt: {formatDate(item.recorded_at, true)}</p>
      <SourceReviewSummary item={item} />
      <Detail title="Kaynak kaydının kimlikleri"><p className="small reference-id">Analiz: {item.analysis_id || 'Doğrulanamadı'}</p><p className="small reference-id">Bağlam: {item.id}</p><p className="small reference-id">Sürüm: {item.version_id || 'Doğrulanamadı'}</p></Detail>
    </div>{sourceQueueHref(item) ? <a className="button secondary" href={sourceQueueHref(item)!} onClick={event => open?.(item, event)}>Tam kaynak bağlamını aç</a> : <Notice>Analiz bağı doğrulanamadı. Bu kayıttan inceleme açılamaz.</Notice>}</article>)}</div>
    {page.coverage.pagination_limit_reached && <Notice>Sayfalama sınırına ulaşıldı. Müvekkil veya kaynak kayıt tarihini daraltıp yeniden gözlemleyin.</Notice>}
    {page.coverage.has_more && page.coverage.next_offset !== null && <button className="button secondary" disabled={busy} onClick={next}>Sonraki sınırlı portföy penceresini getir</button>}
  </section>;
}
function QueueWorkspace({ portfolio, filters, setFilters, blocked, error: scopeError }: { portfolio: PortfolioFilters; filters: QueueFilters;
  setFilters: (update: (old: QueueFilters) => QueueFilters) => void; blocked: boolean; error: string }) {
  const { returns } = usePortfolio();
  const [page, setPage] = useState<PortfolioQueuePage | null>(null); const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  const fence = useRef(new SourceReadFence()); useEffect(() => { const gate = fence.current; return () => gate.invalidate(); }, []);
  useEffect(() => { if (blocked) { fence.current.invalidate(); setPage(null); setBusy(false); setError(''); } }, [blocked]);
  function edit(values: Partial<QueueFilters>) { fence.current.invalidate(); setPage(null); setError(''); setBusy(false); setFilters(old => ({ ...old, ...values })); }
  async function load(offset: number) {
    if (blocked) return; const task = fence.current.begin(); setPage(null); setBusy(true); setError(''); const expected = queueFilters(portfolio, filters);
    try { const result = await request<PortfolioQueuePage>(`/work/source-reviews?${queueQuery(expected, offset)}`, { signal: task.signal });
      verifyPortfolioQueue(result, expected, offset); if (task.current()) setPage(result);
    } catch (cause) { if (task.current()) { fence.current.invalidate(); setPage(null); setBusy(false); setError(messageOf(cause)); } }
    finally { if (task.current()) setBusy(false); }
  }
  return <><PageHeader eyebrow="PORTFÖY ÇALIŞMASI" title="Kaynak incelemeleri" description="Mevcut erişiminizdeki çalışma alanlarının kaynak kararları, yenileme gereksinimleri ve sınırlı özel gözlemler." />
    <p>Soldaki müvekkil ve çalışma alanı tarih filtreleri uygulanır. Birden fazla müvekkil seçimi, seçilenlerden en az biriyle ilişkili alanları getirir; erişim ayrıca doğrulanır.</p>
    <p className="small muted">Aşağıdaki tarihler kaynak bağlamının kayıt günüdür ve Türkiye saatini kullanır. Çalışma alanı, olay ve hukuki süre tarihleri ayrı kalır. Saklanan olumlu karar güncel kamu kaynağı izni değildir.</p>
    {scopeError && <Notice error>{scopeError}</Notice>}{error && <Notice error>{error}</Notice>}
    <form onSubmit={event => { event.preventDefault(); void load(0); }} className="authority-context-form">
      <fieldset disabled={busy || blocked}><legend>Portföy kaynak kuyruğunu daralt</legend><div className="form-grid">
        <Field label="Portföy kaynak inceleme durumu" className="span-full">{id => <select id={id} value={filters.bucket} onChange={event => edit({ bucket: event.target.value as QueueFilters['bucket'] })}><option value="all">Tüm kayıtlar</option><option value="action_required">Karar, yenileme veya düzeltme bekleyen</option></select>}</Field>
        <Field label="Portföy kaynak kayıt tarihi başlangıcı">{id => <input id={id} type="date" value={filters.source_date_from} onChange={event => edit({ source_date_from: event.target.value })} />}</Field>
        <Field label="Portföy kaynak kayıt tarihi bitişi">{id => <input id={id} type="date" min={filters.source_date_from || undefined} value={filters.source_date_to} onChange={event => edit({ source_date_to: event.target.value })} />}</Field>
      </div><button type="submit" className="button secondary">Portföy kaynak kuyruğunu güncelle</button></fieldset>
    </form>
    {page && !blocked && <PortfolioQueueResults page={page} open={(item, event) => { event.preventDefault(); if (busy) return; try { const token = returns.put(captureReturn(page, item)); window.location.hash = sourceQueueHref(item, token)!; } catch (cause) { setPage(null); setError(messageOf(cause)); } }} busy={busy} next={() => void load(page.coverage.next_offset!)} />}
  </>;
}
export default function PortfolioSourceReviewQueue({ returnToken }: { returnToken?: string }) {
  const { filters, revision, loading, error } = usePortfolio();
  const [sourceFilters, setSourceFilters] = useState<QueueFilters>({ bucket: 'all', source_date_from: '', source_date_to: '' });
  if (returnToken) return <PortfolioReturnQueue token={returnToken} />;
  return <QueueWorkspace key={`${workspaceQuery(filters)}:${revision}`} portfolio={filters} filters={sourceFilters}
    setFilters={setSourceFilters} blocked={loading || !!error} error={error} />;
}
