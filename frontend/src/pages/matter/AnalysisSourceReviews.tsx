import { useEffect, useRef, useState } from 'react';
import { ApiError, downloadSourceContext, request } from '../../api';
import { Detail, Field, Notice } from '../../components';
import { formatDate, messageOf } from '../../utils';
import type { AnalysisRecord } from './analysisTypes';
import { AUTHORITY_ROLES, type AuthorityRole } from './authorityTypes';
import { SourceContextView, SourceManifest, SourceQuote } from './SourceReviewEvidence';
import { canExport, canonicalJson, currentView, DIMENSIONS, DIMENSION_LABELS, occurrenceKey, OUTCOMES, pendingReceipt, reviewPayload, selectionsPayload,
  sourceIdentity, SourceReadFence, verifyManifest, verifyQuotes, verifyView } from './sourceReviewTypes';
import type { Candidates, ContextView, Decision, EditableAssessment, EditableSelection, Preview, ReviewInputs, Spec, Summary } from './sourceReviewTypes';
import { renewalPayload, verifyRenewalMetadata, type EditableMapping, type RenewalMetadata } from './sourceRenewalTypes';
import { SourceRenewalMapping, SourceRenewalComparison } from './SourceRenewalMapping';

import { SourceReviewQueue } from './SourceReviewQueue';
import { verifyReadiness, type ReadinessFilters, type ReadinessPage } from './sourceReadinessTypes';

type SaveRequest = { path: string; body: unknown; kind: 'context' | 'review' };
type Saver = (value: SaveRequest) => Promise<void>;
const nonce = () => crypto.randomUUID().replaceAll('-', '');

