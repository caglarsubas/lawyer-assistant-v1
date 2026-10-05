import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react';
import { ApiError, request } from '../api';
import { Badge, Detail, Field, Icon, Loading, Notice, PageHeader } from '../components';
import type { PublicSourcePassages, SourcePermittedUse, SourceReviewCategory, SourceReviewDecision, SourceReviewEvent, SourceReviewState, User } from '../types';
import { formatDate, messageOf, statusLabel } from '../utils';

const CATEGORIES: Record<SourceReviewCategory, string> = { rights: 'Kullanım hakları', source_identity: 'Kaynak kimliği', extraction: 'Metin çıkarımı', legal: 'Hukuki inceleme' };
const DECISIONS: Record<SourceReviewDecision, string> = { accepted: 'Kabul edildi', needs_changes: 'Düzeltme gerekli', rejected: 'Reddedildi' };
const USES: Record<SourcePermittedUse, string> = { storage: 'Saklama', local_processing: 'Yerel işleme', internal_display: 'Kurum içi gösterim', indexing: 'Dizinleme', local_inference: 'Yerel model kullanımı', export: 'Dışa aktarma' };
export interface AssessmentDraft { category: SourceReviewCategory; decision: SourceReviewDecision; rationale: string; reference: string; sha256: string; passage_ids: string[]; permitted_uses: SourcePermittedUse[] }
export const EMPTY_ASSESSMENT: AssessmentDraft = { category: 'rights', decision: 'needs_changes', rationale: '', reference: '', sha256: '', passage_ids: [], permitted_uses: [] };
type LoadState<T> = { status: 'loading' } | { status: 'loaded'; value: T } | { status: 'failed'; message: string; code?: number };
export function canReviewSource(user: User) { return ['admin', 'curator'].includes(user.role); }
export function sourceReviewPath(sourceId: string) {
  if (!/^[a-f0-9]{64}$/.test(sourceId)) throw new Error('Kaynak kimliği geçersiz.');
  return `/public-sources/${sourceId}`;
}
export function assessmentPayload(draft: AssessmentDraft, revision: number) {
  const rationale = draft.rationale.trim(); const reference = draft.reference.trim(); const sha256 = draft.sha256.trim();
  if (rationale.length < 3 || rationale.length > 4000) throw new Error('Gerekçe 3–4000 karakter olmalı.');
  if ((reference || sha256) && (!reference || !/^[a-f0-9]{64}$/.test(sha256))) throw new Error('Dayanak referansı ve 64 haneli küçük harfli SHA256 özeti birlikte gerekli.');
  if (draft.decision === 'accepted' && !reference) throw new Error('Kabul için en az bir dayanak referansı ve içerik özeti gerekli.');
  if (draft.passage_ids.length > 100 || new Set(draft.passage_ids).size !== draft.passage_ids.length) throw new Error('En fazla 100 farklı pasaj seçebilirsiniz.');
  if (draft.decision === 'accepted' && draft.category === 'extraction' && !draft.passage_ids.length) throw new Error('Metin çıkarımını kabul etmek için incelediğiniz pasajları seçin.');
  if (draft.decision === 'accepted' && draft.category === 'rights' && !draft.permitted_uses.length) throw new Error('Hak incelemesini kabul etmek için en az bir izin verilen kullanım seçin.');
  return { expected_revision: revision, category: draft.category, decision: draft.decision, rationale,
    evidence_refs: reference ? [{ reference, sha256 }] : [],
    passage_ids: draft.category === 'extraction' ? draft.passage_ids : [],
    permitted_uses: draft.category === 'rights' ? draft.permitted_uses : [] };
}

