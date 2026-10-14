import { Detail, Notice } from '../components';
import { formatDate } from '../utils';
import type { IdentityRelation, ReturnComparison } from '../workbench/returnComparison';

const RELATION: Record<IdentityRelation, string> = { same: 'Aynı gözlenen kimlik', different: 'Farklı gözlenen kimlikler', unknown: 'İlişki bilinmiyor' };
const HEAD = { unknown: 'Doğrulanamadı', unreviewed: 'Henüz karar kaydedilmedi', changes_requested: 'Değişiklik istendi', reviewed_conditional: 'Koşullu inceleme kaydedildi' };
export type ReturnLinks = { selected: string | null; head: string | null; context: string | null };
export default function ReturnIdentityComparison({ value: c, links }: { value: ReturnComparison; links: ReturnLinks }) {
  return <section aria-label="Önceki ve yeni karar başı ile sürüm karşılaştırması">
    <h3>Önceki ve yeni kimlikler</h3>
    <p className="small muted">Kimlik karşılaştırmasıdır. Kararların birbirini desteklediğini, önceki kararı kaldırdığını veya kanıtın güncel olduğunu göstermez. Önceki gözlemler değiştirilmez.</p>
    <div className="source-selection-table" role="region" aria-label="Karar başı ve analiz sürümü karşılaştırma tablosu" tabIndex={0}>
      <table><caption className="small muted">İlk seçimin gözlemleri ve yeni yetkili gözlem</caption><thead><tr><th scope="col">Kayıt</th><th scope="col">İlk gözlem</th><th scope="col">Yeni gözlem</th><th scope="col">Kimlik ilişkisi</th></tr></thead><tbody>
        <tr><th scope="row">Karar başı</th><td><p>{HEAD[c.before.head_state]}</p><p className="reference-id">{c.before.head_id || (c.before.head_state === 'unreviewed' ? 'Karar kaydı yok' : 'Bilinmiyor')}</p><p className="small muted">{formatDate(c.before.head_observed_at, true)}</p></td>
          <td><p>{HEAD[c.current.head_state]}</p><p className="reference-id">{c.current.head_id || (c.current.head_state === 'unreviewed' ? 'Karar kaydı yok' : 'Bilinmiyor')}</p><p className="small muted">{formatDate(c.current.observed_at, true)}</p></td><td>{RELATION[c.head_relation]}</td></tr>
        <tr><th scope="row">Analizin son sürümü</th><td><p className="reference-id">{c.before.version_id || (c.before.version_observed_at ? 'Gözlemde doğrulanamadı' : 'Önceki sürüm gözlenmedi')}</p><p className="small muted">{c.before.version_observed_at ? formatDate(c.before.version_observed_at, true) : 'Gözlem zamanı bilinmiyor'}</p></td>
          <td><p className="reference-id">{c.current.version_id || 'Doğrulanamadı'}</p><p className="small muted">{formatDate(c.current.observed_at, true)}</p></td><td>{RELATION[c.version_relation]}</td></tr>
      </tbody></table>
    </div>
    {c.head_relation === 'different' && <Notice>İlk gözlemdeki karar başı ile yeni gözlenen baş farklı. Seçilen tarihsel karar korunur; yeni baş otomatik seçilmez.</Notice>}
    {c.version_relation === 'different' && <Notice>Analizin son sürüm kimliği değişti. Sabit kanıt sürümü değiştirilmedi; yenileme ve yeni bağımsız inceleme ayrıca gerekir.</Notice>}
    {(c.head_relation === 'unknown' || c.version_relation === 'unknown') && <p className="small muted">Bilinmeyen kimlik veya gözlem, değişiklik olmadığı şeklinde yorumlanmaz.</p>}
    <p>Sabit kanıt sürümü ile yeni gözlenen son sürüm: {RELATION[c.current.frozen_version_relation]}. Bu ilişki içerik uygunluğu veya kaynak izni değildir.</p>
    {c.selected && <p>Seçilen tarihsel karar ile yeni gözlenen baş: {RELATION[c.selected_head_relation]}. Geçmiş zincirinde son başa erişim kontrol edilmedi; kararın etkisi ayrıca incelenir.</p>}
    <Detail title="Sabit kanıt ve tam kimlikler">
      <p className="reference-id">Çalışma alanı: {c.fixed.matter_id} · Analiz: {c.fixed.analysis_id}</p><p className="reference-id">Sabit bağlam: {c.fixed.context_id}</p>
      <p className="reference-id">Sabit kanıt sürümü: {c.fixed.version_id}</p><p className="reference-id">Sabit bağlam SHA-256: {c.fixed.manifest_sha256}</p>
      {c.selected && <><p className="reference-id">Seçilen tarihsel karar: {c.selected.id}</p><p className="reference-id">Seçilen karar SHA-256: {c.selected.packet_sha256 || 'Doğrulanamadı'}</p></>}
    </Detail>
    <div className="practice-record-actions" role="group" aria-label="Yeni gözlemden güvenli devam">
      {links.selected && <a className="text-link" href={links.selected}>Seçilen kaydın tam kimliğini yeniden aç</a>}
      {links.head && <a className="text-link" href={links.head}>Yeni gözlenen karar başının tam kimliğini aç</a>}
      {links.context && c.selected && <a className="text-link" href={links.context}>Bağlamı yeni kimlik gözlemiyle aç</a>}
    </div>
    <p className="small muted">Her bağlantı yeni yetki ve kimlik kontrolü yapar. İnceleme araçları, alıntılar ve indirme ayrıca açıkça başlatılır; eski onay veya izin devralınmaz.</p>
  </section>;
}
