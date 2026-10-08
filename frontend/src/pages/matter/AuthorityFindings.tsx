import { useEffect, useRef, useState } from 'react';
import { ApiError, downloadAuthorityReview, post, request } from '../../api';
import { Badge, Detail, Field, Notice } from '../../components';
import { formatDate, messageOf } from '../../utils';
import { LinkedAuthorityView } from './AnalysisAuthorities';
import { assessmentPayload, committedFindingReceipt, FINDING_DIMENSIONS, FINDING_OUTCOMES } from './authorityFindingTypes';
import type { EditableAssessment, FindingInputs, FindingOutcome, FindingSummary, FindingView } from './authorityFindingTypes';
import { occurrence, occurrenceKey } from './authorityTypes';

export function FindingViewContent({ value }: { value: FindingView }) {
  const snapshot = value.snapshot;
  return <><p className="small">{value.sequence}. inceleme · {value.reviewer_name} · {formatDate(value.recorded_at, true)}</p>
    {!value.public_source_access || !snapshot ? <Notice error>Kaynak izinleri doğrulanamadı. Kamu pasajları ve bunları içerebilen inceleme notları bekletiliyor; önceki kayıt korunur.</Notice> : <>
      <Badge status={value.freshness.status}>{value.freshness.status === 'current' ? 'İnceleme bağları güncel' : 'Yeniden inceleme gerekli · Aktarım kapalı'}</Badge>
      <p className="small muted">Bunlar avukatın beyan ettiği bulgulardır. Taslak, hukuki engeller, kaynak onayı ve yeterlilik sonucu değişmez.</p>
      <p className="authored-text">{snapshot.assessment.note}</p>
      <p className="small">Beyan edilen etkin inceleme süresi: {snapshot.assessment.review_seconds === null ? 'Ölçülmedi' : `${snapshot.assessment.review_seconds} saniye`}. Model çağrısı yapılmadı.</p>
      {snapshot.assessment.sources.map((source, index) => { const linked = snapshot.context_snapshot.manifest?.sources.find(item => occurrenceKey(item.selection) === occurrenceKey(source));
        return <Detail key={occurrenceKey(source)} title={`${index + 1}. kaynak için avukat bulguları`}><p className="small">Bağlı adımlar: {source.target_ids.join(' · ')}</p>
          {source.observations.map(item => <section key={item.dimension}><h4>{snapshot.dimensions[item.dimension]}</h4><p><strong>{FINDING_OUTCOMES[item.outcome]}</strong></p><p className="authored-text">{item.note}</p></section>)}
          {linked && <Detail title="İncelenen özgün pasaj ve taslak adımları"><LinkedAuthorityView source={linked} /></Detail>}
        </Detail>;
      })}
    </>}
    <Detail title="İnceleme sürümü ve bağları"><p className="reference-id">{value.id} · SHA-256: {value.review_sha256}</p><p className="small">{value.freshness.reasons.join(' · ') || 'Kaynak bağları güncel; hukuki onay verilmez.'}</p>{value.public_source_access && snapshot && <><p className="reference-id">Bağlam: {snapshot.context_manifest_sha256}</p><p className="reference-id">Önceki inceleme: {snapshot.previous_review_id || 'Yok'}</p></>}</Detail>
  </>;
}

