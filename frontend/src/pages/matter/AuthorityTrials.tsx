import { useEffect, useRef, useState } from 'react';
import { ApiError, downloadAuthorityTrial, post, request } from '../../api';
import { Badge, Detail, Field, Notice } from '../../components';
import { formatDate, messageOf } from '../../utils';
import { ComparisonEvidence } from './AuthorityComparisons';
import type { FindingSummary } from './authorityFindingTypes';
import { JUDGMENT_OUTCOMES, SEMANTIC_OUTCOMES } from './authorityAdjudicationTypes';
import { EFFORT_PHASES, pendingTrial, TRIAL_ARMS, trialEffort, trialReviewers } from './authorityTrialTypes';
import type { EditableTrialEffort, TrialCaptureContext, TrialRegistrationContext, TrialView } from './authorityTrialTypes';

const armLabels = { original: 'Özgün çalışma', revised: 'Revize çalışma' };
const phaseLabels = { preparation_seconds: 'Hazırlama', verification_seconds: 'Doğrulama / avukat incelemesi', correction_seconds: 'Düzeltme' };
const freshEffort = (): EditableTrialEffort[] => TRIAL_ARMS.map(arm => ({ arm, preparation_seconds: '', verification_seconds: '', correction_seconds: '' }));

export function TrialContent({ value }: { value: TrialView }) {
  if (!value.public_source_access || !value.protocol) return <Notice error>Protokol, notlar ve kaynak alıntıları bekletiliyor. Kaynak bağlarını yeniden açın.</Notice>;
  const data = value.snapshot; const rubric = value.protocol.basis.rubric;
  return <><h4>{value.protocol.title}</h4><p className="authored-text">{value.protocol.question}</p>
    <Badge status={value.freshness.status}>{value.freshness.status === 'current' ? 'Deneme bağları güncel' : 'Yeniden inceleme gerekli · Aktarım kapalı'}</Badge>
    <p className="small">{value.capture_complete ? 'Gerekli kayıtlar mevcut' : 'Kayıtlar / ölçümler eksik'}. Bu durum doğruluk, hukuki onay veya zaman kazancı kanıtı değildir.</p>
    <p className="small">Revizyondan önce kayıt; özgün taslak kayıt öncesi hazırlanmıştır. Sabit olgu ve alıntılarla insan revizyonu. Model karşılaştırması veya kör inceleme yapılmaz.</p>
    <Detail title="Sabit değerlendirme ölçütleri">{Object.entries(rubric).map(([key, text]) => <p key={key}>{text}</p>)}<p>Örnek türü: {value.protocol.sample_kind === 'synthetic' ? 'Sentetik' : 'Gerçek olarak beyan edildi'}. Mesleki yeterlilik ve gerçek bağımsızlık ayrıca doğrulanır.</p></Detail>
    {data ? <><p className="authored-text">{data.assessment.note}</p><p>{data.sequence}. kayıt · {formatDate(data.recorded_at, true)} · Ayrı görüşler: {data.basis.observations.length}/2</p>
      <p className="small">Farklı beyanlar: anlam {data.disagreement.semantic_dimensions ?? 'Bilinmiyor'} · bulgular {data.disagreement.finding_dimensions ?? 'Bilinmiyor'}. Görüşler oylanmaz ve tek sonuca dönüştürülmez.</p>
      <Detail title="Etkin iş süresi ve bilinmeyen ölçümler"><p>Bekleme süresi hariç, ayrı beyan edilen çalışma süreleri. Özgün çalışma süresi geriye dönük bir beyandır.</p>{data.assessment.arms.map(arm => <section key={arm.arm}><h4>{armLabels[arm.arm]}</h4>{EFFORT_PHASES.map(key => <p key={key}>{phaseLabels[key]}: {arm[key] === null ? 'Ölçülmedi' : `${arm[key]} saniye`}</p>)}</section>)}<p>Ortak hazırlık: {data.assessment.shared_setup_included ? 'Dahil olarak beyan edildi' : 'Doğrulanmadı'} · Tüm inceleme/düzeltme: {data.assessment.verification_and_correction_included ? 'Dahil olarak beyan edildi' : 'Doğrulanmadı'} · Çakışmayan etkin süre: {data.assessment.non_overlapping_active_time ? 'Beyan edildi' : 'Doğrulanmadı'}</p></Detail>
      <Detail title="Saklanan ayrı görüşler">{data.basis.observations.map(item => <section key={item.id}><h4>{item.reviewer_name}</h4><p className="authored-text">{item.assessment.note}</p><p className="small">Beyan edilen kapsam: anlam {item.coverage.semantic.assessed}/{item.coverage.semantic.total} · bulgular {item.coverage.findings.assessed}/{item.coverage.findings.total}. Karşı dayanak derlemi bilinmiyor.</p>{item.assessment.observations.map(row => <p className="authored-text" key={row.dimension}>{rubric[row.dimension]} · {row.outcome && SEMANTIC_OUTCOMES[row.outcome]}: {row.note}</p>)}
        <Detail title="Özgün bulgular, karşı dayanak sınırları ve alıntı bağlantıları">{item.assessment.judgments.map(row => <p className="authored-text" key={`${row.source_index}:${row.dimension}`}>{row.source_index + 1}. kaynak · {data.basis.comparison.comparison_snapshot.dimensions[row.dimension]} · {row.outcome && JUDGMENT_OUTCOMES[row.outcome]}: {row.note}<span className="small">{row.target_refs.join(' · ')} · {row.private_source_refs.join(' · ')}</span></p>)}<p>Etkin ayrı inceleme: {item.assessment.review_seconds === null ? 'Ölçülmedi' : `${item.assessment.review_seconds} saniye`}. İş süresiyle ayrıca toplanmaz.</p><p>{item.assessment.adverse_scope.status === 'not_searched' ? 'Karşı dayanak araştırılmadı' : 'Yalnız seçili kaynaklar incelendi'} · {item.assessment.adverse_scope.inspected_source_indices.map(i => i + 1).join(', ') || 'Kaynak yok'}</p><p className="authored-text">{item.assessment.adverse_scope.limitations}</p></Detail>
      </section>)}</Detail>
      <ComparisonEvidence comparison={data.basis.comparison.comparison_snapshot} />
    </> : <p>Özel taslağı aynı olgu ve alıntılarla revize edin, özgün bulgularla karşılaştırın ve iki atanmış ayrı hesaptan görüş kaydedin. Ardından kayıtları burada seçin.</p>}
    <Detail title="Deneme bağları"><p className="reference-id">{value.id} · {value.protocol_sha256}</p><p>{value.freshness.reasons.join(' · ') || 'Teknik bağlar güncel.'}</p></Detail></>;
}

