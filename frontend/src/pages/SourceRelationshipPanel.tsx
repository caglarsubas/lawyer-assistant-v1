import { useEffect, useRef, useState } from 'react';
import { ApiError, request } from '../api';
import { Detail, Field, Loading, Notice } from '../components';
import type { SourceReviewEvent } from '../types';
import { messageOf } from '../utils';
import type { ComparisonEvidence } from './sourceComparison';

export const RELATIONSHIPS = {
  unresolved: 'Henüz çözümlenemedi', same_work_same_version: 'Aynı hukuki eser ve sürüm',
  same_work_different_version: 'Aynı hukuki eser, farklı sürümler', different_work: 'Farklı hukuki eserler',
} as const;
type Classification = keyof typeof RELATIONSHIPS;
type SourcePin = { revision: number; assigned_to: { id: string; name: string } | null; identity_assessment: SourceReviewEvent | null };
export interface RelationshipEvent {
  id: string; revision: number; reviewer: { id: string; name: string }; created_at: string;
  input: { classification: Classification; rationale: string; identities: { source_id: string; work_ref: string; version_ref: string }[];
    evidence_refs: { reference: string; sha256: string }[]; effort: { active_seconds: number; basis: 'estimate' | 'self_reported_timer' } | null };
  source_reviews: Record<string, SourcePin>;
  comparison_evidence: { evidence_json: string; evidence_sha256: string };
}
export interface RelationshipState {
  schema_version: 'source-relationship-state-v1'; pair_id: string; source_ids: string[]; revision: number;
  source_reviews: Record<string, SourcePin>; latest: RelationshipEvent | null; history: RelationshipEvent[];
  history_truncated: boolean; stale: boolean; can_record: boolean; identity_reviews_ready: boolean; resolved_for_handoff: boolean;
  confidentiality: 'firm_confidential'; signed: false; publication_eligible: false; independent_originals_verified: false; current_law_verified: false;
}
export interface RelationshipDraft { classification: Classification; rationale: string; leftWork: string; rightWork: string; leftVersion: string; rightVersion: string; reference: string; sha256: string; seconds: string; basis: 'estimate' | 'self_reported_timer' }
const EMPTY: RelationshipDraft = { classification: 'unresolved', rationale: '', leftWork: '', rightWork: '', leftVersion: '', rightVersion: '', reference: '', sha256: '', seconds: '', basis: 'estimate' };

