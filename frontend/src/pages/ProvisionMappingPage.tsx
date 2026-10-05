import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react';
import { ApiError, request } from '../api';
import { Badge, Detail, Empty, Field, Icon, Loading, Notice, PageHeader } from '../components';
import type { ProvisionCandidate, ProvisionCandidates, ProvisionKind, ProvisionMapping, ProvisionMappingEvent, ProvisionMappingState, ProvisionResolution, ProvisionSpanPreview, SourceReviewDecision, User } from '../types';
import { formatDate, messageOf } from '../utils';
import { canReviewSource, sourceReviewPath } from './SourceReviewPage';

const KINDS: Record<ProvisionKind, string> = { article: 'Madde', temporary_article: 'Geçici madde', additional_article: 'Ek madde' };
const DECISIONS: Record<SourceReviewDecision, string> = { accepted: 'Kabul et', needs_changes: 'Düzeltme iste', rejected: 'Reddet' };
const ROLES: Record<ProvisionResolution['text_role'], string> = { unknown: 'Bilinmiyor', operative_text: 'Hüküm metni', amendment_text: 'Değişiklik metni', transitional_text: 'Geçiş hükmü', quoted_text: 'Alıntı metin' };
const STATUS = { machine_proposed: 'Öneri · incelenmedi', accepted: 'İnsan incelemesi · kabul edildi', needs_changes: 'Düzeltme gerekli', rejected: 'Reddedildi' };
type Load<T> = { status: 'loading' } | { status: 'loaded'; value: T } | { status: 'failed'; message: string; code?: number };
export interface ProposalDraft { candidate_id: string | null; start: string; end: string; kind: ProvisionKind; label: string; rationale: string }
export interface MappingReviewDraft { decision: SourceReviewDecision; rationale: string; reference: string; sha256: string; start: string; end: string; instrument_ref: string; provision_ref: string; provision_version_ref: string; text_role: ProvisionResolution['text_role']; valid_from: string; valid_until: string; validity_end_mode: 'unknown' | 'closed' | 'open_ended'; checked_through: string; validity_evidence_start: string; validity_evidence_end: string }
export const EMPTY_PROPOSAL: ProposalDraft = { candidate_id: null, start: '', end: '', kind: 'article', label: '', rationale: '' };
export const EMPTY_MAPPING_REVIEW: MappingReviewDraft = { decision: 'needs_changes', rationale: '', reference: '', sha256: '', start: '', end: '', instrument_ref: '', provision_ref: '', provision_version_ref: '', text_role: 'unknown', valid_from: '', valid_until: '', validity_end_mode: 'unknown', checked_through: '', validity_evidence_start: '', validity_evidence_end: '' };
export function mappingReviewDraft(mapping: ProvisionMapping): MappingReviewDraft {
  const resolution = mapping.resolution; const open = resolution?.open_ended_validity;
  return { ...EMPTY_MAPPING_REVIEW, start: String(mapping.span.start), end: String(mapping.span.end),
    ...(resolution ? { instrument_ref: resolution.instrument_ref, provision_ref: resolution.provision_ref, provision_version_ref: resolution.provision_version_ref, text_role: resolution.text_role, valid_from: resolution.valid_from || '', valid_until: resolution.valid_until || '' } : {}),
    validity_end_mode: open ? 'open_ended' : resolution?.valid_until ? 'closed' : 'unknown',
    checked_through: open?.checked_through || '', validity_evidence_start: open ? String(open.evidence_start) : '', validity_evidence_end: open ? String(open.evidence_end) : '' };
}
function fail<T>(cause: unknown): Load<T> { return { status: 'failed', message: messageOf(cause), ...(cause instanceof ApiError ? { code: cause.status } : {}) }; }
export function provisionPath(sourceId: string) { return `${sourceReviewPath(sourceId)}/provision-mappings`; }
export function spanCoordinates(start: string, end: string) {
  if (!/^\d+$/.test(start) || !/^\d+$/.test(end)) throw new Error('Başlangıç ve bitiş için negatif olmayan tam sayılar girin.');
  const a = Number(start); const b = Number(end);
  if (!Number.isSafeInteger(a) || !Number.isSafeInteger(b) || a < 0 || b <= a || b - a > 20000) throw new Error('Aralık en az 1, en fazla 20.000 Unicode karakteri içermeli.');
  return { start: a, end: b };
}
export function matchesPreview(preview: ProvisionSpanPreview | null, sourceId: string, start: string, end: string) {
  try { const coordinates = spanCoordinates(start, end); return Boolean(preview && preview.source_id === sourceId && preview.span.start === coordinates.start && preview.span.end === coordinates.end); } catch { return false; }
}
function rationale(value: string) { const text = value.trim(); if (text.length < 3 || text.length > 4000) throw new Error('Gerekçe 3–4000 karakter olmalı.'); return text; }
export function proposalPayload(draft: ProposalDraft, state: ProvisionMappingState, preview: ProvisionSpanPreview | null) {
  if (!matchesPreview(preview, state.source.id, draft.start, draft.end)) throw new Error('Kaydetmeden önce bu aralığın tam metnini önizleyin.');
  const label = draft.label.trim(); if (!label || label.length > 200) throw new Error('Madde etiketi 1–200 karakter olmalı.');
  return { expected_revision: state.revision, expected_source_review_revision: state.source_review_revision, candidate_id: draft.candidate_id, ...spanCoordinates(draft.start, draft.end), kind: draft.kind, label, rationale: rationale(draft.rationale) };
}
function calendarDate(value: string) {
  if (!value) return null;
  const parsed = new Date(`${value}T00:00:00Z`);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value) || value.startsWith('0000') || Number.isNaN(parsed.getTime()) || parsed.toISOString().slice(0, 10) !== value) throw new Error('Tarihler geçerli YYYY-MM-DD biçiminde olmalı; bilinmeyen tarihi boş bırakın.');
  return value;
}
export function mappingReviewPayload(draft: MappingReviewDraft, state: ProvisionMappingState, preview: ProvisionSpanPreview | null, validityPreview: ProvisionSpanPreview | null = null) {
  const reference = draft.reference.trim(); const sha256 = draft.sha256.trim();
  if ((reference || sha256) && (!reference || reference.length > 1000 || !/^[a-f0-9]{64}$/.test(sha256))) throw new Error('Dayanak referansı ve 64 haneli küçük harfli SHA256 özeti birlikte gerekli.');
  let resolution: ProvisionResolution | null = null;
  if (draft.decision === 'accepted') {
    if (!state.source_review_ready) throw new Error('Kabul için dört kaynak incelemesi ve gerekli yerel kullanım izinleri tamamlanmalı.');
    if (!reference) throw new Error('Kabul kararı için dayanak referansı ve içerik özeti gerekli.');
    if (!matchesPreview(preview, state.source.id, draft.start, draft.end) || !preview?.non_whitespace_covered) throw new Error('Kabul için bu aralığı önizleyin; metnin tamamı doğrulanmış pasajlarla kapsanmalı.');
    const refs = { instrument_ref: draft.instrument_ref.trim(), provision_ref: draft.provision_ref.trim(), provision_version_ref: draft.provision_version_ref.trim() };
    if (Object.values(refs).some(value => value.length < 3 || value.length > 300)) throw new Error('Düzenleme, hüküm ve hüküm sürümü referanslarını ayrı ayrı 3–300 karakter olarak girin.');
    const valid_from = calendarDate(draft.valid_from); const valid_until = calendarDate(draft.valid_until);
    if (valid_from && valid_until && valid_until <= valid_from) throw new Error('Yürürlük sonu başlangıçtan önce veya aynı gün olamaz.');
    if (draft.validity_end_mode === 'closed' && !valid_until) throw new Error('Bilinen bitiş tarihi için yürürlük sonunu girin.');
    if (draft.validity_end_mode !== 'closed' && valid_until) throw new Error('Bitiş tarihi ile seçilen yürürlük durumu çelişiyor.');
    resolution = { ...spanCoordinates(draft.start, draft.end), ...refs, text_role: draft.text_role, valid_from, valid_until };
    if (draft.validity_end_mode === 'open_ended') {
      const checked = calendarDate(draft.checked_through);
      if (!valid_from || !checked || checked < valid_from || checked > new Date().toISOString().slice(0, 10)) throw new Error('Açık uçlu inceleme için başlangıç ve denetim tarihi gerekli; denetim başlangıçtan önce veya gelecekte olamaz.');
      if (!matchesPreview(validityPreview, state.source.id, draft.validity_evidence_start, draft.validity_evidence_end) || !validityPreview?.non_whitespace_covered) throw new Error('Açık uçlu yürürlük dayanağını bu kaynakta önizleyin; pasaj kapsamı tam olmalı.');
      const support = spanCoordinates(draft.validity_evidence_start, draft.validity_evidence_end);
      resolution.open_ended_validity = { checked_through: checked, evidence_start: support.start, evidence_end: support.end };
    }
  }
  return { expected_revision: state.revision, expected_source_review_revision: state.source_review_revision, decision: draft.decision, rationale: rationale(draft.rationale), evidence_refs: reference ? [{ reference, sha256 }] : [], resolution };
}
export async function writeProvisionMapping(sourceId: string, mappingId: string | null, payload: unknown, signal?: AbortSignal): Promise<{ state: ProvisionMappingState; conflict: boolean }> {
  const path = provisionPath(sourceId);
  if (mappingId !== null && !/^[a-f0-9]{32}$/.test(mappingId)) throw new Error('Eşleştirme kimliği geçersiz.');
  try { return { state: await request<ProvisionMappingState>(mappingId ? `${path}/${mappingId}/review` : path, { method: 'POST', body: JSON.stringify(payload), signal }), conflict: false }; }
  catch (cause) { if (cause instanceof ApiError && cause.status === 409) return { state: await request<ProvisionMappingState>(path, { signal }), conflict: true }; throw cause; }
}
export async function fetchProvisionSpan(sourceId: string, sourceVersion: string, textSha256: string, start: string, end: string, signal?: AbortSignal) {
  const coordinates = spanCoordinates(start, end);
  const value = await request<ProvisionSpanPreview>(`${sourceReviewPath(sourceId)}/provision-span?start=${coordinates.start}&end=${coordinates.end}`, { signal });
  if (!matchesPreview(value, sourceId, start, end) || value.source_version_id !== sourceVersion || value.text_sha256 !== textSha256) throw new ApiError('Önizleme kaynak sürümü veya seçili metin aralığıyla eşleşmiyor.', 409);
  return value;
}
export async function fetchMappingDossier(sourceId: string, signal?: AbortSignal) {
  let response: Response;
  try { response = await fetch(`/api/v1${provisionPath(sourceId)}/export`, { credentials: 'same-origin', cache: 'no-store', signal }); }
  catch (cause) { if (signal?.aborted) throw cause; throw new ApiError('Eşleştirme dosyası indirilemedi.', 0); }
  if (!response.ok) throw new ApiError(response.status === 401 ? 'Oturum sona erdi.' : response.status === 403 ? 'Eşleştirme dosyasına erişim yetkiniz yok.' : 'Dosyanın bütünlüğü doğrulanamadı.', response.status);
  if (!response.headers.get('Content-Disposition')?.toLowerCase().startsWith('attachment')) throw new ApiError('Güvenli dosya eki yanıtı alınamadı.', 0);
  return new Blob([await response.blob()], { type: 'application/octet-stream' });
}

