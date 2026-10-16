import { Detail, Notice } from '../components';
import { formatDate } from '../utils';
import { compareDestinationIdentities } from '../workbench/comparisonReturn';
import { compareHandoffArrivalDestinationArrivalDestinationEvent, type HandoffArrivalDestinationArrivalDestinationEvent } from '../workbench/handoffArrivalDestinationArrivalDestinationEvent';
import HandoffArrivalDestinationArrivalEventPanel from './HandoffArrivalDestinationArrivalEventPanel';
const relation = { same: 'Aynı kimlik gözlendi', different: 'Farklı kimlik gözlendi', unknown: 'İlişki doğrulanamadı' };
const admission = (v: string) => v === 'complete' ? 'Tamamlandı' : v === 'pending' ? 'Bekliyor' : 'Doğrulanamadı';
export default function HandoffArrivalDestinationArrivalDestinationEventPanel({ handoff, value }: { handoff: HandoffArrivalDestinationArrivalDestinationEvent; value: ReturnType<typeof compareHandoffArrivalDestinationArrivalDestinationEvent> }) {
  const saved = handoff.observation, f = value.fresh, prior = compareDestinationIdentities(saved.destination, f);
  const snapshots = [['Ayrı saklanan geçiş hedefi', saved.destination], ['Hedefi koruyan yeni kuyruk', handoff.queue.fresh], ['Hedefi koruyan yeni hazırlık', handoff.prepared], ['Yeni tam karar varışı', f]] as const;
  return <section aria-label="Varışı koruyan geçiş hedefini koruyan geçiş ve tam karar varışı">
    <h3>Varışı koruyan geçiş hedefini koruyarak tam karara geçiş</h3>
    <p>Hedefi koruyan yeni hazırlıktan varışa — karar başı: {relation[value.head_relation]}. Analizin son sürümü: {relation[value.version_relation]}. Revizyon: {relation[value.revision_relation]}.</p>
    <p>Ayrı saklanan geçiş hedefinden yeni varışa — karar başı: {relation[prior.head_relation]}. Analizin son sürümü: {relation[prior.version_relation]}. Revizyon: {relation[prior.revision_relation]}.</p>
    <p className="small muted">Yeni hazırlık: {formatDate(handoff.observed_at[1], true)} · Yeni varış: {formatDate(f.metadata.observed_at, true)}. Ayrı gözlemler atomik bir an değildir.</p>
    {(value.head_relation !== 'same' || value.version_relation !== 'same' || value.revision_relation !== 'same') && <Notice>Değişiklik veya belirsizlik gözlendi. Başka karar seçilmedi; önceki onay taşınmadı.</Notice>}
    <Detail title="Saklanan geçiş hedefi ve yeni geçişin ayrı kimlikleri">
      <p className="reference-id">Sabit karar: {saved.destination.selected.id} · Paket: {saved.destination.selected.packet_sha256}</p>
      <p className="reference-id">Kanıt sürümü: {saved.destination.metadata.context.version_id} · Manifest: {saved.destination.metadata.context.manifest_sha256}</p>
      {snapshots.map(([label, s]) => <div key={label}><h4>{label}</h4><p className="reference-id">Baş: {s.head?.id || 'Bilinmiyor'} · Paket: {s.head?.packet_sha256 || 'Doğrulanamadı'}</p>
        <p className="reference-id">Son sürüm: {s.metadata.analysis.current_version_id || 'Bilinmiyor'} · Revizyon: {s.metadata.analysis.revision}</p>
        <p>Kabuller — bağlam: {admission(s.metadata.admission.context_state)}; seçilen karar: {admission(s.selected.admission)}; baş: {admission(s.metadata.admission.review_state)}.</p></div>)}
      <HandoffArrivalDestinationArrivalEventPanel handoff={saved.handoff} value={{ fresh: f, ...compareDestinationIdentities(saved.handoff.prepared, f) }} />
    </Detail>
    <p className="small muted">Özgün müşteri ve tarih filtreleri, sabit kanıt ve bağımsız inceleme geçmişi değişmeden korundu. Yalnız özel kimlik metadatası karşılaştırıldı; kaynaklar, hukuki etki veya yeni başa yol doğrulanmadı. Açık ve doğrulanmış dönüş bütün özgün hedef dönüşünü değişmeden geri taşır; özgün dönüş API’sinde bu yeni varış ayrıca saklanmaz. Arayüzün açık ve doğrulanmış dönüşünde yeni varış ayrı saklanır.</p>
  </section>;
}