// A conflict always refreshes the server projection. The caller retains its draft;
// this helper never retries a write against a newer revision.
export async function writeSourceReview(sourceId: string, action: 'assignment' | 'assessments', payload: unknown, signal?: AbortSignal): Promise<{ state: SourceReviewState; conflict: boolean }> {
  const path = `${sourceReviewPath(sourceId)}/review`;
  try { return { state: await request<SourceReviewState>(`${path}/${action}`, { method: 'POST', body: JSON.stringify(payload), signal }), conflict: false }; }
  catch (cause) {
    if (cause instanceof ApiError && cause.status === 409) return { state: await request<SourceReviewState>(path, { signal }), conflict: true };
    throw cause;
  }
}

export async function fetchSourceAttachment(sourceId: string, kind: 'original' | 'export', signal?: AbortSignal): Promise<Blob> {
  let response: Response;
  try { response = await fetch(`/api/v1${sourceReviewPath(sourceId)}/${kind === 'original' ? 'original' : 'review/export'}`, { credentials: 'same-origin', signal, cache: 'no-store' }); }
  catch (cause) { if (signal?.aborted) throw cause; throw new ApiError('Dosya indirilemedi. Yerel hizmete bağlantıyı kontrol edin.', 0); }
  if (!response.ok) throw new ApiError(response.status === 401 ? 'Oturum sona erdi. Yeniden giriş yapın.' : response.status === 403 ? 'Bu kaynağı indirme yetkiniz yok.' : 'Kaynak bütünlüğü veya indirme işlemi doğrulanamadı.', response.status);
  if (!response.headers.get('Content-Disposition')?.toLowerCase().startsWith('attachment')) throw new ApiError('Güvenli dosya eki yanıtı alınamadı.', 0);
  return new Blob([await response.blob()], { type: 'application/octet-stream' });
}

function failed<T>(cause: unknown): LoadState<T> { return { status: 'failed', message: messageOf(cause), ...(cause instanceof ApiError ? { code: cause.status } : {}) }; }
function ReadFailure({ state, retry }: { state: Extract<LoadState<unknown>, { status: 'failed' }>; retry: () => void }) {
  return <Notice error>{state.code === 403 ? 'Bu inceleme alanını yalnızca yetkili yönetici ve küratörler görebilir.' : state.message} {![401, 403].includes(state.code || 0) && <button className="text-button" onClick={retry}>Yeniden dene</button>}</Notice>;
}

export default function SourceReviewPage({ sourceId, user }: { sourceId: string; user: User }) {
  if (!canReviewSource(user)) return <><PageHeader eyebrow="KAYNAK İNCELEMESİ" title="İnceleme yetkisi gerekli." /><Notice>Kaynak incelemelerini yalnızca yetkili yönetici ve küratörler görebilir.</Notice><a className="text-link" href="#/coverage">Kapsam kaydına dön</a></>;
  if (!/^[a-f0-9]{64}$/.test(sourceId)) return <Notice error>Kaynak kimliği geçersiz. <a className="text-link" href="#/coverage">Kapsam kaydına dön</a></Notice>;
  return <SourceReviewWorkspace key={`${user.id}:${sourceId}`} sourceId={sourceId} user={user} />;
}

