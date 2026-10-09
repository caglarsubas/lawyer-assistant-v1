import { useEffect, useRef, useState } from 'react';
import { ApiError, downloadAuthorityTrialCohort, request } from '../../api';
import { Badge, Detail, Field, Notice } from '../../components';
import { formatDate, messageOf } from '../../utils';
import { TrialContent } from './AuthorityTrials';
import { SEMANTIC_OUTCOMES, JUDGMENT_OUTCOMES } from './authorityAdjudicationTypes';
import { authorityReservedFamilies, pendingAuthorityCohort } from './authorityCohortTypes';
import type { AuthorityCohortCandidate, AuthorityCohortDimension, AuthorityCohortManifest, AuthorityCohortPreview, AuthorityCohortReport, AuthorityCohortView } from './authorityCohortTypes';

const seconds = (value: number | null) => value === null ? 'Bilinmiyor' : `${value} saniye`;
const outcomeLabels: Record<string, string> = { ...SEMANTIC_OUTCOMES, ...JUDGMENT_OUTCOMES };
export function AuthorityCohortSummary({ report }: { report: AuthorityCohortReport }) {
  const count = report.counts;
  return <><p><strong>{count.selected_records} seçilmiş deneme</strong> · {count.profile_groups} ayrı ayar grubu · {count.declared_families} beyan edilen aile</p>
    <p>{count.captures_present}/{count.selected_records} saklanan deneme kaydı · {count.current_reviewer_pairs}/{count.selected_records} güncel görüş çifti · {count.accounted_effort_records}/{count.selected_records} tam süre beyanı</p>
    <p>{count.records_with_outcome_differences}/{count.selected_records} denemede farklı sonuç beyanları · {count.records_with_unknown_observations}/{count.selected_records} denemede bilinmeyen gözlemler</p>
    <p className="small muted">Yalnız seçilen kayıtlar incelenir. Kayıt bulunması doğruluk veya yeterli inceleme anlamına gelmez. Hukuki onay, bağımsızlık, ayrılmış değerlendirme ve süre kazancı hesaplanmaz. Özgün taslak kayıt öncesi hazırlanmıştır; bu çalışma insan revizyonudur.</p>
    <Detail title="Aileler, tekrarlar ve ortak kaynaklar"><p>Tekrarlanan olgu girdisi: {report.duplicate_inputs.length} grup · Aynı özgün sürüm: {report.repeated_versions.length} grup · Farklı ailelerde ortak özel belge: {report.cross_family_private_sources.length} · Tekrarlanan kamu pasajı: {report.repeated_public_passages.length} · Ayrılmış aileyle örtüşme: {report.reserved_overlaps.length}</p>
      <p className="small muted">Aileler beyan edilmiştir; yakın örnekler veya bağımsızlık keşfedilmez. Aynı pasajı seçmek aynı hukuki yorumu benimsemek anlamına gelmez.</p>
      {report.families.map(item => <p key={item.family_sha256} className="small">Aile {item.family_sha256.slice(0, 12)}… · {item.trial_ids.length} kayıt · {item.reserved_overlap ? 'Ayrılan aileyle örtüşüyor' : 'Ayrılmış beyan listesinde yok'}</p>)}
      {report.cross_family_private_sources.map(item => <Detail key={item.document_id} title={`Ortak özel belge · ${item.document_id}`}><p>{item.selections.map(selected => `${selected.trial_id} / ${selected.family_sha256.slice(0, 12)}…`).join(' · ')}</p></Detail>)}
      {report.repeated_public_passages.map((item, index) => <Detail key={index} title={`Ortak kamu pasajı ${index + 1}`}><p>{Object.values(item.selection).join(' · ')}</p><p>{item.selections.map(selected => selected.trial_id).join(' · ')}</p></Detail>)}
    </Detail></>;
}