export function relationshipPath(evidence: ComparisonEvidence) {
  return `/public-sources/${evidence.receipt.left.source_id}/relationship?other_source_id=${evidence.receipt.right.source_id}`;
}
export function validateRelationshipState(state: RelationshipState, evidence: ComparisonEvidence) {
  const ids = [evidence.receipt.left.source_id, evidence.receipt.right.source_id].sort();
  if (!state || state.schema_version !== 'source-relationship-state-v1' || JSON.stringify(state.source_ids) !== JSON.stringify(ids)
    || JSON.stringify(Object.keys(state.source_reviews ?? {}).sort()) !== JSON.stringify(ids)
    || !Number.isInteger(state.revision) || state.revision < 0 || state.revision > 200 || !/^[a-f0-9]{64}$/.test(state.pair_id)
    || state.confidentiality !== 'firm_confidential' || state.signed !== false || state.publication_eligible !== false
    || state.independent_originals_verified !== false || state.current_law_verified !== false
    || !Array.isArray(state.history) || state.history.length > 50
    || !['stale', 'can_record', 'identity_reviews_ready', 'resolved_for_handoff', 'history_truncated'].every(key => typeof state[key as keyof RelationshipState] === 'boolean')
    || ids.some(id => !Number.isInteger(state.source_reviews[id].revision) || state.source_reviews[id].revision < 0 || state.source_reviews[id].revision > 1000)
    || (state.latest !== null && (!state.latest || !Object.hasOwn(RELATIONSHIPS, state.latest.input?.classification)))
    || state.history.some(event => !event || !Object.hasOwn(RELATIONSHIPS, event.input?.classification))) throw new Error('İlişki kaydı seçili kaynaklar veya inceleme kapsamıyla eşleşmiyor.');
  return state;
}
export function relationshipPayload(draft: RelationshipDraft, state: RelationshipState, evidence: ComparisonEvidence) {
  validateRelationshipState(state, evidence);
  if (!state.can_record) throw new Error('Önce iki kaynak incelemesini de üstlenin.');
  if (!Object.hasOwn(RELATIONSHIPS, draft.classification) || draft.rationale.trim().length < 3) throw new Error('İlişki ve inceleme gerekçesini belirtin.');
  if (draft.classification !== 'unresolved' && (!state.identity_reviews_ready || !/^[a-f0-9]{64}$/.test(draft.sha256)
      || draft.sha256 === evidence.evidence_sha256 || !draft.reference.trim())) throw new Error('Kabul edilmiş iki kimlik incelemesi ve karşılaştırmadan ayrı dayanak gereklidir.');
  const a = evidence.receipt.left, b = evidence.receipt.right;
  const identities = draft.classification === 'unresolved' ? [] : [
    { source_id: a.source_id, work_ref: draft.leftWork.trim(), version_ref: draft.leftVersion.trim() },
    { source_id: b.source_id, work_ref: draft.rightWork.trim(), version_ref: draft.rightVersion.trim() },
  ];
  if (identities.some(item => item.work_ref.length < 3 || item.version_ref.length < 3)) throw new Error('Her iki eseri ve sürümü açıkça tanımlayın.');
  if (identities.length) {
    const sameWork = identities[0].work_ref === identities[1].work_ref, sameVersion = identities[0].version_ref === identities[1].version_ref;
    if ((draft.classification === 'same_work_same_version' && (!sameWork || !sameVersion))
      || (draft.classification === 'same_work_different_version' && (!sameWork || sameVersion))
      || (draft.classification === 'different_work' && sameWork)) throw new Error('Eser/sürüm referansları seçilen ilişkiyle tutarlı olmalıdır.');
  }
  if (Boolean(draft.reference.trim()) !== Boolean(draft.sha256) || (draft.sha256 && !/^[a-f0-9]{64}$/.test(draft.sha256))) throw new Error('Dayanak referansını ve SHA256 değerini birlikte belirtin.');
  const seconds = draft.seconds === '' ? null : Number(draft.seconds);
  if (seconds !== null && (!/^\d+$/.test(draft.seconds) || !Number.isInteger(seconds) || seconds < 0 || seconds > 86400)) throw new Error('Aktif süre 0–86400 tam saniye veya bilinmiyorsa boş olmalıdır.');
  return { expected_revision: state.revision, expected_source_revisions: Object.fromEntries(Object.entries(state.source_reviews).map(([id, value]) => [id, value.revision])),
    classification: draft.classification, rationale: draft.rationale.trim(), identities,
    comparison: { passage_id: a.passage_id, other_passage_id: b.passage_id, offset: a.start - a.passage_start, other_offset: b.start - b.passage_start, evidence_sha256: evidence.evidence_sha256 },
    evidence_refs: draft.reference.trim() ? [{ reference: draft.reference.trim(), sha256: draft.sha256 }] : [],
    effort: seconds === null ? null : { active_seconds: seconds, basis: draft.basis } };
}

