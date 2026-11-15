import { useEffect, useRef, useState, type FormEvent } from 'react';
import { ApiError } from '../api';
import { Detail, Field, Loading, Notice } from '../components';
import type { SourceReviewDecision, User } from '../types';
import { formatDate, messageOf } from '../utils';
import type { DecisionState } from './decisionMapping';
import DecisionEquivalenceReview from './DecisionEquivalenceReview';
import { writeCuratorReview } from './curatorReviewBinding';
import { evidence, fetchGraphBHandoff, fetchIdentities, identityPath, identityPins, identityProposalPayload, mayIndependentlyReview, validateIdentityContinuation, validateIdentityState, type GraphBHandoff, type IdentityState } from './decisionIdentity';

export default function DecisionIdentityReview({ source, user, onDenied }: { source: DecisionState; user: User; onDenied: () => void }) {
  const [state, setState] = useState<IdentityState | null>(null);
  const [pending, setPending] = useState<{ before: IdentityState; verified: boolean } | null>(null);
  const [handoff, setHandoff] = useState<GraphBHandoff | null>(null); const urls = useRef(new Set<string>());
  const [error, setError] = useState(''); const [busy, setBusy] = useState(false); const [denied, setDenied] = useState(false);
  const [institution, setInstitution] = useState(''); const [proceeding, setProceeding] = useState(''); const [decisionId, setDecisionId] = useState('');
  const [reference, setReference] = useState(''); const [sha, setSha] = useState(''); const [institutionRef, setInstitutionRef] = useState(''); const [institutionSha, setInstitutionSha] = useState('');
  const [reviewRef, setReviewRef] = useState(''); const [reviewSha, setReviewSha] = useState(''); const [rationale, setRationale] = useState('');
  const [decision, setDecision] = useState<SourceReviewDecision>('needs_changes');
  const controller = useRef<AbortController | null>(null);
  function start() { controller.current?.abort(); const operation = new AbortController(); controller.current = operation; setBusy(true); setError(''); setHandoff(null); return operation; }
  function fail(cause: unknown, operation: AbortController) {
    if (operation.signal.aborted) return;
    setError(messageOf(cause));
    if (cause instanceof ApiError && [401, 403].includes(cause.status)) {
      setState(null); setPending(null); setDenied(true); setInstitution(''); setProceeding(''); setDecisionId(''); setReference(''); setSha(''); setInstitutionRef(''); setInstitutionSha(''); setReviewRef(''); setReviewSha(''); setRationale(''); onDenied();
      for (const url of urls.current) URL.revokeObjectURL(url); urls.current.clear();
    }
  }
  async function load() {
    const operation = start();
    const before = pending?.before || state;
    if (before) setPending({ before, verified: false });
    try {
      const result = await fetchIdentities(source, operation.signal);
      if (operation.signal.aborted) return;
      if (before) validateIdentityContinuation(result, before);
      setState(result);
      setPending(before && (pending || before.revision !== result.revision) ? { before, verified: true } : null);
    }
    catch (cause) { fail(cause, operation); } finally { if (!operation.signal.aborted) setBusy(false); }
  }
  useEffect(() => { void load(); return () => { controller.current?.abort(); for (const url of urls.current) URL.revokeObjectURL(url); urls.current.clear(); }; }, []);
  async function download() {
    if (!state || busy || pending) return;
    const operation = start();
    try {
      const result = await fetchGraphBHandoff(state, user, operation.signal);
      if (!operation.signal.aborted) {
        const url = URL.createObjectURL(new Blob([result.evidence_json], { type: 'application/json' })); urls.current.add(url);
        const link = document.createElement('a'); link.href = url; link.download = `gizli-graph-b-devir-${result.data.packet_id}.json`; document.body.append(link); link.click(); link.remove();
        window.setTimeout(() => { URL.revokeObjectURL(url); urls.current.delete(url); }, 1000);
        setHandoff(result.data);
      }
    } catch (cause) { fail(cause, operation); } finally { if (!operation.signal.aborted) setBusy(false); }
  }
  async function save(event: FormEvent, review: boolean) {
    event.preventDefault(); if (!state || busy || pending) return;
    const operation = start();
    let submitted = false;
    try {
      const body = review ? { ...identityPins(state, rationale), decision, evidence_refs: evidence(reviewRef, reviewSha) }
        : identityProposalPayload(state, { institution_id: institution.trim(), proceeding_id: proceeding.trim(), decision_id: decisionId.trim(),
          identity_evidence: evidence(reference, sha), institution_evidence: evidence(institutionRef, institutionSha) }, rationale);
      const path = identityPath(source.source.id);
      submitted = true;
      const result = await writeCuratorReview<IdentityState>(`${path}${review ? '/review' : ''}`, path, body, operation.signal);
      if (operation.signal.aborted) return;
      setPending({ before: state, verified: false });
      if (result.conflict) {
        setError(result.refreshError || result.reason);
        if (!result.state) return;
        validateIdentityContinuation(validateIdentityState(result.state, source), state);
        setState(result.state);
        setPending({ before: state, verified: true });
        return;
      }
      validateIdentityContinuation(validateIdentityState(result.state, source), state, true);
      setState(result.state); setPending(null); setRationale('');
    } catch (cause) {
      if (!operation.signal.aborted && submitted && (!(cause instanceof ApiError) || cause.status === 0 || cause.status >= 500)) {
        setPending({ before: state, verified: false });
      }
      fail(cause, operation);
    } finally { if (!operation.signal.aborted) setBusy(false); }
  }
  return <section className="source-review-section"><h2>Kanonik karar kimliği ve bağımsız inceleme</h2>
    <p>Karar, yargılama ve tarihsel kurum ayrı kimliklerdir. Esas veya başvuru numarası tek başına karar kimliği oluşturmaz.</p>
    {busy && <Loading label="Kimlik incelemesi yükleniyor…" />}{error && <Notice error>{error}</Notice>}
    {!denied && <button className="button secondary" disabled={busy} onClick={() => void load()}>Kimlik incelemesini yenile</button>}
    {pending && <Notice error>
      <p>Kimlik taslağının dayandığı revizyon {pending.before.revision}. {pending.verified ? `Güncel revizyon ${state?.revision}.` : 'Güncel kayıt henüz doğrulanmadı.'} Taslağınız açık.</p>
      {pending.verified && <button className="button secondary" type="button" disabled={busy} onClick={() => { setPending(null); setError(''); }}>Güncel kimlik kaydını inceledim, yeni incelemeye başla</button>}
    </Notice>}
    {state && <><IdentitySummary state={state} />
      <button className="button secondary" disabled={busy || Boolean(pending) || !state.staged_handoff_ready || !state.export_allowed} onClick={() => void download()}>Graph B için gizli aday paketini indir (JSON)</button>
      <p className="small muted">Güncel bağımsız kabul ve açık dışa aktarma izni gerekir. Kimlik, kurum ve bağımsız inceleme dayanakları bu kaynağın kabul edilmiş pasajına bağlanmalı. Harici referanslar çözülmez.</p>
      <p className="small source-passage-text">Dayanak biçimi: source:{source.source.id}:passage:pasaj-kimliği · SHA256: pasajın içerik özeti</p>
      {handoff && <HandoffSummary data={handoff} />}
      <Detail title="Açık kimlik önerisi"><form onSubmit={event => void save(event, false)}><fieldset disabled={busy || Boolean(pending) || state.assigned_to?.id !== user.id || !source.handoff_ready}>
        <Field label="Tarihsel kurum kimliği">{id => <input id={id} required value={institution} placeholder="urn:tr-law:institution:…" maxLength={180} onChange={e => setInstitution(e.target.value)} />}</Field>
        <Field label="Yargılama kimliği">{id => <input id={id} required value={proceeding} placeholder="urn:tr-law:proceeding:…" maxLength={180} onChange={e => setProceeding(e.target.value)} />}</Field>
        <Field label="Karar kimliği">{id => <input id={id} required value={decisionId} placeholder="urn:tr-law:decision:…" maxLength={180} onChange={e => setDecisionId(e.target.value)} />}</Field>
        <Field label="Kimlik dayanağı">{id => <input id={id} required value={reference} maxLength={1000} onChange={e => setReference(e.target.value)} />}</Field>
        <Field label="Kimlik dayanağı SHA256">{id => <input id={id} required value={sha} maxLength={64} onChange={e => setSha(e.target.value)} />}</Field>
        <Field label="Kurum dayanağı">{id => <input id={id} required value={institutionRef} maxLength={1000} onChange={e => setInstitutionRef(e.target.value)} />}</Field>
        <Field label="Kurum dayanağı SHA256">{id => <input id={id} required value={institutionSha} maxLength={64} onChange={e => setInstitutionSha(e.target.value)} />}</Field>
        <Field label="Kimlik önerisinin gerekçesi">{id => <textarea id={id} required minLength={3} maxLength={4000} value={rationale} onChange={e => setRationale(e.target.value)} />}</Field>
        <button className="button">Kimlik önerisini kaydet</button>
      </fieldset></form><p className="small muted">Kaynak sorumlusu önerir. Yeni öneri önceki kabulü kullanmaz; kaynak ve eşleme değişince yeniden inceleme gerekir.</p></Detail>
      {state.current && <Detail title="Bağımsız kimlik incelemesi"><p>Öneren ve dayanak incelemelerindeki tüm hesaplardan farklı bir incelemeci gerekir. Bu kural ayrı kişiyi veya çıkar çatışmasının yokluğunu otomatik kanıtlamaz.</p>
        <form onSubmit={event => void save(event, true)}><fieldset disabled={busy || Boolean(pending) || !mayIndependentlyReview(state, user)}>
          <Field label="Kimlik inceleme kararı">{id => <select id={id} value={decision} onChange={e => setDecision(e.target.value as SourceReviewDecision)}><option value="needs_changes">Düzeltme iste</option><option value="rejected">Reddet</option><option value="accepted">Kabul et</option></select>}</Field>
          <Field label="Bağımsız inceleme dayanağı">{id => <input id={id} required value={reviewRef} maxLength={1000} onChange={e => setReviewRef(e.target.value)} />}</Field>
          <Field label="Bağımsız dayanak SHA256">{id => <input id={id} required value={reviewSha} maxLength={64} onChange={e => setReviewSha(e.target.value)} />}</Field>
          <Field label="Bağımsız inceleme gerekçesi">{id => <textarea id={id} required minLength={3} maxLength={4000} value={rationale} onChange={e => setRationale(e.target.value)} />}</Field>
          <button className="button">Bağımsız incelemeyi kaydet</button>
        </fieldset></form></Detail>}
      <fieldset className="source-review-fieldset" disabled={Boolean(pending)}><legend className="visually-hidden">Eşdeğerlik incelemesi</legend><DecisionEquivalenceReview identity={state} user={user} onDenied={onDenied} /></fieldset>
    </>}
  </section>;
}
export function IdentitySummary({ state }: { state: IdentityState }) {
  return <><p>Kimlik revizyonu {state.revision} · {state.stale ? 'Yeniden inceleme gerekli' : state.canonical_identity_reviewed ? 'Ayrı hesap incelemesi kabul edildi' : 'İnceleme bekliyor'}</p>
    <Notice>Büroya özel · Graf yayımlanmadı · Genel kimlik sicili doğrulanmadı · Hukuki etki ve kesinleşme bilinmiyor.</Notice>
    {state.current && <><dl>{Object.entries(state.current.proposal.identity).filter(([key]) => key.endsWith('_id')).map(([key, value]) => <div key={key}><dt>{{ institution_id: 'Kurum', proceeding_id: 'Yargılama', decision_id: 'Karar' }[key]}</dt><dd className="source-passage-text">{String(value)}</dd></div>)}<div><dt>Belgeye bağlı karar sürümü</dt><dd className="source-passage-text">{state.current.proposal.version_id}</dd></div></dl>
      <Detail title="Tam kimlik inceleme geçmişi">{state.history.map(event => <article key={event.id}><p>Revizyon {event.revision} · {event.actor.name} · {formatDate(event.created_at, true)} · {event.decision === 'accepted' ? 'Kabul' : event.decision === 'rejected' ? 'Ret' : event.decision === 'needs_changes' ? 'Düzeltme gerekli' : 'Öneri'}</p><p>{event.rationale}</p><p className="small muted">Eşleme {event.proposal.mapping_revision} · Kaynak inceleme {event.proposal.source_review_revision} · {event.proposal.snapshot_sha256}</p><pre className="source-passage-text">{JSON.stringify(event.proposal.identity, null, 2)}</pre>{event.evidence_refs.map(ref => <p className="source-passage-text" key={`${ref.reference}:${ref.sha256}`}>{ref.reference} · {ref.sha256}</p>)}</article>)}</Detail></>}
  </>;
}
export function HandoffSummary({ data }: { data: GraphBHandoff }) {
  return <div className="source-passage"><h3>İndirilen Graph B aday paketi</h3><p>Büroya özel · İmzasız · Yayımlanmadı</p><p>3 kimlik ilişkisi adayı · Fiziksel dosya özetleri doğrulandı · Hukuki doğruluk doğrulanmadı</p>
    <p className="source-passage-text">Paket: {data.packet_id}</p><p>Kimlik {data.identity_revision} · Eşleme {data.mapping_revision} · Kaynak inceleme {data.source_review_revision}</p>
    <p>Graf ilişkisinden ayrı tutulan eşleme: {data.omitted_mapping_ids.length}</p><Detail title="Paket sınırları">{data.limitations.map(text => <p key={text}>{text}</p>)}</Detail></div>;
}
