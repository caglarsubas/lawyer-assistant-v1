import { Detail, Notice } from '../components';
import { formatDate } from '../utils';
import { compareDestinationIdentities } from '../workbench/comparisonReturn';
import { compareHandoffArrivalDestinationArrivalEvent, type HandoffArrivalDestinationArrivalEvent } from '../workbench/handoffArrivalDestinationArrivalEvent';
import HandoffArrivalDestinationEventPanel from './HandoffArrivalDestinationEventPanel';
const relation = { same: 'Aynı kimlik gözlendi', different: 'Farklı kimlik gözlendi', unknown: 'İlişki doğrulanamadı' };
const admission = (v: string) => v === 'complete' ? 'Tamamlandı' : v === 'pending' ? 'Bekliyor' : 'Doğrulanamadı';
export default function HandoffArrivalDestinationArrivalEventPanel({ handoff, value }: { handoff: HandoffArrivalDestinationArrivalEvent; value: ReturnType<typeof compareHandoffArrivalDestinationArrivalEvent> }) {
  const saved = handoff.observation, f = value.fresh, prior = compareDestinationIdentities(saved.arrival, f);
  const snapshots = [['Ayrı saklanan hedef geçişi varışı', saved.arrival], ['Varışı koruyan yeni kuyruk', handoff.queue.fresh], ['Varışı koruyan yeni hazırlık', handoff.prepared], ['Yeni tam karar varışı', f]] as const;
  return <section aria-label="Hedef geçişi varışını koruyan geçiş ve tam karar varışı">
    <h3>Hedef geçişi varışını koruyarak tam karara geçiş</h3>
    <p>Varışı koruyan yeni hazırlıktan varışa — karar başı: {relation[value.head_relation]}. Analizin son sürümü: {relation[value.version_relation]}. Revizyon: {relation[value.revision_relation]}.</p>
    <p>Ayrı saklanan hedef geçişi varışından yeni varışa — karar başı: {relation[prior.head_relation]}. Analizin son sürümü: {relation[prior.version_relation]}. Revizyon: {relation[prior.revision_relation]}.</p>
    <p className="small muted">Yeni hazırlık: {formatDate(handoff.observed_at[1], true)} · Yeni varış: {formatDate(f.metadata.observed_at, true)}. Ayrı gözlemler atomik bir an değildir.</p>
    {(value.head_relation !== 'same' || value.version_relation !== 'same' || value.revision_relation !== 'same') && <Notice>Değişiklik veya belirsizlik gözlendi. Başka karar seçilmedi; önceki onay taşınmadı.</Notice>}
    <Detail title="Saklanan hedef geçişi varışı ve yeni geçişin ayrı kimlikleri">
      <p className="reference-id">Sabit karar: {saved.arrival.selected.id} · Paket: {saved.arrival.selected.packet_sha256}</p>
      <p className="reference-id">Kanıt sürümü: {saved.arrival.metadata.context.version_id} · Manifest: {saved.arrival.metadata.context.manifest_sha256}</p>
      {snapshots.map(([label, s]) => <div key={label}><h4>{label}</h4><p className="reference-id">Baş: {s.head?.id || 'Bilinmiyor'} · Paket: {s.head?.packet_sha256 || 'Doğrulanamadı'}</p>
        <p className="reference-id">Son sürüm: {s.metadata.analysis.current_version_id || 'Bilinmiyor'} · Revizyon: {s.metadata.analysis.revision}</p>
        <p>Kabuller — bağlam: {admission(s.metadata.admission.context_state)}; seçilen karar: {admission(s.selected.admission)}; baş: {admission(s.metadata.admission.review_state)}.</p></div>)}
      <HandoffArrivalDestinationEventPanel handoff={saved.handoff} value={{ fresh: f, ...compareDestinationIdentities(saved.handoff.prepared, f) }} />
    </Detail>
    <p className="small muted">Özgün müşteri ve tarih filtreleri, sabit kanıt ve bağımsız inceleme geçmişi değişmeden korundu. Yalnız özel kimlik metadatası karşılaştırıldı; kaynaklar, hukuki etki veya yeni başa yol doğrulanmadı. Açık ve doğrulanmış dönüş bütün özgün varış dönüşünü değişmeden geri taşır; bu yeni varış ayrıca saklanmaz.</p>
  </section>;
}
