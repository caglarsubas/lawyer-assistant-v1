import { useEffect, useRef, useState } from 'react';
import { post, request } from '../../api';
import { Badge, Detail, Field, Notice } from '../../components';
import { formatDate, isRunning, messageOf, statusLabel } from '../../utils';
import AuthorityProposalSummary from './AuthorityProposalSummary';
import { FeedbackResponses, FeedbackSummary, ReviewFindingPicker } from './AnalysisFeedback';
import { AnalysisContentView } from './AnalysisView';
import type { AnalysisRecord, AnalysisSuggestion } from './analysisTypes';

export function ProposalReview({ job, onSource }: { job: AnalysisSuggestion; onSource: (id: string) => void }) {
  if (job.public_source_access === false) return <Notice error>Kamu dayanağı içeriği ve bunu içerebilen model metinleri bekletiliyor. Önceki aday gösterilmez.</Notice>;
  return <>
    <p className="small muted">Model: {job.provider_pin.model} · {job.mode === 'repair' ? 'En fazla bir ek düzeltme geçişi' : 'Tek öneri geçişi'} · {(job.iterations || []).length}/{job.max_passes} saklanan geçiş · Hukuki onay verilmedi.</p>
    {job.provider_pin.transport.uses_public_network && <p className="small muted">Onaylı dizüstü tüneli internet üzerinden yerel modele erişir; bu aktarım air-gapped değildir.</p>}
    {job.error && <Notice error>{job.error}</Notice>}
    {job.freshness.status === 'stale' && <Notice error>Öneri artık güncel değil; yeni taslağa alınamaz.{job.freshness.reasons.map((reason) => <p key={reason}>{reason}</p>)}</Notice>}
    {job.adopted_version_id && <p className="small muted">Öneri bir taslak sürümüne alındı. Bu işlem hukuki inceleme veya onay değildir.</p>}
    {job.authority_feedback && <AuthorityProposalSummary feedback={job.authority_feedback} responses={job.authority_responses} pass={job.authority_response_pass} />}
    {job.review_feedback && <FeedbackSummary feedback={job.review_feedback} responses={job.feedback_responses} pass={job.feedback_response_pass} onSource={onSource} />}
    {job.review_notes?.length ? <Detail title={`Modelin inceleme notları (${job.review_notes.length})`}><p className="small muted">Kaynak bağlantıları adaydır; notların anlam ve doğruluğu ayrıca incelenmelidir.</p><ul>{job.review_notes.map((note, index) => <li key={index}><strong>{note.target_id} · Geçiş {note.pass}:</strong> {note.text}{note.evidence_ids.map((id) => <button key={id} className="source-link" onClick={() => onSource(id)}>Özgün dayanak</button>)}</li>)}</ul></Detail> : null}
    {job.candidate && <Detail title="Önerilen taslak ve kaynakları"><p className="small muted">{job.status === 'completed' ? 'Öneri çalışması tamamlandı.' : 'Önceki geçişten saklanan kısmi öneri.'} Sabit olgular, kaynaklar, kurallar ve koşullar değiştirilemez; avukatın mevcut taslağı korunur.</p><p className="reference-id">Önerilen bölüm değişiklikleri: {job.candidate.revision_comparison.changed_sections.join(', ') || 'Yok'}</p><AnalysisContentView content={job.candidate} freshness={job.freshness} onSource={onSource} proposed /></Detail>}
    <Detail title="Çalışma bütçesi ve geçiş ayrıntıları">
      <p className="reference-id">Kaynak analiz sürümü: {job.source_version_id}</p>
      <p>{job.budget_seconds} saniye · Son sınır: {formatDate(job.deadline_at, true)} · Her geçişte en fazla 1.000 çıktı tokenı. Kontroller beyan edilen yapıyla sınırlıdır.</p>
      {(job.iterations || []).map((item) => <div key={item.pass}><p>Geçiş {item.pass}: {item.outcome === 'rejected_new_critical_checks' ? 'Yeni kritik kontrol nedeniyle öneri değişikliği alınmadı' : 'Yapısal kontrollerden sonra aday olarak saklandı'} · {item.provider_seconds} sn model çağrısı · {item.prompt.utf8_bytes} UTF-8 bayt</p><p className="reference-id">İleti özeti: {item.prompt.messages_sha256}</p>{item.patch?.feedback_responses && item.patch.feedback_responses.length > 0 && <Detail title={`Geçiş ${item.pass} bulgu yanıtları · ${item.outcome === 'rejected_new_critical_checks' ? 'adaya alınmadı' : 'aday'}`}><FeedbackResponses responses={item.patch.feedback_responses} onSource={onSource} /></Detail>}</div>)}
      <p className="small muted">Durdurma ve süre sınırı kontrol noktalarında uygulanır; devam eden model çağrısının bitmesi gerekebilir. Otomatik yeniden deneme yapılmaz. Bu ölçümler hukuki kalite veya derin araştırma başarısını göstermez.</p>
    </Detail>
  </>;
}

