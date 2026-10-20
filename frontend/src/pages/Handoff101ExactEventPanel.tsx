import { Detail, Notice } from '../components';
import { formatDate } from '../utils';
import { compareDestinationIdentities } from '../workbench/comparisonReturn';
import { compareHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationEvent, type HandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationEvent } from '../workbench/handoff101ExactEvent';
import HandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalEventPanel from './Handoff98ExactEventPanel';
const relation = { same: 'Aynı kimlik gözlendi', different: 'Farklı kimlik gözlendi', unknown: 'İlişki doğrulanamadı' };
const admission = (v: string) => v === 'complete' ? 'Tamamlandı' : v === 'pending' ? 'Bekliyor' : 'Doğrulanamadı';
export default function HandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationEventPanel({ handoff, value }: { handoff: HandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationEvent; value: ReturnType<typeof compareHandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationEvent> }) {
  const saved = handoff.observation, f = value.fresh, prior = compareDestinationIdentities(saved.destination, f);
  const snapshots = [['Korunan yeni son hedefin eksiksiz zincirinin ayrı kaydı', saved.destination], ['Yeni son hedefin eksiksiz zincirini koruyan yeni kuyruk', handoff.queue.fresh], ['Yeni son hedefin eksiksiz zincirini koruyan yeni hazırlık', handoff.prepared], ['Yeni son hedefin eksiksiz zincirini koruyan yeni karar hedefi', f]] as const;
  return <section aria-label="Yeni son hedefin eksiksiz zincirinin tüm geçmişini koruyan karar geçişi">
    <h3>Yeni son hedefin eksiksiz zincirinin tüm geçmişiyle seçilen karara geçiş</h3>
    <p>Yeni son hedefin eksiksiz zincirini koruyan yeni hazırlıktan varışa — karar başı: {relation[value.head_relation]}. Analizin son sürümü: {relation[value.version_relation]}. Revizyon: {relation[value.revision_relation]}.</p>
    <p>Saklanan yeni son hedefin eksiksiz zincirinden yeni varışa — karar başı: {relation[prior.head_relation]}. Analizin son sürümü: {relation[prior.version_relation]}. Revizyon: {relation[prior.revision_relation]}.</p>
    <p className="small muted">Yeni hazırlık: {formatDate(handoff.observed_at[1], true)} · Yeni varış: {formatDate(f.metadata.observed_at, true)}. Ayrı gözlemler atomik bir an değildir.</p>
    {(value.head_relation !== 'same' || value.version_relation !== 'same' || value.revision_relation !== 'same') && <Notice>Değişiklik veya belirsizlik gözlendi. Başka karar seçilmedi; önceki onay taşınmadı.</Notice>}
    <Detail title="Yeni son hedefin eksiksiz zincirinin tam geçmişi ve yeni geçişin ayrı kimlikleri">
      <p className="reference-id">Sabit karar: {saved.destination.selected.id} · Paket: {saved.destination.selected.packet_sha256}</p>
      <p className="reference-id">Kanıt sürümü: {saved.destination.metadata.context.version_id} · Manifest: {saved.destination.metadata.context.manifest_sha256}</p>
      {snapshots.map(([label, s]) => <div key={label}><h4>{label}</h4><p className="reference-id">Baş: {s.head?.id || 'Bilinmiyor'} · Paket: {s.head?.packet_sha256 || 'Doğrulanamadı'}</p>
        <p className="reference-id">Son sürüm: {s.metadata.analysis.current_version_id || 'Bilinmiyor'} · Revizyon: {s.metadata.analysis.revision}</p>
        <p>Kabuller — bağlam: {admission(s.metadata.admission.context_state)}; seçilen karar: {admission(s.selected.admission)}; baş: {admission(s.metadata.admission.review_state)}.</p></div>)}
      <HandoffArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalDestinationArrivalEventPanel handoff={saved.handoff} value={{ fresh: f, ...compareDestinationIdentities(saved.handoff.prepared, f) }} />
    </Detail>
    <p className="small muted">Özgün müşteri ve tarih filtreleri, sabit kanıt ve bağımsız inceleme geçmişi değişmeden korundu. Yalnız özel kimlik metadatası karşılaştırıldı; kaynaklar, hukuki etki veya yeni başa yol doğrulanmadı. Açık ve doğrulanmış dönüş korunan 103 gözlemi ve bu varışın ayrı kimliğini portföye taşır. Yeni kuyruk gözlemi ayrıca yapılır.</p>
  </section>;
}
