import { useEffect, useRef, useState } from 'react';
import { ApiError, downloadAuthorityTrial, post, request } from '../../api';
import { Badge, Detail, Field, Notice } from '../../components';
import { formatDate, isRunning, messageOf, statusLabel } from '../../utils';
import { ComparisonEffortForm, RegistrationForm } from './AnalysisComparisons';
import { LinkFields } from './AuthorityAdjudications';
import { occurrenceKey } from './authorityTypes';
import { LinkedAuthorityView } from './AnalysisAuthorities';
import AuthorityProposalSummary from './AuthorityProposalSummary';
import { adjudicationAssessment, JUDGMENT_OUTCOMES, SEMANTIC_DIMENSIONS, SEMANTIC_OUTCOMES } from './authorityAdjudicationTypes';
import type { AdverseScope, AssessmentInputs, FindingJudgment, SemanticObservation } from './authorityAdjudicationTypes';
import { FINDING_OUTCOMES } from './authorityFindingTypes';
import { blankTrialLinks } from './authorityModelTypes';
import type { ModelComparison, ModelInputSelection, ModelTrialCapture, ModelTrialEvidence, ModelTrialContext, TrialAssessment, TrialSourceInput } from './authorityModelTypes';
import { ARM_LABELS } from './comparisonTypes';
import type { ComparisonArm } from './comparisonTypes';

const ARMS = Object.keys(ARM_LABELS) as ComparisonArm[];
const seconds = (value: number | null) => value === null ? 'Ölçülmedi' : `${value.toFixed(3)} sn`;

export function TrialSummary({ value }: { value: ModelTrialEvidence }) {
  const plan = value.protocol;
  if (!plan || !value.public_source_access) return <Notice error>Kaynak veya kayıt kabulü doğrulanamadı; deneme metinleri bekletiliyor.</Notice>;
  return <><h4>{plan.title}</h4><Badge>{value.freshness.status === 'stale' ? 'Yeniden inceleme gerekli' : value.capture_complete ? 'Deneme kaydı tamamlandı' : 'Deneme kaydı eksik'}</Badge>
    <p>{value.current_reviewer_count}/2 atanmış inceleyen · Aktif çalışma hesabı {value.effort_accounted ? 'kaydedildi' : 'eksik'}</p>
    <p>{plan.authority_basis.input_ref.kind === 'admitted_renewal' ? 'Son kabul edilmiş kaynak bağı yenilemesi' : 'Güncel özgün kaynak incelemesi'} · Yerel model: {plan.provider_pin.model}</p>
    <p className="small">Adaylar çalışma taslağına alınmaz. Kayıt tamamlanması hukuki doğruluk, uzman bağımsızlığı, kaynak onayı veya model faydası değildir. Karşı dayanak kapsamı yalnız seçili kaynaklardır.</p>
    {plan.provider_pin.transport.uses_public_network && <p className="small">Onaylı dizüstü tüneli internet üzerinden yerel modele erişir; aktarım air-gapped değildir.</p>}
    {value.freshness.status === 'stale' && <Notice error>{value.freshness.reasons.join(' ')}</Notice>}
    <Detail title="Sabit soru, ölçütler ve kaynaklar"><p>{plan.question}</p><p>{plan.rubric_text}</p><p>{formatDate(plan.registered_at, true)} · Taslak {plan.source_version_id}</p><p className="reference-id">Protokol {plan.protocol_sha256} · Girdi {plan.task_input_sha256} · İnceleme {plan.authority_basis.input_ref.sha256}</p>
      {plan.authority_basis.assessment.sources.map((assessed, index) => { const source = plan.authority_basis.manifest.sources.find(item => occurrenceKey(item.selection) === occurrenceKey(assessed)); return <Detail key={index} title={`${index + 1}. özgün kamu kaynağı`}>{source && <LinkedAuthorityView source={source} />}{assessed.observations.map(item => <p key={item.dimension}>{plan.authority_basis.authority_dimensions[item.dimension]} · {FINDING_OUTCOMES[item.outcome]}: {item.note}</p>)}</Detail>; })}
    </Detail></>;
}

