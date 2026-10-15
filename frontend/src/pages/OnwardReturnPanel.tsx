import { Detail, Notice } from '../components';
import { formatDate } from '../utils';
import type { OnwardReturn } from '../workbench/onwardReturn';
import { compareDestinationIdentities, type ComparisonQueueReconciliation } from '../workbench/comparisonReturn';

const relation = { same: 'Aynı kimlik gözlendi', different: 'Farklı kimlik gözlendi', unknown: 'İlişki doğrulanamadı' };
const admission = (v: string) => v === 'complete' ? 'Tamamlandı' : v === 'pending' ? 'Bekliyor' : 'Doğrulanamadı';
export default function OnwardReturnPanel({ observation, value, prepare, busy }: { observation: OnwardReturn; value: ComparisonQueueReconciliation; prepare?: () => void; busy?: boolean }) {
  if (value.state === 'not_observed') return <Notice>Seçilen kayıt bu pencerede gözlenmedi. Korunan ileri hedef ayrıntıları açılmadı; güncel erişim veya ilişki kurulmadı.</Notice>;
  const h = observation.handoff, d = observation.destination, f = value.fresh, r = h.observation.handoff.receipt;
  const a = compareDestinationIdentities(h.observation.arrival, f), p = compareDestinationIdentities(h.prepared, f);
  const snapshots = [['Önceki hedef', r.destination], ['Özgün varış', h.observation.arrival], ['İleri geçiş kuyruğu', h.queue.fresh],
    ['İleri geçiş hazırlığı', h.prepared], ['Korunan ileri hedef', d], ['Yeni kuyrukta gözlenen tam kayıt', f]] as const;
  return <section aria-label="Korunan ileri hedef ve yeni kuyruk gözlemi">
    <h3>İleri hedeften portföye dönüş</h3>
    <p>İleri hedeften yeni kuyruğa — karar başı: {relation[value.head_relation]}. Analizin son sürümü: {relation[value.version_relation]}. Revizyon: {relation[value.revision_relation]}.</p>
    <p className="small muted">Korunan hedef: {formatDate(d.metadata.observed_at, true)} · Yeni kuyruk: {formatDate(value.queue_observed_at, true)} · Tam kayıt: {formatDate(f.metadata.observed_at, true)}. Ayrı gözlemler atomik bir an değildir; önceki onay taşınmaz.</p>
    <Detail title="İleri hedef, özgün varış ve yeni kuyruğun ayrı kimlikleri">
      <p>Özgün varıştan yeni kuyruğa — baş: {relation[a.head_relation]}; sürüm: {relation[a.version_relation]}; revizyon: {relation[a.revision_relation]}.</p>
      <p>İleri hazırlıktan yeni kuyruğa — baş: {relation[p.head_relation]}; sürüm: {relation[p.version_relation]}; revizyon: {relation[p.revision_relation]}.</p>
      <p className="reference-id">Özgün baş: {r.intent.target.head_id || 'Bilinmiyor'} · Özgün son sürüm: {r.intent.target.current_version_id || 'Bilinmiyor'}</p>
      <p className="reference-id">Sabit karar: {r.handoff.selected.id} · Paket: {r.handoff.selected.packet_sha256}</p>
      <p className="reference-id">Kanıt sürümü: {r.handoff.frozen_version_id} · Manifest: {r.handoff.manifest_sha256}</p>
      {snapshots.map(([label, s]) => <div key={label}><h4>{label}</h4><p className="reference-id">Baş: {s.head?.id || 'Bilinmiyor'} · Paket: {s.head?.packet_sha256 || 'Doğrulanamadı'}</p>
        <p className="reference-id">Son sürüm: {s.metadata.analysis.current_version_id || 'Bilinmiyor'} · Revizyon: {s.metadata.analysis.revision}</p>
        <p>Kabuller — bağlam: {admission(s.metadata.admission.context_state)}; seçilen karar: {admission(s.selected.admission)}; baş: {admission(s.metadata.admission.review_state)}.</p></div>)}
    </Detail>
    <p className="small muted">Özgün filtreler, sabit kanıt ve tarihsel inceleme korundu. Yalnız özel kimlik metadatası karşılaştırıldı; kaynaklar, hukuki etki veya yeni başa yol doğrulanmadı. Bekleyen kabul tamamlanmadı, başka karar seçilmedi.</p>
    {prepare && <button className="button secondary" disabled={busy} onClick={prepare}>İleri dönüşü koruyarak tam karar geçişini doğrula</button>}
  </section>;
}
