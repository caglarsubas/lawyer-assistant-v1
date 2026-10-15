import { Detail, Notice } from '../components';
import { formatDate } from '../utils';
import type { ComparisonEventHandoff, compareComparisonEventArrival } from '../workbench/comparisonEventHandoff';

const relation = { same: 'Aynı kimlik gözlendi', different: 'Farklı kimlik gözlendi', unknown: 'İlişki doğrulanamadı' };
export default function ComparisonEventArrivalPanel({ handoff, value }: { handoff: ComparisonEventHandoff; value: ReturnType<typeof compareComparisonEventArrival> }) {
  const r = handoff.receipt, q = handoff.queue, p = handoff.prepared, f = value.fresh;
  return <section aria-label="Karşılaştırma geçişi ve tam karar varışı">
    <h3>Karşılaştırmadan tam karara varış</h3>
    <p>Hazırlıktan varışa — karar başı: {relation[value.head_relation]}. Analizin son sürümü: {relation[value.version_relation]}. Revizyon: {relation[value.revision_relation]}.</p>
    <p className="small muted">Geçişin son gözlemi: {formatDate(handoff.observed_at[1], true)} · Varış: {formatDate(f.metadata.observed_at, true)}. Seçilen tarihsel karar ve sabit kanıt korunur. Ayrı gözlemler atomik bir an değildir.</p>
    {(value.head_relation !== 'same' || value.version_relation !== 'same' || value.revision_relation !== 'same') && <Notice>Değişiklik veya belirsizlik gözlendi. Başka karar seçilmedi; onay taşınmadı. Yeni karşılaştırma için aynı filtrelerle portföye dönün.</Notice>}
    <Detail title="Karşılaştırmadan varışa ayrı kimlik gözlemleri">
      <p className="reference-id">Özgün baş: {r.intent.target.head_id || 'Bilinmiyor'} · Özgün son sürüm: {r.intent.target.current_version_id || 'Bilinmiyor'}</p>
      <p className="reference-id">Sabit seçili olay: {r.handoff.selected.id} · Paket: {r.handoff.selected.packet_sha256}</p>
      <p className="reference-id">Kanıt sürümü: {r.handoff.frozen_version_id} · Manifest: {r.handoff.manifest_sha256}</p>
      <p className="reference-id">Önceki geçiş başı: {r.handoff.head.id} · Önceki hedef başı: {r.destination.head?.id || 'Bilinmiyor'}</p>
      <p className="reference-id">Kuyruk başı: {q.fresh.head?.id || 'Bilinmiyor'} · Son sürüm: {q.fresh.metadata.analysis.current_version_id || 'Bilinmiyor'} · Revizyon: {q.fresh.metadata.analysis.revision}</p>
      <p className="reference-id">Hazırlık başı: {p.head?.id || 'Bilinmiyor'} · Paket: {p.head?.packet_sha256 || 'Doğrulanamadı'} · Son sürüm: {p.metadata.analysis.current_version_id || 'Bilinmiyor'} · Revizyon: {p.metadata.analysis.revision}</p>
      <p className="reference-id">Varış başı: {f.head?.id || 'Bilinmiyor'} · Paket: {f.head?.packet_sha256 || 'Doğrulanamadı'} · Son sürüm: {f.metadata.analysis.current_version_id || 'Bilinmiyor'} · Revizyon: {f.metadata.analysis.revision}</p>
    </Detail>
    <p className="small muted">Yalnız özel kayıt kimlikleri gözlendi. Kaynaklar, hukuki etki veya yeni başa yol doğrulanmadı. İnceleme araçları ayrı ve güncel kontroller gerektirir; bu geçiş kabul veya bağımsız onay vermez.</p>
  </section>;
}
