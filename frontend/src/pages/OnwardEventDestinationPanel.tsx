import { Detail, Notice } from '../components';
import { formatDate } from '../utils';
import type { OnwardEventHandoff, compareOnwardEventDestination } from '../workbench/onwardEventHandoff';
import { compareDestinationIdentities } from '../workbench/comparisonReturn';
const relation = { same: 'Aynı kimlik gözlendi', different: 'Farklı kimlik gözlendi', unknown: 'İlişki doğrulanamadı' };
const admission = (v: string) => v === 'complete' ? 'Tamamlandı' : v === 'pending' ? 'Bekliyor' : 'Doğrulanamadı';
export default function OnwardEventDestinationPanel({ handoff, value }: { handoff: OnwardEventHandoff; value: ReturnType<typeof compareOnwardEventDestination> }) {
  const o = handoff.observation, old = o.handoff, arrival = old.observation, r = arrival.handoff.receipt, f = value.fresh;
  const d = compareDestinationIdentities(o.destination, f), a = compareDestinationIdentities(arrival.arrival, f);
  const snapshots = [['Önceki hedef', r.destination], ['Önceki kuyruk', arrival.handoff.queue.fresh], ['Önceki hazırlık', arrival.handoff.prepared],
    ['Özgün varış', arrival.arrival], ['İleri geçiş kuyruğu', old.queue.fresh], ['İleri geçiş hazırlığı', old.prepared],
    ['Korunan ileri hedef', o.destination], ['Yeni kuyruk', handoff.queue.fresh], ['Yeni hazırlık', handoff.prepared], ['Güncel varış', f]] as const;
  return <section aria-label="İleri dönüşü koruyan geçiş ve tam karar varışı">
    <h3>İleri dönüşü koruyarak tam karara geçiş</h3>
    <p>Yeni hazırlıktan varışa — karar başı: {relation[value.head_relation]}. Analizin son sürümü: {relation[value.version_relation]}. Revizyon: {relation[value.revision_relation]}.</p>
    <p>Korunan ileri hedeften varışa — karar başı: {relation[d.head_relation]}. Analizin son sürümü: {relation[d.version_relation]}. Revizyon: {relation[d.revision_relation]}.</p>
    <p className="small muted">Yeni hazırlık: {formatDate(handoff.observed_at[1], true)} · Güncel varış: {formatDate(f.metadata.observed_at, true)}. Ayrı gözlemler atomik bir an değildir; önceki kayıtlar değiştirilmez.</p>
    {(value.head_relation !== 'same' || value.version_relation !== 'same' || value.revision_relation !== 'same') && <Notice>Değişiklik veya belirsizlik gözlendi. Başka karar seçilmedi; onay taşınmadı. Kaynak araçları ayrı ve güncel kontroller gerektirir.</Notice>}
    <Detail title="Korunan ileri dönüş ve yeni geçişin ayrı kimlikleri">
      <p>Özgün varıştan yeni varışa — baş: {relation[a.head_relation]}; sürüm: {relation[a.version_relation]}; revizyon: {relation[a.revision_relation]}.</p>
      <p className="reference-id">Özgün baş: {r.intent.target.head_id || 'Bilinmiyor'} · Özgün son sürüm: {r.intent.target.current_version_id || 'Bilinmiyor'}</p>
      <p className="reference-id">Sabit karar: {r.handoff.selected.id} · Paket: {r.handoff.selected.packet_sha256}</p>
      <p className="reference-id">Kanıt sürümü: {r.handoff.frozen_version_id} · Manifest: {r.handoff.manifest_sha256}</p>
      <p className="reference-id">Özgün geçiş başı: {r.handoff.head.id} · Paket: {r.handoff.head.packet_sha256}</p>
      {snapshots.map(([label, s]) => <div key={label}><h4>{label}</h4><p className="reference-id">Baş: {s.head?.id || 'Bilinmiyor'} · Paket: {s.head?.packet_sha256 || 'Doğrulanamadı'}</p>
        <p className="reference-id">Son sürüm: {s.metadata.analysis.current_version_id || 'Bilinmiyor'} · Revizyon: {s.metadata.analysis.revision}</p><p>Kabuller — bağlam: {admission(s.metadata.admission.context_state)}; seçilen karar: {admission(s.selected.admission)}; baş: {admission(s.metadata.admission.review_state)}.</p></div>)}
    </Detail>
    <p className="small muted">Yalnız özel kimlik metadatası gözlendi. Kaynaklar, hukuki etki veya yeni başa yol doğrulanmadı; bekleyen kabuller tamamlanmadı. Doğrulanmış dönüş özgün ileri dönüşü değişmeden korur; bu varış ayrı bir gözlem olarak saklanır ve önceki kayıtların yerine geçmez.</p>
  </section>;
}