function Dimension({ value }: { value: AuthorityCohortDimension }) {
  return <Detail title={`${value.source_index === undefined ? '' : `Kaynak ${value.source_index + 1} · `}${value.label}${value.outcome_difference ? ' · Farklı sonuçlar' : ''}`}>
    <p>{value.unknown_observations}/2 bilinmeyen veya çözümlenmemiş gözlem · {value.outcome_difference === null ? 'Görüş çifti eksik; fark bilinmiyor' : value.outcome_difference ? 'Farklı beyanlar korunuyor' : 'Kaydedilen sonuç etiketleri aynı; doğruluk değerlendirilmedi'}</p>
    {value.observations.map(item => <Detail key={item.reviewer_id} title={`${item.reviewer_name} · ${outcomeLabels[item.outcome] || item.outcome}`}><p className="authored-text">{item.note}</p><p className="small">Hedefler: {item.target_refs.join(', ') || 'Seçilmedi'} · Özel pasajlar: {item.private_source_refs.join(', ') || 'Seçilmedi'} · Kamu kaynakları: {item.public_source_indices.map(index => index + 1).join(', ') || 'Seçilmedi'}</p></Detail>)}
  </Detail>;
}

export function AuthorityCohortRows({ manifest }: { manifest: AuthorityCohortManifest }) {
  const [opened, setOpened] = useState<string[]>([]);
  return <>{manifest.reconciliation.profiles.map((profile, index) => <Detail key={profile.profile_sha256} title={`Ayar grubu ${index + 1} · ${profile.profile.sample_kind === 'synthetic' ? 'Sentetik' : 'Gerçek beyanı'} · ${profile.trial_ids.length} deneme`}>
    <p className="small muted">Tam ayar özeti: {profile.profile_sha256}. Farklı ayarlar birleştirilmez; model çağrısı yapılmaz.</p>
    {manifest.reconciliation.rows.filter(row => row.profile_sha256 === profile.profile_sha256).map(row => <Detail key={row.trial_id} title={row.title}>
      <p>{row.source_freshness.status === 'current' ? 'Sabit anda dayanak güncel' : 'Sabit anda dayanak değişmişti'} · {row.capture_present ? 'Deneme kaydı mevcut' : 'Deneme kaydı yok'} · {row.current_reviewer_count}/2 güncel ayrı görüş</p>
      <p>Anlam: {row.unknown_semantic_observations}/{row.semantic_observation_slots} bilinmeyen gözlem · Bulgular: {row.unknown_finding_observations}/{row.finding_observation_slots} bilinmeyen gözlem · Farklı beyan: {row.outcome_difference_count ?? 'Bilinmiyor'}</p>
      <Detail title="Beyan edilen etkin iş ve ayrı değerlendirme süreleri"><p>Boş değer bilinmiyor; açık sıfır o aşamada çalışma olmadığı beyanıdır. Bekleme süresi dahil değildir. Özgün hazırlık süresi geriye dönük beyan edilir.</p>
        {row.recorded_effort ? row.recorded_effort.arms.map(arm => <p key={arm.arm}>{arm.arm === 'original' ? 'Özgün' : 'Revize'} · Hazırlama: {seconds(arm.preparation_seconds)} · İnceleme: {seconds(arm.verification_seconds)} · Düzeltme: {seconds(arm.correction_seconds)}</p>) : <p>İş süresi kaydı yok.</p>}
        <p>Tam süre hesabı: {row.effort_accounted ? 'Beyan edildi' : 'Eksik veya güncel değil'}. Ayrı değerlendirme süresi iş süresine otomatik eklenmez. Süre kazancı ve GPU hesap süresi bilinmiyor.</p>
        {row.assessment_times.map(item => <p key={item.reviewer_id}>İnceleyen {item.reviewer_id} · Ayrı değerlendirme: {seconds(item.review_seconds)}</p>)}
      </Detail>
      <Detail title="Anlam, mantık ve belirsizlik gözlemleri">{row.semantic.map(item => <Dimension key={item.dimension} value={item} />)}</Detail>
      <Detail title="Özgün kaynak bulgularına ilişkin görüşler">{row.findings.map(item => <Dimension key={`${item.source_index}:${item.dimension}`} value={item} />)}</Detail>
      <Detail title="Karşı dayanak aramasının beyan edilen kapsamı"><p>Karşı dayanak hatırlama oranı ve tüm külliyatın kapsamı bilinmiyor.</p>{row.adverse_scopes.map(item => <p key={item.reviewer_id} className="authored-text">{item.reviewer_id} · {item.scope.status === 'not_searched' ? 'Aranmadı' : 'Yalnız seçilen kaynaklar incelendi'} · {item.scope.limitations}</p>)}</Detail>
      <button className="text-button" onClick={() => setOpened(old => old.includes(row.trial_id) ? old.filter(id => id !== row.trial_id) : [...old, row.trial_id])}>{opened.includes(row.trial_id) ? 'Özgün deneme ve pasajları kapat' : 'Özgün deneme ve pasajları aç'}</button>
      {opened.includes(row.trial_id) && <TrialContent value={manifest.entries.find(item => item.trial_id === row.trial_id)!.capture} />}
    </Detail>)}
  </Detail>)}</>;
}

