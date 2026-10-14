import { useState } from 'react';
import { Field, Notice } from '../../components';
import { formatDate } from '../../utils';
import { READINESS_REASONS, READINESS_STATES, type ReadinessFilters, type ReadinessItem, type ReadinessPage } from './sourceReadinessTypes';

const HISTORY = { unknown: 'Bilinmiyor', unreviewed: 'Karar kaydı yok', changes_requested: 'Değişiklik istendi', reviewed_conditional: 'Koşullu inceleme kaydedildi' };
const OBSERVATION = { unknown: 'Tamamlanmadı', unchanged: 'Seçili özel bağlarda değişiklik gözlenmedi', changed: 'Bağımlılık değişikliği gözlendi' };
export function SourceReviewQueue({ page, busy, load, clear, inspect, renew }: {
  page: ReadinessPage | null; busy: boolean; load: (filters: ReadinessFilters, offset: number) => void;
  clear: () => void; inspect: (id: string) => void; renew: (id: string) => void;
}) {
  const [filters, setFilters] = useState<ReadinessFilters>({ bucket: 'all', date_from: '', date_to: '' });
  const edit = (values: Partial<ReadinessFilters>) => { clear(); setFilters(old => ({ ...old, ...values })); };
  return <section className="source-review-queue" aria-label="Kaynak inceleme kuyruğu">
    <h4>Kaynak inceleme kuyruğu</h4>
    <p>Bu analizin kayıtları için sınırlı özel gözlem. Saklanan karar, güncel kamu kaynağı izni veya hukuki hazır olma durumu değildir. Özgün pasajlar yalnızca açık kontrol sırasında okunur.</p>
    <form className="authority-context-form" onSubmit={event => { event.preventDefault(); load(filters, 0); }}>
      <fieldset disabled={busy}><legend>Kayıt tarihine göre daralt · Türkiye saati</legend>
        <Field label="İnceleme kuyruğu filtresi">{id => <select id={id} value={filters.bucket} onChange={event => edit({ bucket: event.target.value as ReadinessFilters['bucket'] })}>
          <option value="all">Tüm kayıtlar</option><option value="action_required">Karar, yenileme veya düzeltme bekleyen</option></select>}</Field>
        <Field label="Kaynak kayıt tarihi başlangıcı">{id => <input id={id} type="date" value={filters.date_from} onChange={event => edit({ date_from: event.target.value })} />}</Field>
        <Field label="Kaynak kayıt tarihi bitişi">{id => <input id={id} type="date" value={filters.date_to} min={filters.date_from || undefined} onChange={event => edit({ date_to: event.target.value })} />}</Field>
        <button type="submit" className="button secondary">İnceleme kuyruğunu güncelle</button>
      </fieldset>
    </form>
    {page && <>
      <p className="small muted">Gözlem: {formatDate(page.observed_at, true)} · Bu pencerede {page.coverage.scanned_count} kayıt gözlendi, {page.coverage.returned_count} kayıt gösteriliyor.
        Öncelik yalnızca bu pencereye aittir; toplam kapsam bilinmiyor. Kaynaklar kontrol edilmedi.</p>
      {!page.items.length && <Notice>Bu pencerede filtreye uygun kayıt yok. Tüm incelemelerin tamamlandığı anlamına gelmez.</Notice>}
      {page.items.map(item => <section className="authority-candidate" key={item.id}>
        <h4>{READINESS_STATES[item.state]}</h4><p className="small">Kayıt: {formatDate(item.recorded_at, true)}</p>
        <SourceReviewSummary item={item} />
        <div className="practice-record-actions"><button className="text-button" disabled={busy} onClick={() => inspect(item.id)}>Kaynak ve karar bağlarını kontrol et</button>
          <button className="text-button" disabled={busy || item.state === 'pending' || item.state === 'unavailable'} onClick={() => renew(item.id)}>Yeni bağlamı açıkça hazırla</button></div>
        <p className="small reference-id">{item.id} {item.version_id ? `· ${item.version_id}` : ''}</p>
      </section>)}
      {page.coverage.pagination_limit_reached && <Notice>Sayfalama sınırına ulaşıldı. Kayıt tarihini daraltarak yeniden gözlemleyin.</Notice>}
      {page.coverage.has_more && page.coverage.next_offset !== null && <button className="text-button" disabled={busy} onClick={() => load(filters, page.coverage.next_offset!)}>Sonraki sınırlı pencereyi getir</button>}
    </>}
  </section>;
}

export function SourceReviewSummary({ item }: { item: ReadinessItem }) {
  return <>
    <p><strong>Saklanan karar:</strong> {HISTORY[item.historical_review.state]} · Tarihsel kayıt; güncel uygunluk belirlemez.</p>
    <p><strong>Özel gözlem:</strong> {OBSERVATION[item.private_observation.state]}</p>
    <p><strong>Kamu kaynağı:</strong> Kontrol edilmedi · Hukuki hazır olma belirlenmedi.</p>
    {!!item.private_observation.reasons.length && <ul>{item.private_observation.reasons.map(reason => <li key={reason}>{READINESS_REASONS[reason]}</li>)}</ul>}
  </>;
}