function SelectionEditor({ candidates, productId, versionId, matterId, analysisId, base, busy, save, fail, renewal }: {
  candidates: Candidates; productId: string; versionId: string; matterId: string; analysisId: string; base: string; busy: boolean; save: Saver; fail: (cause: unknown) => void;
  renewal: RenewalMetadata | null;
}) {
  const [title, setTitle] = useState(''); const [purpose, setPurpose] = useState(''); const [selected, setSelected] = useState<EditableSelection[]>([]);
  const [preview, setPreview] = useState<Preview | null>(null); const [loading, setLoading] = useState(false);
  const fence = useRef(new SourceReadFence()); const receipt = useRef<{ key: string; id: string } | null>(null);
  const [reason, setReason] = useState(''); const [added, setAdded] = useState<string[]>([]);
  const [mappings, setMappings] = useState<EditableMapping[]>(() => renewal?.sources.map(row => ({ parent_passage_id: row.identity.passage_id, new_passage_ids: [], disposition: '', note: '' })) || []);
  useEffect(() => { const gate = fence.current; return () => gate.invalidate(); }, []);
  const links = selectionsPayload(selected, Object.keys(candidates.targets));
  const renewalSpec = renewal && links ? renewalPayload(renewal, mappings, reason, added, links) : null;
  const allowed = candidates.current_version && candidates.private_freshness.status === 'current' && links !== null && title.trim().length >= 3 && purpose.trim().length >= 3 && (!renewal || renewalSpec !== null);
  const spec: Spec | null = links ? { version_id: versionId, product_id: productId, title, purpose, selections: links,
    expected_release_id: candidates.graph_release_pin.release_id, expected_serving_sha256: candidates.graph_release_pin.serving_sha256,
    ...(renewalSpec ? { renewal: renewalSpec } : {}) } : null;
  function edit(change: () => void) { fence.current.invalidate(); change(); setPreview(null); receipt.current = null; }
  async function inspect() {
    if (!allowed || !spec) return; const task = fence.current.begin(); setLoading(true); setPreview(null);
    try {
      const value = await request<Preview>(`${base}/preview`, { method: 'POST', body: JSON.stringify(spec), signal: task.signal });
      await verifyManifest(value.manifest, matterId, analysisId);
      const captured = Object.fromEntries(Object.keys(spec).map(key => [key, value.manifest[key as keyof Spec]]));
      if (canonicalJson(captured) !== canonicalJson(spec) || !/^[a-f0-9]{64}$/.test(value.preview_sha256)) throw new Error('Önizlenen seçim değişti; kaynakları yeniden açın.');
      if (task.current()) setPreview(value);
    } catch (cause) { if (task.current()) fail(cause); } finally { if (task.current()) setLoading(false); }
  }
  async function freeze() {
    if (!preview || !spec) return; const key = JSON.stringify({ ...spec, expected_preview_sha256: preview.preview_sha256 });
    if (receipt.current?.key !== key) receipt.current = { key, id: nonce() };
    await save({ path: base, body: { ...spec, expected_preview_sha256: preview.preview_sha256, request_id: receipt.current.id }, kind: 'context' });
  }
  return <form className="authority-context-form" onSubmit={event => { event.preventDefault(); void inspect(); }}>
    <p>En fazla 8 özgün pasajı seçin. Her pasaj için rol, gerekçe ve en az bir analiz adımı belirtin. Bağımsız inceleme ayrıca gerekir.</p>
    {!candidates.current_version || candidates.private_freshness.status !== 'current' ? <Notice error>Güncel özel dayanaklı son analiz sürümü gerekli.</Notice> : null}
    <fieldset disabled={busy || loading}><legend>Kaynak seçimini hazırla</legend>
      <Field label="Kaynak seçimi başlığı">{id => <input id={id} value={title} required minLength={3} maxLength={200} onChange={event => edit(() => setTitle(event.target.value))} />}</Field>
      <Field label="Kaynak seçiminin amacı">{id => <textarea id={id} value={purpose} required minLength={3} maxLength={2000} onChange={event => edit(() => setPurpose(event.target.value))} />}</Field>
      {candidates.sources.map((quote, index) => {
        const key = occurrenceKey(quote); const item = selected.find(row => occurrenceKey(row) === key);
        const update = (values: Partial<EditableSelection>) => edit(() => setSelected(old => old.map(row => occurrenceKey(row) === key ? { ...row, ...values } : row)));
        return <section className="authority-candidate" key={key}>
          <label className="authority-option"><input type="checkbox" checked={!!item} disabled={!item && selected.length >= 8} onChange={event => edit(() => setSelected(old => event.target.checked
            ? [...old, { ...sourceIdentity(quote), target_ids: [], relationship: '', note: '' }] : old.filter(row => occurrenceKey(row) !== key)))} />{index + 1}. kaynak pasajını seç</label>
          <SourceQuote quote={quote} />{item && <>
            <Field label={`${index + 1}. kaynak bağlantısının rolü`}>{id => <select id={id} value={item.relationship} required onChange={event => update({ relationship: event.target.value as AuthorityRole | '' })}><option value="">Rol seçin</option>{Object.entries(AUTHORITY_ROLES).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select>}</Field>
            <Field label={`${index + 1}. kaynak bağlantısının gerekçesi`}>{id => <textarea id={id} value={item.note} required minLength={3} maxLength={2000} onChange={event => update({ note: event.target.value })} />}</Field>
            <fieldset><legend>{index + 1}. kaynak için analiz adımları · En fazla 12</legend>{Object.entries(candidates.targets).map(([id, target]) => <div key={id}>
              <label className="authority-option"><input type="checkbox" checked={item.target_ids.includes(id)} disabled={!item.target_ids.includes(id) && item.target_ids.length >= 12} onChange={event => update({ target_ids: event.target.checked ? [...item.target_ids, id] : item.target_ids.filter(value => value !== id) })} />{id}</label>
              <Detail title={`${id} adımının mevcut içeriği`}><pre className="data-pre">{JSON.stringify(target, null, 2)}</pre></Detail>
            </div>)}</fieldset>
          </>}
        </section>;
      })}
      {!candidates.sources.length && <Notice>Bu araştırmada izinli kaynak pasajı yok. İlgili hukuk kaynağının bulunmadığı anlamına gelmez.</Notice>}
      {renewal && <SourceRenewalMapping meta={renewal} rows={mappings} reason={reason} added={added} selections={links || []}
        change={(rows, why, extra) => edit(() => { setMappings(rows); setReason(why); setAdded(extra); })} />}
      <Detail title="Araştırma kapsamı ve sınırları"><pre className="data-pre">{JSON.stringify(candidates.coverage, null, 2)}</pre><ul>{candidates.limitations.map((item, index) => <li key={index}>{item}</li>)}</ul></Detail>
      <button className="button secondary" type="submit" disabled={!allowed}>Kaynak seçimini önizle</button>
    </fieldset>
    {preview && <Detail title="Kaydedilecek kaynak seçimi" open><SourceManifest manifest={preview.manifest} /><button className="button" type="button" disabled={busy || loading} onClick={() => void freeze()}>Önizlenen seçimi değiştirilemez kaydet</button></Detail>}
  </form>;
}

function ReviewEditor({ inputs, base, busy, save }: { inputs: ReviewInputs; base: string; busy: boolean; save: Saver }) {
  const [rows, setRows] = useState<EditableAssessment[]>(() => inputs.manifest.sources.map(source => ({ ...sourceIdentity(source.evidence), target_ids: [...source.selection.target_ids], relationship: '', note: '',
    observations: DIMENSIONS.map(dimension => ({ dimension, outcome: '', note: '' })) })));
  const [decision, setDecision] = useState<Decision | ''>(''); const [note, setNote] = useState(''); const receipt = useRef<{ key: string; id: string } | null>(null);
  const [renewalOutcome, setRenewalOutcome] = useState<keyof typeof OUTCOMES | ''>(''); const [renewalNote, setRenewalNote] = useState('');
  const renewalAssessment = inputs.manifest.renewal && renewalOutcome ? { expected_comparison_sha256: inputs.manifest.renewal_comparison_sha256!, outcome: renewalOutcome, note: renewalNote } : undefined;
  const value = decision ? reviewPayload(rows, note, decision, inputs, renewalAssessment) : null;
  function update(index: number, values: Partial<EditableAssessment>) { receipt.current = null; setRows(old => old.map((row, i) => i === index ? { ...row, ...values } : row)); }
  async function submit() { if (!value || !inputs.can_record) return; const key = JSON.stringify(value); if (receipt.current?.key !== key) receipt.current = { key, id: nonce() };
    await save({ path: base, body: { ...value, request_id: receipt.current.id }, kind: 'review' }); }
  return <form className="authority-context-form" onSubmit={event => { event.preventDefault(); void submit(); }}>
    <p>Seçimi yapan ve analiz yazarından farklı bir avukat, her pasajı ve üç inceleme boyutunu ayrı değerlendirir. Kendi yorumunuzu açıkça belirtin; önceki beyanlar değişmez.</p>
    {!inputs.can_record && <Notice error>Arşivlenmiş çalışma alanında yeni inceleme kaydedilemez.</Notice>}
    <fieldset disabled={busy || !inputs.can_record}><legend>Bağımsız avukat incelemesi</legend>
      {inputs.manifest.renewal && inputs.manifest.renewal_comparison && <>
        <SourceRenewalComparison value={inputs.manifest.renewal_comparison} reason={inputs.manifest.renewal.reason} />
        <Field label="Bağımsız yenileme eşlemesi değerlendirmesi">{id => <select id={id} required value={renewalOutcome} onChange={event => { receipt.current = null; setRenewalOutcome(event.target.value as typeof renewalOutcome); }}><option value="">Durum seçin</option>{Object.entries(OUTCOMES).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select>}</Field>
        <Field label="Bağımsız yenileme eşlemesi gerekçesi">{id => <textarea id={id} required minLength={3} maxLength={2000} value={renewalNote} onChange={event => { receipt.current = null; setRenewalNote(event.target.value); }} />}</Field>
      </>}
      {rows.map((row, index) => <section className="authority-candidate" key={occurrenceKey(row)}>
        <h4>{index + 1}. pasaj · {inputs.manifest.sources[index].evidence.locator}</h4>
        <p>Seçimi yapanın yorumu: <strong>{AUTHORITY_ROLES[inputs.manifest.sources[index].selection.relationship]}</strong></p><p className="authored-text">{inputs.manifest.sources[index].selection.note}</p>
        <SourceQuote quote={inputs.manifest.sources[index].evidence} />
        <Field label={`${index + 1}. pasaj için bağımsız yorumunuz`}>{id => <select id={id} value={row.relationship} required onChange={event => update(index, { relationship: event.target.value as AuthorityRole | '' })}><option value="">Yorumunuzu seçin</option>{Object.entries(AUTHORITY_ROLES).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select>}</Field>
        <Field label={`${index + 1}. pasaj için bağımsız yorum gerekçesi`}>{id => <textarea id={id} required minLength={3} maxLength={2000} value={row.note} onChange={event => update(index, { note: event.target.value })} />}</Field>
        <Detail title="İncelenecek sabit analiz adımları"><pre className="data-pre">{JSON.stringify(inputs.manifest.sources[index].target_snapshots, null, 2)}</pre></Detail>
        {row.observations.map((item, i) => <section key={item.dimension}><h4>{DIMENSION_LABELS[item.dimension]}</h4>
          <Field label={`${index + 1}. pasaj · ${DIMENSION_LABELS[item.dimension]} · durum`}>{id => <select id={id} value={item.outcome} required onChange={event => update(index, { observations: row.observations.map((value, j) => j === i ? { ...value, outcome: event.target.value as typeof item.outcome } : value) })}><option value="">Durum seçin</option>{Object.entries(OUTCOMES).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select>}</Field>
          <Field label={`${index + 1}. pasaj · ${DIMENSION_LABELS[item.dimension]} · gerekçe`}>{id => <textarea id={id} required minLength={3} maxLength={2000} value={item.note} onChange={event => update(index, { observations: row.observations.map((value, j) => j === i ? { ...value, note: event.target.value } : value) })} />}</Field>
        </section>)}
      </section>)}
      <Field label="Bağımsız inceleme kararı">{id => <select id={id} value={decision} required onChange={event => { receipt.current = null; setDecision(event.target.value as Decision | ''); }}><option value="">Karar seçin</option><option value="reviewed_conditional">Koşullu incelemeyi tamamla</option><option value="changes_requested">Değişiklik iste</option></select>}</Field>
      <Field label="Bağımsız incelemenin genel gerekçesi">{id => <textarea id={id} required minLength={3} maxLength={2000} value={note} onChange={event => { receipt.current = null; setNote(event.target.value); }} />}</Field>
      <p className="small muted">Koşullu tamamlama için tüm boyutları doğrulayın. Değişiklik isteği en az bir değişiklik gereksinimini belirtmelidir. Hukuki onay veya kesinleşme belirlenmez.</p>
      <button className="button" disabled={!value} type="submit">Bağımsız kararı değiştirilemez kaydet</button>
    </fieldset>
  </form>;
}

function SourceWorkspace({ matterId, record }: { matterId: string; record: AnalysisRecord }) {
  const base = `/matters/${encodeURIComponent(matterId)}/analyses/${encodeURIComponent(record.id)}/source-contexts`;
  const [products, setProducts] = useState<{ id: string; title: string }[]>([]); const [product, setProduct] = useState(''); const [productMore, setProductMore] = useState(false);
  const [candidates, setCandidates] = useState<Candidates | null>(null); const [items, setItems] = useState<Summary[]>([]); const [more, setMore] = useState(false);
  const [contextId, setContextId] = useState(''); const [view, setView] = useState<ContextView | null>(null); const [inputs, setInputs] = useState<ReviewInputs | null>(null);
  const [reviews, setReviews] = useState<Summary[]>([]); const [reviewMore, setReviewMore] = useState(false);
  const [renewal, setRenewal] = useState<RenewalMetadata | null>(null);
  const [queue, setQueue] = useState<ReadinessPage | null>(null);
  const [busy, setBusy] = useState(false); const [error, setError] = useState(''); const [notice, setNotice] = useState(''); const [pending, setPending] = useState<SaveRequest | null>(null);
  const fence = useRef(new SourceReadFence()); useEffect(() => { const gate = fence.current; return () => gate.invalidate(); }, []);
  function clear(cause?: unknown) {
    fence.current.invalidate(); setBusy(false); setCandidates(null); setView(null); setInputs(null); setProducts([]); setProduct(''); setItems([]); setReviews([]);
    setMore(false); setProductMore(false); setReviewMore(false); setPending(null); setNotice(''); setError(cause ? messageOf(cause) : '');
    setRenewal(null); setQueue(null);
  }
  async function run<T>(load: (signal: AbortSignal, current: () => boolean) => Promise<T>, accept: (value: T) => void) {
    const task = fence.current.begin(); setBusy(true); setError(''); setView(null); setInputs(null); setCandidates(null); setNotice('');
    try { const value = await load(task.signal, task.current); if (task.current()) accept(value); }
    catch (cause) { if (task.current()) clear(cause); } finally { if (task.current()) setBusy(false); }
  }
  async function save(value: SaveRequest) {
    const task = fence.current.begin(); setBusy(true); setError('');
    try {
      const result = await request<ContextView>(value.path, { method: 'POST', body: JSON.stringify(value.body), signal: task.signal });
      if (!currentView(result) && /^sac-[a-f0-9]{20}-[a-f0-9]{32}$/.test(result.id)) {
        if (task.current()) { clear(); setContextId(result.id); setNotice(`Kayıt saklandı; kaynak bağları bekletiliyor. Geçmişi ayrıca kontrol edin. Kayıt: ${result.id}`); } return;
      }
      await verifyView(result, matterId, record.id);
      const supplied = value.body as Record<string, unknown>;
      if (result.manifest_sha256 !== supplied[value.kind === 'context' ? 'expected_preview_sha256' : 'expected_manifest_sha256']
        || (value.kind === 'review' && canonicalJson(result.review.snapshot?.input) !== canonicalJson(supplied))) throw new Error('Saklanan kararın tam önizleme veya istek bağı eşleşmiyor.');
      if (task.current()) { setPending(null); setCandidates(null); setInputs(null); setRenewal(null); setView(result); setContextId(result.id); setNotice(value.kind === 'context' ? 'Kaynak seçimi kaydedildi. Bağımsız inceleme ayrıca gerekli.' : 'Bağımsız karar kaydedildi. Önceki kararlar korunur.'); }
    } catch (cause) {
      if (task.current()) {
        const id = pendingReceipt(cause, value.kind); clear(cause);
        if (id) { setError(''); if (value.kind === 'context') setContextId(id); setNotice(`Kayıt saklandı; son izin kontrolü tamamlanamadı. Yeni inceleme gerekli. Kayıt: ${id}`); }
        else if (cause instanceof ApiError && cause.status === 0) { setError(''); setPending(value); }
      }
    } finally { if (task.current()) setBusy(false); }
  }
  function inspect(id: string, reviewId?: string) { setContextId(id); setRenewal(null); void run(async signal => {
    const result = await request<ContextView>(`${base}/${encodeURIComponent(id)}${reviewId ? `/reviews/${encodeURIComponent(reviewId)}` : ''}`, { signal });
    await verifyView(result, matterId, record.id); return result;
  }, setView); }
  function renew(id: string) { setContextId(id); setRenewal(null); void run(async signal => {
    const result = await request<RenewalMetadata>(`${base}/${encodeURIComponent(id)}/renewal-context`, { signal });
    verifyRenewalMetadata(result, matterId, record.id, id); return result;
  }, value => { setRenewal(value); setNotice('Önceki kimlik bağları açıldı. Güncel araştırma pasajlarını seçin; tüm eşlemeleri açıkça belirtin. Önceki inceleme devralınmaz.'); }); }
  async function readCandidates() { if (!product) return; void run(async signal => {
    const params = new URLSearchParams({ product_id: product, version_id: record.latest_version_id });
    const result = await request<Candidates>(`${base}/candidates?${params}`, { signal }); await verifyQuotes(result.sources, result.graph_release_pin);
    if (result.snapshot.release_id !== result.graph_release_pin.release_id || result.snapshot.serving_sha256 !== result.graph_release_pin.serving_sha256) throw new Error('Araştırmanın kaynak sürümü değişti.');
    return result;
  }, setCandidates); }
  function reviewContext() { if (!contextId) return; void run(async signal => {
    const result = await request<ReviewInputs>(`${base}/${encodeURIComponent(contextId)}/reviews/context`, { signal }); await verifyManifest(result.manifest, matterId, record.id);
    if (!result.independent_reviewer_required || !/^[a-f0-9]{64}$/.test(result.expected_manifest_sha256)) throw new Error('Bağımsız inceleme bağı doğrulanamadı.'); return result;
  }, setInputs); }
  function readiness(filters: ReadinessFilters, offset: number) {
    setRenewal(null); setQueue(null); setContextId('');
    void run(async signal => {
      const params = new URLSearchParams({ bucket: filters.bucket, offset: String(offset) });
      if (filters.date_from) params.set('date_from', filters.date_from);
      if (filters.date_to) params.set('date_to', filters.date_to);
      const result = await request<ReadinessPage>(`${base}/readiness?${params}`, { signal });
      verifyReadiness(result, matterId, record.id, offset); return result;
    }, setQueue);
  }
  function history(append = false) { void run(signal => request<Summary[]>(`${base}?limit=10&offset=${append ? items.length : 0}`, { signal }), page => { setItems(old => append ? [...old, ...page] : page); setMore(page.length === 10); }); }
  function reviewHistory(append = false) { void run(signal => request<Summary[]>(`${base}/${encodeURIComponent(contextId)}/reviews?limit=10&offset=${append ? reviews.length : 0}`, { signal }), page => { setReviews(old => append ? [...old, ...page] : page); setReviewMore(page.length === 10); }); }
  function research(append = false) { void run(signal => request<{ id: string; title: string }[]>(`${base.replace('/source-contexts', '/authority-contexts')}/research-products?limit=10&offset=${append ? products.length : 0}`, { signal }), page => { setProducts(old => append ? [...old, ...page] : page); setProductMore(page.length === 10); }); }
  async function download(format: 'json' | 'docx' | 'pdf') {
    if (!view || !canExport(view)) return; const task = fence.current.begin(); setBusy(true); setError(''); setInputs(null); setCandidates(null);
    try { await downloadSourceContext(matterId, record.id, contextId, format, task.current, task.signal); }
    catch (cause) { if (task.current()) clear(cause); } finally { if (task.current()) setBusy(false); }
  }
  return <><p>Bağımsız kamu kaynak pasajlarını bu özel analiz sürümüne bağlayın. Farklı bir avukatın incelemesi ve geçmiş kararları aynı yerde izlenir; özel bilgiler başka çalışma alanlarına aktarılmaz.</p>
    {pending && <Notice error>Kayıt sonucu bilinmiyor. Aynı istek kimliği korunuyor; kendiliğinden tekrar gönderilmez. <button className="text-button" disabled={busy} onClick={() => void save(pending)}>Aynı isteğin sonucunu kontrol et</button></Notice>}
    {notice && <Notice>{notice}</Notice>}{error && <Notice error>{error}</Notice>}
    <SourceReviewQueue page={queue} busy={busy || !!pending} load={readiness} clear={clear} inspect={inspect} renew={renew} />
    <div className="practice-record-actions"><button className="text-button" disabled={busy || !!pending} onClick={() => research()}>Araştırma pasajlarını getir</button><button className="text-button" disabled={busy || !!pending} onClick={() => history()}>Kaynak seçimi geçmişini getir</button></div>
    {products.length > 0 && <><Field label="Kaynak pasajları için araştırma kaydı">{id => <select id={id} disabled={busy} value={product} onChange={event => { fence.current.invalidate(); setProduct(event.target.value); setCandidates(null); setView(null); setInputs(null); setError(''); }}><option value="">Araştırma seçin</option>{products.map(item => <option key={item.id} value={item.id}>{item.title}</option>)}</select>}</Field>
      <button className="button secondary" disabled={busy || !product} onClick={() => void readCandidates()}>Özgün pasajları ve sürümleri aç</button>{productMore && <button className="text-button" disabled={busy} onClick={() => research(true)}>Daha fazla araştırma getir</button>}</>}
    {renewal && <><p className="small reference-id">Yenilenecek bağlam: {renewal.id}</p><button className="text-button" disabled={busy || !!pending} onClick={() => { fence.current.invalidate(); setRenewal(null); setCandidates(null); }}>Ayrı kaynak seçimine dön</button></>}
    {candidates && <SelectionEditor key={`${product}:${candidates.graph_release_pin.release_id}:${renewal?.id}:${renewal?.manifest_sha256}:${renewal?.review_id}`} candidates={candidates} productId={product} versionId={record.latest_version_id} matterId={matterId} analysisId={record.id} base={base} busy={busy} save={save} fail={clear} renewal={renewal} />}
    {items.map(item => <div className="practice-record-actions" key={item.id}><span className="small">{formatDate(item.recorded_at, true)}</span><button className="text-button reference-id" disabled={busy || !!pending} onClick={() => inspect(item.id)}>Kaynak seçimini aç · {item.id}</button></div>)}
    {more && <button className="text-button" disabled={busy || !!pending} onClick={() => history(true)}>Daha fazla kaynak seçimi getir</button>}
    {contextId && <div className="practice-record-actions"><button className="text-button" disabled={busy || !!pending} onClick={() => inspect(contextId)}>Güncel kaynak ve karar bağlarını kontrol et</button><button className="text-button" disabled={busy || !!pending} onClick={() => renew(contextId)}>Bu kaydın kaynak bağlamını yenile</button><button className="text-button" disabled={busy || !!pending} onClick={reviewContext}>Bağımsız inceleme içeriğini getir</button><button className="text-button" disabled={busy || !!pending} onClick={() => reviewHistory()}>Bağımsız karar geçmişini getir</button></div>}
    {view && <><SourceContextView value={view} /><div className="practice-record-actions">{(['json', 'docx', 'pdf'] as const).map(format => <button key={format} className="text-button" disabled={busy || !canExport(view)} onClick={() => void download(format)}>{format.toUpperCase()} kaynak incelemesini indir</button>)}</div></>}
    {inputs && <ReviewEditor key={`${contextId}:${inputs.expected_manifest_sha256}:${inputs.expected_review_id}`} inputs={inputs} base={`${base}/${encodeURIComponent(contextId)}/reviews`} busy={busy} save={save} />}
    {reviews.map(item => <div className="practice-record-actions" key={item.id}><span className="small">{formatDate(item.recorded_at, true)} · İncelemeci: {item.recorded_by}</span><button className="text-button reference-id" disabled={busy || !!pending} onClick={() => inspect(contextId, item.id)}>Saklanan kararı aç · {item.id}</button></div>)}
    {reviewMore && <button className="text-button" disabled={busy || !!pending} onClick={() => reviewHistory(true)}>Daha fazla bağımsız karar getir</button>}
  </>;
}

export default function AnalysisSourceReviews(props: { matterId: string; record: AnalysisRecord }) {
  return <SourceWorkspace key={`${props.matterId}:${props.record.id}:${props.record.latest_version_id}`} {...props} />;
}