export default function SourceRelationshipPanel({ evidence, onError }: { evidence: ComparisonEvidence; onError: (cause: unknown) => void }) {
  const [state, setState] = useState<RelationshipState | null>(null), [draft, setDraft] = useState<RelationshipDraft>(EMPTY);
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [refresh, setRefresh] = useState(0);
  const operation = useRef<AbortController | null>(null);
  const urls = useRef(new Set<string>());
  const path = relationshipPath(evidence);
  useEffect(() => {
    const controller = new AbortController(); operation.current = controller; setState(null); setError(''); setBusy(true);
    const timeout = setTimeout(() => { controller.abort(); setBusy(false); setError('İlişki kaydı zamanında doğrulanamadı. Elle yeniden doğrulayın.'); }, 30000);
    void request<RelationshipState>(path, { signal: controller.signal }).then(value => {
      if (!controller.signal.aborted) setState(validateRelationshipState(value, evidence));
    }).catch(cause => { if (!controller.signal.aborted) { setError(messageOf(cause)); if (cause instanceof ApiError && [401, 403].includes(cause.status)) onError(cause); } })
      .finally(() => { clearTimeout(timeout); if (!controller.signal.aborted) setBusy(false); });
    return () => { clearTimeout(timeout); controller.abort(); };
  }, [path, evidence.evidence_sha256, refresh, onError]); // A new selection mounts a fresh panel.
  function change<K extends keyof RelationshipDraft>(key: K, value: RelationshipDraft[K]) { setDraft(current => ({ ...current, [key]: value })); }
  async function save() {
    if (!state || busy) return;
    const controller = new AbortController(); operation.current?.abort(); operation.current = controller;
    const timeout = setTimeout(() => { controller.abort(); setState(null); setBusy(false); setError('Kaydetme sonucu doğrulanamadı. İşlemi tekrarlamadan önce güncel ilişki kaydını açın.'); }, 30000);
    try {
      const payload = relationshipPayload(draft, state, evidence); setBusy(true); setError('');
      const value = await request<RelationshipState>(path, { method: 'POST', body: JSON.stringify(payload), signal: controller.signal });
      if (!controller.signal.aborted) { setState(validateRelationshipState(value, evidence)); setDraft(EMPTY); }
    } catch (cause) { if (!controller.signal.aborted) { if (cause instanceof ApiError) setState(null); setError(messageOf(cause)); if (cause instanceof ApiError && [401, 403].includes(cause.status)) onError(cause); } }
    finally { clearTimeout(timeout); if (!controller.signal.aborted) setBusy(false); }
  }
  async function download() {
    if (busy) return;
    const controller = new AbortController(); operation.current?.abort(); operation.current = controller; setBusy(true); setError('');
    const timeout = setTimeout(() => { controller.abort(); setState(null); setBusy(false); setError('İnceleme dosyası zamanında doğrulanamadı; yeniden açın.'); }, 30000);
    try {
      const dossier = await request<{ schema_version: string; review: RelationshipState }>(path.replace('/relationship?', '/relationship/export?'), { signal: controller.signal });
      if (controller.signal.aborted) return;
      if (dossier.schema_version !== 'source-relationship-dossier-v1') throw new Error('İnceleme dosyası doğrulanamadı.');
      const fresh = validateRelationshipState(dossier.review, evidence); setState(fresh);
      const url = URL.createObjectURL(new Blob([JSON.stringify(dossier)], { type: 'application/json' })); urls.current.add(url);
      const link = document.createElement('a'); link.href = url; link.download = `kuruma-ozel-kaynak-iliskisi-${fresh.pair_id.slice(0, 16)}.json`; document.body.append(link); link.click(); link.remove();
      window.setTimeout(() => { URL.revokeObjectURL(url); urls.current.delete(url); }, 1000);
    } catch (cause) { if (!controller.signal.aborted) { setState(null); setError(messageOf(cause)); if (cause instanceof ApiError && [401, 403].includes(cause.status)) onError(cause); } }
    finally { clearTimeout(timeout); if (!controller.signal.aborted) setBusy(false); }
  }
  useEffect(() => { const activeUrls = urls.current; return () => { operation.current?.abort(); activeUrls.forEach(URL.revokeObjectURL); activeUrls.clear(); }; }, []);
  return <section className="source-review-section"><h2>Kaynaklar arasındaki insan incelemesi</h2>
    <Notice>Kararı kurumunuza özel kaydedin. İki kaynağı birleştirmez, bağımsız örnek veya güncel hukuk onayı vermez. Önce her iki kaynağın kimlik incelemesini tamamlayın.</Notice>
    {error && <Notice error>{error}</Notice>}<button className="text-button" onClick={() => { operation.current?.abort(); setRefresh(value => value + 1); }}>İlişki kaydını yeniden doğrula</button>
    {!state ? busy ? <Loading label="İlişki kaydı doğrulanıyor…" /> : <p>Güncel ilişki kaydını yeniden doğrulayarak devam edin.</p> : <>
      <RelationshipSummary state={state} />
      <button className="button secondary" disabled={busy} onClick={() => void download()}>Kuruma özel inceleme dosyasını doğrula ve indir</button>
      {!state.can_record && <p>Karar kaydetmek için her iki kaynak incelemesini de üstlenmelisiniz. Kaynak inceleme sayfalarından devam edin.</p>}
      <form onSubmit={event => { event.preventDefault(); void save(); }}><fieldset className="source-review-fieldset" disabled={!state.can_record || busy}>
        <legend>Yeni ilişki görüşü · Revizyon {state.revision}</legend>
        <Field label="İlişki">{id => <select id={id} value={draft.classification} onChange={event => change('classification', event.target.value as Classification)}>{Object.entries(RELATIONSHIPS).map(([value, label]) => <option key={value} value={value} disabled={value !== 'unresolved' && !state.identity_reviews_ready}>{label}</option>)}</select>}</Field>
        {draft.classification !== 'unresolved' && <div className="form-grid">{(['leftWork', 'leftVersion', 'rightWork', 'rightVersion'] as const).map((key, index) => <Field key={key} label={['Birinci hukuki eser referansı', 'Birinci sürüm referansı', 'İkinci hukuki eser referansı', 'İkinci sürüm referansı'][index]}>{id => <input id={id} maxLength={300} value={draft[key]} onChange={event => change(key, event.target.value)} />}</Field>)}</div>}
        <Field label="Gerekçe ve belirsizlikler">{id => <textarea id={id} minLength={3} maxLength={4000} required value={draft.rationale} onChange={event => change('rationale', event.target.value)} />}</Field>
        <Field label="Karşılaştırmadan ayrı inceleme dayanağı">{id => <input id={id} maxLength={1000} value={draft.reference} onChange={event => change('reference', event.target.value)} />}</Field>
        <Field label="Dayanak SHA256">{id => <input id={id} maxLength={64} value={draft.sha256} onChange={event => change('sha256', event.target.value)} />}</Field>
        <div className="form-grid"><Field label="Bu ilişki incelemesinin aktif süresi (saniye)">{id => <input id={id} type="number" min={0} max={86400} value={draft.seconds} onChange={event => change('seconds', event.target.value)} />}</Field><Field label="Süre dayanağı">{id => <select id={id} value={draft.basis} onChange={event => change('basis', event.target.value as RelationshipDraft['basis'])}><option value="estimate">Tahmin</option><option value="self_reported_timer">Zamanlayıcı beyanı</option></select>}</Field></div>
        <p className="small muted">Bilinmeyen süreyi boş bırakın. Kaynak incelemesinde zaten beyan edilen süreyi tekrar eklemeyin. Bu işlem otomatik zamanlayıcı başlatmaz.</p>
        <button className="button primary" type="submit">İnsan görüşünü kaydet</button>
      </fieldset></form>
    </>}
  </section>;
}

