import { useEffect, useState, type FormEvent } from 'react';
import { patch, post, request } from '../../api';
import { Badge, Empty, Field, Icon, Loading, Notice } from '../../components';
import type { DocumentRecord, Fact, FactStatus, Matter, Passage } from '../../types';
import { FACT_LABELS, formatDate, locatorText, messageOf } from '../../utils';
import { DocumentViewer } from './DocumentsPanel';

export default function FactsPanel({ matter, onChange }: { matter: Matter; onChange: () => Promise<void> }) {
  const [editing, setEditing] = useState<Fact | 'new' | null>(null); const [source, setSource] = useState<string | null>(null);
  return <section><div className="section-heading"><div><h2>Olguların kaydı</h2><p className="muted small">Beyan, varsayım ve belgeye dayalı olgular birbirinin yerine geçmez.</p></div><button className="button secondary" onClick={() => setEditing(editing ? null : 'new')}><Icon name={editing ? 'close' : 'plus'} size={17} />{editing ? 'Formu kapat' : 'Olgu ekle'}</button></div>
    {editing && <FactForm key={editing === 'new' ? 'new' : editing.id} matter={matter} fact={editing === 'new' ? undefined : editing} onCancel={() => setEditing(null)} onSave={async () => { await onChange(); setEditing(null); }} />}
    {!matter.facts?.length ? <Empty title="Olguları görünür kılın.">Belgede geçen bir olguyu, taraf beyanını veya çalışma varsayımını ekleyin. Çelişen bilgileri ayrı ayrı kaydedin.</Empty> : <div className="fact-list">{matter.facts.map((fact, index) => <article className="fact-row" key={fact.id}><span className="matter-number">{String(index + 1).padStart(2, '0')}</span><div className="fact-body"><div className="fact-heading"><Badge status={fact.status} /><span className="small muted">Sürüm {fact.revision} · {formatDate(fact.updated_at)}</span></div><p>{fact.text}</p>{fact.evidence_id ? <button className="text-button" onClick={() => setSource(fact.evidence_id!)}><Icon name="file" size={15} />Dayanağı incele</button> : <span className="small muted">Kaynak pasajı bağlanmamış</span>}</div><button className="icon-button" aria-label={`Olguyu düzelt: ${fact.text.slice(0, 50)}`} onClick={() => setEditing(fact)}><Icon name="edit" size={17} /></button></article>)}</div>}
    {source && <EvidenceViewer matter={matter} evidenceId={source} onClose={() => setSource(null)} />}
  </section>;
}

