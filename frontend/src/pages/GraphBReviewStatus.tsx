import { useEffect, useRef, useState } from 'react';
import { ApiError, request } from '../api';
import { Detail, Loading, Notice } from '../components';
import type { User } from '../types';
import { formatDate, messageOf } from '../utils';
import { fetchGraphBSigning, type GraphBSigningPacket } from './graphBSigning';
import type { EquivalenceState, EvidenceSelection } from './decisionEquivalence';
import { signedReviewPath, validateSignedReview, type SignedGraphBState } from './signedGraphBReview';
export { signedReviewPath, validateSignedReview, type SignedGraphBState } from './signedGraphBReview';

export default function GraphBReviewStatus({ state, user, source, selection, onDenied }: { state: EquivalenceState; user: User; source: string; selection: EvidenceSelection; onDenied: () => void }) {
  const [review, setReview] = useState<SignedGraphBState | null>(null); const [error, setError] = useState(''); const [busy, setBusy] = useState(false);
  const controller = useRef<AbortController | null>(null); const urls = useRef(new Set<string>());
  const [packet, setPacket] = useState<GraphBSigningPacket | null>(null);
  function clearFiles() { setPacket(null); for (const url of urls.current) URL.revokeObjectURL(url); urls.current.clear(); }
  async function load() {
    controller.current?.abort(); const operation = new AbortController(); controller.current = operation; setBusy(true); setReview(null); setError(''); clearFiles();
    try {
      const value = await request<SignedGraphBState>(signedReviewPath(source, selection), { signal: operation.signal });
      validateSignedReview(value, state, user); if (!operation.signal.aborted) setReview(value);
    } catch (cause) {
      if (!operation.signal.aborted) { setError(messageOf(cause)); if (cause instanceof ApiError && [401, 403].includes(cause.status)) onDenied(); }
    } finally { if (!operation.signal.aborted) setBusy(false); }
  }
  async function download() {
    if (!review || busy) return;
    controller.current?.abort(); const operation = new AbortController(); controller.current = operation; setBusy(true); setError(''); clearFiles();
    try {
      const result = await fetchGraphBSigning(state, review, source, selection, user, operation.signal);
      if (!operation.signal.aborted) {
        const url = URL.createObjectURL(new Blob([result.evidence_json], { type: 'application/json' })); urls.current.add(url);
        const link = document.createElement('a'); link.href = url; link.download = `gizli-graph-b-imza-girdileri-${result.data.packet_id}.json`; document.body.append(link); link.click(); link.remove();
        window.setTimeout(() => { URL.revokeObjectURL(url); urls.current.delete(url); }, 1000); setPacket(result.data);
      }
    } catch (cause) {
      if (!operation.signal.aborted) { setError(messageOf(cause)); setReview(null); if (cause instanceof ApiError && [401, 403].includes(cause.status)) onDenied(); }
    } finally { if (!operation.signal.aborted) setBusy(false); }
  }
  useEffect(() => () => { controller.current?.abort(); for (const url of urls.current) URL.revokeObjectURL(url); urls.current.clear(); }, []);
  return <section className="source-review-section"><h3>İmzalı Graph B incelemesi</h3>
    <p>Bağımsız incelemeci karar tarihini, kurumun tarihsel kimliğini ve altı ilişkinin zaman dayanaklarını ayrı değerlendirir. İmza uygulama dışında oluşturulur.</p>
    <button className="button secondary" disabled={busy} onClick={() => void load()}>İmzalı incelemeyi yenile</button>
    {busy && <Loading label="İmzalı inceleme kontrol ediliyor…" />}{error && <Notice error>{error}</Notice>}
    {review && <><SignedGraphBSummary state={review} />
      <button className="button secondary" disabled={busy || !review.signed_review_current || !state.export_allowed} onClick={() => void download()}>Graph B imza girdilerini indir (JSON)</button>
      <p className="small muted">Yalnızca incelenmiş kamu dayanakları imza girdilerine aktarılır. İndirilen zarf büroya özeldir; dış imza, ayrı yayımlama izni ve etkinleştirme gerekir.</p></>}
    {packet && <Notice>Altı ilişkinin imza girdileri doğrulandı · İmzalanmadı · Graf yayımlanmadı. Paket: <span className="source-passage-text">{packet.packet_id}</span></Notice>}
  </section>;
}
export function SignedGraphBSummary({ state }: { state: SignedGraphBState }) {
  const labels = { approve: 'Kabul', reject: 'Ret', needs_changes: 'Düzeltme gerekli' };
  return <><p>İnceleme revizyonu {state.revision} · {state.stale ? 'Yeniden inceleme gerekli' : state.signed_review_current ? 'Güncel bağımsız imza doğrulandı' : 'İmzalı kabul yok'}</p>
    {!state.trust_configured && <Notice>Bağımsız incelemecinin güvenilen kamu anahtarı yapılandırılmalı.</Notice>}
    <Notice>Büroya özel · Graf yayımlanmadı · İmza mesleki yeterliği veya hukuki doğruluğu tek başına kanıtlamaz. Kurumun görev/yetkisi ve kararın kesinleşmesi bu incelemenin kapsamı dışındadır.</Notice>
    {state.current && <><p>{state.current.envelope.body.public_reviewer} · {labels[state.current.envelope.body.decision]} · {formatDate(state.current.envelope.body.reviewed_at, true)}</p>
      <p>Karar tarihi değerlendirmesi: {state.current.envelope.body.qualifications.decision_on || 'Bilinmiyor; hukuki kabul yok'}</p>
      <p>Kurum kimliği: {state.current.envelope.body.qualifications.institution.registered_name} · {state.current.envelope.body.qualifications.institution.register_record_id}</p></>}
    <Detail title="Tam imzalı inceleme geçmişi">{state.history.map(event => <article key={event.id}><p>Revizyon {event.revision} · {event.actor.name} · {labels[event.envelope.body.decision]}</p>
      <p>İnceleme görevlendirmesi: {event.envelope.body.appointment.valid_from} – {event.envelope.body.appointment.valid_until}</p>
      {event.envelope.body.qualifications.relations.map(entry => <p key={`${entry.source_id}:${entry.relation}`} className="source-passage-text">{entry.source_id.slice(0, 8)} · {entry.relation} · {entry.end_status === 'unknown' ? 'Zamansal uygulanabilirlik bilinmiyor' : `${entry.valid_from} – ${entry.valid_until || `Kontrol ufku: ${entry.checked_through}`}`}</p>)}</article>)}</Detail>
  </>;
}