function ReviewCard({ item, base, matterId, analysisId, contextId }: { item: FindingSummary; base: string; matterId: string; analysisId: string; contextId: string }) {
  const [view, setView] = useState<FindingView | null>(null); const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  const mounted = useRef(true); useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  async function inspect() { setView(null); setError(''); setBusy(true); try { const value = await request<FindingView>(`${base}/${encodeURIComponent(item.id)}`, { cache: 'no-store' }); if (mounted.current) setView(value); } catch (cause) { if (mounted.current) setError(messageOf(cause)); } finally { if (mounted.current) setBusy(false); } }
  async function download(format: 'json' | 'docx' | 'pdf') { setBusy(true); setError(''); try { await downloadAuthorityReview(matterId, analysisId, contextId, item.id, format); } catch (cause) { if (mounted.current) { setView(null); setError(messageOf(cause)); } } finally { if (mounted.current) setBusy(false); } }
  return <Detail title={`${item.sequence}. avukat incelemesi · ${item.reviewer_name}`}><button className="text-button" disabled={busy} onClick={() => void inspect()}>İncelemeyi aç / güncel bağları kontrol et</button>{view && <><FindingViewContent value={view} /><div className="practice-record-actions">{(['json', 'docx', 'pdf'] as const).map(format => <button key={format} className="text-button" disabled={busy || !view.public_source_access || !view.snapshot || view.freshness.status !== 'current'} onClick={() => void download(format)}>{format.toUpperCase()} incelemeyi indir</button>)}</div></>}{error && <Notice error>{error}</Notice>}</Detail>;
}

