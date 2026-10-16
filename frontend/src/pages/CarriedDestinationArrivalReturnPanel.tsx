import { Detail, Notice } from '../components';
import { formatDate } from '../utils';
import type { CarriedDestinationArrivalReturn } from '../workbench/carriedDestinationArrivalReturn';
import { compareDestinationIdentities, type ComparisonQueueReconciliation } from '../workbench/comparisonReturn';
const relation = { same: 'Aynı kimlik gözlendi', different: 'Farklı kimlik gözlendi', unknown: 'İlişki doğrulanamadı' };
const admission = (v: string) => v === 'complete' ? 'Tamamlandı' : v === 'pending' ? 'Bekliyor' : 'Doğrulanamadı';
export default function CarriedDestinationArrivalReturnPanel({ observation, value }: { observation: CarriedDestinationArrivalReturn; value: ComparisonQueueReconciliation }) {
  if (value.state === 'not_observed') return <Notice>Seçilen kayıt bu pencerede gözlenmedi. Korunan hedef varışı ayrıntıları açılmadı; güncel erişim veya ilişki kurulmadı.</Notice>;
  const latest = observation.handoff, d = latest.observation, h = d.handoff, c = h.observation, o = c.handoff.observation, old = o.handoff.observation, r = old.handoff.receipt, f = value.fresh;
  const a = compareDestinationIdentities(d.destination, f), p = compareDestinationIdentities(latest.prepared, f), prior = compareDestinationIdentities(c.arrival, f);
  const snapshots = [['Önceki hedef', r.destination], ['Özgün varış', old.arrival], ['İlk ileri geçiş kuyruğu', o.handoff.queue.fresh],
    ['İlk ileri geçiş hazırlığı', o.handoff.prepared], ['Özgün ileri hedef', o.destination], ['Taşıyan kuyruk', c.handoff.queue.fresh],
    ['Taşıyan hazırlık', c.handoff.prepared], ['Özgün taşınan varış', c.arrival], ['Son geçiş kuyruğu', h.queue.fresh],
    ['Son geçiş hazırlığı', h.prepared], ['Özgün taşınan hedef', d.destination], ['Yeni geçiş kuyruğu', latest.queue.fresh], ['Yeni geçiş hazırlığı', latest.prepared],
    ['Korunan hedef varışı', observation.arrival], ['Yeni kuyrukta gözlenen tam kayıt', f]] as const;
  return <section aria-label="Korunan hedef varışı ve yeni kuyruk gözlemi">
    <h3>Hedef varışından portföye dönüş</h3>
    <p>Hedef varışından yeni kuyruğa — karar başı: {relation[value.head_relation]}. Analizin son sürümü: {relation[value.version_relation]}. Revizyon: {relation[value.revision_relation]}.</p>
    <p className="small muted">Korunan hedef: {formatDate(observation.arrival.metadata.observed_at, true)} · Yeni kuyruk: {formatDate(value.queue_observed_at, true)} · Tam kayıt: {formatDate(f.metadata.observed_at, true)}. Ayrı gözlemler atomik bir an değildir; önceki onay taşınmaz.</p>
    <Detail title="Hedef varışı, özgün hedef ve yeni kuyruğun ayrı kimlikleri">
      <p>Özgün taşınan hedeften yeni kuyruğa — baş: {relation[a.head_relation]}; sürüm: {relation[a.version_relation]}; revizyon: {relation[a.revision_relation]}.</p>
      <p>Son hazırlıktan yeni kuyruğa — baş: {relation[p.head_relation]}; sürüm: {relation[p.version_relation]}; revizyon: {relation[p.revision_relation]}.</p>
      <p>Özgün taşınan varıştan yeni kuyruğa — baş: {relation[prior.head_relation]}; sürüm: {relation[prior.version_relation]}; revizyon: {relation[prior.revision_relation]}.</p>
      <p className="reference-id">Özgün baş: {r.intent.target.head_id || 'Bilinmiyor'} · Özgün son sürüm: {r.intent.target.current_version_id || 'Bilinmiyor'}</p>
      <p className="reference-id">Sabit karar: {r.handoff.selected.id} · Paket: {r.handoff.selected.packet_sha256}</p>
      <p className="reference-id">Kanıt sürümü: {r.handoff.frozen_version_id} · Manifest: {r.handoff.manifest_sha256}</p>
      {snapshots.map(([label, s]) => <div key={label}><h4>{label}</h4><p className="reference-id">Baş: {s.head?.id || 'Bilinmiyor'} · Paket: {s.head?.packet_sha256 || 'Doğrulanamadı'}</p>
        <p className="reference-id">Son sürüm: {s.metadata.analysis.current_version_id || 'Bilinmiyor'} · Revizyon: {s.metadata.analysis.revision}</p>
        <p>Kabuller — bağlam: {admission(s.metadata.admission.context_state)}; seçilen karar: {admission(s.selected.admission)}; baş: {admission(s.metadata.admission.review_state)}.</p></div>)}
    </Detail>
    <p className="small muted">Özgün filtreler, sabit kanıt ve bağımsız inceleme geçmişi korundu. Yalnız özel kimlik metadatası karşılaştırıldı; kaynaklar, hukuki etki veya yeni başa yol doğrulanmadı. Bekleyen kabul tamamlanmadı, başka karar seçilmedi.</p>
  </section>;
}
