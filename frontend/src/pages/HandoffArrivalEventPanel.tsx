import { Detail, Notice } from '../components';
import { formatDate } from '../utils';
import type { HandoffArrivalEvent, compareHandoffArrivalEvent } from '../workbench/handoffArrivalEvent';
import { compareDestinationIdentities } from '../workbench/comparisonReturn';
const relation = { same: 'Aynı kimlik gözlendi', different: 'Farklı kimlik gözlendi', unknown: 'İlişki doğrulanamadı' };
const admission = (v: string) => v === 'complete' ? 'Tamamlandı' : v === 'pending' ? 'Bekliyor' : 'Doğrulanamadı';
export default function HandoffArrivalEventPanel({ handoff, value }: { handoff: HandoffArrivalEvent; value: ReturnType<typeof compareHandoffArrivalEvent> }) {
  const carried = handoff.observation, saved = carried.handoff.observation, purpose = saved.handoff, arrival = purpose.observation, latest = arrival.handoff, d = latest.observation;
  const h = d.handoff, c = h.observation, o = c.handoff.observation, old = o.handoff.observation, r = old.handoff.receipt, f = value.fresh;
  const retained = compareDestinationIdentities(carried.arrival, f), prior = compareDestinationIdentities(arrival.arrival, f);
  const snapshots = [['Önceki hedef', r.destination], ['Özgün varış', old.arrival], ['İlk ileri geçiş kuyruğu', o.handoff.queue.fresh],
    ['İlk ileri geçiş hazırlığı', o.handoff.prepared], ['Özgün ileri hedef', o.destination], ['Taşıyan kuyruk', c.handoff.queue.fresh],
    ['Taşıyan hazırlık', c.handoff.prepared], ['Özgün taşınan varış', c.arrival], ['Son geçiş kuyruğu', h.queue.fresh],
    ['Son geçiş hazırlığı', h.prepared], ['Özgün taşınan hedef', d.destination], ['Hedef varışı kuyruğu', latest.queue.fresh],
    ['Hedef varışı hazırlığı', latest.prepared], ['Korunan hedef varışı', arrival.arrival], ['Önceki amaç kuyruğu', purpose.queue.fresh],
    ['Önceki amaç hazırlığı', purpose.prepared], ['Korunan geçiş hedefi', saved.destination], ['Korunan hedefin yeni kuyruğu', carried.handoff.queue.fresh], ['Korunan hedefin yeni hazırlığı', carried.handoff.prepared], ['Korunan geçiş varışı', carried.arrival], ['Yeni geçiş kuyruğu', handoff.queue.fresh],
    ['Yeni geçiş hazırlığı', handoff.prepared], ['Güncel varış', f]] as const;
  return <section aria-label="Geçiş varışını koruyan geçiş ve tam karar varışı">
    <h3>Geçiş varışını koruyarak tam karara geçiş</h3>
    <p>Yeni hazırlıktan varışa — karar başı: {relation[value.head_relation]}. Analizin son sürümü: {relation[value.version_relation]}. Revizyon: {relation[value.revision_relation]}.</p>
    <p>Korunan geçiş varışından yeni varışa — karar başı: {relation[retained.head_relation]}. Analizin son sürümü: {relation[retained.version_relation]}. Revizyon: {relation[retained.revision_relation]}.</p>
    <p className="small muted">Yeni hazırlık: {formatDate(handoff.observed_at[1], true)} · Güncel varış: {formatDate(f.metadata.observed_at, true)}. Ayrı gözlemler atomik bir an değildir; önceki kayıtlar değiştirilmez.</p>
    {(value.head_relation !== 'same' || value.version_relation !== 'same' || value.revision_relation !== 'same') && <Notice>Değişiklik veya belirsizlik gözlendi. Başka karar seçilmedi; onay taşınmadı. Kaynak araçları ayrı ve güncel kontroller gerektirir.</Notice>}
    <Detail title="Korunan geçiş varışı ve yeni geçişin ayrı kimlikleri">
      <p>Korunan hedef varışından yeni varışa — baş: {relation[prior.head_relation]}; sürüm: {relation[prior.version_relation]}; revizyon: {relation[prior.revision_relation]}.</p>
      <p className="reference-id">Özgün baş: {r.intent.target.head_id || 'Bilinmiyor'} · Özgün son sürüm: {r.intent.target.current_version_id || 'Bilinmiyor'}</p>
      <p className="reference-id">Sabit karar: {r.handoff.selected.id} · Paket: {r.handoff.selected.packet_sha256}</p>
      <p className="reference-id">Kanıt sürümü: {r.handoff.frozen_version_id} · Manifest: {r.handoff.manifest_sha256}</p>
      {snapshots.map(([label, s]) => <div key={label}><h4>{label}</h4><p className="reference-id">Baş: {s.head?.id || 'Bilinmiyor'} · Paket: {s.head?.packet_sha256 || 'Doğrulanamadı'}</p>
        <p className="reference-id">Son sürüm: {s.metadata.analysis.current_version_id || 'Bilinmiyor'} · Revizyon: {s.metadata.analysis.revision}</p>
        <p>Kabuller — bağlam: {admission(s.metadata.admission.context_state)}; seçilen karar: {admission(s.selected.admission)}; baş: {admission(s.metadata.admission.review_state)}.</p></div>)}
    </Detail>
    <p className="small muted">Özgün filtreler, sabit kanıt ve bağımsız inceleme geçmişi korundu. Yalnız özel kimlik metadatası karşılaştırıldı; kaynaklar, hukuki etki veya yeni başa yol doğrulanmadı. Bekleyen kabul tamamlanmadı, başka karar seçilmedi. Doğrulanmış dönüş özgün geçiş varışını ve bütün önceki gözlemleri değişmeden korur; güncel varış bunların yerine geçmez. Kendiliğinden ayrıca saklanmaz; açık ve doğrulanmış dönüşte ayrı hedef olarak saklanır.</p>
  </section>;
}
