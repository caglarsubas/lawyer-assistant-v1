import { useEffect, useRef, useState, type FormEvent } from 'react';
import { ApiError, request } from '../api';
import { Detail, Field, Loading, Notice, PageHeader } from '../components';
import type { PublicSourceOriginalText, PublicSourcePassages, SourceReviewDecision, User } from '../types';
import { messageOf } from '../utils';
import { canReviewSource, fetchOriginalSourceText, SourcePassageList, sourceReviewPath } from './SourceReviewPage';
import { fetchOriginalSourcePdf, mappedPdfPage, type PdfInspection } from './SourcePdfInspection';
import { decisionPath, decisionReviewPayload, emptyResolution, fetchDecisionOccurrences, KIND_LABELS, type DecisionOccurrence, type DecisionOccurrences, type DecisionResolution, type DecisionState } from './decisionMapping';

export default function DecisionMappingPage({ sourceId, user }: { sourceId: string; user: User }) {
  if (!canReviewSource(user)) return <Notice error>İnceleme yetkisi gerekli.</Notice>;
  try { decisionPath(sourceId); } catch (cause) { return <Notice error>{messageOf(cause)}</Notice>; }
  return <DecisionWorkspace key={`${sourceId}:${user.id}:${user.role}:${user.permissions?.join(',')}`} sourceId={sourceId} user={user} />;
}
type Original = { passageId: string; offset: number; state: { status: 'loading' } | { status: 'failed'; message: string; code?: number } | { status: 'loaded'; value: PublicSourceOriginalText | PdfInspection } };
function DecisionWorkspace({ sourceId, user }: { sourceId: string; user: User }) {
  const [state, setState] = useState<DecisionState | null>(null);
  const [passages, setPassages] = useState<PublicSourcePassages | null>(null);
  const [original, setOriginal] = useState<Original | null>(null);
  const [offset, setOffset] = useState(0); const [occurrences, setOccurrences] = useState<DecisionOccurrences | null>(null);
  const [selected, setSelected] = useState<DecisionOccurrence | null>(null); const [mappingId, setMappingId] = useState<string | null>(null);
  const [resolution, setResolution] = useState<DecisionResolution | null>(null);
  const [decision, setDecision] = useState<SourceReviewDecision>('needs_changes'); const [rationale, setRationale] = useState('');
  const [reference, setReference] = useState(''); const [sha256, setSha256] = useState('');
  const [busy, setBusy] = useState(false); const [error, setError] = useState(''); const [message, setMessage] = useState('');
  const [denied, setDenied] = useState(false); const controller = useRef<AbortController | null>(null);
  function begin() { controller.current?.abort(); const next = new AbortController(); controller.current = next; setBusy(true); setError(''); setMessage(''); return next; }
  function clearSelection() { setOccurrences(null); setSelected(null); setMappingId(null); setResolution(null); setRationale(''); setReference(''); setSha256(''); setDecision('needs_changes'); }
  function failure(cause: unknown, operation: AbortController) {
    if (operation.signal.aborted) return;
    setError(messageOf(cause));
    if (cause instanceof ApiError && [401, 403].includes(cause.status)) { setDenied(true); setState(null); setPassages(null); setOriginal(null); clearSelection(); }
  }
  async function load(nextOffset = offset) {
    const operation = begin(); setState(null); setPassages(null); setOriginal(null); clearSelection(); setOffset(nextOffset);
    try {
      const [s, p] = await Promise.all([request<DecisionState>(decisionPath(sourceId), { signal: operation.signal }), request<PublicSourcePassages>(`${sourceReviewPath(sourceId)}/passages?offset=${nextOffset}&limit=20`, { signal: operation.signal })]);
      if (s.source.id !== sourceId || p.source_id !== sourceId || s.source.source_version_id !== p.source_version_id || s.publication_eligible !== false) throw new Error('Kaynak kimliği doğrulanamadı.');
      if (!operation.signal.aborted) { setState(s); setPassages(p); }
    } catch (cause) { failure(cause, operation); } finally { if (!operation.signal.aborted) setBusy(false); }
  }
  useEffect(() => { void load(0); return () => controller.current?.abort(); }, []); // Keyed workspace clears all confidential state on identity/source changes.
  async function inspect(passageId: string) {
    if (!passages) return;
    const passage = passages.items.find(item => item.id === passageId); if (!passage) return;
    const operation = begin(); clearSelection();
    try { const data = await fetchDecisionOccurrences(passages, passage, operation.signal); if (!operation.signal.aborted) setOccurrences(data); }
    catch (cause) { failure(cause, operation); } finally { if (!operation.signal.aborted) setBusy(false); }
  }
  async function inspectOriginal(passageId: string, nextOffset = 0) {
    if (!passages || busy) return;
    const passage = passages.items.find(item => item.id === passageId); if (!passage) return;
    const operation = begin(); setOriginal({ passageId, offset: nextOffset, state: { status: 'loading' } });
    try {
      const value = mappedPdfPage(passage) !== null ? await fetchOriginalSourcePdf(passages, passageId, operation.signal) : await fetchOriginalSourceText(passages, passageId, nextOffset, operation.signal);
      if (!operation.signal.aborted) setOriginal({ passageId, offset: nextOffset, state: { status: 'loaded', value } });
    } catch (cause) { failure(cause, operation); if (!operation.signal.aborted && !(cause instanceof ApiError && [401, 403].includes(cause.status))) setOriginal({ passageId, offset: nextOffset, state: { status: 'failed', message: messageOf(cause) } }); }
    finally { if (!operation.signal.aborted) setBusy(false); }
  }
  function select(item: DecisionOccurrence, id: string | null = null, value: DecisionResolution | null = null) {
    setSelected(item); setMappingId(id); setResolution(value || emptyResolution(item)); setDecision('needs_changes'); setRationale(''); setReference(''); setSha256(''); setError('');
  }
  async function save(event: FormEvent) {
    event.preventDefault(); if (!state || !selected || !resolution || !occurrences) return;
    const operation = begin();
    try {
      const payload = mappingId ? decisionReviewPayload(state, decision, rationale, resolution, reference, sha256) : {
        expected_revision: state.revision, expected_source_review_revision: state.source_review_revision,
        passage_id: occurrences.passage_id, candidate_id: selected.id, rationale: rationale.trim(),
      };
      const result = await request<DecisionState>(mappingId ? `${decisionPath(sourceId)}/${mappingId}/review` : decisionPath(sourceId), { method: 'POST', body: JSON.stringify(payload), signal: operation.signal });
      if (result.source.id !== sourceId || result.publication_eligible !== false) throw new Error('İnceleme yanıtı kaynağa bağlı değil.');
      if (!operation.signal.aborted) { setState(result); setMappingId(result.items.find(item => item.candidate.id === selected.id)?.id || null); setMessage('İnceleme kaydedildi. Graf yayımlanmadı.'); setRationale(''); }
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 409 && !operation.signal.aborted) {
        try { const updated = await request<DecisionState>(decisionPath(sourceId), { signal: operation.signal }); if (!operation.signal.aborted) { setState(updated); setMappingId(updated.items.find(item => item.candidate.id === selected.id)?.id || null); setMessage('Kayıt değişti. Taslağınız korundu; güncel revizyonu inceleyip yeniden gönderin.'); } }
        catch (refreshCause) { failure(refreshCause, operation); }
      } else failure(cause, operation);
    } finally { if (!operation.signal.aborted) setBusy(false); }
  }
  const owner = state?.assigned_to?.id === user.id;
  return <div className="source-review-page"><a className="text-link" href={`#/sources/${sourceId}`}>Kaynak ve özgün belge incelemesine dön</a>
    <PageHeader eyebrow="KARAR EŞLEŞTİRME" title="Anmadan hesap verebilir incelemeye." description="Seçili pasajdaki numara, tarih ve atıfları inceleyin; belge kimliğini alıntılanan kararlardan ayrı değerlendirin." />
    <Notice>Bu ekran büroya özel inceleme kaydıdır. Referanslar insan beyanıdır; kesinleşme, bağlayıcılık ve hukuki etki bilinmiyor. Graf ve kaynak tarihleri değişmez.</Notice>
    {busy && <Loading label="İnceleme işlemi sürüyor…" />}{error && <Notice error>{error}</Notice>}{message && <Notice>{message}</Notice>}
    {!denied && <button className="button secondary" disabled={busy} onClick={() => void load()}>Güncel kaydı yenile</button>}
    {state && <><p>{state.assigned_to?.name || 'Sorumlu atanmadı'} · Eşleme revizyonu {state.revision} · Kaynak inceleme revizyonu {state.source_review_revision}</p>
      {!owner && <Notice>Değişiklik yapmak için kaynak incelemesini üstlenin.</Notice>}{!state.source_review_ready && <Notice>Kabul için haklar, kaynak kimliği, metin çıkarımı ve hukuki inceleme tamamlanmalıdır.</Notice>}
      <p className="small muted">İnceleme devri: {state.handoff_ready ? 'Hazır; bağımsız yayımlama incelemesi gerekir' : 'Bekliyor'} · Yayımlanmadı</p>
      <section className="source-review-section"><h2>Pasajı seçin</h2>{passages && <SourcePassageList data={passages} offset={offset} selected={[]} canSelect={false} onSelect={() => undefined} onPage={next => { if (!busy) void load(next); }} onCandidates={id => { if (!busy) void inspect(id); }} candidatesDisabled={busy} original={original} onOriginal={(id, next) => { void inspectOriginal(id, next); }} onCloseOriginal={() => { if (!busy) setOriginal(null); }} />}</section>
      {occurrences && <section className="source-review-section"><h2>Seçili pasajdaki anmalar · {occurrences.count}</h2><p className="small muted">{occurrences.passage_id} · Yalnızca bu pasaj; otomatik adaylar henüz çözümlenmedi.</p>
        {occurrences.items.length ? <OccurrenceList items={occurrences.items} selectedId={selected?.id || null} disabled={busy} onSelect={item => { const existing = state.items.find(value => value.candidate.id === item.id); select(item, existing?.id || null, existing?.resolution || null); }} /> : <Notice>Bu pasajda tanınan yazım biçimi bulunamadı. Bu sonuç kararın atıf içermediğini göstermez.</Notice>}
        <Detail title="Tarama sınırları">{occurrences.limitations.map(text => <p key={text}>{text}</p>)}</Detail>
      </section>}
      {selected && resolution && <section className="source-review-section"><h2>{mappingId ? 'İnsan incelemesi' : 'Anmayı inceleme listesine ekleyin'}</h2><p className="source-passage-text">{selected.text}</p><p className="small muted">Unicode [{selected.start}, {selected.end}) · {selected.sha256}</p>
        <form onSubmit={event => void save(event)}><fieldset disabled={!owner || busy}>
          {mappingId && <><Field label="İnceleme kararı">{id => <select id={id} value={decision} onChange={event => setDecision(event.target.value as SourceReviewDecision)}><option value="needs_changes">Düzeltme iste</option><option value="rejected">Reddet</option><option value="accepted">Kabul et</option></select>}</Field>
            {decision === 'accepted' && <ResolutionFields value={resolution} onChange={setResolution} />}
            <Field label="Dayanak referansı">{id => <input id={id} value={reference} onChange={event => setReference(event.target.value)} maxLength={1000} />}</Field><Field label="Dayanak SHA256">{id => <input id={id} value={sha256} onChange={event => setSha256(event.target.value)} maxLength={64} />}</Field>
          </>}
          <Field label="Gerekçe">{id => <textarea id={id} required minLength={3} maxLength={4000} value={rationale} onChange={event => setRationale(event.target.value)} />}</Field>
          <button className="button" disabled={mappingId !== null && decision === 'accepted' && !state.source_review_ready}>{mappingId ? 'İncelemeyi kaydet' : 'İnceleme önerisi kaydet'}</button>
        </fieldset></form>
      </section>}
      <DecisionHistory state={state} />
    </>}
  </div>;
}
export function OccurrenceList({ items, selectedId, disabled, onSelect }: { items: DecisionOccurrence[]; selectedId: string | null; disabled: boolean; onSelect: (item: DecisionOccurrence) => void }) {
  return <div className="source-passage-list">{items.map(item => <article className="source-passage" key={item.id}><h3>{KIND_LABELS[item.kind]}</h3><p className="source-passage-text">{item.text}</p><p className="small muted">Otomatik aday · kimlik ve rol bilinmiyor · [{item.start}, {item.end})</p><button className="button secondary" aria-pressed={selectedId === item.id} disabled={disabled} onClick={() => onSelect(item)}>Bu anmayı incele</button></article>)}</div>;
}
function ResolutionFields({ value, onChange }: { value: DecisionResolution; onChange: (value: DecisionResolution) => void }) {
  const change = (key: keyof DecisionResolution, next: string) => onChange({ ...value, [key]: ['start', 'end'].includes(key) ? Number(next) : next || null });
  return <><Field label="Anmanın rolü">{id => <select id={id} value={value.occurrence_role} onChange={event => change('occurrence_role', event.target.value)}><option value="unknown">Bilinmiyor</option><option value="own_decision">Belgenin kendi kararı</option><option value="cited_authority">Atıf yapılan otorite</option><option value="editorial">Editoryal bilgi</option></select>}</Field>
    {([['proceeding_ref', 'Yargılama referansı'], ['decision_ref', 'Karar referansı'], ['institution_ref', 'Kurum referansı'], ['target_ref', 'Atıf hedefi'], ['target_version_ref', 'Hedefin tarihsel sürümü']] as const).map(([key, label]) => <Field key={key} label={`${label} · bilinmiyorsa boş`}>{id => <input id={id} maxLength={300} value={value[key] || ''} onChange={event => change(key, event.target.value)} />}</Field>)}
    <Field label="Tarih rolü">{id => <select id={id} value={value.event_role} onChange={event => change('event_role', event.target.value)}><option value="unknown">Bilinmiyor</option><option value="decision">Karar tarihi</option><option value="publication">Yayım tarihi</option></select>}</Field><Field label="Tarih · bilinmiyorsa boş">{id => <input id={id} type="date" value={value.event_date || ''} onChange={event => change('event_date', event.target.value)} />}</Field>
    <Field label="Atfın kullanımı">{id => <select id={id} value={value.authority_treatment} onChange={event => change('authority_treatment', event.target.value)}><option value="unknown">Bilinmiyor</option><option value="cites">Atıf yapıyor</option><option value="quotes">Alıntılıyor</option><option value="applies">Uyguluyor</option><option value="distinguishes">Ayırt ediyor</option></select>}</Field>
    <p className="small muted">Dayanak aralığı seçili anmayı içermeli. Genişletilen aralığı pasajın tam metninden inceleyin.</p>{(['start', 'end'] as const).map(key => <Field key={key} label={key === 'start' ? 'Dayanak başlangıcı (Unicode)' : 'Dayanak bitişi (hariç)'}>{id => <input id={id} type="number" min={0} required value={value[key]} onChange={event => change(key, event.target.value)} />}</Field>)}
  </>;
}
export function DecisionHistory({ state }: { state: DecisionState }) {
  return <section className="source-review-section"><h2>Kayıtlar ve inceleme geçmişi</h2>{state.items.map(item => <article className="source-passage" key={item.id}><p className="source-passage-text">{item.candidate.text}</p><p>{item.status === 'machine_proposed' ? 'İnceleme bekliyor' : item.status === 'accepted' ? 'İnsan incelemesi kabul edildi' : item.status === 'rejected' ? 'Reddedildi' : 'Düzeltme gerekli'}{item.stale ? ' · Yeniden inceleme gerekli' : ''}</p>{item.resolution && <Detail title="İnsan tarafından girilen çözümleme"><dl>{Object.entries(item.resolution).map(([key, value]) => <div key={key}><dt>{{ start: 'Dayanak başlangıcı', end: 'Dayanak bitişi', occurrence_role: 'Anma rolü', proceeding_ref: 'Yargılama referansı', decision_ref: 'Karar referansı', institution_ref: 'Kurum referansı', target_ref: 'Atıf hedefi', target_version_ref: 'Hedef sürümü', event_role: 'Tarih rolü', event_date: 'Tarih', authority_treatment: 'Atfın kullanımı' }[key as keyof DecisionResolution]}</dt><dd>{value ?? 'Bilinmiyor'}</dd></div>)}</dl></Detail>}<p className="small">{item.last_event.reviewer.name} · {item.last_event.created_at}</p></article>)}
    <Detail title="Önceki görüşler korunur">{state.history.map(event => <article key={event.id}><p>Revizyon {event.revision} · {event.reviewer.name} · {event.created_at} · {event.decision || 'Öneri'}</p><p>{event.rationale}</p>{event.snapshot.resolution && <pre className="source-passage-text">{JSON.stringify(event.snapshot.resolution, null, 2)}</pre>}{event.evidence_refs.map(ref => <p key={`${ref.reference}:${ref.sha256}`}>{ref.reference} · {ref.sha256}</p>)}</article>)}{state.history_truncated && <Notice>Bu görünüm yalnızca son 50 olayı içerir. Eski olaylar silinmedi.</Notice>}</Detail>
  </section>;
}
