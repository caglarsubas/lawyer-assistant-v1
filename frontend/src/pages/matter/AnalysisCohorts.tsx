import { useEffect, useRef, useState } from 'react';
import { request } from '../../api';
import { Badge, Detail, Field, Notice } from '../../components';
import { formatDate, messageOf, statusLabel } from '../../utils';
import { ComparisonResults } from './AnalysisComparisons';
import { ARM_LABELS, type ComparisonArm } from './comparisonTypes';
import type { CohortCandidate, CohortManifest, CohortOutcome, CohortPreview, CohortReport, CohortView } from './cohortTypes';

const ARMS = Object.keys(ARM_LABELS) as ComparisonArm[];
const OUTCOME: Record<string, string> = { confirmed: 'Doğrulandığı beyanı', needs_change: 'Değişiklik gerekli', not_assessed: 'Değerlendirilmedi', repaired: 'Giderildiği beyanı', withheld: 'Bekletildi', unresolved: 'Çözülmedi' };
export const cohortSeconds = (value: number | null) => value === null ? 'Bilinmiyor' : `${value.toFixed(3)} sn`;
export function reservedFamilyLabels(text: string) {
  const labels = text.split('\n').map((item) => item.trim()).filter(Boolean);
  if (labels.length > 60 || labels.some((item) => item.length > 200) || new Set(labels).size !== labels.length) throw new Error('En fazla 60 farklı aile adı girin; her satır en fazla 200 karakter olmalıdır.');
  return labels;
}
function Outcomes({ values }: { values: CohortOutcome[] }) {
  return <>{values.map((item) => <Detail key={item.reviewer_id} title={`${item.reviewer_name} · ${OUTCOME[item.outcome] || item.outcome}`}><p className="authored-text">{item.note}</p><p className="small muted">Adımlar: {item.target_ids.join(', ')} · Kaynaklar: {item.source_refs.length ? item.source_refs.join(', ') : 'Bağlı alıntı beyan edilmedi'}</p></Detail>)}</>;
}
export function CohortSummary({ report }: { report: CohortReport }) {
  const count = report.counts;
  return <><p>{count.selected_records} seçilen kayıt · {count.profile_groups} ayrı ayar grubu · {count.declared_families} beyan edilen aile</p>
    <p className="small muted">Sabit kayıtta güncel dayanak: {count.current_source_records}/{count.selected_records} · Tam kayıt: {count.complete_capture_records}/{count.selected_records} · İki inceleyen: {count.current_reviewer_pairs}/{count.selected_records} · Aktif süre hesabı: {count.accounted_effort_records}/{count.selected_records}</p>
    <p>Farklı inceleyen sonuçları: {count.records_with_outcome_differences}/{count.selected_records} · Değerlendirilmemiş gözlem: {count.records_with_unknown_assessments}/{count.selected_records} · Çözülmemiş/eksik bulgu: {count.records_with_unresolved_findings}/{count.selected_records}</p>
    <p className="small muted">Geliştirme envanteri. Seçim tüm denemeleri temsil etmez. Kayıt tamamlanması hukuki doğruluk, uzman bağımsızlığı, ayrılmış değerlendirme veya süre kazancı kanıtı sağlamaz. Farklı ayarlar ve gerçek/kurgusal örnekler ayrı tutulur.</p>
    <Detail title="Aile ve tekrar incelemesi"><p>Tekrarlanan girdi grubu: {report.duplicate_inputs.length} · Aynı kaynak sürümü grubu: {report.repeated_versions.length} · Farklı ailelerde ortak özel belge: {report.cross_family_sources.length} · Ayrılmış aileyle örtüşme: {report.reserved_overlaps.length}</p>
      <p className="small muted">Aileler beyan edilmiştir; sistem benzer örnekleri keşfetmez veya bağımsızlığı doğrulamaz. Örtüşmeler otomatik birleştirilmez.</p>
      {report.families.map((item) => <p key={item.family_sha256} className="small">Aile {item.family_sha256.slice(0, 12)}… · {item.comparison_ids.length} kayıt · {item.reserved_overlap ? 'Ayrılan aileyle örtüşüyor' : 'Beyan edilen ayrılmış listede yok'}</p>)}
      {report.cross_family_sources.map((item) => <Detail key={item.document_id} title={`Ortak belge · ${item.document_id}`}><p>{item.selections.map((entry) => `${entry.comparison_id} / ${entry.family_sha256.slice(0, 12)}…`).join(' · ')}</p></Detail>)}
    </Detail></>;
}
export function CohortRows({ manifest, onSource }: { manifest: CohortManifest; onSource: (id: string) => void }) {
  const [opened, setOpened] = useState<string[]>([]);
  return <>{manifest.reconciliation.profiles.map((group, index) => <Detail key={group.profile_sha256} title={`Ayar grubu ${index + 1} · ${group.profile.provider_pin.model} · ${group.profile.sample_kind === 'synthetic' ? 'Kurgusal' : 'Gerçek beyanı'} · ${group.comparison_ids.length} kayıt`}>
    <p className="small muted">Ayar grubu: {group.profile_sha256} · Ölçüt: {group.profile.rubric_sha256}</p><p>Seçilen bulgu politikası: {group.profile.feedback_policy.selected ? 'Açık seçim' : 'Bulgu seçilmedi'}</p>
    {manifest.reconciliation.rows.filter((row) => row.profile_sha256 === group.profile_sha256).map((row) => <Detail key={row.comparison_id} title={row.title}>
      <p>{row.source_freshness.status === 'current' ? 'Sabit anda dayanak güncel' : 'Sabit anda dayanak güncel değildi'} · {row.current_reviewer_count}/2 inceleyen · {row.outcome_difference_count} farklı sonuç · {row.unknown_assessment_observations}/24 bilinmeyen anlamsal gözlem</p>
      {ARMS.map((arm) => { const value = row.arms[arm]; return <Detail key={arm} title={`${ARM_LABELS[arm]} · ${value.status === 'not_started' ? 'Başlatılmadı' : statusLabel(value.status)}`}>
        <p>{value.retained_passes} saklanan geçiş · Duvar saati: {cohortSeconds(value.elapsed_seconds)} · Sağlayıcı gidiş/dönüşü: {cohortSeconds(value.provider_round_trip_seconds)} · GPU hesap süresi: Bilinmiyor</p>
        <p>Aktif hazırlık: {cohortSeconds(value.active_effort?.preparation_seconds ?? null)} · Doğrulama/inceleme: {cohortSeconds(value.active_effort?.verification_seconds ?? null)} · Düzeltme: {cohortSeconds(value.active_effort?.correction_seconds ?? null)}</p>
        <p className="small muted">Tam aktif çalışma hesabı: {value.active_effort_accounted ? 'Dahil beyanı kaydedildi' : 'Eksik veya doğrulanmadı'} · Başarısız/eksik çalışmada toplam çağrı maliyeti bilinmiyor. Değerlendirme süresi ayrı tutulur.</p>
        {value.assessment_times.map((item) => <p key={item.reviewer_id} className="small">İnceleyen {item.reviewer_id} · Ayrı değerlendirme: {cohortSeconds(item.review_seconds)}</p>)}
        {value.dimensions.map((item) => <Detail key={item.dimension} title={`${item.label}${item.outcome_difference ? ' · Farklı sonuçlar' : ''}`}><p>{item.unknown_observations}/2 bilinmeyen gözlem</p><Outcomes values={item.observations} /></Detail>)}
        {value.findings.map((item) => <Detail key={item.finding_index} title={`Bulgu ${item.finding_index + 1} · ${item.target_id}${item.outcome_difference ? ' · Farklı sonuçlar' : ''}`}><p>{item.unresolved_or_missing ? 'Çözülmemiş veya eksik gözlem korunuyor.' : 'İnceleyen beyanları kaydedildi; hukuki onay verilmez.'}</p><Outcomes values={item.observations} /></Detail>)}
      </Detail>; })}
      <button className="text-button" onClick={() => setOpened((old) => old.includes(row.comparison_id) ? old.filter((id) => id !== row.comparison_id) : [...old, row.comparison_id])}>{opened.includes(row.comparison_id) ? 'Özgün deneme ayrıntılarını kapat' : 'Özgün deneme ve alıntıları aç'}</button>
      {opened.includes(row.comparison_id) && <ComparisonResults value={manifest.captures.find((item) => item.comparison_id === row.comparison_id)!.capture} onSource={onSource} />}
    </Detail>)}
  </Detail>)}</>;
}
export function FrozenCohort({ value, base, busy, onSource }: { value: CohortView; base: string; busy: boolean; onSource: (id: string) => void }) {
  return <article className="practice-record"><div className="practice-record-heading"><strong>{value.manifest.title}</strong><Badge>{value.freshness.status === 'stale' ? 'Grup dayanağı değişti' : 'Sabit kayıtla güncel durum eşleşiyor'}</Badge></div>
    <p className="small muted">Kaydedildi: {formatDate(value.registered_at, true)}</p>{value.freshness.status === 'stale' && <Notice>Deneme veya dayanaklar değişti. Aşağıdaki özet önceki sabit kaydı gösterir. Güncel kayıt için yeni önizleme ve ayrı grup kaydı oluşturun.</Notice>}
    <CohortSummary report={value.manifest.reconciliation} /><a className="text-button" href={busy ? undefined : `/api/v1${base}/${encodeURIComponent(value.id)}/export`} download aria-disabled={busy}>Özel sabit grup kaydını indir</a>
    <Detail title="Amaç, bütünlük ve değişiklikler"><p className="authored-text">{value.manifest.purpose}</p><p className="small muted">Grup özeti: {value.manifest_sha256}</p><p>Ayrılmış aile beyanı: {value.manifest.reserved_family_sha256.length ? `${value.manifest.reserved_family_sha256.length} aile` : 'Verilmedi; bağımsızlık değerlendirilmedi'}</p>{value.freshness.reasons.map((item, index) => <p key={index} className="small">{item.comparison_id || 'Grup kuralları'} · {item.code === 'selected_record_unavailable' ? 'Seçilen kayıt kullanılamıyor' : item.code === 'cohort_recipe_changed' ? 'Grup değerlendirme kuralları değişti' : 'Deneme veya dayanağı değişti'}</p>)}</Detail>
    <CohortRows manifest={value.manifest} onSource={onSource} />
  </article>;
}

