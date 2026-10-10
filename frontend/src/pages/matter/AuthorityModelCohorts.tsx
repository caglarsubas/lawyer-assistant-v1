import { useEffect, useRef, useState } from 'react';
import { ApiError, downloadAuthorityTrialCohort, request } from '../../api';
import { Badge, Detail, Field, Notice } from '../../components';
import { formatDate, messageOf, statusLabel } from '../../utils';
import { Dimension } from './AuthorityTrialCohorts';
import { TrialSummary, TrialResults } from './AuthorityModelTrials';
import { authorityReservedFamilies } from './authorityCohortTypes';
import { ARM_LABELS } from './comparisonTypes';
import type { ComparisonArm } from './comparisonTypes';
import { pendingModelCohort } from './authorityModelCohortTypes';
import type { ModelCohortCandidate, ModelCohortManifest, ModelCohortPreview, ModelCohortReport, ModelCohortView } from './authorityModelCohortTypes';

const seconds = (value: number | null) => value === null ? 'Bilinmiyor' : `${value.toFixed(3)} sn`;
export function ModelCohortSummary({ report }: { report: ModelCohortReport }) {
  const count = report.counts;
  return <><p><strong>{count.selected_records} seçilmiş model denemesi</strong> · {count.profile_groups} ayrı ayar grubu · {count.declared_families} beyan edilen aile</p>
    <p>{count.captures_present}/{count.selected_records} başlatılmış deneme · {count.complete_capture_records}/{count.selected_records} tam kayıt · {count.current_reviewer_pairs}/{count.selected_records} güncel görüş çifti · {count.accounted_effort_records}/{count.selected_records} tam süre beyanı</p>
    <p>{count.records_with_outcome_differences}/{count.selected_records} denemede farklı görüş · {count.records_with_unknown_observations}/{count.selected_records} denemede bilinmeyen gözlemler</p>
    <p className="small muted">Yalnız açıkça seçilmiş kayıtların sabit envanteri. Model çağrısı veya aday benimseme yapılmaz. Tam kayıt hukuki doğruluk, bağımsız inceleme, ayrılmış değerlendirme veya model faydası sağlamaz. Farklı ayarlar ve özgün/yenilenmiş kaynak girdileri birleştirilmez.</p>
    <Detail title="Aileler, tekrarlar ve ortak kaynaklar"><p>Tekrarlanan tam girdi: {report.duplicate_inputs.length} grup · Tekrarlanan özel taslak sürümü: {report.repeated_versions.length} grup · Farklı ailelerde ortak özel belge: {report.cross_family_private_sources.length} · Tekrarlanan kamu pasajı: {report.repeated_public_passages.length} · Ayrılmış aile örtüşmesi: {report.reserved_overlaps.length}</p>
      <p className="small muted">Aileler beyan edilir; yakın örnekler otomatik keşfedilmez. Pasaj ortaklığı aynı hukuki yorumu benimsemek veya yeni bir bağımsız örnek anlamına gelmez.</p>
      {report.families.map(item => <p key={item.family_sha256}>Aile {item.family_sha256.slice(0, 12)}… · {item.trial_ids.length} kayıt · {item.reserved_overlap ? 'Ayrılan aileyle örtüşüyor' : 'Ayrılan listede yok'}</p>)}
      {report.cross_family_private_sources.map(item => <Detail key={item.document_id} title={`Ortak özel belge · ${item.document_id}`}><p>{item.selections.map(selected => selected.trial_id).join(' · ')}</p></Detail>)}
      {report.repeated_public_passages.map((item, index) => <Detail key={index} title={`Ortak kamu pasajı ${index + 1}`}><p>{Object.values(item.selection).join(' · ')}</p><p>{item.selections.map(selected => selected.trial_id).join(' · ')}</p></Detail>)}
    </Detail></>;
}