function RegistrationEditor({ context, base, saved, failed }: { context: TrialRegistrationContext; base: string; saved: (value: TrialView) => void; failed: (cause: unknown) => void }) {
  const [title, setTitle] = useState(''); const [question, setQuestion] = useState(''); const [family, setFamily] = useState('');
  const [sample, setSample] = useState(''); const [reviewers, setReviewers] = useState<string[]>([]); const [busy, setBusy] = useState(false);
  const nonce = useRef(crypto.randomUUID().replaceAll('-', '')); const mounted = useRef(true); useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  const ready = trialReviewers(context, reviewers) && title.trim().length >= 3 && question.trim().length >= 3 && family.trim().length >= 3 && ['real', 'synthetic'].includes(sample);
  async function save() {
    if (!ready) return; setBusy(true);
    try {
      const hash = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(family.trim()));
      const sha = Array.from(new Uint8Array(hash), byte => byte.toString(16).padStart(2, '0')).join('');
      const value = await post<TrialView>(base, { request_id: nonce.current, context_sha256: context.context_sha256, title, question,
        sample_kind: sample, split_family_sha256: sha, reviewer_ids: reviewers });
      if (mounted.current) saved(value);
    } catch (cause) { if (mounted.current) failed(cause); }
    finally { if (mounted.current) setBusy(false); }
  }
  return <form className="authority-context-form" onSubmit={event => { event.preventDefault(); void save(); }}>
    <p>Revizyondan önce olgu, öncül, tarih ve alıntıları sabitleyin. Taslak/inceleme yazarından ve protokol sahibinden ayrı iki avukat hesabı seçin.</p>
    {!context.can_register && <Notice error>Özgün taslak güncel olmalı; iki uygun hesap ve izinli kaynaklar gerekli. Model yardımlı taslaklar bu insan revizyonu denemesine dahil edilmez.</Notice>}
    <fieldset disabled={busy || !context.can_register}>
      <Field label="Deneme başlığı">{id => <input id={id} maxLength={200} value={title} onChange={event => setTitle(event.target.value)} />}</Field>
      <Field label="İncelenecek soru">{id => <textarea id={id} maxLength={2000} value={question} onChange={event => setQuestion(event.target.value)} />}</Field>
      <Field label="Örnek ailesi · Aynı senaryo için aynı adı kullanın">{id => <input id={id} maxLength={200} value={family} onChange={event => setFamily(event.target.value)} />}</Field>
      <Field label="Örnek türü">{id => <select id={id} value={sample} onChange={event => setSample(event.target.value)}><option value="">Tür seçin</option><option value="synthetic">Sentetik</option>{!context.synthetic_only && <option value="real">Gerçek · Kaynak hakları ayrıca doğrulanır</option>}</select>}</Field>
      <Field label="İki ayrı inceleyen">{id => <select id={id} multiple value={reviewers} onChange={event => setReviewers(Array.from(event.target.selectedOptions, option => option.value))}>{context.eligible_reviewers.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select>}</Field>
      <button className="button" type="submit" disabled={!ready}>Revizyon öncesi protokolü kaydet</button>
    </fieldset></form>;
}