function SourceReviewWorkspace({ sourceId, user }: { sourceId: string; user: User }) {
  const [review, setReview] = useState<LoadState<SourceReviewState>>({ status: 'loading' });
  const [passages, setPassages] = useState<LoadState<PublicSourcePassages>>({ status: 'loading' });
  const [offset, setOffset] = useState(0); const [draft, setDraft] = useState<AssessmentDraft>({ ...EMPTY_ASSESSMENT });
  const [assignmentRationale, setAssignmentRationale] = useState('');
  const [busy, setBusy] = useState(false); const [downloading, setDownloading] = useState(false);
  const [message, setMessage] = useState(''); const [error, setError] = useState('');
  const reviewController = useRef<AbortController | null>(null); const passageController = useRef<AbortController | null>(null);
  const mutationController = useRef<AbortController | null>(null); const downloadController = useRef<AbortController | null>(null);
  const objectUrls = useRef(new Set<string>()); const path = sourceReviewPath(sourceId);
  const denyAccess = useCallback((cause: unknown) => {
    if (cause instanceof ApiError && [401, 403].includes(cause.status)) {
      reviewController.current?.abort(); passageController.current?.abort();
      mutationController.current?.abort(); downloadController.current?.abort();
      setReview(failed(cause)); setPassages(failed(cause));
      setDraft({ ...EMPTY_ASSESSMENT }); setAssignmentRationale(''); setBusy(false); setDownloading(false);
    }
  }, []);
  const loadReview = useCallback(() => {
    reviewController.current?.abort(); const controller = new AbortController(); reviewController.current = controller;
    setReview({ status: 'loading' });
    void request<SourceReviewState>(`${path}/review`, { signal: controller.signal }).then(value => { if (!controller.signal.aborted) setReview({ status: 'loaded', value }); }).catch(cause => { if (!controller.signal.aborted) { setReview(failed(cause)); denyAccess(cause); } });
  }, [path, denyAccess]);
  const loadPassages = useCallback((nextOffset: number) => {
    passageController.current?.abort(); const controller = new AbortController(); passageController.current = controller;
    setOffset(nextOffset); setPassages({ status: 'loading' });
    void request<PublicSourcePassages>(`${path}/passages?offset=${nextOffset}&limit=20`, { signal: controller.signal }).then(value => { if (!controller.signal.aborted) setPassages({ status: 'loaded', value }); }).catch(cause => { if (!controller.signal.aborted) { setPassages(failed(cause)); denyAccess(cause); } });
  }, [path, denyAccess]);
  useEffect(() => {
    loadReview(); loadPassages(0);
    const urls = objectUrls.current;
    return () => { reviewController.current?.abort(); passageController.current?.abort(); mutationController.current?.abort(); downloadController.current?.abort(); urls.forEach(url => URL.revokeObjectURL(url)); urls.clear(); };
  }, [loadReview, loadPassages]);
  const state = review.status === 'loaded' ? review.value : null;
  const owns = state?.assigned_to?.id === user.id;
  const canRelease = state?.assigned_to && (owns || user.role === 'admin');
  async function mutate(action: 'assignment' | 'assessments', payload: unknown) {
    if (busy) return; setBusy(true); setError(''); setMessage('');
    const controller = new AbortController(); mutationController.current = controller;
    reviewController.current?.abort();
    try {
      const result = await writeSourceReview(sourceId, action, payload, controller.signal);
      if (controller.signal.aborted) return;
      setReview({ status: 'loaded', value: result.state });
      if (result.conflict) setError('İnceleme başka bir işlemde değişti. Güncel kayıt yüklendi; yazdıklarınız korundu. Değişiklikleri karşılaştırıp yeniden kaydedin. Otomatik tekrar yapılmadı.');
      else { setMessage('İnceleme kaydı kaydedildi. Kaynak yayımlanmadı.'); if (action === 'assignment') setAssignmentRationale(''); else setDraft(previous => ({ ...EMPTY_ASSESSMENT, category: previous.category })); }
    } catch (cause) { if (!controller.signal.aborted) { setError(messageOf(cause)); denyAccess(cause); } }
    finally { if (!controller.signal.aborted) setBusy(false); }
  }
  function assign(action: 'claim' | 'release') {
    if (!state) return;
    if (assignmentRationale.trim().length < 3 || assignmentRationale.trim().length > 4000) { setError('Görevlendirme gerekçesi 3–4000 karakter olmalı.'); return; }
    void mutate('assignment', { action, expected_revision: state.revision, rationale: assignmentRationale.trim() });
  }
  function assess(event: FormEvent) {
    event.preventDefault(); if (!state || !owns || busy) return;
    try { void mutate('assessments', assessmentPayload(draft, state.revision)); } catch (cause) { setError(messageOf(cause)); }
  }
  async function download(kind: 'original' | 'export') {
    if (downloading) return; setDownloading(true); setError('');
    const controller = new AbortController(); downloadController.current = controller;
    try {
      const blob = await fetchSourceAttachment(sourceId, kind, controller.signal); if (controller.signal.aborted) return;
      const url = URL.createObjectURL(blob); objectUrls.current.add(url);
      const link = document.createElement('a'); link.href = url; link.download = `${kind === 'original' ? 'kaynak' : 'gizli-inceleme-dosyasi'}-${sourceId.slice(0, 16)}.${kind === 'original' ? 'bin' : 'json'}`;
      document.body.append(link); link.click(); link.remove();
      window.setTimeout(() => { URL.revokeObjectURL(url); objectUrls.current.delete(url); }, 1000);
    } catch (cause) { if (!controller.signal.aborted) { setError(messageOf(cause)); denyAccess(cause); } }
    finally { if (!controller.signal.aborted) setDownloading(false); }
  }
  function togglePassage(id: string) {
    setDraft(previous => ({ ...previous, passage_ids: previous.passage_ids.includes(id) ? previous.passage_ids.filter(value => value !== id) : previous.passage_ids.length < 100 ? [...previous.passage_ids, id] : previous.passage_ids }));
  }
  return <div className="source-review-page">
    <a className="text-link" href="#/coverage"><Icon name="layers" size={16} />Kapsam ve kaynak kaydına dön</a>
    <PageHeader eyebrow="KAYNAK İNCELEMESİ" title={state?.source.title || 'Kaynağı inceleyin.'} description="Özgün belgeyi ve çıkarılan pasajları karşılaştırın; her değerlendirmeyi gerekçesi ve dayanağıyla kaydedin." />
    <Notice>İnceleme notları ve görevlendirmeler şifreli, büroya özel kayıtlardır. Bu ekran kaynağı otomatik yayımlamaz, araştırmada kullanıma açmaz veya güncel hukuk olduğunu onaylamaz.</Notice>
    {error && <Notice error>{error}</Notice>}{message && <Notice>{message}</Notice>}
    {review.status === 'loading' ? <Loading label="İnceleme kaydı yükleniyor…" /> : review.status === 'failed' ? <ReadFailure state={review} retry={loadReview} /> : state && <>
      <SourceReviewSummary state={state} />
      <div className="button-group source-review-actions"><a className="button secondary" href={`#/sources/${sourceId}/provisions`}><Icon name="book" size={16} />Madde eşleştirmelerini aç</a><button className="button secondary" disabled={downloading || busy} onClick={() => void download('original')}><Icon name="download" size={16} />Özgün dosyayı indir</button><button className="button secondary" disabled={downloading || busy} onClick={() => void download('export')}><Icon name="download" size={16} />İnceleme dosyasını indir (JSON)</button><button className="text-button" disabled={busy} onClick={loadReview}>İnceleme kaydını yenile</button></div>
      {downloading && <p role="status" className="small muted">Dosya eki hazırlanıyor…</p>}
      <section className="source-review-section" aria-labelledby="source-assignment-title"><h2 id="source-assignment-title">İnceleme sorumluluğu</h2><p className="small">{state.assigned_to ? <><strong>{state.assigned_to.name}</strong> bu kaydın inceleme sorumlusu.</> : 'Henüz bir inceleme sorumlusu yok.'} Revizyon: {state.revision}.</p>
        <p className="small muted">İşlemler oturumunuzdaki {user.name} adına kaydedilir. Yalnızca sorumlu kişi değerlendirme ekleyebilir.</p>
        {(!state.assigned_to || canRelease) && <div className="source-assignment-form"><Field label="Görevlendirme gerekçesi">{id => <textarea id={id} maxLength={4000} rows={2} value={assignmentRationale} disabled={busy} onChange={event => setAssignmentRationale(event.target.value)} />}</Field><button className="button secondary" disabled={busy} onClick={() => assign(state.assigned_to ? 'release' : 'claim')}>{state.assigned_to ? owns ? 'Sorumluluğu bırak' : 'Görevlendirmeyi gerekçeyle kaldır' : 'İncelemeyi üstlen'}</button></div>}
      </section>
      <section className="source-review-section" aria-labelledby="source-assessment-title"><h2 id="source-assessment-title">Değerlendirme ekle</h2>
        {!owns && <p className="small muted">Yeni değerlendirme için önce incelemeyi üstlenin. Başkasına atanmış incelemeyi devralmak otomatik değildir.</p>}
        <form onSubmit={assess}><fieldset className="source-review-fieldset" disabled={!owns || busy}><legend className="visually-hidden">Yeni insan incelemesi</legend>
          <div className="form-grid"><Field label="İnceleme alanı">{id => <select id={id} value={draft.category} onChange={event => setDraft(previous => ({ ...previous, category: event.target.value as SourceReviewCategory }))}>{Object.entries(CATEGORIES).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select>}</Field><Field label="Karar">{id => <select id={id} value={draft.decision} onChange={event => setDraft(previous => ({ ...previous, decision: event.target.value as SourceReviewDecision }))}>{Object.entries(DECISIONS).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select>}</Field></div>
          <Field label="Gerekçe" hint="Değerlendirdiğiniz kapsamı ve bilinen sınırları yazın. Önceki incelemeler geçmişte korunur.">{id => <textarea id={id} required minLength={3} maxLength={4000} rows={4} value={draft.rationale} onChange={event => setDraft(previous => ({ ...previous, rationale: event.target.value }))} />}</Field>
          <Field label="Dayanak referansı" hint="Kabul kararı için gerekli. Yerel kayıt veya belge konumunu belirtin; bağlantı otomatik açılmaz.">{id => <input id={id} maxLength={1000} required={draft.decision === 'accepted'} value={draft.reference} onChange={event => setDraft(previous => ({ ...previous, reference: event.target.value }))} />}</Field>
          <Field label="Dayanağın SHA256 içerik özeti" hint="Destekleyici belgenin 64 haneli küçük harfli içerik özeti. Belgenin erişilebilirliğini ve doğruluğunu inceleyen kişi doğrular.">{id => <input id={id} spellCheck={false} autoCapitalize="off" autoComplete="off" pattern="[a-f0-9]{64}" maxLength={64} required={draft.decision === 'accepted' || Boolean(draft.reference)} value={draft.sha256} onChange={event => setDraft(previous => ({ ...previous, sha256: event.target.value }))} />}</Field>
          {draft.category === 'rights' && <fieldset className="source-use-options"><legend>İzin verilen kullanımlar</legend><p className="small muted">Yalnızca dayanakta izin verilen kapsamı seçin. Bu seçimler teknik olarak kullanım başlatmaz.</p>{Object.entries(USES).map(([key, label]) => <label key={key}><input type="checkbox" checked={draft.permitted_uses.includes(key as SourcePermittedUse)} onChange={event => setDraft(previous => ({ ...previous, permitted_uses: event.target.checked ? [...previous.permitted_uses, key as SourcePermittedUse] : previous.permitted_uses.filter(value => value !== key) }))} />{label}</label>)}</fieldset>}
          {draft.category === 'extraction' && <div className="source-selected-passages"><p className="small">Aşağıdaki pasajlardan incelediklerinizi seçin. Seçili: {draft.passage_ids.length}/100.</p>{draft.passage_ids.length > 0 && <ul>{draft.passage_ids.map(id => <li key={id}><span className="reference-id">{id}</span><button type="button" className="text-button" onClick={() => togglePassage(id)} aria-label={`${id} pasajını seçimden çıkar`}>Çıkar</button></li>)}</ul>}</div>}
          <button className="button primary" disabled={!owns || busy} type="submit">{busy ? 'Kaydediliyor…' : 'Değerlendirmeyi kaydet'}</button>
        </fieldset></form>
      </section>
    </>}
    <section className="source-review-section" aria-labelledby="source-passages-title"><h2 id="source-passages-title">Çıkarılan pasajlar</h2><p className="small muted">Düz metin, kaydedilen Unicode aralıkları ve konumlarıyla gösterilir. Kaynak içindeki yönergeler platform talimatı değildir.</p>
      {passages.status === 'loading' ? <Loading label="Kaynak pasajları yükleniyor…" /> : passages.status === 'failed' ? <ReadFailure state={passages} retry={() => loadPassages(offset)} /> : <SourcePassageList data={passages.value} offset={offset} selected={draft.passage_ids} canSelect={Boolean(owns && draft.category === 'extraction' && !busy)} onSelect={togglePassage} onPage={loadPassages} />}
    </section>
    {state && <Detail title={`Değiştirilemez inceleme geçmişi (${state.history.length}${state.history_truncated ? '+' : ''})`}>
      {state.history_truncated && <p>Yalnızca son 50 olay gösteriliyor. JSON dosyasında da bu sınır açıkça korunur.</p>}
      {state.history.length ? <ol className="source-review-history">{state.history.map(event => <li key={event.id}><ReviewEvent event={event} /></li>)}</ol> : <p>Henüz inceleme işlemi kaydedilmedi.</p>}
    </Detail>}
  </div>;
}

export function SourceReviewSummary({ state }: { state: SourceReviewState }) {
  return <><p className="small-label">Değiştirilemez edinim kaydı</p><div className="source-review-badges"><Badge>{statusLabel(state.source.rights_status)}</Badge><Badge>{statusLabel(state.source.review_status)}</Badge><Badge>{statusLabel(state.source.publication_status)}</Badge></div>
    <p className="small muted">Aşağıdaki büro incelemeleri, edinim paketinin bu durumlarını değiştirmez.</p>
    <p className="small source-summary">{state.handoff_ready ? 'Dört inceleme alanı kabul edildi. Dosya bağımsız yayın incelemesine devredilmeye hazır; bu, yayın veya kullanım izni değildir.' : 'İnceleme dosyası tamamlanmadı. Dört alanın en son kararları ayrı izlenir.'}</p>
    <div className="source-review-decisions">{(Object.keys(CATEGORIES) as SourceReviewCategory[]).map(category => { const event = state.assessments.find(value => value.category === category); return <article key={category}><h3>{CATEGORIES[category]}</h3><Badge status={event?.decision === 'accepted' ? 'reviewed' : event?.decision}>{event?.decision ? DECISIONS[event.decision] : 'İnceleme bekliyor'}</Badge>{event && <><p className="small muted">{event.reviewer.name} · {formatDate(event.created_at, true)}</p><Detail title="Son değerlendirmenin dayanakları"><ReviewEvent event={event} /></Detail></>}</article>; })}</div>
    <Detail title="Kaynak kimliği, bütünlük ve tarih sınırları"><dl className="coverage-fields"><div><dt>Kaynak adresi</dt><dd className="reference-id">{state.source.source_url}</dd></div><div><dt>Kaynak sürümü</dt><dd className="reference-id">{state.source.source_version_id}</dd></div><div><dt>Paket SHA256</dt><dd className="reference-id">{state.source.id}</dd></div><div><dt>Edinim tarihi</dt><dd>{formatDate(state.source.acquired_at, true)}</dd></div><div><dt>Yayımlanma</dt><dd>{formatDate(state.source.dates.published_on)}</dd></div><div><dt>Yürürlük başlangıcı</dt><dd>{formatDate(state.source.dates.effective_from)}</dd></div><div><dt>Yürürlük sonu</dt><dd>{formatDate(state.source.dates.effective_until)}</dd></div><div><dt>Paket bütünlüğü</dt><dd>{state.source.integrity_scope === 'all_artifacts_verified' ? 'Tüm dosyalar doğrulandı' : 'Doğrulanmış kapsam bildirilmedi'}</dd></div>{Object.entries(state.source.artifacts).map(([name, value]) => <div key={name}><dt>{name}</dt><dd className="reference-id">{value.sha256} · {value.bytes} bayt</dd></div>)}</dl>
      <p className="small">Kaynak adresi yalnızca köken bilgisidir; dış bağlantı kurulmaz. Bilinmeyen tarihler ve tarihsel metinlerin güncel uygulanabilirliği insan incelemesi gerektirir.</p>
      {state.source.injection_risk_hints.length > 0 && <p className="small">Kaynak metninde talimat benzeri içerik işaretlendi: {state.source.injection_risk_hints.join(' · ')}</p>}
      <ul>{[...new Set([...state.source.limitations, ...state.limitations])].map((limitation, index) => <li key={index}>{limitation}</li>)}</ul>
    </Detail></>;
}

export function SourcePassageList({ data, offset, selected, canSelect, onSelect, onPage }: { data: PublicSourcePassages; offset: number; selected: string[]; canSelect: boolean; onSelect: (id: string) => void; onPage: (offset: number) => void }) {
  return <><div className="source-passage-pagination"><p className="small" role="status">{data.items.length ? `${offset + 1}–${offset + data.items.length}` : '0'} / {data.total} pasaj</p><div className="button-group"><button className="button secondary" disabled={offset === 0} onClick={() => onPage(Math.max(0, offset - 20))}>Önceki</button><button className="button secondary" disabled={data.next_offset === null} onClick={() => { if (data.next_offset !== null) onPage(data.next_offset); }}>Sonraki</button></div></div>
    <div className="source-passage-list">{data.items.map(passage => <article key={passage.id} className="source-passage"><div className="source-passage-heading"><h3>{passage.id}</h3>{canSelect && <label><input type="checkbox" checked={selected.includes(passage.id)} disabled={!selected.includes(passage.id) && selected.length >= 100} onChange={() => onSelect(passage.id)} />İnceledim</label>}</div><p className="small muted">{passage.locator}</p><p className="source-passage-text">{passage.text}</p><Detail title="Pasaj konumu ve içerik özeti"><dl className="coverage-fields"><div><dt>Unicode aralığı</dt><dd>[{passage.start}, {passage.end})</dd></div><div><dt>Pasaj SHA256</dt><dd className="reference-id">{passage.text_sha256}</dd></div><div><dt>Metin SHA256</dt><dd className="reference-id">{data.text_sha256}</dd></div><div><dt>Özgün dosya SHA256</dt><dd className="reference-id">{data.raw_sha256}</dd></div></dl></Detail></article>)}</div>
  </>;
}

function ReviewEvent({ event }: { event: SourceReviewEvent }) {
  const label = event.event_type === 'claim' ? 'İnceleme üstlenildi' : event.event_type === 'release' ? 'Görevlendirme kaldırıldı' : `${event.category ? CATEGORIES[event.category] : 'İnceleme'} · ${event.decision ? DECISIONS[event.decision] : 'Karar belirtilmedi'}`;
  return <div><p><strong>{label}</strong> · Revizyon {event.revision}</p><p className="small muted">{event.reviewer.name} · {formatDate(event.created_at, true)}</p><p className="source-review-rationale">{event.rationale}</p>{event.evidence_refs.length > 0 && <ul>{event.evidence_refs.map((reference, index) => <li key={index}><span>{reference.reference}</span><p className="reference-id">{reference.sha256}</p></li>)}</ul>}{event.passage_ids.length > 0 && <p className="small">İncelenen pasajlar: {event.passage_ids.join(', ')}</p>}{event.permitted_uses.length > 0 && <p className="small">İzin kapsamı: {event.permitted_uses.map(value => USES[value]).join(', ')}</p>}</div>;
}