export function ModelCohortRows({ manifest }: { manifest: ModelCohortManifest }) {
  return <>{manifest.reconciliation.profiles.map((profile, index) => <Detail key={profile.profile_sha256} title={`Ayar grubu ${index + 1} · ${profile.profile.sample_kind === 'synthetic' ? 'Sentetik' : 'Gerçek beyanı'} · ${profile.trial_ids.length} deneme`}>
    <p>{profile.profile.provider_pin.model} · {profile.profile.input_kind === 'admitted_renewal' ? 'Kabul edilmiş kaynak bağı yenilemesi' : 'Özgün kaynak incelemesi'}</p><p className="small reference-id">Tam ayar {profile.profile_sha256} · Ölçüt {profile.profile.rubric_sha256}</p>
    {manifest.reconciliation.rows.filter(row => row.profile_sha256 === profile.profile_sha256).map(row => <Detail key={row.trial_id} title={row.title}>
      <p>{row.source_freshness.status === 'current' ? 'Sabit anda bağlar güncel' : 'Sabit anda bağlar değişmişti'} · {row.current_reviewer_count}/2 güncel inceleyen · {row.capture_complete ? 'Tam kayıt' : 'Kayıt eksik'}</p>
      {(Object.keys(ARM_LABELS) as ComparisonArm[]).map(arm => { const value = row.arms[arm]; return <Detail key={arm} title={`${ARM_LABELS[arm]} · ${value.status === 'not_started' ? 'Başlatılmadı' : statusLabel(value.status)}`}>
        <p>{value.retained_passes} saklanan geçiş · Kuyruk dahil {seconds(value.elapsed_seconds)} · Sağlayıcı {seconds(value.provider_round_trip_seconds)} · GPU zamanı bilinmiyor</p>
        <p>Anlam: {value.unknown_semantic_observations}/{value.semantic_observation_slots} bilinmeyen · Bulgular: {value.unknown_finding_observations}/{value.finding_observation_slots} bilinmeyen · Farklı durum beyanı: {value.outcome_difference_count ?? 'Bilinmiyor'}</p>
        <Detail title="Kaynak bağlı görüşler ve çözülmemiş bulgular">{value.semantic.map(item => <Dimension key={item.dimension} value={item} />)}{value.findings.map(item => <Dimension key={`${item.source_index}:${item.dimension}`} value={item} />)}</Detail>
        <Detail title="Etkin çalışma ve karşı dayanak kapsamı"><p>{value.active_effort ? `Hazırlık ${seconds(value.active_effort.preparation_seconds)} · Doğrulama ${seconds(value.active_effort.verification_seconds)} · Düzeltme ${seconds(value.active_effort.correction_seconds)}` : 'Güncel aktif çalışma beyanı yok.'}</p><p>Hesap {value.active_effort_accounted ? 'tam beyan edilmiş' : 'eksik veya güncel değil'}. Süre kazancı ve karşı dayanak hatırlama oranı hesaplanmaz.</p>{value.assessment_times.map(item => <p key={item.reviewer_id}>{item.reviewer_id} · Ayrı değerlendirme {seconds(item.review_seconds)}</p>)}{value.adverse_scopes.map(item => <p key={item.reviewer_id}>{item.reviewer_id} · {item.scope.status === 'not_searched' ? 'Araştırılmadı' : 'Yalnız seçili kaynaklar'} · {item.scope.limitations}</p>)}</Detail>
      </Detail>; })}
      <Detail title="Tam özgün deneme, adaylar ve kaynak pasajları"><TrialSummary value={manifest.entries.find(item => item.trial_id === row.trial_id)!.capture} /><TrialResults value={manifest.entries.find(item => item.trial_id === row.trial_id)!.capture} /></Detail>
    </Detail>)}
  </Detail>)}</>;
}

export function ModelCohortContent({ value }: { value: ModelCohortView }) {
  if (!value.public_source_access || !value.manifest || value.freshness.status === 'withheld') return <Notice error>Model grubu metinleri, görüşler ve kaynak pasajları bekletiliyor; kaynak ve kayıt kabulünü kontrol edin.</Notice>;
  return <article className="practice-record"><div className="practice-record-heading"><strong>{value.manifest.title}</strong><Badge status={value.freshness.status}>{value.freshness.status === 'current' ? 'Grup bağları güncel' : 'Grup değişti · Aktarım kapalı'}</Badge></div>
    {value.freshness.status === 'stale' && <Notice>Özgün sabit kayıt korunur. Güncel grup için yeniden önizleyip ayrı kayıt oluşturun.</Notice>}
    <ModelCohortSummary report={value.manifest.reconciliation} /><Detail title="Amaç, bütünlük ve değişiklikler"><p>{value.manifest.purpose}</p><p className="reference-id">{value.manifest_sha256}</p>{value.freshness.reasons.map((reason, index) => <p key={index}>{reason.trial_id || 'Grup kuralları'} · {reason.code}</p>)}</Detail><ModelCohortRows manifest={value.manifest} />
  </article>;
}