function ReadFailure({ state, retry }: { state: Extract<Load<unknown>, { status: 'failed' }>; retry: () => void }) { return <Notice error>{state.message} {![401, 403].includes(state.code || 0) && <button className="text-button" onClick={retry}>Yeniden dene</button>}</Notice>; }
export default function ProvisionMappingPage({ sourceId, user }: { sourceId: string; user: User }) {
  if (!canReviewSource(user)) return <><PageHeader eyebrow="MADDE EŞLEŞTİRMESİ" title="İnceleme yetkisi gerekli." /><Notice>Madde eşleştirmelerini yalnızca yetkili yönetici ve küratörler görebilir.</Notice></>;
  if (!/^[a-f0-9]{64}$/.test(sourceId)) return <Notice error>Kaynak kimliği geçersiz.</Notice>;
  return <MappingWorkspace key={`${user.id}:${sourceId}`} sourceId={sourceId} user={user} />;
}
function MappingWorkspace({ sourceId, user }: { sourceId: string; user: User }) {
  const [state, setState] = useState<Load<ProvisionMappingState>>({ status: 'loading' });
  const [candidates, setCandidates] = useState<Load<ProvisionCandidates>>({ status: 'loading' });
  const [offset, setOffset] = useState(0); const [proposal, setProposal] = useState<ProposalDraft>({ ...EMPTY_PROPOSAL });
  const [review, setReview] = useState<MappingReviewDraft>({ ...EMPTY_MAPPING_REVIEW }); const [selectedId, setSelectedId] = useState<string | null>(null);
  const [proposalPreview, setProposalPreview] = useState<ProvisionSpanPreview | null>(null); const [reviewPreview, setReviewPreview] = useState<ProvisionSpanPreview | null>(null);
  const [validityPreview, setValidityPreview] = useState<ProvisionSpanPreview | null>(null);
  const [busy, setBusy] = useState(false); const [previewing, setPreviewing] = useState<'proposal' | 'review' | 'validity' | null>(null); const [downloading, setDownloading] = useState(false);
  const [message, setMessage] = useState(''); const [error, setError] = useState('');
  const reads = useRef<{ state?: AbortController; candidates?: AbortController; preview?: AbortController; mutation?: AbortController; download?: AbortController }>({});
  const urls = useRef(new Set<string>()); const path = sourceReviewPath(sourceId);
  const deny = useCallback((cause: unknown) => {
    if (cause instanceof ApiError && [401, 403].includes(cause.status)) {
      Object.values(reads.current).forEach(controller => controller?.abort()); setState(fail(cause)); setCandidates(fail(cause));
      setProposal({ ...EMPTY_PROPOSAL }); setReview({ ...EMPTY_MAPPING_REVIEW }); setProposalPreview(null); setReviewPreview(null); setValidityPreview(null); setSelectedId(null); setBusy(false); setPreviewing(null); setDownloading(false);
    }
  }, []);
  const loadState = useCallback(() => {
    reads.current.state?.abort(); const controller = new AbortController(); reads.current.state = controller; setState({ status: 'loading' });
    void request<ProvisionMappingState>(provisionPath(sourceId), { signal: controller.signal }).then(value => { if (!controller.signal.aborted) setState({ status: 'loaded', value }); }).catch(cause => { if (!controller.signal.aborted) { setState(fail(cause)); deny(cause); } });
  }, [sourceId, deny]);
  const loadCandidates = useCallback((pageOffset: number) => {
    reads.current.candidates?.abort(); const controller = new AbortController(); reads.current.candidates = controller; setOffset(pageOffset); setCandidates({ status: 'loading' });
    void request<ProvisionCandidates>(`${path}/provision-candidates?offset=${pageOffset}&limit=20`, { signal: controller.signal }).then(value => { if (!controller.signal.aborted) setCandidates({ status: 'loaded', value }); }).catch(cause => { if (!controller.signal.aborted) { setCandidates(fail(cause)); deny(cause); } });
  }, [path, deny]);
  useEffect(() => { loadState(); loadCandidates(0); const objectUrls = urls.current; return () => { Object.values(reads.current).forEach(controller => controller?.abort()); objectUrls.forEach(url => URL.revokeObjectURL(url)); objectUrls.clear(); }; }, [loadState, loadCandidates]);
  const data = state.status === 'loaded' ? state.value : null; const owns = data?.assigned_to?.id === user.id;
  const selected = data?.items.find(item => item.id === selectedId) || null;
  function chooseCandidate(candidate: ProvisionCandidate) {
    reads.current.preview?.abort(); setPreviewing(null); setError('');
    setProposal(previous => ({ ...previous, candidate_id: candidate.id, start: String(candidate.proposed_span.start), end: String(candidate.proposed_span.end), kind: candidate.kind, label: candidate.label }));
    setProposalPreview(candidates.status === 'loaded' ? { source_id: sourceId, source_version_id: candidates.value.source_version_id, text_sha256: candidates.value.text_sha256, span: candidate.proposed_span, passage_ids: candidate.passage_ids, non_whitespace_covered: candidate.non_whitespace_covered } : null);
  }
  function chooseMapping(mapping: ProvisionMapping) {
    reads.current.preview?.abort(); setPreviewing(null); setSelectedId(mapping.id); setError('');
    setReview(mappingReviewDraft(mapping)); setValidityPreview(null);
    setReviewPreview(data ? { source_id: sourceId, source_version_id: data.source.source_version_id, text_sha256: data.source.artifacts['text.txt']?.sha256 || '', span: mapping.span, passage_ids: mapping.passage_ids, non_whitespace_covered: mapping.non_whitespace_covered } : null);
  }
  function changeSpan(target: 'proposal' | 'review', field: 'start' | 'end', value: string) {
    reads.current.preview?.abort(); setPreviewing(null);
    if (target === 'proposal') { setProposal(previous => ({ ...previous, [field]: value })); setProposalPreview(null); }
    else { setReview(previous => ({ ...previous, [field]: value })); setReviewPreview(null); }
  }
  function changeValiditySpan(field: 'start' | 'end', value: string) {
    reads.current.preview?.abort(); setPreviewing(null); setValidityPreview(null);
    setReview(previous => ({ ...previous, [field === 'start' ? 'validity_evidence_start' : 'validity_evidence_end']: value }));
  }
  async function preview(target: 'proposal' | 'review' | 'validity') {
    setError(''); const draft = target === 'proposal' ? proposal : target === 'validity' ? { start: review.validity_evidence_start, end: review.validity_evidence_end } : review;
    if (!data) return;
    try { spanCoordinates(draft.start, draft.end); } catch (cause) { setError(messageOf(cause)); return; }
    reads.current.preview?.abort(); const controller = new AbortController(); reads.current.preview = controller; setPreviewing(target); if (target === 'proposal') setProposalPreview(null); else if (target === 'validity') setValidityPreview(null); else setReviewPreview(null);
    try { const value = await fetchProvisionSpan(sourceId, data.source.source_version_id, data.source.artifacts['text.txt']?.sha256 || '', draft.start, draft.end, controller.signal); if (!controller.signal.aborted) { if (target === 'proposal') setProposalPreview(value); else if (target === 'validity') setValidityPreview(value); else setReviewPreview(value); } }
    catch (cause) { if (!controller.signal.aborted) { setError(messageOf(cause)); deny(cause); } }
    finally { if (!controller.signal.aborted) setPreviewing(null); }
  }
  async function mutate(mappingId: string | null, payload: unknown) {
    if (busy) return; setBusy(true); setError(''); setMessage(''); reads.current.state?.abort();
    const controller = new AbortController(); reads.current.mutation = controller;
    try { const result = await writeProvisionMapping(sourceId, mappingId, payload, controller.signal); if (controller.signal.aborted) return;
      setState({ status: 'loaded', value: result.state });
      if (result.conflict) setError('Kaynak incelemesi veya eşleştirmeler değişti. Güncel kayıt yüklendi; girdileriniz korundu. Karşılaştırıp yeniden kaydedin. Otomatik tekrar yapılmadı.');
      else { setMessage(mappingId ? 'İnsan incelemesi kaydedildi. Eşleştirme yayımlanmadı.' : 'Metin aralığı inceleme önerisi olarak kaydedildi.'); if (mappingId) setReview(previous => ({ ...previous, rationale: '', reference: '', sha256: '' })); else { setProposal(previous => ({ ...previous, rationale: '' })); const added = result.state.items.find(item => !data?.items.some(previous => previous.id === item.id)); if (added) { setSelectedId(added.id); setValidityPreview(null); setReview({ ...EMPTY_MAPPING_REVIEW, start: String(added.span.start), end: String(added.span.end) }); setReviewPreview({ source_id: sourceId, source_version_id: result.state.source.source_version_id, text_sha256: result.state.source.artifacts['text.txt']?.sha256 || '', span: added.span, passage_ids: added.passage_ids, non_whitespace_covered: added.non_whitespace_covered }); } } }
    } catch (cause) { if (!controller.signal.aborted) { setError(messageOf(cause)); if (cause instanceof ApiError && cause.status === 409) setState(fail(cause)); deny(cause); } }
    finally { if (!controller.signal.aborted) setBusy(false); }
  }
  function submitProposal(event: FormEvent) { event.preventDefault(); if (!data || !owns || busy) return; try { void mutate(null, proposalPayload(proposal, data, proposalPreview)); } catch (cause) { setError(messageOf(cause)); } }
  function submitReview(event: FormEvent) { event.preventDefault(); if (!data || !selected || !owns || busy) return; try { void mutate(selected.id, mappingReviewPayload(review, data, reviewPreview, validityPreview)); } catch (cause) { setError(messageOf(cause)); } }
  async function download() { if (downloading) return; setDownloading(true); setError(''); const controller = new AbortController(); reads.current.download = controller;
    try { const blob = await fetchMappingDossier(sourceId, controller.signal); if (controller.signal.aborted) return; const url = URL.createObjectURL(blob); urls.current.add(url); const link = document.createElement('a'); link.href = url; link.download = `gizli-madde-eslestirmeleri-${sourceId.slice(0, 16)}.json`; document.body.append(link); link.click(); link.remove(); window.setTimeout(() => { URL.revokeObjectURL(url); urls.current.delete(url); }, 1000); }
    catch (cause) { if (!controller.signal.aborted) { setError(messageOf(cause)); deny(cause); } } finally { if (!controller.signal.aborted) setDownloading(false); }
  }
  return <div className="provision-mapping-page source-review-page">
    <a className="text-link" href={`#/sources/${sourceId}`}><Icon name="layers" size={16} />Kaynak incelemesine dön</a>
    <PageHeader eyebrow="HUKUK KÜLLİYATINI HAZIRLAMA" title="Maddeyi kaynağıyla eşleştirin." description="Metin sınırlarını inceleyin; düzenleme, hüküm ve sürüm referanslarını ayrı kaydedin." />
    <Notice>Başlık adayları otomatik öneridir. Eşleştirmeler büroya özeldir; insan kabulü bile kaynağı yayımlamaz veya araştırmada kullanıma açmaz.</Notice>
    {error && <Notice error>{error}</Notice>}{message && <Notice>{message}</Notice>}
    {state.status === 'loading' ? <Loading label="Eşleştirme kaydı yükleniyor…" /> : state.status === 'failed' ? <ReadFailure state={state} retry={loadState} /> : data && <>
      <MappingSummary state={data} user={user} />
      <div className="button-group source-review-actions"><a className="button secondary" href={`#/sources/${sourceId}`}>Kaynak incelemesi ve görevlendirme</a><button className="button secondary" disabled={downloading || busy} onClick={() => void download()}><Icon name="download" size={16} />{downloading ? 'Dosya hazırlanıyor…' : 'Eşleştirme dosyasını indir (JSON)'}</button><button className="text-button" disabled={busy} onClick={loadState}>Kaydı yenile</button></div>
      <section className="source-review-section"><h2>1. Metin aralığı önerin</h2><p className="small muted">Bir başlık seçin veya Unicode konumlarını elle girin. Tam metni önizledikten sonra inceleme önerisi oluşturun.</p>
        {candidates.status === 'loading' ? <Loading label="Başlık adayları aranıyor…" /> : candidates.status === 'failed' ? <ReadFailure state={candidates} retry={() => loadCandidates(offset)} /> : <ProvisionCandidateList data={candidates.value} offset={offset} selectedId={proposal.candidate_id} disabled={busy} onSelect={chooseCandidate} onPage={loadCandidates} />}
        <form onSubmit={submitProposal} className="provision-proposal-form"><fieldset className="source-review-fieldset" disabled={!owns || busy}><legend className="visually-hidden">Yeni metin aralığı önerisi</legend>
          <div className="provision-form-heading"><h3>{proposal.candidate_id ? 'Seçili başlığın önerisi' : 'Elle seçilen metin aralığı'}</h3>{proposal.candidate_id && <button className="text-button" type="button" onClick={() => { reads.current.preview?.abort(); setPreviewing(null); setProposal(previous => ({ ...EMPTY_PROPOSAL, rationale: previous.rationale })); setProposalPreview(null); }}>Elle aralık gir</button>}</div>
          <div className="form-grid"><Field label="Madde türü">{id => <select id={id} value={proposal.kind} disabled={Boolean(proposal.candidate_id)} onChange={event => setProposal(previous => ({ ...previous, kind: event.target.value as ProvisionKind }))}>{Object.entries(KINDS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select>}</Field><Field label="Madde etiketi">{id => <input id={id} required maxLength={200} readOnly={Boolean(proposal.candidate_id)} value={proposal.label} onChange={event => setProposal(previous => ({ ...previous, label: event.target.value }))} />}</Field></div>
          <SpanFields start={proposal.start} end={proposal.end} onChange={(field, value) => changeSpan('proposal', field, value)} /><button type="button" className="button secondary" disabled={previewing !== null} onClick={() => void preview('proposal')}>{previewing === 'proposal' ? 'Metin okunuyor…' : 'Öneri aralığını önizle'}</button>
          {proposalPreview && <ProvisionQuote preview={proposalPreview} title="Önerilen aralığın tam metni" />}
          <Field label="Öneri gerekçesi">{id => <textarea id={id} required minLength={3} maxLength={4000} rows={3} value={proposal.rationale} onChange={event => setProposal(previous => ({ ...previous, rationale: event.target.value }))} />}</Field>
          <button className="button primary" disabled={!matchesPreview(proposalPreview, sourceId, proposal.start, proposal.end) || previewing !== null}>İnceleme önerisi olarak kaydet</button>
        </fieldset></form>
      </section>
      <section className="source-review-section"><h2>2. Eşleştirmeyi insan incelemesinden geçirin</h2>
        {!data.items.length ? <Empty title="Henüz eşleştirme önerisi yok.">Üstteki kaynak başlıklarından başlayın veya tam bir metin aralığı önerin.</Empty> : <>
          <div className="provision-mapping-list" aria-label="Kayıtlı eşleştirmeler">{data.items.map(mapping => <button key={mapping.id} className={`provision-mapping-item ${mapping.id === selectedId ? 'selected' : ''}`} aria-pressed={mapping.id === selectedId} disabled={busy} onClick={() => chooseMapping(mapping)}><span><strong>{mapping.label}</strong><span className="small muted">[{mapping.span.start}, {mapping.span.end})</span></span><span><Badge status={mapping.stale ? 'stale' : mapping.status === 'accepted' ? 'reviewed' : mapping.status}>{mapping.stale ? 'Kaynak incelemesi değişti · yeniden inceleyin' : STATUS[mapping.status]}</Badge></span></button>)}</div>
          {!selected ? <p className="small muted">Kaydını ve tam metnini görmek için bir eşleştirme seçin.</p> : <>
            <MappingRecord mapping={selected} />
            <form onSubmit={submitReview}><fieldset className="source-review-fieldset" disabled={!owns || busy}><legend className="visually-hidden">Seçili eşleştirme incelemesi</legend>
              <Field label="Eşleştirme kararı">{id => <select id={id} value={review.decision} onChange={event => setReview(previous => ({ ...previous, decision: event.target.value as SourceReviewDecision }))}>{Object.entries(DECISIONS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select>}</Field>
              {review.decision === 'accepted' && <>
                {!data.source_review_ready && <Notice>Önce dört kaynak incelemesini ve yerel işleme / kurum içi gösterim izinlerini tamamlayın.</Notice>}
                <SpanFields start={review.start} end={review.end} onChange={(field, value) => changeSpan('review', field, value)} /><button type="button" className="button secondary" disabled={previewing !== null} onClick={() => void preview('review')}>{previewing === 'review' ? 'Metin okunuyor…' : 'Kabul edilecek aralığı önizle'}</button>
                {reviewPreview && <ProvisionQuote preview={reviewPreview} title="Kabul edilecek tam metin" />}
                <p className="small muted provision-identity-note">Aşağıdaki referansları inceleyen kişi yazar. Bunlar kendiliğinden çözülmüş graf kimlikleri veya güncel hukuk kabulü değildir.</p>
                <Field label="Düzenleme referansı" hint="Hükmün ait olduğu düzenlemeyi tanımlayın.">{id => <input id={id} required minLength={3} maxLength={300} value={review.instrument_ref} onChange={event => setReview(previous => ({ ...previous, instrument_ref: event.target.value }))} />}</Field>
                <Field label="Hüküm referansı">{id => <input id={id} required minLength={3} maxLength={300} value={review.provision_ref} onChange={event => setReview(previous => ({ ...previous, provision_ref: event.target.value }))} />}</Field>
                <Field label="Hüküm sürümü referansı" hint="İncelediğiniz tarihsel metin sürümünü ayrı belirtin.">{id => <input id={id} required minLength={3} maxLength={300} value={review.provision_version_ref} onChange={event => setReview(previous => ({ ...previous, provision_version_ref: event.target.value }))} />}</Field>
                <Field label="Metnin hukuki rolü">{id => <select id={id} value={review.text_role} onChange={event => setReview(previous => ({ ...previous, text_role: event.target.value as ProvisionResolution['text_role'] }))}>{Object.entries(ROLES).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select>}</Field>
                <div className="form-grid"><Field label="Yürürlük başlangıcı" hint="Bilinmiyorsa boş bırakın.">{id => <input id={id} type="date" required={review.validity_end_mode === 'open_ended'} value={review.valid_from} onChange={event => setReview(previous => ({ ...previous, valid_from: event.target.value }))} />}</Field><Field label="Yürürlük sonunun durumu">{id => <select id={id} value={review.validity_end_mode} onChange={event => { reads.current.preview?.abort(); setPreviewing(null); setValidityPreview(null); setReview(previous => ({ ...previous, validity_end_mode: event.target.value as MappingReviewDraft['validity_end_mode'], valid_until: '' })); }}><option value="unknown">Bilinmiyor</option><option value="closed">Bitiş tarihi biliniyor</option><option value="open_ended">Açık uçlu · dayanakla incelendi</option></select>}</Field></div>
                {review.validity_end_mode === 'closed' && <Field label="Yürürlük sonu" hint="Bu tarih geçerlilik aralığına dahil değildir.">{id => <input id={id} type="date" required value={review.valid_until} onChange={event => setReview(previous => ({ ...previous, valid_until: event.target.value }))} />}</Field>}
                {review.validity_end_mode === 'unknown' && <p className="small muted">Bilinmeyen bitiş, hükmün halen yürürlükte olduğu anlamına gelmez; yayımlama hazırlığını engeller.</p>}
                {review.validity_end_mode === 'open_ended' && <div role="group" aria-label="Açık uçlu yürürlük dayanağı">
                  <p className="small">Bu inceleme, aşağıdaki tarihe kadar bir bitiş saptanmadığını kaydeder. Sonraki tarihlerde uygulanabilirlik için yeni inceleme gerekir.</p>
                  <Field label="Durumun denetlendiği son tarih" hint="Bu gün kapsama dahildir; gelecekteki bir tarih seçilemez.">{id => <input id={id} type="date" required max={new Date().toISOString().slice(0, 10)} value={review.checked_through} onChange={event => setReview(previous => ({ ...previous, checked_through: event.target.value }))} />}</Field>
                  <h3>Yürürlük durumunun kaynak dayanağı</h3><p className="small muted">Aynı kaynaktaki ilgili aralığı seçip okuyun. Hükmün metninden farklı bir bölüm seçebilirsiniz.</p>
                  <SpanFields start={review.validity_evidence_start} end={review.validity_evidence_end} onChange={changeValiditySpan} />
                  <button type="button" className="button secondary" disabled={previewing !== null} onClick={() => void preview('validity')}>{previewing === 'validity' ? 'Dayanak okunuyor…' : 'Yürürlük dayanağını önizle'}</button>
                  {validityPreview && <ProvisionQuote preview={validityPreview} title="Açık uçlu yürürlük dayanağı" />}
                </div>}
              </>}
              <Field label="İnceleme gerekçesi">{id => <textarea id={id} required minLength={3} maxLength={4000} rows={3} value={review.rationale} onChange={event => setReview(previous => ({ ...previous, rationale: event.target.value }))} />}</Field>
              <Field label="Dayanak referansı" hint="Kabul için gerekli. Referans otomatik açılmaz; dayanağın gerçekliğini inceleyen kişi doğrular.">{id => <input id={id} maxLength={1000} required={review.decision === 'accepted'} value={review.reference} onChange={event => setReview(previous => ({ ...previous, reference: event.target.value }))} />}</Field>
              <Field label="Dayanağın SHA256 içerik özeti">{id => <input id={id} autoComplete="off" spellCheck={false} pattern="[a-f0-9]{64}" maxLength={64} required={review.decision === 'accepted' || Boolean(review.reference)} value={review.sha256} onChange={event => setReview(previous => ({ ...previous, sha256: event.target.value }))} />}</Field>
              <button className="button primary" disabled={review.decision === 'accepted' && (!data.source_review_ready || !matchesPreview(reviewPreview, sourceId, review.start, review.end) || !reviewPreview?.non_whitespace_covered || previewing !== null || (review.validity_end_mode === 'open_ended' && (!matchesPreview(validityPreview, sourceId, review.validity_evidence_start, review.validity_evidence_end) || !validityPreview?.non_whitespace_covered)))}>İnsan incelemesini kaydet</button>
            </fieldset></form>
          </>}
        </>}
      </section>
      <Detail title={`Eşleştirme geçmişi (${data.history.length}${data.history_truncated ? '+' : ''})`}>{data.history_truncated && <p className="small">En yeni 50 olay gösterilir. Önceki olaylar saklanır; dışa aktarılan dosya da bu sınırı açıkça belirtir.</p>}{data.history.length ? <ol className="source-review-history">{data.history.map(event => <li key={event.id}><MappingHistory event={event} /></li>)}</ol> : <p className="small">Henüz bir eşleştirme olayı kaydedilmedi.</p>}</Detail>
    </>}
  </div>;
}
function SpanFields({ start, end, onChange }: { start: string; end: string; onChange: (field: 'start' | 'end', value: string) => void }) { return <div className="form-grid"><Field label="Başlangıç konumu" hint="Unicode karakteri; ilk konum 0.">{id => <input id={id} inputMode="numeric" required pattern="[0-9]+" value={start} onChange={event => onChange('start', event.target.value)} />}</Field><Field label="Bitiş konumu" hint="Bu konumdaki karakter aralığa dahil değildir.">{id => <input id={id} inputMode="numeric" required pattern="[0-9]+" value={end} onChange={event => onChange('end', event.target.value)} />}</Field></div>; }
export function MappingSummary({ state, user }: { state: ProvisionMappingState; user: User }) { return <div className="provision-summary"><h2>{state.source.title}</h2><div className="source-review-badges"><Badge>{state.items.length} eşleştirme</Badge><Badge status={state.source_review_ready ? 'reviewed' : undefined}>{state.source_review_ready ? 'Kaynak önkoşulları tamamlandı' : 'Kaynak önkoşulları eksik'}</Badge><Badge>Yayımlanmadı</Badge></div><p className="small">{state.assigned_to ? `İnceleme sorumlusu: ${state.assigned_to.name}.` : 'Kaynak incelemesi henüz atanmadı.'} {state.assigned_to?.id !== user.id && 'Yazmak için kaynak inceleme ekranında sorumluluğu üstlenin.'}</p>{state.handoff_ready && <p className="small">Eşleştirme dosyası bağımsız incelemeye hazır; yayın veya kullanım izni değildir.</p>}<Detail title="Kapsam, revizyonlar ve sınırlamalar"><dl className="coverage-fields"><div><dt>Eşleştirme revizyonu</dt><dd>{state.revision}</dd></div><div><dt>Kaynak inceleme revizyonu</dt><dd>{state.source_review_revision}</dd></div><div><dt>Kaynak sürümü</dt><dd>{state.source.source_version_id}</dd></div><div><dt>Kaynak paketi</dt><dd className="reference-id">{state.source.id}</dd></div><div><dt>Aktarımdaki hak durumu</dt><dd>İnceleme bekliyor</dd></div></dl><p className="small">Kabul için kaynak kimliği, kullanım hakları, metin çıkarımı ve hukuki inceleme kabul edilmeli; haklar yerel işleme ve kurum içi gösterimi kapsamalı. Kaynak incelemesindeki her değişiklik kabul edilmiş eşleştirmeleri yeniden incelemeye gönderir.</p><ul>{state.limitations.map((value, index) => <li key={index}>{value}</li>)}</ul></Detail></div>; }
export function ProvisionCandidateList({ data, offset, selectedId, disabled, onSelect, onPage }: { data: ProvisionCandidates; offset: number; selectedId: string | null; disabled: boolean; onSelect: (item: ProvisionCandidate) => void; onPage: (offset: number) => void }) { return <div className="provision-candidates"><div className="source-passage-pagination"><p className="small">{data.items.length ? `${offset + 1}–${offset + data.items.length}` : '0'} / {data.total} başlık adayı</p><div className="button-group"><button className="button secondary" disabled={disabled || offset === 0} onClick={() => onPage(Math.max(0, offset - 20))}>Önceki adaylar</button><button className="button secondary" disabled={disabled || data.next_offset === null} onClick={() => { if (data.next_offset !== null) onPage(data.next_offset); }}>Sonraki adaylar</button></div></div>{data.truncated && <Notice>Başlık tespiti sınırına ulaşıldı. Bu liste bütün metnin eksiksiz dökümü değildir.</Notice>}{!data.items.length ? <p className="small muted">Bu sayfada açık bir madde başlığı bulunamadı. Özgün kaynağı inceleyip elle aralık önerebilirsiniz.</p> : <ul className="provision-candidate-list">{data.items.map(item => <li key={item.id}><button type="button" disabled={disabled} className={selectedId === item.id ? 'selected' : ''} aria-pressed={selectedId === item.id} onClick={() => onSelect(item)}><strong>{item.label}</strong><span className="small muted">{KINDS[item.kind]} · [{item.heading.start}, {item.heading.end})</span><Badge>Otomatik aday · kimlik çözülmedi</Badge></button>{item.warnings.length > 0 && <Detail title="Aday uyarıları"><ul>{item.warnings.map((value, index) => <li key={index}>{value}</li>)}</ul><p className="source-passage-text">{item.heading.text}</p></Detail>}</li>)}</ul>}<Detail title="Başlık tespitinin sınırları"><p className="small">Başlık ve konum eşleşmesi; hükmün kimliğini, yürürlük tarihini, okuma sırasını veya metin sınırlarının hukuki doğruluğunu onaylamaz. Düzenleme kimliği ve tarihler otomatik atanmaz.</p><ul>{data.limitations.map((value, index) => <li key={index}>{value}</li>)}</ul><p className="reference-id">Tespit sürümü: {data.extraction_version}</p></Detail></div>; }
export function ProvisionQuote({ preview, title }: { preview: ProvisionSpanPreview; title: string }) { return <article className="provision-quote"><div className="provision-form-heading"><h3>{title}</h3><span className="small muted">[{preview.span.start}, {preview.span.end})</span></div><p className="source-passage-text" tabIndex={0} role="region" aria-label={title}>{preview.span.text}</p>{!preview.non_whitespace_covered && <Notice error>Aralığın boşluk dışındaki tüm karakterleri doğrulanmış pasajlarla kapsanmıyor. Kabul için sınırları veya kaynak çıkarımını düzeltin.</Notice>}<Detail title="Tam metin, pasajlar ve içerik özeti"><dl className="coverage-fields"><div><dt>Aralık SHA256</dt><dd className="reference-id">{preview.span.sha256}</dd></div><div><dt>Metin SHA256</dt><dd className="reference-id">{preview.text_sha256}</dd></div><div><dt>Kesişen pasajlar</dt><dd>{preview.passage_ids.join(', ') || 'Yok'}</dd></div><div><dt>Boşluk dışı kapsam</dt><dd>{preview.non_whitespace_covered ? 'Pasajlarla tam kapsanıyor; hukuki doğruluk sonucu değildir' : 'Eksik'}</dd></div></dl></Detail></article>; }
export function MappingRecord({ mapping }: { mapping: ProvisionMapping }) { return <article className="provision-record"><div className="provision-form-heading"><h3>{mapping.label}</h3><Badge status={mapping.stale ? 'stale' : mapping.status === 'accepted' ? 'reviewed' : mapping.status}>{mapping.stale ? 'Yeniden inceleme gerekli' : STATUS[mapping.status]}</Badge></div>{mapping.stale && <Notice error>Bu kabul önceki kaynak incelemesine bağlı. Güncel revizyonu değerlendirmeden geçerli kabul olarak kullanmayın.</Notice>}<p className="source-passage-text" tabIndex={0} role="region" aria-label="Kaydedilmiş tam metin">{mapping.span.text}</p><Detail title="Kaydedilmiş kimlik, rol ve tarih incelemesi">{mapping.resolution ? <><dl className="coverage-fields"><div><dt>Düzenleme referansı</dt><dd>{mapping.resolution.instrument_ref}</dd></div><div><dt>Hüküm referansı</dt><dd>{mapping.resolution.provision_ref}</dd></div><div><dt>Hüküm sürümü referansı</dt><dd>{mapping.resolution.provision_version_ref}</dd></div><div><dt>Metnin rolü</dt><dd>{ROLES[mapping.resolution.text_role]}</dd></div><div><dt>Yürürlük başlangıcı</dt><dd>{mapping.resolution.valid_from ? formatDate(mapping.resolution.valid_from) : 'Bilinmiyor'}</dd></div><div><dt>Yürürlük sonu</dt><dd>{mapping.resolution.open_ended_validity ? 'Açık uçlu · dayanakla incelendi' : mapping.resolution.valid_until ? formatDate(mapping.resolution.valid_until) : 'Bilinmiyor'}</dd></div>{mapping.resolution.open_ended_validity && <><div><dt>Denetlenen son tarih (dahil)</dt><dd>{formatDate(mapping.resolution.open_ended_validity.checked_through)}</dd></div><div><dt>Yürürlük dayanağı aralığı</dt><dd>[{mapping.resolution.open_ended_validity.evidence_start}, {mapping.resolution.open_ended_validity.evidence_end})</dd></div><div><dt>Sonraki tarihler</dt><dd>Uygulanabilirlik için yeniden inceleme gerekir.</dd></div></>}<div><dt>İncelenen kaynak revizyonu</dt><dd>{mapping.reviewed_source_revision}</dd></div></dl><p className="small muted">Referanslar inceleyenin beyanıdır; doğrulanmış graf kimliği sayılmaz.</p></> : <p className="small">Düzenleme, hüküm, sürüm kimliği ve yürürlük tarihleri henüz çözümlenmedi.</p>}<p className="reference-id">Tam metin aralığı: [{mapping.span.start}, {mapping.span.end}) · {mapping.span.sha256}</p><p className="small">Pasajlar: {mapping.passage_ids.join(', ') || 'Yok'}</p><MappingHistory event={mapping.last_event} /></Detail></article>; }
function MappingHistory({ event }: { event: ProvisionMappingEvent }) { return <div><p><strong>{event.event_type === 'propose' ? 'Metin aralığı önerildi' : event.decision ? DECISIONS[event.decision] : 'İnceleme kaydı'}</strong> · Revizyon {event.revision}</p><p className="small muted">{event.reviewer.name} · {formatDate(event.created_at, true)} · Kaynak incelemesi {event.source_review_revision}</p><p className="source-review-rationale">{event.rationale}</p>{event.evidence_refs.length > 0 && <ul>{event.evidence_refs.map((item, index) => <li key={index}>{item.reference}<p className="reference-id">{item.sha256}</p></li>)}</ul>}<p className="small">{event.snapshot.label} · [{event.snapshot.span.start}, {event.snapshot.span.end})</p></div>; }