export default function AnalysisCohorts({ matterId, onSource }: { matterId: string; onSource: (id: string) => void }) {
  const base = `/matters/${encodeURIComponent(matterId)}/analysis-cohorts`;
  const [candidates, setCandidates] = useState<CohortCandidate[]>([]); const [selected, setSelected] = useState<CohortCandidate[]>([]);
  const [title, setTitle] = useState(''); const [purpose, setPurpose] = useState(''); const [reserved, setReserved] = useState('');
  const [records, setRecords] = useState<{ id: string; title: string }[]>([]); const [preview, setPreview] = useState<CohortPreview | null>(null); const [value, setValue] = useState<CohortView | null>(null);
  const [busy, setBusy] = useState(false); const [error, setError] = useState(''); const [candidateMore, setCandidateMore] = useState(false); const [recordMore, setRecordMore] = useState(false);
  const controller = useRef<AbortController | null>(null); const pending = useRef<{ key: string; id: string } | null>(null);
  useEffect(() => () => controller.current?.abort(), []);
  async function action<T>(task: (signal: AbortSignal) => Promise<T>, apply: (result: T) => void) {
    if (busy) return; const current = new AbortController(); controller.current = current; setBusy(true); setError('');
    try { const result = await task(current.signal); if (!current.signal.aborted) apply(result); }
    catch (cause) { if (!current.signal.aborted) setError(messageOf(cause)); }
    finally { if (!current.signal.aborted) setBusy(false); }
  }
  function changed() { setPreview(null); }
  function loadCandidates(append = false) { void action((signal) => request<CohortCandidate[]>(`${base}/candidates?limit=10&offset=${append ? candidates.length : 0}`, { signal }), (page) => { setCandidates((old) => append ? [...old, ...page.filter((item) => !old.some((entry) => entry.comparison_id === item.comparison_id))] : page); setCandidateMore(page.length === 10); }); }
  function loadRecords(append = false) { void action((signal) => request<{ id: string; title: string }[]>(`${base}?limit=10&offset=${append ? records.length : 0}`, { signal }), (page) => { setRecords((old) => append ? [...old, ...page.filter((item) => !old.some((entry) => entry.id === item.id))] : page); setRecordMore(page.length === 10); }); }
  function examine() { void action(async (signal) => {
    const labels = reservedFamilyLabels(reserved); const hashes = await Promise.all(labels.map(async (label) => { const bytes = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(label)); return Array.from(new Uint8Array(bytes), (byte) => byte.toString(16).padStart(2, '0')).join(''); }));
    return request<CohortPreview>(`${base}/preview`, { method: 'POST', signal, body: JSON.stringify({ title, purpose, selections: selected.map(({ analysis_id, comparison_id }) => ({ analysis_id, comparison_id })), reserved_family_sha256: hashes }) });
  }, setPreview); }
  function freeze() { if (!preview) return; const body = { title: preview.manifest.title, purpose: preview.manifest.purpose, selections: preview.manifest.selections, reserved_family_sha256: preview.manifest.reserved_family_sha256, expected_preview_sha256: preview.preview_sha256 }; const key = JSON.stringify(body); if (pending.current?.key !== key) pending.current = { key, id: crypto.randomUUID().replaceAll('-', '') }; const requestId = pending.current.id;
    void action((signal) => request<CohortView>(base, { method: 'POST', signal, body: JSON.stringify({ ...body, request_id: requestId }) }), (result) => { pending.current = null; setValue(result); setPreview(null); setRecords((old) => [{ id: result.id, title: result.manifest.title }, ...old.filter((entry) => entry.id !== result.id)]); });
  }
  return <><p>Bu çalışma alanındaki kayıtlı denemeleri açık seçimle birlikte inceleyin. Sabit kayıt, farklı ayarlar, aile örtüşmeleri ve bilinmeyen ölçümleri korur; model çağrısı yapılmaz.</p>
    <div className="practice-record-actions"><button className="text-button" disabled={busy} onClick={() => loadCandidates()}>Bu çalışma alanının denemelerini getir</button><button className="text-button" disabled={busy} onClick={() => loadRecords()}>Sabit grup kayıtlarını getir</button></div>
    <form onSubmit={(event) => { event.preventDefault(); examine(); }}><Field label="Grup başlığı">{(id) => <input id={id} disabled={busy} maxLength={200} value={title} onChange={(event) => { setTitle(event.target.value); changed(); }} />}</Field><Field label="İnceleme amacı">{(id) => <textarea id={id} disabled={busy} rows={2} maxLength={2000} value={purpose} onChange={(event) => { setPurpose(event.target.value); changed(); }} />}</Field>
      <Detail title="Gelecekteki değerlendirme için ayrılmış aileler · İsteğe bağlı"><Field label="Her satıra bir aile adı">{(id) => <textarea id={id} disabled={busy} maxLength={12060} rows={3} value={reserved} onChange={(event) => { setReserved(event.target.value); changed(); }} />}</Field><p className="small muted">Deneme kaydındaki aynı aile adını kullanın. Bu beyan bağımsızlık veya ayrılmış değerlendirme onayı değildir. Boş bırakılırsa ayrılmış aile envanteri verilmemiştir.</p></Detail>
      <fieldset disabled={busy}><legend>2–12 kayıt seçin · {selected.length} seçildi</legend>{candidates.map((item) => <label key={item.comparison_id}><input type="checkbox" checked={selected.some((entry) => entry.comparison_id === item.comparison_id)} disabled={busy || (selected.length === 12 && !selected.some((entry) => entry.comparison_id === item.comparison_id))} onChange={(event) => { setSelected((old) => event.target.checked ? [...old, item] : old.filter((entry) => entry.comparison_id !== item.comparison_id)); changed(); }} />{item.title} · Sürüm {item.source_version} · {item.sample_kind === 'synthetic' ? 'Kurgusal' : 'Gerçek beyanı'}</label>)}</fieldset>
      {candidateMore && <button className="text-button" type="button" disabled={busy} onClick={() => loadCandidates(true)}>Önceki denemeleri getir</button>}<button className="button secondary" disabled={busy || selected.length < 2 || title.trim().length < 3 || purpose.trim().length < 3}>Seçimi ve eksikleri önizle</button>
    </form>
    {preview && <Detail title="Henüz kaydedilmemiş grup önizlemesi" open><CohortSummary report={preview.manifest.reconciliation} /><p className="small muted">Yalnız seçilen kayıtlar dondurulur. Yeni sonuç veya beyan gelirse yeniden önizleme gerekir.</p><CohortRows manifest={preview.manifest} onSource={onSource} /><button className="button secondary" disabled={busy} onClick={freeze}>Önizlemeye bağlı özel grup kaydını sabitle</button></Detail>}
    <Detail title={`Sabit grup kayıtları · ${records.length} getirildi`}>{records.map((record) => <button key={record.id} className="text-button" disabled={busy} onClick={() => void action((signal) => request<CohortView>(`${base}/${encodeURIComponent(record.id)}`, { signal }), setValue)}>{record.title}</button>)}{recordMore && <button className="text-button" disabled={busy} onClick={() => loadRecords(true)}>Önceki grup kayıtlarını getir</button>}</Detail>
    {value && <><button className="text-button" disabled={busy} onClick={() => void action((signal) => request<CohortView>(`${base}/${encodeURIComponent(value.id)}`, { signal }), setValue)}>Sabit grubun güncelliğini kontrol et</button><FrozenCohort key={`${value.id}:${value.manifest_sha256}`} value={value} base={base} busy={busy} onSource={onSource} /></>}{error && <Notice error>{error}</Notice>}
  </>;
}