export default function AuthorityModelCohorts({ matterId }: { matterId: string }) {
  const base = `/matters/${encodeURIComponent(matterId)}/authority-model-cohorts`;
  const [candidates, setCandidates] = useState<ModelCohortCandidate[]>([]); const [selected, setSelected] = useState<string[]>([]); const [candidateMore, setCandidateMore] = useState(false);
  const [records, setRecords] = useState<{ id: string; registered_at: string }[]>([]); const [recordMore, setRecordMore] = useState(false);
  const [title, setTitle] = useState(''); const [purpose, setPurpose] = useState(''); const [reserved, setReserved] = useState('');
  const [preview, setPreview] = useState<ModelCohortPreview | null>(null); const [view, setView] = useState<ModelCohortView | null>(null);
  const [busy, setBusy] = useState(false); const [error, setError] = useState(''); const [notice, setNotice] = useState('');
  const controller = useRef<AbortController | null>(null); const lock = useRef(false); const nonce = useRef<{ key: string; id: string } | null>(null);
  useEffect(() => () => { controller.current?.abort(); }, []);
  function clearReceived() { setPreview(null); setView(null); setCandidates([]); setRecords([]); setSelected([]); setCandidateMore(false); setRecordMore(false); }
  async function action<T>(run: (signal: AbortSignal) => Promise<T>, apply: (result: T) => void) {
    if (lock.current) return; lock.current = true; const current = new AbortController(); controller.current = current; setBusy(true); setError('');
    try { const result = await run(current.signal); if (!current.signal.aborted) apply(result); }
    catch (cause) { if (!current.signal.aborted) { clearReceived(); if (cause instanceof ApiError && pendingModelCohort(cause.data)) { setNotice('Grup saklandı; son izin kontrolü tamamlanmadı. İçerik bekletiliyor. Aynı isteği göndermek bu kaydı tamamlamaz.'); nonce.current = null; } else setError(messageOf(cause)); } }
    finally { lock.current = false; if (!current.signal.aborted) setBusy(false); }
  }
  function accept(result: ModelCohortView) { setPreview(null); setView(result); if (!result.public_source_access || result.freshness.status === 'withheld') { setCandidates([]); setSelected([]); setRecords([]); setCandidateMore(false); setRecordMore(false); } }
  function loadCandidates(append = false) { void action(signal => request<ModelCohortCandidate[]>(`${base}/candidates?limit=10&offset=${append ? candidates.length : 0}`, { signal, cache: 'no-store' }), page => { setPreview(null); setCandidates(old => append ? [...old, ...page.filter(item => !old.some(prior => prior.trial_id === item.trial_id))] : page); if (!append) setSelected([]); setCandidateMore(page.length === 10); }); }
  function loadRecords(append = false) { void action(signal => request<{ id: string; registered_at: string }[]>(`${base}?limit=10&offset=${append ? records.length : 0}`, { signal, cache: 'no-store' }), page => { setRecords(old => append ? [...old, ...page.filter(item => !old.some(prior => prior.id === item.id))] : page); setRecordMore(page.length === 10); }); }
  function examine() { void action(async signal => {
    const hashes = await Promise.all(authorityReservedFamilies(reserved).map(async label => { const bytes = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(label)); return Array.from(new Uint8Array(bytes), byte => byte.toString(16).padStart(2, '0')).join(''); }));
    return request<ModelCohortPreview>(`${base}/preview`, { method: 'POST', signal, cache: 'no-store', body: JSON.stringify({ title, purpose, selections: selected.map(trial_id => ({ trial_id })), reserved_family_sha256: hashes }) });
  }, result => { setView(null); setPreview(result); }); }
  function freeze() { if (!preview) return; const body = { title: preview.manifest.title, purpose: preview.manifest.purpose, selections: preview.manifest.selections, reserved_family_sha256: preview.manifest.reserved_family_sha256, expected_preview_sha256: preview.preview_sha256 }; const key = JSON.stringify(body); if (nonce.current?.key !== key) nonce.current = { key, id: crypto.randomUUID().replaceAll('-', '') }; const id = nonce.current.id;
    void action(signal => request<ModelCohortView>(base, { method: 'POST', signal, cache: 'no-store', body: JSON.stringify({ ...body, request_id: id }) }), result => { nonce.current = null; accept(result); if (result.public_source_access) setRecords(old => [{ id: result.id, registered_at: result.registered_at }, ...old.filter(item => item.id !== result.id)]); });
  }
  return <><p>Bu çalışma alanından 2–12 kayıtlı yerel model dayanak denemesi seçin. Eksik kayıtlar, farklı görüşler ve bilinmeyen süreler görünür kalır.</p>
    <div className="practice-record-actions"><button className="text-button" disabled={busy} onClick={() => loadCandidates()}>Model dayanak denemelerini getir</button><button className="text-button" disabled={busy} onClick={() => loadRecords()}>Sabit model gruplarını getir</button></div>
    <form className="authority-context-form" onSubmit={event => { event.preventDefault(); examine(); }}><fieldset disabled={busy}><legend>Dayanak grubu seçimi · {selected.length}/12</legend>
      <Field label="Dayanak grubu başlığı">{id => <input id={id} maxLength={200} value={title} onChange={event => { setTitle(event.target.value); setPreview(null); }} />}</Field><Field label="Dayanak grubu inceleme amacı">{id => <textarea id={id} maxLength={2000} rows={2} value={purpose} onChange={event => { setPurpose(event.target.value); setPreview(null); }} />}</Field>
      <Detail title="İsteğe bağlı ayrılmış örnek aileleri"><Field label="Her satıra aynı kayıt aile adını yazın">{id => <textarea id={id} rows={2} maxLength={12060} value={reserved} onChange={event => { setReserved(event.target.value); setPreview(null); }} />}</Field><p className="small muted">Boş liste beyan verilmedi demektir. Bu seçim bağımsızlık veya değerlendirme onayı sağlamaz.</p></Detail>
      <p>Açık seçim · {selected.length}/12</p>{candidates.map(item => <label className="check-option" key={item.trial_id}><input type="checkbox" checked={selected.includes(item.trial_id)} disabled={!item.admission_complete || (!selected.includes(item.trial_id) && selected.length >= 12)} onChange={event => { setSelected(old => event.target.checked ? [...old, item.trial_id] : old.filter(id => id !== item.trial_id)); setPreview(null); }} /><span>{formatDate(item.registered_at, true)} · {item.trial_id} · {item.admission_complete ? 'Kayıt kabul edilmiş; içeriği önizlemede kontrol edin' : 'Kayıt kabulü bekletiliyor'}</span></label>)}
      {candidateMore && <button type="button" className="text-button" onClick={() => loadCandidates(true)}>Önceki dayanak denemelerini getir</button>}<button className="button secondary" type="submit" disabled={selected.length < 2 || title.trim().length < 3 || purpose.trim().length < 3}>Dayanak grubu seçimini önizle</button>
    </fieldset></form>
    {preview && <Detail title="Kaydedilmemiş dayanak grubu önizlemesi" open><ModelCohortSummary report={preview.manifest.reconciliation} /><ModelCohortRows manifest={preview.manifest} /><p className="small muted">Deneme, görüş veya dayanak değişirse yeniden önizleme gerekir. Yalnız bu seçim saklanır.</p><button className="button secondary" disabled={busy} onClick={freeze}>Önizlemeye bağlı dayanak grubunu sabitle</button></Detail>}
    <Detail title={`Sabit dayanak grupları · ${records.length} getirildi`}>{records.map(item => <button key={item.id} className="text-button" disabled={busy} onClick={() => void action(signal => request<ModelCohortView>(`${base}/${encodeURIComponent(item.id)}`, { signal, cache: 'no-store' }), accept)}>Grubu aç · {formatDate(item.registered_at, true)}</button>)}{recordMore && <button className="text-button" disabled={busy} onClick={() => loadRecords(true)}>Önceki dayanak gruplarını getir</button>}</Detail>
    {view && <><ModelCohortContent key={`${view.id}:${view.manifest_sha256}:${view.freshness.status}`} value={view} /><div className="practice-record-actions"><button className="text-button" disabled={busy} onClick={() => void action(signal => request<ModelCohortView>(`${base}/${encodeURIComponent(view.id)}`, { signal, cache: 'no-store' }), accept)}>Dayanak grubunun güncelliğini kontrol et</button><button className="text-button" disabled={busy || !view.public_source_access || view.freshness.status !== 'current'} onClick={() => void action(() => downloadAuthorityTrialCohort(base, view.id), () => undefined)}>Özel dayanak grubu JSON paketini indir</button></div></>}
    {notice && <Notice>{notice}</Notice>}{error && <Notice error>{error}</Notice>}
  </>;
}