function ProposalCard({ job, base, record, onSource, onAdopt, onUpdate }: { job: AnalysisSuggestion; base: string; record: AnalysisRecord; onSource: (id: string) => void; onAdopt: () => Promise<void>; onUpdate: (job: AnalysisSuggestion) => void }) {
  const [note, setNote] = useState(''); const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  async function cancel() { setBusy(true); setError(''); try { onUpdate(await post<AnalysisSuggestion>(`${base}/${encodeURIComponent(job.id)}/cancel`, {})); } catch (cause) { onUpdate({ ...job, candidate: undefined, review_notes: [], iterations: [], authority_feedback: undefined, authority_responses: [], can_adopt: false }); setError(messageOf(cause)); } finally { setBusy(false); } }
  async function adopt() { setBusy(true); setError(''); try { await post(`${base}/${encodeURIComponent(job.id)}/adopt`, { expected_revision: record.revision, candidate_sha256: job.candidate_sha256, change_note: note }); await onAdopt(); } catch (cause) { onUpdate({ ...job, candidate: undefined, review_notes: [], iterations: [], authority_feedback: undefined, authority_responses: [], can_adopt: false }); setError(messageOf(cause)); } finally { setBusy(false); } }
  return <article className="practice-record"><div className="practice-record-heading"><strong>{formatDate(job.created_at, true)}</strong><Badge>{job.status === 'completed' ? 'Öneri hazır · İnceleme gerekli' : statusLabel(job.status)}</Badge></div><p className="small muted">Aşama: {({ queued: 'Sırada', preparing: 'Sabit taslak hazırlanıyor', suggesting: 'Model önerisi', checking: 'Yapısal kontroller', checked: 'Geçiş saklandı', repairing: 'Ek düzeltme önerisi', finished: 'Çalışma bitti' } as Record<string, string>)[job.phase] || job.phase}</p><ProposalReview job={job} onSource={onSource} />
    {isRunning(job.status) && <><button className="text-button" disabled={busy || job.status === 'cancelling'} onClick={() => void cancel()}>Öneri çalışmasını durdur</button>{job.status === 'cancelling' && <p role="status">Durdurma isteği alındı; devam eden çağrının bitmesi bekleniyor. Yeni sonuç uygulanmayacak.</p>}</>}
    {job.comparison_ref && <p className="small muted">Protokole bağlı deneme adayıdır; çalışma taslağına alınamaz. Karşılaştırma ekranında gözlem ve süre kayıtlarıyla inceleyin.</p>}{job.status === 'completed' && !job.adopted_version_id && !job.comparison_ref && <><Field label="Yeni taslağa alma gerekçesi">{(id) => <input id={id} minLength={3} maxLength={1000} value={note} disabled={busy || !job.can_adopt} onChange={(event) => setNote(event.target.value)} />}</Field><button className="button secondary" disabled={busy || !job.can_adopt || note.trim().length < 3} onClick={() => void adopt()}>{busy ? 'Kaydediliyor…' : 'Öneriyi yeni taslak sürümüne al'}</button><p className="small muted">Önce öneriyi ve özgün kaynakları karşılaştırın. Yeni sürüm İnceleme gerekli olarak saklanır; önceki sürüm ve olgu defteri korunur.{!job.can_adopt && ' Değişiklik yoksa, dayanaklar değişmişse veya öneri daha önce alınmışsa uygulanamaz.'}</p></>}
    {error && <Notice error>{error}</Notice>}
  </article>;
}

