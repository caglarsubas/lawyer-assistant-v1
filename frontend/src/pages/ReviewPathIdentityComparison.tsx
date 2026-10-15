import { Detail, Notice } from '../components';
import { formatDate } from '../utils';
import type { ReviewPathComparison } from '../workbench/reviewPathHandoff';

const relation = { same: 'Aynı kimlik gözlendi', different: 'Farklı kimlik gözlendi', unknown: 'İlişki doğrulanamadı' };
const admission = (state: string) => state === 'complete' ? 'Tamamlandı' : state === 'pending' ? 'Bekliyor' : 'Doğrulanamadı';
export default function ReviewPathIdentityComparison({ value }: { value: ReviewPathComparison }) {
  const h = value.handoff, d = value.destination, o = value.original.before;
  return <section aria-label="Zincir geçişi ve hedef kimlik karşılaştırması">
    <h3>Geçişten hedefe kimlik karşılaştırması</h3>
    <p>Karar başı: {relation[value.head_relation]}. Analizin son sürümü: {relation[value.version_relation]}. Analiz revizyonu: {relation[value.revision_relation]}.</p>
    <p className="small muted">Geçiş son gözlemi: {formatDate(h.observed_at[4], true)} · Hedef gözlemi: {formatDate(d.observed_at, true)}. Ayrı gözlemler atomik bir an değildir. Seçilen tarihsel karar ve sabit kanıt sürümü korunur; farklı baş seçilmez.</p>
    {(value.head_relation !== 'same' || value.version_relation !== 'same' || value.revision_relation !== 'same') && <Notice>Geçiş ile hedef arasında değişiklik veya belirsizlik var. Başka bir kayıt seçmek için aynı filtrelerle portföye dönün ve yeni gözlem yapın. İnceleme onayı aktarılmadı.</Notice>}
    <Detail title="Özgün gözlem, geçiş ve hedef kimlikleri">
      <h4>Özgün kuyruk karşılaştırma gözlemi</h4>
      <p className="reference-id">Karar başı: {o.head_id || 'Bilinmiyor'} · Durum: {o.head_state}</p>
      <p className="reference-id">Son sürüm: {o.version_id || 'Bilinmiyor'} · Sürüm gözlemi: {o.version_observed_at ? formatDate(o.version_observed_at, true) : 'Gözlenmedi'}</p>
      <p>Baş gözlemi: {formatDate(o.head_observed_at, true)}. Bu değerler geçiş gözlemiyle değiştirilmedi.</p>
      <h4>Ayrıca seçilen sabit kayıt</h4>
      <p className="reference-id">Sabit seçilen karar: {h.selected.id} · Paket: {h.selected.packet_sha256}</p>
      <p className="reference-id">Kanıt sürümü: {h.frozen_version_id} · Manifest: {h.manifest_sha256}</p>
      <h4>Geçiş hazırlanırken gözlenen baş ve sürüm</h4>
      <p className="reference-id">Karar başı: {h.head.id} · Paket: {h.head.packet_sha256}</p>
      <p className="reference-id">Son sürüm: {h.current_version_id} · Revizyon: {h.revision}</p>
      <h4>Hedefte yeni gözlenen baş ve sürüm</h4>
      <p className="reference-id">Karar başı: {d.head?.id || 'Bilinmiyor'} · Paket: {d.head?.packet_sha256 || 'Doğrulanamadı'}</p>
      <p className="reference-id">Son sürüm: {d.current_version_id || 'Bilinmiyor'} · Revizyon: {d.revision}</p>
      <p>Hedef kabulü — bağlam: {admission(d.context_admission)}; seçilen karar: {admission(d.selected_admission)}; baş: {admission(d.head_admission)}.</p>
    </Detail>
    <p className="small muted">Bu karşılaştırma yalnızca özel kayıt metadatasıdır. Kaynak metni ve izinleri kontrol edilmedi; güncel bağımsız inceleme, hukuki onay veya zincir bütünlüğü verilmedi. Kaynak araçları ayrı ve güncel kontroller gerektirir.</p>
  </section>;
}
