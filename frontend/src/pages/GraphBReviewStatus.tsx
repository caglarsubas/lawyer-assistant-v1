import { useEffect, useRef, useState } from 'react';
import { ApiError, request } from '../api';
import { Detail, Loading, Notice } from '../components';
import type { User } from '../types';
import { formatDate, messageOf } from '../utils';
import { equivalencePath, type EquivalenceState, type EvidenceSelection } from './decisionEquivalence';

export interface SignedGraphBState {
  schema_version: 'signed-graph-b-review-v1'; confidentiality: 'firm_confidential'; firm_id: string; context_id: string;
  revision: number; history_complete: true; stale: boolean; trust_configured: boolean; signed_review_current: boolean;
  history: { id: string; revision: number; created_at: string; actor: { id: string; name: string }; envelope: { algorithm: 'Ed25519'; signature: string;
    body: { decision: 'approve' | 'reject' | 'needs_changes'; public_reviewer: string; reviewed_at: string; reviewer_id: string;
      equivalence_revision: number; expected_review_revision: number; qualifications: { decision_on: string; institution: { scope: 'historical_identity_only'; registered_name: string; register_record_id: string;
        identity_window: { valid_from: string; valid_until: string | null; checked_through: string | null } }; relations: { source_id: string; relation: string; end_status: 'unknown' | 'closed' | 'open_ended'; valid_from: string | null; valid_until: string | null; checked_through: string | null; rationale: string }[] }; appointment: { scope: string; valid_from: string; valid_until: string; statement: string } } } }[];
  current: SignedGraphBState['history'][number] | null;
  graph_updated: false; publication_eligible: false; legal_truth_verified: false; institutional_competence_verified: false; finality_verified: false;
}
export function signedReviewPath(source: string, selection: EvidenceSelection) {
  return equivalencePath(source, selection).replace('/decision-equivalence?', '/graph-b-review?');
}
export function validateSignedReview(value: SignedGraphBState, state: EquivalenceState, user: User) {
  if (value?.schema_version !== 'signed-graph-b-review-v1' || value.confidentiality !== 'firm_confidential' || value.firm_id !== user.firm_id || value.context_id !== state.context_id
    || !Number.isSafeInteger(value.revision) || value.revision < 0 || value.revision > 50 || !Array.isArray(value.history) || value.history.length !== value.revision
    || value.history_complete !== true || value.history.some((event, index) => event.revision !== value.revision - index || event.envelope?.algorithm !== 'Ed25519'
      || event.envelope.body.expected_review_revision !== event.revision - 1 || 'credential_data' in event || 'accepted_key' in event)
    || (value.revision === 0 ? value.current !== null : JSON.stringify(value.current) !== JSON.stringify(value.history[0]))
    || [value.graph_updated, value.publication_eligible, value.legal_truth_verified, value.institutional_competence_verified, value.finality_verified].some(item => item !== false)
    || (value.signed_review_current && (value.stale || !value.trust_configured || value.current?.envelope.body.decision !== 'approve'
      || value.current.envelope.body.equivalence_revision !== state.revision))) throw new Error('İmzalı inceleme seçili büro ve karar bağlamıyla eşleşmiyor. Yenileyin.');
  return value;
}
export default function GraphBReviewStatus({ state, user, source, selection, onDenied }: { state: EquivalenceState; user: User; source: string; selection: EvidenceSelection; onDenied: () => void }) {
  const [review, setReview] = useState<SignedGraphBState | null>(null); const [error, setError] = useState(''); const [busy, setBusy] = useState(false);
  const controller = useRef<AbortController | null>(null);
  async function load() {
    controller.current?.abort(); const operation = new AbortController(); controller.current = operation; setBusy(true); setReview(null); setError('');
    try {
      const value = await request<SignedGraphBState>(signedReviewPath(source, selection), { signal: operation.signal });
      validateSignedReview(value, state, user); if (!operation.signal.aborted) setReview(value);
    } catch (cause) {
      if (!operation.signal.aborted) { setError(messageOf(cause)); if (cause instanceof ApiError && [401, 403].includes(cause.status)) onDenied(); }
    } finally { if (!operation.signal.aborted) setBusy(false); }
  }
  useEffect(() => () => controller.current?.abort(), []);
  return <section className="source-review-section"><h3>İmzalı Graph B incelemesi</h3>
    <p>Bağımsız incelemeci karar tarihini, kurumun tarihsel kimliğini ve altı ilişkinin zaman dayanaklarını ayrı değerlendirir. İmza uygulama dışında oluşturulur.</p>
    <button className="button secondary" disabled={busy} onClick={() => void load()}>İmzalı incelemeyi yenile</button>
    {busy && <Loading label="İmzalı inceleme kontrol ediliyor…" />}{error && <Notice error>{error}</Notice>}
    {review && <SignedGraphBSummary state={review} />}
  </section>;
}
export function SignedGraphBSummary({ state }: { state: SignedGraphBState }) {
  const labels = { approve: 'Kabul', reject: 'Ret', needs_changes: 'Düzeltme gerekli' };
  return <><p>İnceleme revizyonu {state.revision} · {state.stale ? 'Yeniden inceleme gerekli' : state.signed_review_current ? 'Güncel bağımsız imza doğrulandı' : 'İmzalı kabul yok'}</p>
    {!state.trust_configured && <Notice>Bağımsız incelemecinin güvenilen kamu anahtarı yapılandırılmalı.</Notice>}
    <Notice>Büroya özel · Graf yayımlanmadı · İmza mesleki yeterliği veya hukuki doğruluğu tek başına kanıtlamaz. Kurumun görev/yetkisi ve kararın kesinleşmesi bu incelemenin kapsamı dışındadır.</Notice>
    {state.current && <><p>{state.current.envelope.body.public_reviewer} · {labels[state.current.envelope.body.decision]} · {formatDate(state.current.envelope.body.reviewed_at, true)}</p>
      <p>Dayanaklandırılan karar tarihi: {state.current.envelope.body.qualifications.decision_on}</p>
      <p>Kurum kimliği: {state.current.envelope.body.qualifications.institution.registered_name} · {state.current.envelope.body.qualifications.institution.register_record_id}</p></>}
    <Detail title="Tam imzalı inceleme geçmişi">{state.history.map(event => <article key={event.id}><p>Revizyon {event.revision} · {event.actor.name} · {labels[event.envelope.body.decision]}</p>
      <p>İnceleme görevlendirmesi: {event.envelope.body.appointment.valid_from} – {event.envelope.body.appointment.valid_until}</p>
      {event.envelope.body.qualifications.relations.map(entry => <p key={`${entry.source_id}:${entry.relation}`} className="source-passage-text">{entry.source_id.slice(0, 8)} · {entry.relation} · {entry.end_status === 'unknown' ? 'Zamansal uygulanabilirlik bilinmiyor' : `${entry.valid_from} – ${entry.valid_until || `Kontrol ufku: ${entry.checked_through}`}`}</p>)}</article>)}</Detail>
  </>;
}