export function RelationshipSummary({ state }: { state: RelationshipState }) {
  return <><p className="small muted">Kurumunuza özel · Revizyon {state.revision}. {state.stale ? 'Dayanak incelemesi değişti; yeniden insan incelemesi gerekir.' : state.resolved_for_handoff ? 'Kaynak kimliği görüşü bağımsız incelemeye hazır.' : 'Kimlik/sürüm çözümlemesi tamamlanmadı.'}</p>
    {state.latest ? <><h3>{RELATIONSHIPS[state.latest.input.classification]}</h3><p className="source-review-rationale">{state.latest.input.rationale}</p><p className="small muted">{state.latest.reviewer.name} · {state.latest.created_at}</p></> : <p>Bu iki kaynak için henüz görüş kaydedilmedi.</p>}
    <Detail title="Önceki görüşler ve dayanakları"><p className="reference-id">İlişki kimliği: {state.pair_id}</p>{state.history_truncated && <p>Son 50 görüş gösteriliyor; geçmiş sınırı açıkça korunur.</p>}
      <ol className="source-review-history">{state.history.map(event => <li key={event.id}><strong>Revizyon {event.revision} · {RELATIONSHIPS[event.input.classification]}</strong><p>{event.input.rationale}</p><p>{event.reviewer.name} · {event.created_at}</p>
        <p className="small">Aktif süre: {event.input.effort === null ? 'bilinmiyor' : `${event.input.effort.active_seconds} saniye · ${event.input.effort.basis === 'estimate' ? 'Tahmin' : 'Zamanlayıcı beyanı'}`}</p>
        {event.input.identities.map(item => <p key={item.source_id} className="reference-id">{item.source_id}: {item.work_ref} · {item.version_ref}</p>)}
        <p className="reference-id">Karşılaştırma: {event.comparison_evidence.evidence_sha256}</p>{event.input.evidence_refs.map(item => <p key={`${item.reference}:${item.sha256}`}>{item.reference}<span className="reference-id"> · {item.sha256}</span></p>)}</li>)}</ol>
    </Detail></>;
}