function CaptureEditor({ context, base, saved, failed }: { context: TrialCaptureContext; base: string; saved: (value: TrialView) => void; failed: (cause: unknown) => void }) {
  const [arms, setArms] = useState(freshEffort); const [note, setNote] = useState(''); const [setup, setSetup] = useState(false); const [verified, setVerified] = useState(false); const [distinct, setDistinct] = useState(false); const [busy, setBusy] = useState(false);
  const nonce = useRef<{ body: string; id: string } | null>(null); const mounted = useRef(true); useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  const times = trialEffort(arms); const ready = context.can_record && times && note.trim().length >= 3;
  async function save() {
    if (!ready) return; setBusy(true);
    const spec = { comparison_id: context.basis.comparison_id, adjudication_ids: context.basis.observations.map(item => item.id),
      expected_basis_sha256: context.basis_sha256, expected_capture_id: context.expected_capture_id, note, arms: times,
      shared_setup_included: setup, verification_and_correction_included: verified, non_overlapping_active_time: distinct };
    const key = JSON.stringify(spec); if (nonce.current?.body !== key) nonce.current = { body: key, id: crypto.randomUUID().replaceAll('-', '') };
    try { const value = await post<TrialView>(`${base}/captures`, { ...spec, request_id: nonce.current.id }); if (mounted.current) saved(value); }
    catch (cause) { if (mounted.current) failed(cause); }
    finally { if (mounted.current) setBusy(false); }
  }
  return <form className="authority-context-form" onSubmit={event => { event.preventDefault(); void save(); }}>
    <p>Seçilen ayrı görüşler: {context.basis.observations.length}/2. Eksik görüş ve sürelerle kayıt saklanabilir; eksikler görünür kalır.</p>
    <ComparisonEvidence comparison={context.basis.comparison.comparison_snapshot} />
    <fieldset disabled={busy || !context.can_record}>
      {arms.map((arm, index) => <Detail key={arm.arm} title={`${armLabels[arm.arm]} · Etkin saniye · Boş = ölçülmedi`}>
        {EFFORT_PHASES.map(key => <Field key={key} label={phaseLabels[key]}>{id => <input id={id} type="number" min={0} max={28800} step={1} value={arm[key]} placeholder="Ölçülmedi" onChange={event => setArms(old => old.map((row, i) => i === index ? { ...row, [key]: event.target.value } : row))} />}</Field>)}
      </Detail>)}
      <label><input type="checkbox" checked={setup} onChange={event => setSetup(event.target.checked)} /> Ortak hazırlık her iki çalışmaya tutarlı dahil edildi</label>
      <label><input type="checkbox" checked={verified} onChange={event => setVerified(event.target.checked)} /> Tüm doğrulama, avukat incelemesi ve düzeltme süreleri dahil edildi</label>
      <label><input type="checkbox" checked={distinct} onChange={event => setDistinct(event.target.checked)} /> Süreler çakışmıyor; bekleme süresi hariç</label>
      <Field label="Kayıt notu ve ölçüm sınırları">{id => <textarea id={id} maxLength={2000} value={note} onChange={event => setNote(event.target.value)} />}</Field>
      <button type="submit" className="button" disabled={!ready}>Deneme kanıtlarını sakla</button>
    </fieldset></form>;
}

