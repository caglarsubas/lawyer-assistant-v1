import { useEffect, useRef, useState, type FormEvent } from 'react';
import { ApiError, request } from '../api';
import { Detail, Field, Loading, Notice } from '../components';
import type { SourceReviewDecision, User } from '../types';
import { formatDate, messageOf } from '../utils';
import { fetchEquivalenceHandoff, type EquivalenceHandoff } from './equivalenceHandoff';
import GraphBReviewStatus from './GraphBReviewStatus';
import type { IdentityState } from './decisionIdentity';
import { equivalencePath, equivalencePayload, fetchEquivalence, mayReviewEquivalence, validateEquivalence, validateSelection, type EquivalenceClaims, type EquivalenceState, type EvidenceProof, type EvidenceSelection } from './decisionEquivalence';

export default function DecisionEquivalenceReview({ identity, user, onDenied }: { identity: IdentityState; user: User; onDenied: () => void }) {
  const [peer, setPeer] = useState(''); const [register, setRegister] = useState('');
  const [selection, setSelection] = useState<EvidenceSelection | null>(null); const [error, setError] = useState('');
  function open(event: FormEvent) {
    event.preventDefault(); setSelection(null); setError('');
    try { setSelection(validateSelection(identity.source.id, { peer: peer.trim(), register: register.trim() })); } catch (cause) { setError(messageOf(cause)); }
  }
  function denied() { setSelection(null); setPeer(''); setRegister(''); onDenied(); }
  return <section className="source-review-section"><h2>Kaynaklar arası karar eşdeğerliği ve kurum sicili</h2>
    <p>İki karar belgesini ayrı sicil kaynağıyla karşılaştırın. Aynı numara veya kurum adı otomatik eşdeğerlik oluşturmaz. Kimlikler ve belge sürümleri korunur.</p>
    <form onSubmit={open}><Field label="Diğer karar kaynağının kimliği">{id => <input id={id} required pattern="[a-f0-9]{64}" maxLength={64} value={peer} onChange={e => { setSelection(null); setPeer(e.target.value); }} />}</Field>
      <Field label="Aktarılmış kurum sicili kaynağının kimliği">{id => <input id={id} required pattern="[a-f0-9]{64}" maxLength={64} value={register} onChange={e => { setSelection(null); setRegister(e.target.value); }} />}</Field>
      <button className="button secondary">Karar ve sicil kaynaklarını aç</button></form>
    {error && <Notice error>{error}</Notice>}
    {selection && <EquivalenceWorkspace key={`${selection.peer}:${selection.register}:${identity.revision}:${identity.mapping_revision}:${identity.source_review_revision}`} identity={identity} user={user} selection={selection} onDenied={denied} />}
  </section>;
}