function FindingEditor({ inputs, base, onSaved, onFailure }: { inputs: FindingInputs; base: string; onSaved: (pending: boolean) => void; onFailure: (cause: unknown) => void }) {
  const sources = inputs.authority_context.manifest?.sources || [];
  const [rows, setRows] = useState<EditableAssessment[]>(() => sources.map(item => ({ ...occurrence(item.selection), target_ids: [...item.selection.target_ids], observations: FINDING_DIMENSIONS.map(dimension => ({ dimension, outcome: '', note: '' })) })));
  const [note, setNote] = useState(''); const [seconds, setSeconds] = useState(''); const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  const nonce = useRef<{ body: string; id: string } | null>(null); const mounted = useRef(true); useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  const assessment = assessmentPayload(rows, note, seconds);
  function update(row: number, dimension: number, change: Partial<EditableAssessment['observations'][number]>) { setRows(old => old.map((value, index) => index === row ? { ...value, observations: value.observations.map((item, i) => i === dimension ? { ...item, ...change } : item) } : value)); }
  async function save() { if (!assessment || !inputs.can_record) return; setBusy(true); setError(''); const spec = { ...assessment, expected_basis_sha256: inputs.basis_sha256, expected_review_id: inputs.expected_review_id }; const key = JSON.stringify(spec); if (nonce.current?.body !== key) nonce.current = { body: key, id: crypto.randomUUID().replaceAll('-', '') };
    try { await post<FindingView>(base, { ...spec, request_id: nonce.current.id }); if (mounted.current) onSaved(false); }
    catch (cause) { if (mounted.current) { if (cause instanceof ApiError && committedFindingReceipt(cause.data)) onSaved(true); else if (cause instanceof ApiError && cause.status !== 0) onFailure(cause); else setError(messageOf(cause)); } }
    finally { if (mounted.current) setBusy(false); }
  }
  return <form className="authority-context-form" onSubmit={event => { event.preventDefault(); void save(); }}>
    <p>Her seçili kaynak ve altı inceleme boyutu için durum ve gerekçe belirtin. Değerlendirilmemiş konular açık kalır; destek beyanı taslağı otomatik onaylamaz.</p>
    {!inputs.can_record && <Notice error>Arşivlenmiş çalışma alanında yeni inceleme kaydedilemez.</Notice>}
    <fieldset disabled={busy || !inputs.can_record}><legend>Kaynak bağlamına bağlı avukat incelemesi</legend>
      <Field label="Genel inceleme notu">{id => <textarea id={id} value={note} required minLength={3} maxLength={2000} onChange={event => setNote(event.target.value)} />}</Field>
      <Field label="Etkin inceleme süresi · Saniye · Ölçülmediyse boş bırakın">{id => <input id={id} type="number" min={1} max={28800} step={1} value={seconds} onChange={event => setSeconds(event.target.value)} />}</Field>
      {rows.map((row, index) => <Detail key={occurrenceKey(row)} title={`${index + 1}. kaynak · Altı boyutu değerlendir`}>
        <LinkedAuthorityView source={sources[index]} />
        {row.observations.map((item, i) => <fieldset key={item.dimension}><legend>{inputs.dimensions[item.dimension]}</legend>
          <Field label={`${index + 1}. kaynak · ${inputs.dimensions[item.dimension]} · Durum`}>{id => <select id={id} value={item.outcome} required onChange={event => update(index, i, { outcome: event.target.value as FindingOutcome | '' })}><option value="">Değerlendirme seçin</option>{Object.entries(FINDING_OUTCOMES).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select>}</Field>
          <Field label={`${index + 1}. kaynak · ${inputs.dimensions[item.dimension]} · Gerekçe`}>{id => <textarea id={id} value={item.note} required minLength={3} maxLength={2000} onChange={event => update(index, i, { note: event.target.value })} />}</Field>
        </fieldset>)}
      </Detail>)}
      <button type="submit" className="button" disabled={!assessment}>Kaynağa bağlı incelemeyi kaydet</button>
    </fieldset>
    {error && <Notice error>{error}</Notice>}
  </form>;
}

export default function AuthorityFindings({ matterId, analysisId, contextId }: { matterId: string; analysisId: string; contextId: string }) {
  const base = `/matters/${encodeURIComponent(matterId)}/analyses/${encodeURIComponent(analysisId)}/authority-contexts/${encodeURIComponent(contextId)}/reviews`;
  const [inputs, setInputs] = useState<FindingInputs | null>(null); const [items, setItems] = useState<FindingSummary[]>([]); const [more, setMore] = useState(false); const [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState(false); const [error, setError] = useState(''); const [notice, setNotice] = useState(''); const mounted = useRef(true); useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  async function load() { setInputs(null); setError(''); setNotice(''); setBusy(true); try { const value = await request<FindingInputs>(`${base}/context`, { cache: 'no-store' }); if (mounted.current) setInputs(value); } catch (cause) { if (mounted.current) setError(messageOf(cause)); } finally { if (mounted.current) setBusy(false); } }
  async function history(append = false) { setInputs(null); setError(''); setBusy(true); try { const page = await request<FindingSummary[]>(`${base}?limit=10&offset=${append ? items.length : 0}`, { cache: 'no-store' }); if (mounted.current) { setItems(old => append ? [...old, ...page.filter(item => !old.some(value => value.id === item.id))] : page); setMore(page.length === 10); setLoaded(true); } } catch (cause) { if (mounted.current) { setItems([]); setError(messageOf(cause)); } } finally { if (mounted.current) setBusy(false); } }
  return <><p className="small">İnceleme bu kaynak bağlamı ve özel taslak sürümüne bağlıdır. Önceki yargılar korunur; yeni inceleme onları silmez. Mesleki yeterlilik veya bağımsız hukuki doğrulama bu kayıtla kanıtlanmaz.</p>
    <div className="practice-record-actions"><button className="text-button" disabled={busy} onClick={() => void load()}>Yeni inceleme için kaynak bağlarını getir</button><button className="text-button" disabled={busy} onClick={() => void history()}>Avukat inceleme geçmişini getir</button></div>
    {notice && <Notice>{notice}</Notice>}{inputs && <FindingEditor inputs={inputs} base={base} onSaved={pending => { setInputs(null); setNotice(pending ? 'İnceleme kaydedildi; son izin kontrolü tamamlanamadı. Saklanan kayıt bekletiliyor; yeni girdilerle ayrı inceleme gerekli.' : 'İnceleme kaydedildi. Güncel bağları kontrol etmek için saklanan kaydı açın.'); void history(); }} onFailure={cause => { setInputs(null); setError(messageOf(cause)); }} />}
    {items.map(item => <ReviewCard key={item.id} item={item} base={base} matterId={matterId} analysisId={analysisId} contextId={contextId} />)}
    {loaded && !items.length && <p>Bu kaynak bağlamında avukat incelemesi yok.</p>}{more && <button className="text-button" disabled={busy} onClick={() => void history(true)}>Önceki incelemeleri getir</button>}{error && <Notice error>{error}</Notice>}
  </>;
}
