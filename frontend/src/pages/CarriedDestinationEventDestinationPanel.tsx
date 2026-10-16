import { Detail, Notice } from '../components';
import { formatDate } from '../utils';
import type { CarriedDestinationEventHandoff, compareCarriedDestinationEventDestination } from '../workbench/carriedDestinationEventHandoff';
import { compareDestinationIdentities } from '../workbench/comparisonReturn';
const relation = { same: 'Aynı kimlik gözlendi', different: 'Farklı kimlik gözlendi', unknown: 'İlişki doğrulanamadı' };
const admission = (v: string) => v === 'complete' ? 'Tamamlandı' : v === 'pending' ? 'Bekliyor' : 'Doğrulanamadı';
export default function CarriedDestinationEventDestinationPanel({ handoff, value }: { handoff: CarriedDestinationEventHandoff; value: ReturnType<typeof compareCarriedDestinationEventDestination> }) {
  const retained = handoff.observation, carried = retained.handoff.observation, o = carried.handoff.observation, arrival = o.handoff.observation, r = arrival.handoff.receipt, f = value.fresh;
  const c = compareDestinationIdentities(retained.destination, f), d = compareDestinationIdentities(o.destination, f);
  const snapshots = [['Önceki hedef', r.destination], ['Özgün varış', arrival.arrival], ['İlk ileri geçiş kuyruğu', o.handoff.queue.fresh],
    ['İlk ileri geçiş hazırlığı', o.handoff.prepared], ['Özgün ileri hedef', o.destination], ['Taşıyan kuyruk', carried.handoff.queue.fresh],
    ['Taşıyan hazırlık', carried.handoff.prepared], ['Özgün taşınan varış', carried.arrival], ['Önceki geçiş kuyruğu', retained.handoff.queue.fresh],
    ['Önceki geçiş hazırlığı', retained.handoff.prepared], ['Korunan taşınan hedef', retained.destination], ['Yeni kuyruk', handoff.queue.fresh],
    ['Yeni hazırlık', handoff.prepared], ['Güncel varış', f]] as const;
  return <section aria-label="Taşınan hedefi koruyan geçiş ve tam karar varışı">
    <h3>Taşınan hedefi koruyarak tam karara geçiş</h3>
    <p>Yeni hazırlıktan varışa — karar başı: {relation[value.head_relation]}. Analizin son sürümü: {relation[value.version_relation]}. Revizyon: {relation[value.revision_relation]}.</p>
    <p>Korunan taşınan hedeften yeni varışa — karar başı: {relation[c.head_relation]}. Analizin son sürümü: {relation[c.version_relation]}. Revizyon: {relation[c.revision_relation]}.</p>
    <p className="small muted">Yeni hazırlık: {formatDate(handoff.observed_at[1], true)} · Güncel varış: {formatDate(f.metadata.observed_at, true)}. Ayrı gözlemler atomik bir an değildir; önceki kayıtlar değiştirilmez.</p>
    {(value.head_relation !== 'same' || value.version_relation !== 'same' || value.revision_relation !== 'same') && <Notice>Değişiklik veya belirsizlik gözlendi. Başka karar seçilmedi; onay taşınmadı. Kaynak araçları ayrı ve güncel kontroller gerektirir.</Notice>}
    <Detail title="Korunan taşınan hedef ve yeni geçişin ayrı kimlikleri">
      <p>Özgün ileri hedeften yeni varışa — baş: {relation[d.head_relation]}; sürüm: {relation[d.version_relation]}; revizyon: {relation[d.revision_relation]}.</p>
      <p className="reference-id">Özgün baş: {r.intent.target.head_id || 'Bilinmiyor'} · Özgün son sürüm: {r.intent.target.current_version_id || 'Bilinmiyor'}</p>
      <p className="reference-id">Sabit karar: {r.handoff.selected.id} · Paket: {r.handoff.selected.packet_sha256}</p>
      <p className="reference-id">Kanıt sürümü: {r.handoff.frozen_version_id} · Manifest: {r.handoff.manifest_sha256}</p>
      <p className="reference-id">Özgün geçiş başı: {r.handoff.head.id} · Paket: {r.handoff.head.packet_sha256}</p>
      {snapshots.map(([label, s]) => <div key={label}><h4>{label}</h4><p className="reference-id">Baş: {s.head?.id || 'Bilinmiyor'} · Paket: {s.head?.packet_sha256 || 'Doğrulanamadı'}</p>
        <p className="reference-id">Son sürüm: {s.metadata.analysis.current_version_id || 'Bilinmiyor'} · Revizyon: {s.metadata.analysis.revision}</p><p>Kabuller — bağlam: {admission(s.metadata.admission.context_state)}; seçilen karar: {admission(s.selected.admission)}; baş: {admission(s.metadata.admission.review_state)}.</p></div>)}
    </Detail>
    <p className="small muted">Yalnız özel kimlik metadatası gözlendi. Kaynaklar, hukuki etki veya yeni başa yol doğrulanmadı; bekleyen kabuller tamamlanmadı. Doğrulanmış dönüş özgün taşınan hedefi değişmeden korur. Bu varış dönüşte yeni bir kayıt olarak saklanmaz ve önceki kayıtların yerine geçmez.</p>
  </section>;
}
