import { Detail, Notice } from '../components';
import { formatDate } from '../utils';
import type { ArrivalEventHandoff, compareArrivalEventDestination } from '../workbench/arrivalEventHandoff';
import { compareDestinationIdentities } from '../workbench/comparisonReturn';
const relation = { same: 'Aynı kimlik gözlendi', different: 'Farklı kimlik gözlendi', unknown: 'İlişki doğrulanamadı' };
export default function ArrivalEventDestinationPanel({ handoff, value }: { handoff: ArrivalEventHandoff; value: ReturnType<typeof compareArrivalEventDestination> }) {
  const o = handoff.observation, r = o.handoff.receipt, f = value.fresh, a = compareDestinationIdentities(o.arrival, f);
  const snapshots = [
    ['Önceki hedef', r.destination], ['Önceki kuyruk', o.handoff.queue.fresh], ['Önceki hazırlık', o.handoff.prepared],
    ['Korunan varış', o.arrival], ['Yeni kuyruk', handoff.queue.fresh], ['Yeni hazırlık', handoff.prepared], ['Güncel hedef', f],
  ] as const;
  return <section aria-label="Varışı koruyan geçiş ve tam karar varışı">
    <h3>Varışı koruyarak tam karara geçiş</h3>
    <p>Yeni hazırlıktan hedefe — karar başı: {relation[value.head_relation]}. Analizin son sürümü: {relation[value.version_relation]}. Revizyon: {relation[value.revision_relation]}.</p>
    <p>Korunan varıştan hedefe — karar başı: {relation[a.head_relation]}. Analizin son sürümü: {relation[a.version_relation]}. Revizyon: {relation[a.revision_relation]}.</p>
    <p className="small muted">Yeni hazırlık: {formatDate(handoff.observed_at[1], true)} · Güncel hedef: {formatDate(f.metadata.observed_at, true)}. Ayrı gözlemler atomik bir an değildir; özgün kayıtlar değiştirilmez.</p>
    {(value.head_relation !== 'same' || value.version_relation !== 'same' || value.revision_relation !== 'same') && <Notice>Değişiklik veya belirsizlik gözlendi. Başka karar seçilmedi; onay taşınmadı. Kaynak araçları ayrı ve güncel kontroller gerektirir.</Notice>}
    <Detail title="Korunan varış ve yeni geçişin ayrı kimlikleri">
      <p className="reference-id">Özgün baş: {r.intent.target.head_id || 'Bilinmiyor'} · Özgün son sürüm: {r.intent.target.current_version_id || 'Bilinmiyor'}</p>
      <p className="reference-id">Sabit karar: {r.handoff.selected.id} · Paket: {r.handoff.selected.packet_sha256}</p>
      <p className="reference-id">Kanıt sürümü: {r.handoff.frozen_version_id} · Manifest: {r.handoff.manifest_sha256}</p>
      <p className="reference-id">Özgün geçiş başı: {r.handoff.head.id} · Paket: {r.handoff.head.packet_sha256}</p>
      {snapshots.map(([label, s]) => <div key={label}><h4>{label}</h4><p className="reference-id">Baş: {s.head?.id || 'Bilinmiyor'} · Paket: {s.head?.packet_sha256 || 'Doğrulanamadı'}</p>
        <p className="reference-id">Son sürüm: {s.metadata.analysis.current_version_id || 'Bilinmiyor'} · Revizyon: {s.metadata.analysis.revision}</p></div>)}
    </Detail>
    <p className="small muted">Yalnız özel kimlik metadatası gözlendi. Kaynaklar, hukuki etki veya yeni başa yol doğrulanmadı; bekleyen kabuller tamamlanmadı. Doğrulanmış dönüş özgün varış gözlemini korur; güncel hedef yeni bir tarihsel kayda dönüştürülmez.</p>
  </section>;
}