export function AuthorityCohortContent({ value }: { value: AuthorityCohortView }) {
  if (!value.public_source_access || !value.manifest || value.freshness.status === 'withheld') return <Notice error>Grup içeriği, notlar ve kaynak pasajları bekletiliyor. Kaynak izinlerini ve seçilen kayıtları yeniden kontrol edin.</Notice>;
  return <article className="practice-record"><div className="practice-record-heading"><strong>{value.manifest.title}</strong><Badge status={value.freshness.status}>{value.freshness.status === 'current' ? 'Grup bağları güncel' : 'Grup dayanağı değişti · Aktarım kapalı'}</Badge></div>
    <p className="small muted">Sabit kayıt: {formatDate(value.registered_at, true)}</p>{value.freshness.status === 'stale' && <Notice>Önceki sabit kayıt korunuyor. Yeni dayanaklar bu kayıt üzerine yazılmaz; güncel grup için yeniden önizleyip ayrı kayıt oluşturun.</Notice>}
    <AuthorityCohortSummary report={value.manifest.reconciliation} />
    <Detail title="Amaç, bütünlük ve değişiklikler"><p className="authored-text">{value.manifest.purpose}</p><p className="small">Sabit grup SHA-256: {value.manifest_sha256}</p><p>Ayrılmış aile beyanı: {value.manifest.reserved_family_sha256.length ? `${value.manifest.reserved_family_sha256.length} aile` : 'Verilmedi; bağımsızlık değerlendirilmedi'}</p>{value.freshness.reasons.map((reason, index) => <p key={index} className="small">{reason.trial_id || 'Grup kuralları'} · {reason.code}</p>)}</Detail>
    <AuthorityCohortRows manifest={value.manifest} />
  </article>;
}