function EquivalenceWorkspace({ identity, user, selection, onDenied }: { identity: IdentityState; user: User; selection: EvidenceSelection; onDenied: () => void }) {
  const [state, setState] = useState<EquivalenceState | null>(null); const [error, setError] = useState(''); const [busy, setBusy] = useState(false); const [denied, setDenied] = useState(false);
  const [relation, setRelation] = useState<EquivalenceClaims['relation']>('undetermined'); const [institution, setInstitution] = useState(''); const [name, setName] = useState(''); const [record, setRecord] = useState('');
  const [canonicalId, setCanonicalId] = useState('');
  const [rationale, setRationale] = useState(''); const [reviewRationale, setReviewRationale] = useState(''); const [decision, setDecision] = useState<SourceReviewDecision>('needs_changes');
  const [proofs, setProofs] = useState<EvidenceProof[]>([]); const [reviewProofs, setReviewProofs] = useState<EvidenceProof[]>([]);
  const [handoff, setHandoff] = useState<EquivalenceHandoff | null>(null); const urls = useRef(new Set<string>());
  const controller = useRef<AbortController | null>(null);
  function start() { controller.current?.abort(); const operation = new AbortController(); controller.current = operation; setError(''); setBusy(true); setHandoff(null); for (const url of urls.current) URL.revokeObjectURL(url); urls.current.clear(); return operation; }
  function fail(cause: unknown, operation: AbortController) {
    if (operation.signal.aborted) return;
    setError(messageOf(cause));
    if (cause instanceof ApiError && cause.status === 409) { setState(null); setProofs([]); setReviewProofs([]); }
    if (cause instanceof ApiError && [401, 403].includes(cause.status)) { setState(null); setProofs([]); setReviewProofs([]); setInstitution(''); setName(''); setRecord(''); setRationale(''); setReviewRationale(''); setDenied(true); onDenied(); }
  }
  async function load() {
    const operation = start(); setState(null); setProofs([]); setReviewProofs([]);
    try { const value = await fetchEquivalence(identity, user, selection, operation.signal); if (!operation.signal.aborted) setState(value); }
    catch (cause) { fail(cause, operation); } finally { if (!operation.signal.aborted) setBusy(false); }
  }
  useEffect(() => { void load(); return () => { controller.current?.abort(); for (const url of urls.current) URL.revokeObjectURL(url); urls.current.clear(); }; }, []);
  async function download() {
    if (!state || busy) return;
    const operation = start();
    try {
      const result = await fetchEquivalenceHandoff(state, identity.source.id, selection, user, operation.signal);
      if (!operation.signal.aborted) {
        const url = URL.createObjectURL(new Blob([result.evidence_json], { type: 'application/json' })); urls.current.add(url);
        const link = document.createElement('a'); link.href = url; link.download = `gizli-cok-kaynakli-graph-b-${result.data.packet_id}.json`; document.body.append(link); link.click(); link.remove();
        window.setTimeout(() => { URL.revokeObjectURL(url); urls.current.delete(url); }, 1000);
        setHandoff(result.data);
      }
    } catch (cause) { fail(cause, operation); } finally { if (!operation.signal.aborted) setBusy(false); }
  }
  async function save(event: FormEvent, review: boolean) {
    event.preventDefault(); if (!state || busy) return;
    const operation = start();
    try {
      const body = review ? equivalencePayload(state, reviewRationale, reviewProofs, undefined, decision)
        : equivalencePayload(state, rationale, proofs, { relation, canonical_decision_id: relation === 'same_decision' ? canonicalId : null, institution_id: institution.trim(), registered_name: name, register_record_id: record });
      const value = await request<EquivalenceState>(equivalencePath(identity.source.id, selection, review), { method: 'POST', body: JSON.stringify(body), signal: operation.signal });
      validateEquivalence(value, identity, user, selection); if (value.context_id !== state.context_id) throw new Error('İnceleme bağlamı değişti; yeniden açın.');
      if (!operation.signal.aborted) { setState(value); setRationale(''); setReviewRationale(''); setProofs([]); setReviewProofs([]); }
    } catch (cause) { fail(cause, operation); } finally { if (!operation.signal.aborted) setBusy(false); }
  }
  return <>{busy && <Loading label="Kaynaklar arası inceleme sürüyor…" />}{error && <Notice error>{error}</Notice>}
    {!denied && <button className="button secondary" disabled={busy} onClick={() => void load()}>Eşdeğerlik incelemesini yenile</button>}
    {state && <><EquivalenceSummary state={state} />
      <button className="button secondary" disabled={busy || !state.same_decision_supported || !state.export_allowed} onClick={() => void download()}>Çok kaynaklı gizli Graph B aday paketini indir (JSON)</button>
      <p className="small muted">İki karar sürümü, kurum sicili ve tam inceleme geçmişleri birlikte indirilir. Üç kaynak için açık dışa aktarma izni ve güncel aynı-karar kabulü gerekir.</p>
      {handoff && <EquivalenceHandoffSummary data={handoff} />}
      <GraphBReviewStatus key={`${state.revision}:${JSON.stringify(state.pins)}`} state={state} user={user} source={identity.source.id} selection={selection} onDenied={onDenied} />
      <Detail title="Kaynaklar ve dayanak revizyonları">{Object.entries(state.sources).map(([key, source]) => <article key={key}><h3>{key === state.register_source_id ? 'Kurum sicili' : 'Karar belgesi'} · {source.title}</h3>
        <p className="small source-passage-text">{key} · {source.source_version_id}</p><p>Kaynak incelemesi {state.pins.source_revisions[key]} · Eşleme {state.pins.mapping_revisions[key]}{key in state.pins.identity_revisions ? ` · Kimlik ${state.pins.identity_revisions[key]}` : ''}</p>
        {state.decisions[key] && <dl>{Object.entries(state.decisions[key]!).map(([field, value]) => <div key={field}><dt>{{decision_id: 'Karar', proceeding_id: 'Yargılama', institution_id: 'Tarihsel kurum', version_id: 'Belge sürümü'}[field]}</dt><dd className="source-passage-text">{value}</dd></div>)}</dl>}
        <a href={`#/sources/${key}/review`}>Kaynağı ve tam pasajlarını incele</a></article>)}</Detail>
      {!state.inputs_ready && <Notice>İki güncel bağımsız kimlik kabulü, üç kaynağın kabul edilmiş incelemeleri ve tam pasaj dayanakları gerekir. Metin veya harici sicil referanslarını önce fiziksel kaynaklara yeniden bağlayın.</Notice>}
      <Detail title="Eşdeğerlik ve sicil önerisi"><form onSubmit={event => void save(event, false)}><fieldset disabled={busy || !state.can_propose}>
        <Field label="Karar karşılaştırmasının sonucu">{id => <select id={id} value={relation} onChange={e => setRelation(e.target.value as EquivalenceClaims['relation'])}><option value="undetermined">Belirlenemedi</option><option value="different_decision">Farklı kararlar</option><option value="same_decision">Aynı karar iddiası</option></select>}</Field>
        {relation === 'same_decision' && <Field label="Önerilen kanonik karar kimliği">{id => <select id={id} required value={canonicalId} onChange={e => setCanonicalId(e.target.value)}><option value="">İncelenmiş kimliklerden seçin</option>{Object.entries(state.decisions).map(([key, value]) => value && <option key={key} value={value.decision_id}>{value.decision_id} · {state.sources[key].source_version_id}</option>)}</select>}</Field>}
        <Field label="Sicildeki tarihsel kurum kimliği">{id => <input id={id} required maxLength={180} value={institution} onChange={e => setInstitution(e.target.value)} placeholder="urn:tr-law:institution:…" />}</Field>
        <Field label="Sicilde kayıtlı kurum adı">{id => <input id={id} required minLength={3} maxLength={300} value={name} onChange={e => setName(e.target.value)} />}</Field>
        <Field label="Sicil kayıt referansı">{id => <input id={id} required minLength={3} maxLength={300} value={record} onChange={e => setRecord(e.target.value)} />}</Field>
        <ProofFields state={state} value={proofs} onChange={setProofs} />
        <Field label="Karşılaştırma ve kurum dayanağı gerekçesi">{id => <textarea id={id} required minLength={3} maxLength={4000} value={rationale} onChange={e => setRationale(e.target.value)} />}</Field>
        <button className="button">Eşdeğerlik önerisini kaydet</button></fieldset></form></Detail>
      {state.current && <Detail title="Bağımsız eşdeğerlik incelemesi"><p>Öneren, iki kararın kimlik incelemecileri ve üç kaynağın tüm dayanak katkıcılarından ayrı hesap gerekir. Ayrı kişi veya mesleki yeterlik bu kontrolle kanıtlanmaz.</p>
        <form onSubmit={event => void save(event, true)}><fieldset disabled={busy || !mayReviewEquivalence(state, user)}>
          <Field label="Eşdeğerlik inceleme kararı">{id => <select id={id} value={decision} onChange={e => setDecision(e.target.value as SourceReviewDecision)}><option value="needs_changes">Düzeltme iste</option><option value="rejected">Reddet</option><option value="accepted">İddiayı kabul et</option></select>}</Field>
          <ProofFields state={state} value={reviewProofs} onChange={setReviewProofs} />
          <Field label="Bağımsız karşılaştırma gerekçesi">{id => <textarea id={id} required minLength={3} maxLength={4000} value={reviewRationale} onChange={e => setReviewRationale(e.target.value)} />}</Field>
          <button className="button">Bağımsız eşdeğerlik incelemesini kaydet</button></fieldset></form></Detail>}
    </>}
  </>;
}

