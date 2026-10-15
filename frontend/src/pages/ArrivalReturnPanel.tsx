import { Detail, Notice } from '../components';
import { formatDate } from '../utils';
import type { ArrivalReturn } from '../workbench/arrivalReturn';
import type { ComparisonQueueReconciliation } from '../workbench/comparisonReturn';
import ComparisonEventArrivalPanel from './ComparisonEventArrivalPanel';
import { compareDestinationIdentities } from '../workbench/comparisonReturn';

const relation = { same: 'Aynı kimlik gözlendi', different: 'Farklı kimlik gözlendi', unknown: 'İlişki doğrulanamadı' };
const admission = (value: string) => value === 'complete' ? 'Tamamlandı' : value === 'pending' ? 'Bekliyor' : 'Doğrulanamadı';
export default function ArrivalReturnPanel({ observation, value }: { observation: ArrivalReturn; value: ComparisonQueueReconciliation }) {
  if (value.state === 'not_observed') return <Notice>Seçilen kayıt bu pencerede gözlenmedi. Korunan varış ayrıntıları açılmadı; güncel erişim veya ilişki kurulmadı.</Notice>;
  const a = observation.arrival, f = value.fresh;
  return <section aria-label="Korunan varış ve yeni kuyruk gözlemi">
    <h3>Varıştan portföye dönüş</h3>
    <p>Varıştan yeni kuyruğa — karar başı: {relation[value.head_relation]}. Analizin son sürümü: {relation[value.version_relation]}. Revizyon: {relation[value.revision_relation]}.</p>
    <p className="small muted">Korunan varış: {formatDate(a.metadata.observed_at, true)} · Yeni kuyruk: {formatDate(value.queue_observed_at, true)} · Tam kayıt: {formatDate(f.metadata.observed_at, true)}. Ayrı gözlemler tek atomik an değildir; önceki onay taşınmaz.</p>
    <Detail title="Varış ve yeni kuyruğun ayrı kimlik gözlemleri">
      <h4>Korunan tarihsel varış — güncel kabul değildir</h4>
      <ComparisonEventArrivalPanel handoff={observation.handoff} value={{ fresh: a, ...compareDestinationIdentities(observation.handoff.prepared, a) }} />
      <h4>Yeni kuyrukta ayrıca gözlenen tam kayıt</h4>
      <p className="reference-id">Yeni gözlenen baş: {f.head?.id || 'Bilinmiyor'} · Paket: {f.head?.packet_sha256 || 'Doğrulanamadı'}</p>
      <p className="reference-id">Son sürüm: {f.metadata.analysis.current_version_id || 'Bilinmiyor'} · Revizyon: {f.metadata.analysis.revision}</p>
      <p>Kabul gözlemleri — bağlam: {admission(f.metadata.admission.context_state)}; seçilen karar: {admission(f.selected.admission)}; baş: {admission(f.metadata.admission.review_state)}. Bekleyen kabul tamamlanmadı.</p>
    </Detail>
    <p className="small muted">Sabit karar, kanıt ve özgün filtreler korundu. Yalnızca özel kimlik metadatası karşılaştırıldı. Kaynak içeriği, hukuki etki veya yeni başa bağlantı doğrulanmadı; başka karar seçilmedi.</p>
  </section>;
}