export default function AuthorityTrialCohorts({ matterId }: { matterId: string }) {
  const base = `/matters/${encodeURIComponent(matterId)}/authority-trial-cohorts`;
  const [candidates, setCandidates] = useState<AuthorityCohortCandidate[]>([]); const [selected, setSelected] = useState<string[]>([]); const [candidateMore, setCandidateMore] = useState(false);
  const [records, setRecords] = useState<{ id: string; registered_at: string }[]>([]); const [recordMore, setRecordMore] = useState(false);
  const [title, setTitle] = useState(''); const [purpose, setPurpose] = useState(''); const [reserved, setReserved] = useState('');
  const [preview, setPreview] = useState<AuthorityCohortPreview | null>(null); const [view, setView] = useState<AuthorityCohortView | null>(null);
  const [busy, setBusy] = useState(false); const [error, setError] = useState(''); const [notice, setNotice] = useState('');
  const controller = useRef<AbortController | null>(null); const lock = useRef(false); const nonce = useRef<{ key: string; id: string } | null>(null);
  useEffect(() => () => { controller.current?.abort(); }, []);
  function clearReceived() { setPreview(null); setView(null); setCandidates([]); setRecords([]); setSelected([]); setCandidateMore(false); setRecordMore(false); }
  async function action<T>(run: (signal: AbortSignal) => Promise<T>, apply: (result: T) => void) {
    if (lock.current) return; lock.current = true; const current = new AbortController(); controller.current = current; setBusy(true); setError('');
    try { const result = await run(current.signal); if (!current.signal.aborted) apply(result); }
    catch (cause) { if (!current.signal.aborted) { clearReceived(); if (cause instanceof ApiError && pendingAuthorityCohort(cause.data)) { setNotice('Grup saklandı; son izin kontrolü tamamlanmadı. İçerik bekletiliyor. Aynı isteği göndermek bu kaydı tamamlamaz.'); nonce.current = null; } else setError(messageOf(cause)); } }
    finally { lock.current = false; if (!current.signal.aborted) setBusy(false); }
  }
  function accept(result: AuthorityCohortView) { setPreview(null); setView(result); if (!result.public_source_access || result.freshness.status === 'withheld') { setCandidates([]); setSelected([]); setRecords([]); setCandidateMore(false); setRecordMore(false); } }
  function loadCandidates(append = false) { void action(signal => request<AuthorityCohortCandidate[]>(`${base}/candidates?limit=10&offset=${append ? candidates.length : 0}`, { signal, cache: 'no-store' }), page => { setPreview(null); setCandidates(old => append ? [...old, ...page.filter(item => !old.some(prior => prior.trial_id === item.trial_id))] : page); if (!append) setSelected([]); setCandidateMore(page.length === 10); }); }
  function loadRecords(append = false) { void action(signal => request<{ id: string; registered_at: string }[]>(`${base}?limit=10&offset=${append ? records.length : 0}`, { signal, cache: 'no-store' }), page => { setRecords(old => append ? [...old, ...page.filter(item => !old.some(prior => prior.id === item.id))] : page); setRecordMore(page.length === 10); }); }
  function examine() { void action(async signal => {
    const hashes = await Promise.all(authorityReservedFamilies(reserved).map(async label => { const bytes = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(label)); return Array.from(new Uint8Array(bytes), byte => byte.toString(16).padStart(2, '0')).join(''); }));
    return request<AuthorityCohortPreview>(`${base}/preview`, { method: 'POST', signal, cache: 'no-store', body: JSON.stringify({ title, purpose, selections: selected.map(trial_id => ({ trial_id })), reserved_family_sha256: hashes }) });
  }, result => { setView(null); setPreview(result); }); }
  function freeze() { if (!preview) return; const body = { title: preview.manifest.title, purpose: preview.manifest.purpose, selections: preview.manifest.selections, reserved_family_sha256: preview.manifest.reserved_family_sha256, expected_preview_sha256: preview.preview_sha256 }; const key = JSON.stringify(body); if (nonce.current?.key !== key) nonce.current = { key, id: crypto.randomUUID().replaceAll('-', '') }; const id = nonce.current.id;
    void action(signal => request<AuthorityCohortView>(base, { method: 'POST', signal, cache: 'no-store', body: JSON.stringify({ ...body, request_id: id }) }), result => { nonce.current = null; accept(result); if (result.public_source_access) setRecords(old => [{ id: result.id, registered_at: result.registered_at }, ...old.filter(item => item.id !== result.id)]); });
  }
  return <><p>Bu çalışma alanından 2–12 kayıtlı insan revizyonu denemesi seçin. Eksik kayıtlar, farklı görüşler ve bilinmeyen süreler görünür kalır.</p>
    <div className="practice-record-actions"><button className="text-button" disabled={busy} onClick={() => loadCandidates()}>Dayanak denemelerini getir</button><button className="text-button" disabled={busy} onClick={() => loadRecords()}>Sabit dayanak gruplarını getir</button></div>
    <form className="authority-context-form" onSubmit={event => { event.preventDefault(); examine(); }}><fieldset disabled={busy}><legend>Dayanak grubu seçimi · {selected.length}/12</legend>
      <Field label="Dayanak grubu başlığı">{id => <input id={id} maxLength={200} value={title} onChange={event => { setTitle(event.target.value); setPreview(null); }} />}</Field><Field label="Dayanak grubu inceleme amacı">{id => <textarea id={id} maxLength={2000} rows={2} value={purpose} onChange={event => { setPurpose(event.target.value); setPreview(null); }} />}</Field>
      <Detail title="İsteğe bağlı ayrılmış örnek aileleri"><Field label="Her satıra aynı kayıt aile adını yazın">{id => <textarea id={id} rows={2} maxLength={12060} value={reserved} onChange={event => { setReserved(event.target.value); setPreview(null); }} />}</Field><p className="small muted">Boş liste beyan verilmedi demektir. Bu seçim bağımsızlık veya değerlendirme onayı sağlamaz.</p></Detail>
      <p>Açık seçim · {selected.length}/12</p>{candidates.map(item => <label className="checkbox-label" key={item.trial_id}><input type="checkbox" checked={selected.includes(item.trial_id)} disabled={item.freshness.status === 'withheld' || (!selected.includes(item.trial_id) && selected.length >= 12)} onChange={event => { setSelected(old => event.target.checked ? [...old, item.trial_id] : old.filter(id => id !== item.trial_id)); setPreview(null); }} /><span>{item.title || 'İçerik bekletiliyor'} · {item.capture_present ? 'Kayıt mevcut' : 'Deneme kaydı yok'} · {item.freshness.status === 'current' ? 'Bağlar güncel' : 'Yeniden inceleme gerekli'}</span></label>)}
      {candidateMore && <button type="button" className="text-button" onClick={() => loadCandidates(true)}>Önceki dayanak denemelerini getir</button>}<button className="button secondary" type="submit" disabled={selected.length < 2 || title.trim().length < 3 || purpose.trim().length < 3}>Dayanak grubu seçimini önizle</button>
    </fieldset></form>
    {preview && <Detail title="Kaydedilmemiş dayanak grubu önizlemesi" open><AuthorityCohortSummary report={preview.manifest.reconciliation} /><AuthorityCohortRows manifest={preview.manifest} /><p className="small muted">Deneme, görüş veya dayanak değişirse yeniden önizleme gerekir. Yalnız bu seçim saklanır.</p><button className="button secondary" disabled={busy} onClick={freeze}>Önizlemeye bağlı dayanak grubunu sabitle</button></Detail>}
    <Detail title={`Sabit dayanak grupları · ${records.length} getirildi`}>{records.map(item => <button key={item.id} className="text-button" disabled={busy} onClick={() => void action(signal => request<AuthorityCohortView>(`${base}/${encodeURIComponent(item.id)}`, { signal, cache: 'no-store' }), accept)}>Grubu aç · {formatDate(item.registered_at, true)}</button>)}{recordMore && <button className="text-button" disabled={busy} onClick={() => loadRecords(true)}>Önceki dayanak gruplarını getir</button>}</Detail>
    {view && <><AuthorityCohortContent key={`${view.id}:${view.manifest_sha256}:${view.freshness.status}`} value={view} /><div className="practice-record-actions"><button className="text-button" disabled={busy} onClick={() => void action(signal => request<AuthorityCohortView>(`${base}/${encodeURIComponent(view.id)}`, { signal, cache: 'no-store' }), accept)}>Dayanak grubunun güncelliğini kontrol et</button><button className="text-button" disabled={busy || !view.public_source_access || view.freshness.status !== 'current'} onClick={() => void action(() => downloadAuthorityTrialCohort(base, view.id), () => undefined)}>Özel dayanak grubu JSON paketini indir</button></div></>}
    {notice && <Notice>{notice}</Notice>}{error && <Notice error>{error}</Notice>}
  </>;
}
