import { Detail, Notice } from '../components';
import { formatDate } from '../utils';
import { sourceContextHref } from './sourceContextNavigationTypes';
import type { ReviewLineage, ReviewMetadata } from './sourceReviewLineageTypes';
const STATE = { unknown: 'Doğrulanamadı', changes_requested: 'Değişiklik istendi', reviewed_conditional: 'Koşullu inceleme kaydedildi' };
const ADMISSION = { complete: 'Tamamlandı', pending: 'Son izin kontrolü bekliyor', unavailable: 'Doğrulanamadı' };
export default function SourceReviewLineagePanel({ value }: { value: ReviewLineage }) {
  const href = (row?: ReviewMetadata | null) => sourceContextHref(value.matter_id, value.analysis_id, value.context_id, row?.id);
  return <section aria-label="Seçilen tarihsel karar ve sınırlı geçmişi">
    <h3>Seçilen tarihsel karar</h3><p className="reference-id">Karar: {value.selected_review.id}</p>
    <p>{STATE[value.selected_review.state]} · {value.selected_review.recorded_at ? formatDate(value.selected_review.recorded_at, true) : 'Kayıt zamanı bilinmiyor'} · Kabul: {ADMISSION[value.selected_review.admission]}</p>
    <p>{value.head_relationship === 'current_head' ? 'Seçilen kimlik, gözlenen karar başıyla aynı.' : value.head_relationship === 'different_from_head' ? 'Seçilen kayıt, gözlenen son karar başından farklı. Son kararın yerine geçmez.' : 'Seçilen kaydın karar başıyla ilişkisi doğrulanamadı.'} Bu kimlik gözlemi kaynak izni, hukuki onay veya indirme yetkisi değildir.</p>
    <Detail title="Gözlenen karar başı ve tam bağlar"><p className="reference-id">Son karar: {value.current_head?.id || 'Doğrulanamadı'}</p>
      <p>{value.current_head ? STATE[value.current_head.state] : 'Karar başı bilinmiyor'}</p>{value.current_head && <p>Son karar kabulü: {ADMISSION[value.current_head.admission]}</p>}
      <p className="reference-id">Sabit bağlam SHA-256: {value.selected_review.manifest_sha256 || 'Doğrulanamadı'}</p>
      <p className="reference-id">Seçilen karar SHA-256: {value.selected_review.packet_sha256 || 'Doğrulanamadı'}</p>
    </Detail>
    <p className="small muted">Bu pencere yalnızca seçilen kayıttan önceki bağlantıları gözler; tüm geçmişin veya son başa erişimin kanıtı değildir. Toplam kapsam bilinmiyor. Kamu kaynakları kontrol edilmedi.</p>
    {value.lineage.status === 'unavailable' && <Notice error>Bağlantıların bir kısmı doğrulanamadı. Eksik veya bozuk bağlantının yerine başka karar seçilmez.</Notice>}
    {value.lineage.status === 'truncated' && <Notice>En fazla {value.lineage.window} kayıt gözlendi; geçmişin devamı bu pencerede incelenmedi.</Notice>}
    {value.lineage.status === 'complete_to_first_event' && <p>Bu seçimin bağlantıları ilk kayıtlı olaya kadar doğrulandı. Daha yeni kararlar bu zincire dahil değildir.</p>}
    <Detail title="Sınırlı önceki karar bağlantıları"><ol className="source-review-lineage">{value.lineage.items.map(row => <li key={row.id}><p>{row.sequence}. kayıt · {STATE[row.state]} · {row.recorded_at ? formatDate(row.recorded_at, true) : 'Bilinmiyor'} · Kabul: {ADMISSION[row.admission]}</p>
      <p className="reference-id">{row.id}</p>{row.id !== value.review_id && href(row) && <a className="text-link" href={href(row)!}>Bu kararın tam kimliğini aç</a>}
    </li>)}</ol></Detail>
    {value.lineage.next_review_id && sourceContextHref(value.matter_id, value.analysis_id, value.context_id, value.lineage.next_review_id) && <a className="button secondary" href={sourceContextHref(value.matter_id, value.analysis_id, value.context_id, value.lineage.next_review_id)!}>Önceki bağlantıyı yeni seçim olarak aç</a>}
    <div className="practice-record-actions"><a className="text-link" href={href()!}>Güncel bağlamın kimliğine dön</a>{value.current_head && href(value.current_head) && value.current_head.id !== value.review_id && <a className="text-link" href={href(value.current_head)!}>Gözlenen karar başının tam kimliğini aç</a>}</div>
  </section>;
}
