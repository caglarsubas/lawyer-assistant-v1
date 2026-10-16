import { Detail, Notice } from '../components';
import { formatDate } from '../utils';
import type { HandoffDestinationArrivalReturn } from '../workbench/handoffDestinationArrivalReturn';
import { compareDestinationIdentities, type ComparisonQueueReconciliation } from '../workbench/comparisonReturn';
const relation = { same: 'Aynı kimlik gözlendi', different: 'Farklı kimlik gözlendi', unknown: 'İlişki doğrulanamadı' };
const admission = (v: string) => v === 'complete' ? 'Tamamlandı' : v === 'pending' ? 'Bekliyor' : 'Doğrulanamadı';
export default function HandoffDestinationArrivalReturnPanel({ observation, value, prepare, busy = false }: { prepare?: () => void; busy?: boolean; observation: HandoffDestinationArrivalReturn; value: ComparisonQueueReconciliation }) {
  if (value.state === 'not_observed') return <Notice>Seçilen kayıt bu pencerede gözlenmedi. Geçiş varışı ayrıntıları açılmadı; güncel erişim veya ilişki kurulmadı.</Notice>;
  const h = observation.handoff, f = value.fresh, selected = h.prepared.selected;
  const p = compareDestinationIdentities(h.prepared, f), a = compareDestinationIdentities(h.observation.destination, f);
  const snapshots = [['Korunan geçiş hedefi', h.observation.destination], ['Yeni geçiş kuyruğu', h.queue.fresh], ['Yeni geçiş hazırlığı', h.prepared],
    ['Ayrı saklanan geçiş varışı', observation.arrival], ['Yeni kuyrukta gözlenen tam kayıt', f]] as const;
  return <section aria-label="Korunan geçiş varışı ve yeni kuyruk gözlemi">
    <h3>Geçiş varışından portföye dönüş</h3>
    <p>Geçiş varışından yeni kuyruğa — karar başı: {relation[value.head_relation]}. Analizin son sürümü: {relation[value.version_relation]}. Revizyon: {relation[value.revision_relation]}.</p>
    <p className="small muted">Saklanan varış: {formatDate(observation.arrival.metadata.observed_at, true)} · Yeni kuyruk: {formatDate(value.queue_observed_at, true)} · Tam kayıt: {formatDate(f.metadata.observed_at, true)}. Ayrı gözlemler atomik bir an değildir; önceki onay taşınmaz.</p>
    <Detail title="Geçiş varışı, hazırlık ve yeni kuyruğun ayrı kimlikleri">
      <p>Geçiş hazırlığından yeni kuyruğa — baş: {relation[p.head_relation]}; sürüm: {relation[p.version_relation]}; revizyon: {relation[p.revision_relation]}.</p>
      <p>Korunan geçiş hedefinden yeni kuyruğa — baş: {relation[a.head_relation]}; sürüm: {relation[a.version_relation]}; revizyon: {relation[a.revision_relation]}.</p>
      <p className="reference-id">Sabit karar: {selected.id} · Paket: {selected.packet_sha256}</p>
      <p className="reference-id">Kanıt sürümü: {observation.arrival.metadata.context.version_id} · Manifest: {observation.arrival.metadata.context.manifest_sha256}</p>
      {snapshots.map(([label, s]) => <div key={label}><h4>{label}</h4><p className="reference-id">Baş: {s.head?.id || 'Bilinmiyor'} · Paket: {s.head?.packet_sha256 || 'Doğrulanamadı'}</p>
        <p className="reference-id">Son sürüm: {s.metadata.analysis.current_version_id || 'Bilinmiyor'} · Revizyon: {s.metadata.analysis.revision}</p>
        <p>Kabuller — bağlam: {admission(s.metadata.admission.context_state)}; seçilen karar: {admission(s.selected.admission)}; baş: {admission(s.metadata.admission.review_state)}.</p></div>)}
    </Detail>
    {prepare && <button className="button secondary" disabled={busy} onClick={prepare}>Geçiş varışını koruyarak tam seçilen karara geçişi hazırla</button>}
    <p className="small muted">Özgün müşteri ve tarih filtreleri, sabit kanıt ve bağımsız inceleme geçmişi değişmeden korundu. Önceki gözlemler yukarıdaki ayrı karşılaştırmalarda kalır. Yalnız özel kimlik metadatası karşılaştırıldı; kaynaklar, hukuki etki veya yeni başa yol doğrulanmadı. Bekleyen kabul tamamlanmadı, başka karar seçilmedi. Bu ek varışı taşıyamayan önceki geçiş hazırlığı kapalıdır.</p>
  </section>;
}
