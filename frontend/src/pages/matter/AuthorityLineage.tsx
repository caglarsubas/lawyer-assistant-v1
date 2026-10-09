import { useEffect, useRef, useState } from 'react';
import { ApiError, post, request } from '../../api';
import { Detail, Field, Notice } from '../../components';
import { formatDate, messageOf } from '../../utils';
import { LinkedAuthorityView } from './AnalysisAuthorities';
import { assessmentPayload, FINDING_DIMENSIONS, FINDING_OUTCOMES } from './authorityFindingTypes';
import type { EditableAssessment, FindingOutcome } from './authorityFindingTypes';
import { occurrence, occurrenceKey } from './authorityTypes';
import { pendingLineageReceipt, sourceBindingReason } from './lineageTypes';
import type { EditableRenewal, LineagePreview, LineageRecord } from './lineageTypes';

function RenewalEditor({ value, base, onSaved, onUnavailable }: { value: LineagePreview; base: string; onSaved: () => Promise<void>; onUnavailable: (cause: unknown) => void }) {
  const preview = value.preview;
  const [entries, setEntries] = useState<EditableRenewal[]>(() => preview.entries.map(entry => ({ dependency_sha256: entry.dependency_sha256, note: '', seconds: '', sources: entry.manifest.sources.map(source => ({ ...occurrence(source.selection), target_ids: source.selection.target_ids.filter(id => Object.hasOwn(preview.targets, id)), observations: FINDING_DIMENSIONS.map(dimension => ({ dimension, outcome: '', note: '' })) })) })));
  const [reason, setReason] = useState(''); const [consent, setConsent] = useState(false); const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  const mounted = useRef(true); const nonce = useRef<{ payload: string; id: string } | null>(null);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  const assessments = entries.map(entry => assessmentPayload(entry.sources, entry.note, entry.seconds));
  const valid = consent && reason.trim().length >= 3 && reason.length <= 2000 && assessments.every(Boolean)
    && entries.every(entry => entry.sources.every(source => source.target_ids.every(id => Object.hasOwn(preview.targets, id))));
  function update(index: number, change: Partial<EditableRenewal>) { setEntries(old => old.map((entry, i) => i === index ? { ...entry, ...change } : entry)); }
  function sourceUpdate(index: number, source: number, change: Partial<EditableAssessment>) { update(index, { sources: entries[index].sources.map((entry, i) => i === source ? { ...entry, ...change } : entry) }); }
  async function save() {
    if (!valid) return; setBusy(true); setError('');
    const spec = { version_id: preview.version_id, expected_revision: preview.expected_revision, expected_preview_sha256: value.preview_sha256,
      change_note: reason, decision: 'retain_for_review', renewals: assessments.map((assessment, i) => ({ ...assessment!, dependency_sha256: entries[i].dependency_sha256 })) };
    const payload = JSON.stringify(spec);
    if (nonce.current?.payload !== payload) nonce.current = { payload, id: crypto.randomUUID().replaceAll('-', '') };
    try { await post(base, { ...spec, request_id: nonce.current.id }); if (mounted.current) await onSaved(); }
    catch (cause) { if (!mounted.current) return;
      if (cause instanceof ApiError && pendingLineageReceipt(cause.data)) onUnavailable(new Error('Yeni sürüm kaydedildi; son izin kontrolü tamamlanmadı. İçerik ve aktarım bekletiliyor. Aynı isteği tekrarlamak kaydı açmaz.'));
      else if (cause instanceof ApiError && cause.status !== 0) onUnavailable(cause);
      else setError(messageOf(cause));
    } finally { if (mounted.current) setBusy(false); }
  }
  return <form onSubmit={event => { event.preventDefault(); void save(); }} className="authority-context-form">
    <p>Güncel taslağı ve her özgün kamu kaynağını inceleyin. Bu işlem kaynak bağını yeniler; bulguları çözmez, kaynak veya hukuki onay vermez. Özgün model katkıları korunur.</p>
    <p className="reference-id">İncelenen sürüm: {preview.version_id} · Taslak SHA-256: {preview.draft_sha256}</p>
    <Detail title="İncelenen güncel taslak adımları">{Object.entries(preview.targets).map(([key, target]) => <div key={key}><strong>{key}</strong><pre className="authored-text">{JSON.stringify(target, null, 2)}</pre></div>)}</Detail>
    <fieldset disabled={busy}><legend>Saklanan kaynak bağlarının avukat tarafından yeniden incelenmesi</legend>
      <Field label="Yeni sürüm için değişiklik gerekçesi">{id => <textarea id={id} value={reason} minLength={3} maxLength={2000} required onChange={event => setReason(event.target.value)} />}</Field>
      {entries.map((entry, i) => <Detail key={entry.dependency_sha256} title={`${i + 1}. saklanan katkı`}>
        <p className="small">Özgün bağı etkileyen durumlar: {preview.entries[i].stale_reasons.map(sourceBindingReason).join(' · ') || 'Ek inceleme'}</p>
        <Field label={`${i + 1}. katkı · Yeniden inceleme notu`}>{id => <textarea id={id} value={entry.note} minLength={3} maxLength={2000} required onChange={event => update(i, { note: event.target.value })} />}</Field>
        <Field label={`${i + 1}. katkı · Etkin inceleme süresi (saniye, isteğe bağlı)`}>{id => <input id={id} type="number" min={1} max={28800} step={1} value={entry.seconds} onChange={event => update(i, { seconds: event.target.value })} />}</Field>
        {entry.sources.map((source, j) => <Detail key={occurrenceKey(source)} title={`${j + 1}. özgün kaynak · Altı boyutu inceleyin`}>
          <LinkedAuthorityView source={preview.entries[i].manifest.sources[j]} />
          <p className="small muted">Yukarıdaki adımlar özgün bağlamdandır. Aşağıda güncel taslağın hedeflerini seçin.</p>
          <Field label={`${i + 1}. katkı · ${j + 1}. kaynak · Güncel taslak hedefleri`}>{id => <select id={id} multiple size={4} value={source.target_ids} required onChange={event => sourceUpdate(i, j, { target_ids: Array.from(event.target.selectedOptions, option => option.value) })}>{Object.keys(preview.targets).map(target => <option key={target} value={target}>{target}</option>)}</select>}</Field>
          {source.observations.map((observation, k) => <fieldset key={observation.dimension}><legend>{preview.dimensions[observation.dimension]}</legend>
            <Field label={`${i + 1}.${j + 1} · ${preview.dimensions[observation.dimension]} · Durum`}>{id => <select id={id} required value={observation.outcome} onChange={event => sourceUpdate(i, j, { observations: source.observations.map((item, n) => n === k ? { ...item, outcome: event.target.value as FindingOutcome | '' } : item) })}><option value="">Değerlendirme seçin</option>{Object.entries(FINDING_OUTCOMES).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select>}</Field>
            <Field label={`${i + 1}.${j + 1} · ${preview.dimensions[observation.dimension]} · Gerekçe`}>{id => <textarea id={id} value={observation.note} minLength={3} maxLength={2000} required onChange={event => sourceUpdate(i, j, { observations: source.observations.map((item, n) => n === k ? { ...item, note: event.target.value } : item) })} />}</Field>
          </fieldset>)}
        </Detail>)}
      </Detail>)}
      <label className="small"><input type="checkbox" checked={consent} onChange={event => setConsent(event.target.checked)} /> Kaynakları bu taslakta inceleme için tutuyorum. Belirsizlikler ve özgün katkılar korunur; hukuki onay vermiyorum.</label>
      <button className="button" type="submit" disabled={!valid}>Kaynak bağlarını yeni taslak sürümünde yenile</button>
    </fieldset>{error && <Notice error>{error}</Notice>}
  </form>;
}

export default function AuthorityLineage({ matterId, analysisId, onSaved }: { matterId: string; analysisId: string; onSaved: () => Promise<void> }) {
  const base = `/matters/${encodeURIComponent(matterId)}/analyses/${encodeURIComponent(analysisId)}/lineage-reviews`;
  const [value, setValue] = useState<LineagePreview | null>(null); const [history, setHistory] = useState<LineageRecord[]>([]);
  const [busy, setBusy] = useState(false); const [error, setError] = useState(''); const [loaded, setLoaded] = useState(false);
  const mounted = useRef(true); useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  function unavailable(cause: unknown) { setValue(null); setHistory([]); setError(messageOf(cause)); }
  async function load(kind: 'preview' | 'history') { setValue(null); setHistory([]); setError(''); setBusy(true); try {
    if (kind === 'preview') { const next = await request<LineagePreview>(`${base}/preview`, { cache: 'no-store' }); if (mounted.current) setValue(next); }
    else { const next = await request<LineageRecord[]>(base, { cache: 'no-store' }); if (mounted.current) { setHistory(next); setLoaded(true); } }
  } catch (cause) { if (mounted.current) unavailable(cause); } finally { if (mounted.current) setBusy(false); } }
  return <><p className="small">Saklanan kamu katkılarını değiştirmeden, mevcut taslak için açık avukat incelemesi kaydedin. Değişmiş veya izni kaldırılmış kaynaklar bu akışla açılamaz.</p>
    <div className="practice-record-actions"><button className="text-button" disabled={busy} onClick={() => void load('preview')}>Yeniden inceleme için güncel taslak ve kaynakları getir</button><button className="text-button" disabled={busy} onClick={() => void load('history')}>Kaynak bağı yenileme geçmişini getir</button></div>
    {value && <RenewalEditor key={value.preview_sha256} value={value} base={base} onSaved={onSaved} onUnavailable={unavailable} />}
    {history.map(item => <Detail key={item.id} title={`${item.snapshot.sequence}. kaynak bağı yenilemesi · ${item.snapshot.reviewer_name}`}><p>{formatDate(item.snapshot.recorded_at, true)} · Hukuki veya kaynak onayı verilmedi.</p><p className="reference-id">Özgün taslak: {item.snapshot.version_id} · Yeni sürüm: {item.version_id}</p><p className="reference-id">{item.id} · SHA-256: {item.sha256}</p>{item.snapshot.renewals?.map(renewal => <Detail key={renewal.dependency_sha256} title="Son yenileme gözlemleri"><p>{renewal.note}</p>{renewal.sources.map(source => <div key={occurrenceKey(source)}><p className="reference-id">{source.authority_id} · Hedefler: {source.target_ids.join(', ')}</p>{source.observations.map(observation => <p key={observation.dimension}>{item.snapshot.dimensions[observation.dimension]} · {FINDING_OUTCOMES[observation.outcome]}: {observation.note}</p>)}</div>)}</Detail>)}</Detail>)}
    {loaded && !value && !history.length && !error && <p>Henüz kaynak bağı yenilemesi yok.</p>}{error && <Notice error>{error}</Notice>}
  </>;
}