export function AnalysisSuggestions({ matterId, record, onSource, onAdopt }: { matterId: string; record: AnalysisRecord; onSource: (id: string) => void; onAdopt: () => Promise<void> }) {
  const [jobs, setJobs] = useState<AnalysisSuggestion[]>([]); const [mode, setMode] = useState<'single' | 'repair'>('single'); const [busy, setBusy] = useState(false); const [error, setError] = useState(''); const [more, setMore] = useState(false); const [loaded, setLoaded] = useState(false);
  const [selection, setSelection] = useState<{ review: string; indices: number[] } | null>(null);
  const review = record.review?.effective_state === 'changes_requested' ? record.review.latest : null;
  const indices = selection && review && selection.review === review.id ? selection.indices : [];
  const pending = useRef<{ payload: string; id: string } | null>(null);
  const base = `/matters/${encodeURIComponent(matterId)}/analyses/${encodeURIComponent(record.id)}/suggestions`;
  const active = jobs.filter((job) => isRunning(job.status)).map((job) => job.id).sort().join('|');
  function update(job: AnalysisSuggestion) { setJobs((old) => [job, ...old.filter((item) => item.id !== job.id)]); }
  useEffect(() => {
    if (!active) return;
    const controller = new AbortController(); let polling = false; let failures = 0;
    const timer = window.setInterval(async () => {
      if (polling) return; polling = true;
      try {
        const current = await Promise.all(active.split('|').map((id) => request<AnalysisSuggestion>(`${base}/${encodeURIComponent(id)}`, { signal: controller.signal })));
        if (controller.signal.aborted) return;
        failures = 0; setError(''); setJobs((old) => old.map((job) => current.find((item) => item.id === job.id) || job));
      } catch (cause) { if (!controller.signal.aborted) { setJobs([]); setError(messageOf(cause)); if (++failures >= 3) window.clearInterval(timer); } }
      finally { polling = false; }
    }, 2500);
    return () => { controller.abort(); window.clearInterval(timer); };
  }, [active, base]);
  async function history(append = false) { setBusy(true); setError(''); try { const page = await request<AnalysisSuggestion[]>(`${base}?limit=10&offset=${append ? jobs.length : 0}`); setJobs((old) => append ? [...old, ...page.filter((item) => !old.some((job) => job.id === item.id))] : page); setMore(page.length === 10); setLoaded(true); } catch (cause) { setJobs([]); setError(messageOf(cause)); } finally { setBusy(false); } }
  async function start() { setBusy(true); setError(''); const body = { expected_revision: record.revision, version_id: record.latest_version_id, mode, ...(review && indices.length ? { review_feedback: { review_id: review.id, finding_indices: indices } } : {}) }; const payload = JSON.stringify(body); if (pending.current?.payload !== payload) pending.current = { payload, id: crypto.randomUUID().replaceAll('-', '') }; try { const job = await post<AnalysisSuggestion>(base, { ...body, request_id: pending.current!.id }); update(job); pending.current = null; } catch (cause) { setError(messageOf(cause)); } finally { setBusy(false); } }
  return <Detail title="Yerel modelden düzenleme önerisi">
    <p>Kaydedilmiş bu sürüm için uygulama ve geçici sonuç düzenlemeleri isteyin. Olgular, roller, kaynaklar, kurallar, koşullar ve adım bağlantıları sabittir. Öneri mevcut taslağı otomatik değiştirmez.</p>
    <Field label="Öneri bütçesi">{(id) => <select id={id} disabled={busy} value={mode} onChange={(event) => setMode(event.target.value as typeof mode)}><option value="single">Tek model geçişi · en fazla 120 sn</option><option value="repair">Kritik yapısal kontrol kalırsa bir ek geçiş · en fazla 240 sn</option></select>}</Field>
    {review && Boolean(review.findings.length) && <ReviewFindingPicker review={review} indices={indices} disabled={busy || Boolean(active) || record.status === 'stale'} onChange={(next) => setSelection({ review: review.id, indices: next })} onSource={onSource} />}
    <div className="practice-record-actions"><button className="button secondary" disabled={busy || Boolean(active) || record.status === 'stale'} onClick={() => void start()}>{busy ? 'İşleniyor…' : 'Yerel model önerisi iste'}</button><button className="text-button" disabled={busy} onClick={() => void history()}>{loaded ? 'Önerileri yenile' : 'Öneri geçmişini getir'}</button></div>
    {record.status === 'stale' && <p className="small muted">Önce değişen dayanakları inceleyip güncel analiz sürümünü saklayın.</p>}{error && <Notice error>{error}</Notice>}
    {jobs.map((job) => <ProposalCard key={job.id} job={job} base={base} record={record} onSource={onSource} onAdopt={onAdopt} onUpdate={update} />)}
    {loaded && !jobs.length && <p className="small muted">Bu analize ait öneri kaydı yok.</p>}{more && <button className="text-button" disabled={busy} onClick={() => void history(true)}>Önceki önerileri getir</button>}
  </Detail>;
}
