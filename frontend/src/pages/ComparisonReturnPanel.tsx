import { Detail, Notice } from '../components';
import { formatDate } from '../utils';
import type { ComparisonQueueReconciliation, ComparisonReturnReceipt } from '../workbench/comparisonReturn';

const relation = { same: 'Aynı kimlik gözlendi', different: 'Farklı kimlik gözlendi', unknown: 'İlişki doğrulanamadı' };
const admission = (value: string) => value === 'complete' ? 'Tamamlandı' : value === 'pending' ? 'Bekliyor' : 'Doğrulanamadı';
export default function ComparisonReturnPanel({ receipt, value, prepare, busy = false }: { receipt: ComparisonReturnReceipt; value: ComparisonQueueReconciliation; prepare?: () => void; busy?: boolean }) {
  if (value.state === 'not_observed') return <Notice>Seçilen kayıt bu pencerede gözlenmedi. Korunan karşılaştırmanın ayrıntıları açılmadı; güncel erişim veya ilişki kurulmadı.</Notice>;
  const h = receipt.handoff, d = receipt.destination, f = value.fresh, o = receipt.intent.target;
  return <section aria-label="Korunan karşılaştırma ve yeni kuyruk gözlemi">
    <h3>Karşılaştırmadan portföye dönüş</h3>
    <p>Hedef gözleminden yeni kuyruğa — karar başı: {relation[value.head_relation]}. Analizin son sürümü: {relation[value.version_relation]}. Revizyon: {relation[value.revision_relation]}.</p>
    <p className="small muted">Korunan hedef gözlemi: {formatDate(d.metadata.observed_at, true)} · Yeni kuyruk: {formatDate(value.queue_observed_at, true)} · Tam kayıt: {formatDate(f.metadata.observed_at, true)}. Ayrı gözlemler tek atomik an değildir; önceki onay taşınmaz.</p>
    {prepare && <button className="button secondary" disabled={busy} onClick={prepare}>Karşılaştırmadaki tam karar geçişini ayrıca doğrula</button>}
    <Detail title="Korunan karşılaştırma ve yeni gözlemin tam kimlikleri">
      <h4>Özgün kuyruk gözlemi</h4>
      <p className="reference-id">Özgün baş: {o.head_id || 'Bilinmiyor'} · Son sürüm: {o.current_version_id || 'Bilinmiyor'}</p>
      <p>Sürüm gözlemi: {o.version_observed_at ? formatDate(o.version_observed_at, true) : 'Gözlenmedi'}. Özgün değerler yenileriyle değiştirilmedi.</p>
      <h4>Seçilen sabit kayıt</h4>
      <p className="reference-id">Sabit karar: {h.selected.id} · Paket: {h.selected.packet_sha256}</p>
      <p className="reference-id">Kanıt sürümü: {h.frozen_version_id} · Manifest: {h.manifest_sha256}</p>
      <h4>Korunan geçiş gözlemi</h4>
      <p className="reference-id">Geçiş başı: {h.head.id} · Paket: {h.head.packet_sha256}</p>
      <p className="reference-id">Son sürüm: {h.current_version_id} · Revizyon: {h.revision}</p>
      <h4>Korunan hedef gözlemi</h4>
      <p className="reference-id">Hedef başı: {d.head?.id || 'Bilinmiyor'} · Paket: {d.head?.packet_sha256 || 'Doğrulanamadı'}</p>
      <p className="reference-id">Son sürüm: {d.metadata.analysis.current_version_id || 'Bilinmiyor'} · Revizyon: {d.metadata.analysis.revision}</p>
      <p>Korunan kabuller — bağlam: {admission(d.metadata.admission.context_state)}; seçilen karar: {admission(d.selected.admission)}; baş: {admission(d.metadata.admission.review_state)}. Bunlar tarihsel gözlemlerdir.</p>
      <h4>Yeni kuyrukta ayrıca gözlenen tam kayıt</h4>
      <p className="reference-id">Yeni gözlenen baş: {f.head?.id || 'Bilinmiyor'} · Paket: {f.head?.packet_sha256 || 'Doğrulanamadı'}</p>
      <p className="reference-id">Son sürüm: {f.metadata.analysis.current_version_id || 'Bilinmiyor'} · Revizyon: {f.metadata.analysis.revision}</p>
      <p>Yeni kabuller — bağlam: {admission(f.metadata.admission.context_state)}; seçilen karar: {admission(f.selected.admission)}; baş: {admission(f.metadata.admission.review_state)}. Bekleyen kabul tamamlanmadı.</p>
    </Detail>
    <p className="small muted">Yalnızca özel kimlik metadatası karşılaştırıldı. Sabit karar, kanıt ve özgün filtreler korundu. Kaynak içeriği, izinler, hukuki etki veya yeni başa bağlantı doğrulanmadı; başka karar seçilmedi.</p>
  </section>;
}
