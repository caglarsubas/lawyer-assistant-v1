import type { ReactNode } from 'react';
import { Detail } from '../components';
import { formatDate } from '../utils';

interface RecordedEvent {
  id: string; revision: number; reviewer: { id: string; name: string }; created_at: string;
  rationale: string; evidence_refs: { reference: string; sha256: string }[];
}
/** The saved event is rendered verbatim. This component cannot revise or approve it. */
export function ReviewRecord({ event, label, children }: { event: RecordedEvent; label: string; children?: ReactNode }) {
  return <article className="review-record">
    <header><h4>{label}</h4><span className="small muted">Revizyon {event.revision}</span></header>
    <p className="review-record-byline">{event.reviewer.name} · {formatDate(event.created_at, true)}</p>
    <p className="small-label">Kaydedilen gerekçe</p><p className="source-review-rationale">{event.rationale}</p>
    {children}
    <Detail title={`Dayanaklar ve kayıt bilgileri (${event.evidence_refs.length})`} variant="technical">
      <dl className="coverage-fields"><div><dt>Olay kimliği</dt><dd className="reference-id">{event.id}</dd></div><div><dt>İnceleyen hesap</dt><dd className="reference-id">{event.reviewer.id}</dd></div></dl>
      {event.evidence_refs.length ? <ul className="review-evidence-list">{event.evidence_refs.map((item, index) => <li key={index}><p>{item.reference}</p><p className="reference-id">SHA-256 · {item.sha256}</p></li>)}</ul> : <p className="small muted">Bu olayda dayanak referansı kaydedilmemiş.</p>}
    </Detail>
  </article>;
}