function TrialAssessmentForm({ value, comparison, busy, onChange }: { value: ModelTrialCapture; comparison: ModelComparison; busy: boolean; onChange: (value: TrialAssessment | null) => void }) {
  const plan = value.protocol!;
  const [observations, setObservations] = useState<SemanticObservation[]>(() => SEMANTIC_DIMENSIONS.map(dimension => ({ dimension, outcome: '', ...blankTrialLinks() })));
  const [judgments, setJudgments] = useState<FindingJudgment[]>(() => plan.authority_basis.assessment.sources.flatMap((source, source_index) => source.observations.map(item => ({ source_index, dimension: item.dimension, outcome: '', ...blankTrialLinks() }))));
  const [scope, setScope] = useState<AdverseScope>({ status: '', inspected_source_indices: [], limitations: '' });
  const [note, setNote] = useState(''); const [time, setTime] = useState('');
  const inputs: AssessmentInputs = { can_record: value.can_observe, basis: { comparison: {
    comparison_snapshot: { ...comparison, authority_review_snapshot: { assessment: plan.authority_basis.assessment } },
    assessment: { dispositions: judgments.map(({ source_index, dimension }) => ({ source_index, dimension })) },
  } } };
  const assessment = adjudicationAssessment(inputs, observations, judgments, scope, note, time);
  const serialized = JSON.stringify(assessment && { ...assessment, comparison_sha256: comparison.comparison_sha256 });
  useEffect(() => { onChange(JSON.parse(serialized)); }, [serialized]);
  return <fieldset disabled={busy}><legend>Bu aday için kendi kaynak bağlı görüşünüz</legend>
    {observations.map((item, index) => <Detail key={item.dimension} title={plan.dimensions[item.dimension]}><Field label="Anlam ve mantık görüşü">{id => <select id={id} value={item.outcome} onChange={event => setObservations(old => old.map((row, i) => i === index ? { ...row, outcome: event.target.value as SemanticObservation['outcome'] } : row))}><option value="">Görüş seçin</option>{Object.entries(SEMANTIC_OUTCOMES).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select>}</Field><LinkFields inputs={inputs} value={item} onChange={change => setObservations(old => old.map((row, i) => i === index ? { ...row, ...change } : row))} /></Detail>)}
    {judgments.map((item, index) => <Detail key={`${item.source_index}:${item.dimension}`} title={`${item.source_index + 1}. kaynak · ${plan.authority_basis.authority_dimensions[item.dimension]}`}><p>Özgün beyan: {plan.authority_basis.assessment.sources[item.source_index].observations.find(row => row.dimension === item.dimension)?.note}</p><Field label="Özgün bulguya ilişkin görüş">{id => <select id={id} value={item.outcome} onChange={event => setJudgments(old => old.map((row, i) => i === index ? { ...row, outcome: event.target.value as FindingJudgment['outcome'] } : row))}><option value="">Görüş seçin</option>{Object.entries(JUDGMENT_OUTCOMES).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select>}</Field><LinkFields inputs={inputs} value={item} onChange={change => setJudgments(old => old.map((row, i) => i === index ? { ...row, ...change } : row))} /></Detail>)}
    <Field label="Karşı dayanak araştırmasının kapsamı">{id => <select id={id} value={scope.status} onChange={event => setScope(old => ({ ...old, status: event.target.value as AdverseScope['status'], inspected_source_indices: [] }))}><option value="">Kapsam seçin</option><option value="not_searched">Araştırılmadı</option><option value="selected_sources_inspected">Yalnız seçili kaynaklar incelendi</option></select>}</Field>
    {scope.status === 'selected_sources_inspected' && <Field label="İncelenen kamu kaynakları">{id => <select id={id} multiple value={scope.inspected_source_indices.map(String)} onChange={event => setScope(old => ({ ...old, inspected_source_indices: Array.from(event.target.selectedOptions, item => Number(item.value)) }))}>{plan.authority_basis.assessment.sources.map((_, i) => <option key={i} value={i}>{i + 1}. kaynak</option>)}</select>}</Field>}
    <Field label="Araştırma sınırları ve eksikler">{id => <textarea id={id} maxLength={2000} value={scope.limitations} onChange={event => setScope(old => ({ ...old, limitations: event.target.value }))} />}</Field>
    <Field label="Bu aday için değerlendirme notu">{id => <textarea id={id} maxLength={2000} value={note} onChange={event => setNote(event.target.value)} />}</Field>
    <Field label="Ayrı değerlendirme süresi · saniye · Ölçülmediyse boş">{id => <input id={id} type="number" min={1} max={28800} value={time} onChange={event => setTime(event.target.value)} />}</Field>
  </fieldset>;
}

function TrialObservationForm({ value, busy, onSave }: { value: ModelTrialCapture; busy: boolean; onSave: (body: object) => void }) {
  const [assessments, setAssessments] = useState<Partial<Record<ComparisonArm, TrialAssessment | null>>>({}); const [note, setNote] = useState('');
  return <Detail title="İki kol için kendi gözlemimi kaydet"><form onSubmit={event => { event.preventDefault(); onSave({ note, execution_sha256: value.execution_sha256, expected_previous_id: value.previous_observation_id, arms: ARMS.map(arm => ({ arm, assessment: assessments[arm] })) }); }}>
    <p>Ekran kör değerlendirme sağlamaz. İki ayrı hesabın görüşleri korunur; anlaşmazlıklar bir oylamayla çözülmez.</p>
    {ARMS.map(arm => <Detail key={arm} title={ARM_LABELS[arm]}><TrialAssessmentForm value={value} comparison={value.arms[arm].comparison!} busy={busy} onChange={assessment => setAssessments(old => ({ ...old, [arm]: assessment }))} /></Detail>)}
    <Field label="İki kol gözleminin genel açıklaması">{id => <textarea id={id} maxLength={2000} value={note} onChange={event => setNote(event.target.value)} />}</Field>
    <button className="button secondary" type="submit" disabled={busy || note.trim().length < 3 || ARMS.some(arm => !assessments[arm])}>Kendi iki kol gözlemimi kaydet</button>
  </form></Detail>;
}

export function TrialResults({ value }: { value: ModelTrialEvidence }) {
  return <>{ARMS.map(arm => { const result = value.arms[arm]; return <Detail key={arm} title={`${ARM_LABELS[arm]} · ${result.status === 'not_started' ? 'Başlatılmadı' : statusLabel(result.status)}`}>
    <p>En fazla {value.protocol!.arms[arm].max_passes} geçiş / {value.protocol!.arms[arm].budget_seconds} sn · Saklanan geçiş: {result.job?.iterations?.length || 0}</p><p>Kuyruk dahil süre: {seconds(result.elapsed_seconds)} · Sağlayıcı gidiş/dönüşü: {seconds(result.provider_round_trip_seconds)} · GPU süresi: Ölçülmedi</p>
    <p className="small">Başarısız veya yarım işte toplam çağrı/maliyet bilinmiyor. Ek geçiş yalnız kritik yapısal kontrol kalırsa yapılır.</p>
    {result.job?.error && <Notice error>{result.job.error}</Notice>}
    {result.job?.authority_feedback && <AuthorityProposalSummary feedback={result.job.authority_feedback} responses={result.job.authority_responses} pass={result.job.authority_response_pass} />}
    {result.comparison && <><Detail title="Önceki taslak ve kaydedilmemiş aday arasındaki değişiklikler">{result.comparison.changes.map(item => <section key={item.target_id}><h4>{item.target_id}</h4><p>Önceki: {JSON.stringify(item.before)}</p><p>Aday: {JSON.stringify(item.after)}</p></section>)}</Detail><Detail title="Tam özgün özel pasajlar">{result.comparison.private_sources.map(source => <Detail key={source.source_ref} title={`${source.source_ref} · ${source.name}`}><p>{source.locator}</p><blockquote>{source.text}</blockquote></Detail>)}</Detail></>}
    {result.job?.iterations?.map(pass => <Detail key={pass.pass} title={`Geçiş ${pass.pass} · ${pass.outcome}`}><p>{pass.provider_seconds} sn · {pass.prompt.utf8_bytes} UTF-8 bayt</p>{pass.patch?.authority_responses && result.job?.authority_feedback && <AuthorityProposalSummary feedback={result.job.authority_feedback} responses={pass.patch.authority_responses} pass={pass.pass} />}</Detail>)}
  </Detail>; })}
    <Detail title={`Ayrı hesap gözlem geçmişi (${value.observations.length})`}>{value.observations.map(event => <Detail key={event.id} title={`${event.reviewer_name} · ${event.sequence}. kayıt`}><p>{event.note}</p>{event.arms.map(item => <Detail key={item.arm} title={ARM_LABELS[item.arm]}><p>{item.assessment.note} · Etkin inceleme: {seconds(item.assessment.review_seconds)}</p>{item.assessment.observations.map(row => <p key={row.dimension}>{value.protocol!.dimensions[row.dimension]} · {row.outcome && SEMANTIC_OUTCOMES[row.outcome]}: {row.note} · {row.target_refs.join(', ')} · {row.private_source_refs.join(', ')} · Kamu: {row.public_source_indices.map(i => i + 1).join(', ')}</p>)}{item.assessment.judgments.map(row => <p key={`${row.source_index}:${row.dimension}`}>{row.source_index + 1}. kaynak · {value.protocol!.authority_basis.authority_dimensions[row.dimension]} · {row.outcome && JUDGMENT_OUTCOMES[row.outcome]}: {row.note}</p>)}<p>Karşı dayanak kapsamı: {item.assessment.adverse_scope.status === 'not_searched' ? 'Araştırılmadı' : 'Yalnız seçili kaynaklar'} · {item.assessment.adverse_scope.limitations}</p></Detail>)}</Detail>)}</Detail>
    <Detail title="İnceleyen görüşleri arasındaki farklar">{value.disagreement === null ? <p>İki atanmış hesabın güncel görüşü olmadan farklar bilinmiyor.</p> : value.disagreement.length ? value.disagreement.map((item, index) => <p key={index}>{ARM_LABELS[item.arm]} · {item.item}: {item.outcomes.join(' / ')}</p>) : <p>Beyan edilen durumlar aynı; bu hukuki görüş birliği belgesi değildir.</p>}</Detail>
    <Detail title={`Aktif çalışma geçmişi (${value.effort_history.length})`}>{value.effort_history.map(event => <Detail key={event.id} title={`${event.reviewer_name} · ${event.sequence}. süre kaydı`}><p>{event.note}</p>{event.arms.map(item => <p key={item.arm}>{ARM_LABELS[item.arm]} · Hazırlık {seconds(item.preparation_seconds)} · Doğrulama {seconds(item.verification_seconds)} · Düzeltme {seconds(item.correction_seconds)}</p>)}<p>Ortak hazırlık {event.shared_setup_included ? 'dahil' : 'doğrulanmadı'} · Doğrulama/düzeltme {event.verification_and_correction_included ? 'dahil' : 'doğrulanmadı'} · Çakışmayan süre {event.active_phases_nonoverlapping ? 'beyan edildi' : 'doğrulanmadı'}</p></Detail>)}</Detail>
  </>;
}

export default function AuthorityModelTrials({ matterId, analysisId, sourceInput, onUnavailable }: { matterId: string; analysisId: string; sourceInput?: TrialSourceInput; onUnavailable?: (cause: unknown) => void }) {
  const base = `/matters/${encodeURIComponent(matterId)}/analyses/${encodeURIComponent(analysisId)}/authority-model-trials`;
  const [selected, setSelected] = useState<ModelInputSelection['findings']>([]); const [context, setContext] = useState<ModelTrialContext | null>(null);
  const [items, setItems] = useState<{ id: string; registered_at: string }[]>([]); const [more, setMore] = useState(false);
  const [value, setValue] = useState<ModelTrialCapture | null>(null); const [busy, setBusy] = useState(false); const [error, setError] = useState(''); const [nonoverlap, setNonoverlap] = useState(false);
  const pending = useRef<{ key: string; id: string } | null>(null); const mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  useEffect(() => { setNonoverlap(false); }, [value?.id, value?.execution_sha256, value?.previous_effort_id]);
  function fail(cause: unknown) { setContext(null); setValue(null); setItems([]); setError(cause instanceof ApiError && (cause.data as { status?: string })?.status === 'committed_needs_revalidation' ? 'Kayıt saklandı; son izin kontrolü tamamlanmadı. İçerik bekletiliyor; aynı isteği yinelemek kabulünü tamamlamaz.' : messageOf(cause)); onUnavailable?.(cause); }
  function accept(next: ModelTrialCapture) { if (!next.public_source_access || !next.protocol) fail(new Error('Kaynak veya kayıt kabulü bekletiliyor.')); else setValue(next); }
  async function operation(task: () => Promise<void>) { setBusy(true); setError(''); try { await task(); } catch (cause) { if (mounted.current) fail(cause); } finally { if (mounted.current) setBusy(false); } }
  async function inspect(id: string) { setValue(null); await operation(async () => { const next = await request<ModelTrialCapture>(`${base}/${encodeURIComponent(id)}`); if (mounted.current) accept(next); }); }
  const active = value?.public_source_access && Object.values(value.arms).some(arm => isRunning(arm.status));
  useEffect(() => { if (!active || !value) return; const controller = new AbortController(); let waiting = false;
    const timer = window.setInterval(async () => { if (waiting) return; waiting = true; try { const next = await request<ModelTrialCapture>(`${base}/${encodeURIComponent(value.id)}`, { signal: controller.signal }); if (!controller.signal.aborted) accept(next); } catch (cause) { if (!controller.signal.aborted) fail(cause); } finally { waiting = false; } }, 2500);
    return () => { controller.abort(); window.clearInterval(timer); }; }, [active, value?.id, base]);
  async function save(path: string, body: object) { await operation(async () => { const key = path + JSON.stringify(body); if (pending.current?.key !== key) pending.current = { key, id: crypto.randomUUID().replaceAll('-', '') }; await post(`${base}/${value!.id}/${path}`, { ...body, request_id: pending.current.id }); pending.current = null; const next = await request<ModelTrialCapture>(`${base}/${value!.id}`); if (mounted.current) accept(next); }); }
  async function register(body: object, family: string) { await operation(async () => { const hash = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(family.trim())); const input = { ...body, selection: context!.selection, split_family_sha256: Array.from(new Uint8Array(hash), byte => byte.toString(16).padStart(2, '0')).join('') }; const key = JSON.stringify(input); if (pending.current?.key !== key) pending.current = { key, id: crypto.randomUUID().replaceAll('-', '') }; const next = await post<ModelTrialCapture>(base, { ...input, request_id: pending.current.id }); if (mounted.current) { pending.current = null; setContext(null); accept(next); } }); }
  async function history(append = false) { await operation(async () => { const page = await request<{ id: string; registered_at: string }[]>(`${base}?limit=10&offset=${append ? items.length : 0}`); if (mounted.current) { setItems(old => append ? [...old, ...page] : page); setMore(page.length === 10); } }); }
  return <><p>Tek geçiş ve koşullu yapısal ek geçişi aynı özel taslak, seçilmiş kamu bulguları ve yerel modelle karşılaştırın. Taslak korunur; iki ayrı hesap özgün kaynaklarla görüş kaydeder.</p>
    {sourceInput && <><fieldset disabled={busy}><legend>İki kola aynı gönderilecek açık bulgular · En fazla beş</legend>{sourceInput.assessment.sources.map((source, index) => <Detail key={index} title={`${index + 1}. kaynak`}>{source.observations.map(item => { const checked = selected.some(row => row.source_index === index && row.dimension === item.dimension); return <label className="check-option" key={item.dimension}><input type="checkbox" checked={checked} disabled={item.outcome === 'supported' || (!checked && selected.length >= 5)} onChange={() => { setContext(null); setSelected(old => checked ? old.filter(row => row.source_index !== index || row.dimension !== item.dimension) : [...old, { source_index: index, dimension: item.dimension }]); }} />{sourceInput.dimensions[item.dimension]} · {FINDING_OUTCOMES[item.outcome]}: {item.note}</label>; })}</Detail>)}</fieldset><div className="practice-record-actions"><button className="text-button" disabled={busy || !selected.length} onClick={() => void operation(async () => { const next = await post<ModelTrialContext>(`${base}/registration-context`, { selection: { ...sourceInput.selection, findings: selected } }); if (mounted.current) setContext(next); })}>Seçilen bulgularla deneme protokolünü hazırla</button></div></>}
    {context && <RegistrationForm context={context} busy={busy} onSave={(body, family) => void register(body, family)} description="Mevcut taslak, özgün kamu pasajları ve seçili insan bulguları iki kol başlamadan sabitlenir. Henüz model çağrılmaz; deneme kaynak veya hukuki onay vermez." />}
    <div className="practice-record-actions"><button className="text-button" disabled={busy} onClick={() => void history()}>Kayıtlı model dayanak denemelerini getir</button></div>{items.map(item => <p key={item.id}><button className="text-button" disabled={busy} onClick={() => void inspect(item.id)}>{formatDate(item.registered_at, true)} · Denemeyi aç</button></p>)}{more && <button className="text-button" disabled={busy} onClick={() => void history(true)}>Önceki kayıtları getir</button>}
    {value && value.protocol && value.public_source_access && <><TrialSummary value={value} /><div className="practice-record-actions"><button className="text-button" disabled={busy} onClick={() => void inspect(value.id)}>Güncel deneme bağlarını kontrol et</button>{value.can_run && <button className="button secondary" disabled={busy} onClick={() => void operation(async () => { const next = await post<ModelTrialCapture>(`${base}/${value.id}/run`, {}); if (mounted.current) accept(next); })}>Kayıtlı iki kolu yerel modelde çalıştır</button>}<button className="text-button" disabled={busy || value.freshness.status !== 'current'} onClick={() => void operation(async () => { await downloadAuthorityTrial(`${base}/${value.id}`, value.id); })}>Özel deneme JSON kaydını indir</button></div>
      {ARMS.map(arm => value.arms[arm].job && isRunning(value.arms[arm].status) && <button key={arm} className="text-button" disabled={busy} onClick={() => void operation(async () => { await post(`${base.replace(/authority-model-trials$/, 'suggestions')}/${value.arms[arm].job!.id}/cancel`, {}); const next = await request<ModelTrialCapture>(`${base}/${value.id}`); if (mounted.current) accept(next); })}>{ARM_LABELS[arm]} · Durdur</button>)}
      <TrialResults value={value} />{value.can_observe && <TrialObservationForm key={`${value.execution_sha256}:${value.previous_observation_id}`} value={value} busy={busy} onSave={body => void save('observations', body)} />}
      {value.can_record_effort && <><label className="check-option"><input type="checkbox" checked={nonoverlap} disabled={busy} onChange={event => setNonoverlap(event.target.checked)} />Aktif çalışma bileşenleri çakışmıyor</label><ComparisonEffortForm key={`${value.execution_sha256}:${value.previous_effort_id}`} value={value} busy={busy || !nonoverlap} onSave={body => void save('effort', { ...body, active_phases_nonoverlapping: nonoverlap })} /></>}
    </>}{error && <Notice error>{error}</Notice>}
  </>;
}
