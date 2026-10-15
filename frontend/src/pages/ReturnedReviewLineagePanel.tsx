import { Detail, Notice } from '../components';
import { formatDate } from '../utils';
import type { ReturnedLineageObservation } from '../workbench/returnedReviewLineage';

export default function ReturnedReviewLineagePanel({ value, choose, busy = false }: { value: ReturnedLineageObservation; choose?: (id: string) => void; busy?: boolean }) {
  return <section aria-label="Karar başından seçilen incelemeye sınırlı kayıt zinciri">
    <h3>Sınırlı kayıt zinciri gözlemi</h3>
    {value.status === 'unknown' ? <Notice>Kayıt zinciri ilişkisi bilinmiyor. {value.reason === 'truncated' ? 'Geçmiş penceresi kesildi; devamı incelenmedi.' : value.reason === 'pending' ? 'Pencerede kabulü bekleyen bir kayıt var.' : value.reason === 'unavailable' ? 'Pencerenin bütünlüğü doğrulanamadı.' : 'Tam seçilen kayıt bu pencerede gözlenmedi.'} Başka pencere kendiliğinden getirilmez.</Notice>
      : <p>{value.status === 'same_event' ? 'Seçilen inceleme ile gözlenen karar başı aynı doğrulanmış kayıttır.' : `Gözlenen karar başından tam seçilen incelemeye ${value.path.length - 1} ardışık önceki-kayıt bağlantısı doğrulandı.`}</p>}
    <p className="small muted">Yalnızca özel inceleme kayıtlarının bağlantılarıdır. Hukuki görüş birliği, kararın kaldırılması, kaynak izni, güncellik veya onay göstermez. İlk gözlem, seçilen kayıt ve sabit kanıt sürümü değiştirilmedi.</p>
    <p className="small muted">Ön kimlik gözlemi: {formatDate(value.before_observed_at, true)} · Pencere: {formatDate(value.window_observed_at, true)} · Son kimlik gözlemi: {formatDate(value.after_observed_at, true)}. Ayrı gözlemler atomik bir an veya gelecekte değişmeme garantisi değildir.</p>
    <Detail title="Sınırlı zincirin tam kimlikleri">
      <p>En çok {value.window} kayıt · Gözlenen {value.observed_count} kayıt · Toplam geçmiş bilinmiyor.</p>
      <p className="reference-id">Gözlenen baş: {value.head_id} · SHA-256: {value.head_packet_sha256}</p>
      <p className="reference-id">Seçilen inceleme: {value.selected_id} · SHA-256: {value.selected_packet_sha256}</p>
      {value.path.length > 0 && <ol>{value.path.map(row => <li key={row.id}><p className="reference-id">Sıra {row.sequence}: {row.id} · SHA-256: {row.packet_sha256}</p>{choose && value.status !== 'unknown' && <button className="text-button" disabled={busy} onClick={() => choose(row.id)}>{row.sequence}. kaydın tam kimlik geçişini doğrula</button>}</li>)}</ol>}
    </Detail>
    <p className="small muted">Kaynak metinleri ve kamu kaynakları kontrol edilmedi. İnceleme, yenileme ve dışa aktarma izinleri ayrıca doğrulanır.</p>
  </section>;
}