function ProofFields({ state, value, onChange }: { state: EquivalenceState; value: EvidenceProof[]; onChange: (value: EvidenceProof[]) => void }) {
  return <>{Object.entries(state.sources).map(([key, source]) => {
    const proof = value.find(p => p.source_id === key) || { source_id: key, passage_id: '', sha256: '' };
    function update(change: Partial<EvidenceProof>) { onChange([...value.filter(p => p.source_id !== key), { ...proof, ...change }]); }
    return <fieldset key={key}><legend>{key === state.register_source_id ? 'Sicil' : 'Karar'} dayanağı · {source.title}</legend>
      <Field label={`${key === state.register_source_id ? 'Sicil' : 'Karar'} pasaj kimliği · ${key.slice(0, 8)}`}>{id => <input id={id} required maxLength={80} value={proof.passage_id} onChange={e => update({ passage_id: e.target.value.trim() })} />}</Field>
      <Field label={`Pasaj SHA256 · ${key.slice(0, 8)}`}>{id => <input id={id} required pattern="[a-f0-9]{64}" maxLength={64} value={proof.sha256} onChange={e => update({ sha256: e.target.value.trim() })} />}</Field>
    </fieldset>;
  })}</>;
}
export function EquivalenceSummary({ state }: { state: EquivalenceState }) {
  const labels = { same_decision: 'Aynı karar iddiası', different_decision: 'Farklı kararlar', undetermined: 'Belirlenemedi' };
  return <><p>Eşdeğerlik revizyonu {state.revision} · {state.stale ? 'Yeniden inceleme gerekli' : state.review_accepted ? 'Ayrı hesap incelemesi kabul edildi' : 'İnceleme bekliyor'}</p>
    <Notice>Büroya özel · Kimlikler birleştirilmedi · Graf yayımlanmadı · Kurumun görev/yetkisi, hukuki etki ve tarihsel geçerlilik doğrulanmadı.</Notice>
    {state.current && <><h3>{labels[state.current.proposal.claims.relation]}</h3><p>{state.current.proposal.claims.registered_name} · {state.current.proposal.claims.register_record_id}</p>
      <p className="source-passage-text">Önerilen kanonik aday: {state.current.proposal.claims.canonical_decision_id || 'Yok; kararlar birleştirilemez'}</p>
      <Detail title="Tam eşdeğerlik ve sicil inceleme geçmişi">{state.history.map(event => <article key={event.id}><p>Revizyon {event.revision} · {event.actor.name} · {formatDate(event.created_at, true)} · {event.decision || 'Öneri'}</p>
        <p>{labels[event.proposal.claims.relation]} · {event.rationale}</p><pre className="source-passage-text">{JSON.stringify({claims: event.proposal.claims, decisions: event.proposal.decisions}, null, 2)}</pre><p className="small source-passage-text">Dayanak sürümü: {event.proposal.snapshot_sha256}</p>
        {event.evidence.map(proof => <p className="small source-passage-text" key={`${proof.source_id}:${proof.passage_id}`}>{proof.source_id} · {proof.passage_id} · {proof.sha256}</p>)}</article>)}</Detail></>}
  </>;
}

export function EquivalenceHandoffSummary({ data }: { data: EquivalenceHandoff }) {
  return <section className="source-review-section"><h3>Çok kaynaklı Graph B devir adayı hazır</h3><p>Üç özgün kaynak · İki karar sürümü · Altı yapı doğrulanmış kimlik adayı</p>
    <p className="source-passage-text">Kanonik aday: {data.canonical_candidate}</p><p className="small source-passage-text">Paket: {data.packet_id}</p>
    <Notice>Büroya özel · İmzalanmadı · Graf yayımlanmadı · Kimlik rezervasyonları korunuyor · Hukuki doğruluk ve kurumun görev/yetkisi doğrulanmadı.</Notice>
    {data.limitations.map(text => <p className="small muted" key={text}>{text}</p>)}
  </section>;
}