function FactForm({ matter, fact, onCancel, onSave }: { matter: Matter; fact?: Fact; onCancel: () => void; onSave: () => Promise<void> }) {
  const [text, setText] = useState(fact?.text || ''); const [status, setStatus] = useState<FactStatus>(fact?.status || 'alleged'); const [reason, setReason] = useState('');
  const [evidenceId, setEvidenceId] = useState(fact?.evidence_id || ''); const [docId, setDocId] = useState(''); const [passages, setPassages] = useState<Passage[]>([]);
  const [loadingPassages, setLoadingPassages] = useState(false); const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  useEffect(() => { if (!docId) { setPassages([]); return; } const controller = new AbortController(); setLoadingPassages(true); request<DocumentRecord>(`/matters/${encodeURIComponent(matter.id)}/documents/${encodeURIComponent(docId)}`, { signal: controller.signal }).then((data) => setPassages(data.passages || [])).catch((cause) => { if (cause.name !== 'AbortError') setError(messageOf(cause)); }).finally(() => { if (!controller.signal.aborted) setLoadingPassages(false); }); return () => controller.abort(); }, [docId, matter.id]);
  async function submit(event: FormEvent) { event.preventDefault(); setBusy(true); setError(''); const payload = { text, status, evidence_id: evidenceId || null, ...(fact ? { reason } : {}) }; try { if (fact) await patch(`/matters/${encodeURIComponent(matter.id)}/facts/${encodeURIComponent(fact.id)}`, payload); else await post(`/matters/${encodeURIComponent(matter.id)}/facts`, payload); await onSave(); } catch (cause) { setError(messageOf(cause)); } finally { setBusy(false); } }
  return <form className="inline-form form-grid" onSubmit={submit}><div className="span-full"><h3>{fact ? 'Olguyu düzelt' : 'Yeni olgu'}</h3>{fact && <p className="small muted">Düzeltme, bu olguya bağlı çalışmaların yeniden incelenmesini gerektirebilir.</p>}</div>{error && <div className="span-full"><Notice error>{error}</Notice></div>}<Field label="Olgu veya beyan" className="span-full">{(id) => <textarea id={id} autoFocus required rows={3} value={text} onChange={(event) => setText(event.target.value)} />}</Field><Field label="Bilginin niteliği">{(id) => <select id={id} value={status} onChange={(event) => setStatus(event.target.value as FactStatus)}>{Object.entries(FACT_LABELS).map(([key, label]) => <option value={key} key={key}>{label}</option>)}</select>}</Field><Field label="Kaynak belge">{(id) => <select id={id} value={docId} onChange={(event) => { setDocId(event.target.value); setEvidenceId(''); }}><option value="">Belge seçin</option>{matter.documents?.map((doc) => <option key={doc.id} value={doc.id}>{doc.name}</option>)}</select>}</Field><Field label="Kaynak pasajı" className="span-full" hint={status === 'documented' ? 'Belgelenmiş olgular için bir kaynak pasajı seçin.' : 'Kaynak mevcutsa bağlayın; beyanı belgeye dayalı olgu olarak sunmayın.'}>{(id) => <select id={id} required={status === 'documented'} disabled={loadingPassages} value={evidenceId} onChange={(event) => setEvidenceId(event.target.value)}><option value="">{loadingPassages ? 'Pasajlar yükleniyor…' : 'Pasaj seçin'}</option>{fact?.evidence_id && !passages.some((passage) => passage.id === fact.evidence_id) && <option value={fact.evidence_id}>Mevcut kaynak bağlantısı</option>}{passages.map((passage) => <option key={passage.id} value={passage.id}>{locatorText(passage.locator)} — {passage.text.slice(0, 110)}</option>)}</select>}</Field>{fact && <Field label="Düzeltme gerekçesi" className="span-full">{(id) => <textarea id={id} required rows={2} value={reason} onChange={(event) => setReason(event.target.value)} />}</Field>}<div className="form-actions span-full"><button type="button" className="button secondary" onClick={onCancel}>Vazgeç</button><button className="button primary" disabled={busy}>{busy ? 'Kaydediliyor…' : fact ? 'Düzeltmeyi kaydet' : 'Olguyu kaydet'}</button></div></form>;
}

export function EvidenceViewer({ matter, evidenceId, onClose }: { matter: Matter; evidenceId: string; onClose: () => void }) {
  const [docId, setDocId] = useState<string | null>(null); const [loading, setLoading] = useState(true); const [error, setError] = useState('');
  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setError(''); setDocId(null);
    async function find() {
      for (const document of matter.documents || []) {
        const result = await request<DocumentRecord>(`/matters/${encodeURIComponent(matter.id)}/documents/${encodeURIComponent(document.id)}`, { signal: controller.signal });
        if (result.passages?.some((passage) => passage.id === evidenceId)) { setDocId(document.id); return; }
      }
      setError('Bu dayanak, dosyanın görüntülenebilir pasajlarında bulunamadı. Kaynak içeriği doğrulanmadan iddiayı kabul etmeyin.');
    }
    find().catch((cause) => { if (cause.name !== 'AbortError') setError(messageOf(cause)); }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [matter.id, matter.documents, evidenceId]);
  return <section className="source-inspector" aria-label="Seçili dayanak"><div className="section-heading"><h3>Dayanağı incele</h3><button className="icon-button" aria-label="Dayanak görünümünü kapat" onClick={onClose}><Icon name="close" size={18} /></button></div>{loading ? <Loading label="Dayanak bulunuyor…" /> : error ? <Notice error>{error}</Notice> : docId && <DocumentViewer matterId={matter.id} documentId={docId} highlightPassageId={evidenceId} />}<p className="reference-id small">{evidenceId}</p></section>;
}