export default function AuthorityTrials({ base, onUnavailable }: { base: string; onUnavailable: (cause: unknown) => void }) {
  const [context, setContext] = useState<TrialRegistrationContext | null>(null); const [items, setItems] = useState<{ id: string; registered_at: string }[]>([]); const [more, setMore] = useState(false);
  const [view, setView] = useState<TrialView | null>(null); const [captureContext, setCaptureContext] = useState<TrialCaptureContext | null>(null);
  const [comparisons, setComparisons] = useState<FindingSummary[]>([]); const [observations, setObservations] = useState<FindingSummary[]>([]);
  const [comparisonMore, setComparisonMore] = useState(false); const [observationMore, setObservationMore] = useState(false);
  const [comparisonId, setComparisonId] = useState(''); const [adjudicationIds, setAdjudicationIds] = useState<string[]>([]);
  const [captures, setCaptures] = useState<{ id: string; sequence: number }[]>([]); const [captureMore, setCaptureMore] = useState(false);
  const [busy, setBusy] = useState(false); const [error, setError] = useState(''); const [notice, setNotice] = useState('');
  const mounted = useRef(true); useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  const trialBase = view ? `${base}/${encodeURIComponent(view.id)}` : '';
  const comparisonBase = base.replace(/\/trials$/, '/comparisons');
  function clear() { setContext(null); setView(null); setCaptureContext(null); setComparisons([]); setObservations([]); setCaptures([]); setComparisonMore(false); setObservationMore(false); setCaptureMore(false); setComparisonId(''); setAdjudicationIds([]); }
  function fail(cause: unknown) { clear(); setItems([]); setError(messageOf(cause)); onUnavailable(cause); }
  function failedSave(cause: unknown) { if (cause instanceof ApiError && pendingTrial(cause.data)) { clear(); setNotice('Kayıt saklandı; son izin kontrolü tamamlanmadı. İçerik bekletiliyor. Yeniden gönderme bu kaydı tamamlamaz.'); } else fail(cause); }
  async function action<T>(run: () => Promise<T>, apply: (value: T) => void) { setBusy(true); setError(''); try { const value = await run(); if (mounted.current) apply(value); } catch (cause) { if (mounted.current) fail(cause); } finally { if (mounted.current) setBusy(false); } }
  function accept(value: TrialView) { clear(); if (!value.public_source_access) fail(new Error('Deneme içeriği bekletiliyor.')); else setView(value); }
  const page = (append = false) => action(() => request<{ id: string; registered_at: string }[]>(`${base}?limit=10&offset=${append ? items.length : 0}`, { cache: 'no-store' }), values => { clear(); setItems(old => append ? [...old, ...values] : values); setMore(values.length === 10); });
  const loadComparisons = (append = false) => action(() => request<FindingSummary[]>(`${comparisonBase}?limit=20&offset=${append ? comparisons.length : 0}`, { cache: 'no-store' }), values => { setComparisons(old => append ? [...old, ...values.filter(row => !old.some(prior => prior.id === row.id))] : values); setComparisonMore(values.length === 20); });
  const loadObservations = (append = false) => action(() => request<FindingSummary[]>(`${comparisonBase}/${encodeURIComponent(comparisonId)}/adjudications?limit=20&offset=${append ? observations.length : 0}`, { cache: 'no-store' }), values => { setObservations(old => append ? [...old, ...values.filter(row => !old.some(prior => prior.id === row.id))] : values); setObservationMore(values.length === 20); });
  const history = (append = false) => action(() => request<{ id: string; sequence: number }[]>(`${trialBase}/captures?limit=10&offset=${append ? captures.length : 0}`, { cache: 'no-store' }), values => { setCaptures(old => append ? [...old, ...values] : values); setCaptureMore(values.length === 10); });
  return <><p className="small">Revizyon öncesi kayıt → Aynı olgu ve alıntılar → Ayrı görüşler → Etkin iş süresi. Otomatik model denemesi, kalite puanı veya hukuki onay verilmez.</p>
    <div className="practice-record-actions"><button className="text-button" disabled={busy} onClick={() => { clear(); void action(() => request<TrialRegistrationContext>(`${base}/registration-context`, { cache: 'no-store' }), setContext); }}>Revizyon öncesi kayıt girdilerini getir</button><button className="text-button" disabled={busy} onClick={() => void page()}>Kayıtlı denemeleri getir</button></div>
    {notice && <Notice>{notice}</Notice>}{context && <RegistrationEditor context={context} base={base} saved={accept} failed={failedSave} />}
    {items.map(item => <p key={item.id}><button className="text-button" disabled={busy} onClick={() => { clear(); void action(() => request<TrialView>(`${base}/${encodeURIComponent(item.id)}`, { cache: 'no-store' }), accept); }}>Denemeyi aç · {formatDate(item.registered_at, true)}</button></p>)}
    {more && <button className="text-button" disabled={busy} onClick={() => void page(true)}>Önceki denemeleri getir</button>}
    {view && <><TrialContent value={view} /><div className="practice-record-actions"><button className="text-button" disabled={busy} onClick={() => void history()}>Saklanan kayıt geçmişini getir</button><button className="text-button" disabled={busy || view.freshness.status !== 'current' || !view.snapshot} onClick={() => void action(() => downloadAuthorityTrial(trialBase, view.id), () => undefined)}>Özel deneme JSON paketini indir</button></div>
      {captures.map(item => <button key={item.id} className="text-button" disabled={busy} onClick={() => void action(() => request<TrialView>(`${trialBase}?capture_id=${encodeURIComponent(item.id)}`, { cache: 'no-store' }), value => { setCaptureContext(null); if (!value.public_source_access) fail(new Error('Deneme geçmişi bekletiliyor.')); else setView(value); })}>{item.sequence}. kaydı aç</button>)}
      {captureMore && <button className="text-button" disabled={busy} onClick={() => void history(true)}>Önceki kayıtları getir</button>}
      {view.can_record && <Detail title="Karşılaştırma ve ayrı görüşleri seç / yeni kayıt oluştur"><button className="text-button" disabled={busy} onClick={() => void loadComparisons()}>Saklanan karşılaştırmaları getir</button>
        {comparisonMore && <button className="text-button" disabled={busy} onClick={() => void loadComparisons(true)}>Önceki karşılaştırmaları getir</button>}
        <Field label="Karşılaştırma">{id => <select id={id} value={comparisonId} disabled={busy} onChange={event => { setComparisonId(event.target.value); setAdjudicationIds([]); setObservations([]); setObservationMore(false); setCaptureContext(null); }}><option value="">Karşılaştırma seçin</option>{comparisons.map(item => <option key={item.id} value={item.id}>{item.sequence}. karşılaştırma · {item.reviewer_name}</option>)}</select>}</Field>
        <button className="text-button" disabled={busy || !comparisonId} onClick={() => void loadObservations()}>Ayrı görüş kayıtlarını getir</button>
        {observationMore && <button className="text-button" disabled={busy} onClick={() => void loadObservations(true)}>Önceki ayrı görüşleri getir</button>}
        <Field label="Atanmış iki hesaptan görüşler · Eksikse boş bırakılabilir">{id => <select id={id} multiple disabled={busy} value={adjudicationIds} onChange={event => { setCaptureContext(null); setAdjudicationIds(Array.from(event.target.selectedOptions, option => option.value)); }}>{observations.map(item => <option key={item.id} value={item.id}>{item.reviewer_name} · {item.sequence}. görüş</option>)}</select>}</Field>
        <button className="text-button" disabled={busy || !comparisonId || adjudicationIds.length > 2} onClick={() => void action(() => post<TrialCaptureContext>(`${trialBase}/capture-context`, { comparison_id: comparisonId, adjudication_ids: adjudicationIds }), setCaptureContext)}>Seçili kayıt bağlarını kontrol et</button>
        {captureContext && <CaptureEditor key={captureContext.basis_sha256 + (captureContext.expected_capture_id || '')} context={captureContext} base={trialBase} saved={accept} failed={failedSave} />}
      </Detail>}
    </>}{error && <Notice error>{error}</Notice>}</>;
}
