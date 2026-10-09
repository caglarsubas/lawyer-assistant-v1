import { useEffect, useRef, useState } from 'react';
import { ApiError, post, request } from '../../api';
import { Badge, Detail, Field, Notice } from '../../components';
import { isRunning, messageOf, statusLabel } from '../../utils';
import type { AnalysisSuggestion } from './analysisTypes';
import type { FindingDimension, FindingView } from './authorityFindingTypes';
import { FINDING_OUTCOMES } from './authorityFindingTypes';
import AuthorityProposalSummary from './AuthorityProposalSummary';

export default function AuthoritySuggestions({ matterId, analysisId, value, onAdopt, onUnavailable }: { matterId: string; analysisId: string; value: FindingView; onAdopt?: () => Promise<void>; onUnavailable: (cause: unknown) => void }) {
  const [selected, setSelected] = useState<{ source_index: number; dimension: FindingDimension }[]>([]);
  const [mode, setMode] = useState<'single' | 'repair'>('single');
  const [jobs, setJobs] = useState<AnalysisSuggestion[]>([]); const [notes, setNotes] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false); const [error, setError] = useState(''); const [notice, setNotice] = useState('');
  const [more, setMore] = useState(false); const offset = useRef(0); const pending = useRef<{ payload: string; id: string } | null>(null);
  const mounted = useRef(true); useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  const snapshot = value.snapshot; const manifest = snapshot?.context_snapshot.manifest;
  const base = `/matters/${encodeURIComponent(matterId)}/analyses/${encodeURIComponent(analysisId)}/suggestions`;
  const active = jobs.filter(job => isRunning(job.status)).map(job => job.id).sort().join('|');
  function update(job: AnalysisSuggestion) { setJobs(old => [job, ...old.filter(item => item.id !== job.id)]); }
  function fail(cause: unknown) { setJobs([]); setError(messageOf(cause)); onUnavailable(cause); }
  useEffect(() => {
    if (!active) return;
    const controller = new AbortController(); let polling = false;
    const timer = window.setInterval(async () => {
      if (polling) return; polling = true;
      try { const values = await Promise.all(active.split('|').map(id => request<AnalysisSuggestion>(`${base}/${encodeURIComponent(id)}`, { cache: 'no-store', signal: controller.signal })));
        if (!controller.signal.aborted) setJobs(old => old.map(job => values.find(item => item.id === job.id) || job));
      } catch (cause) { if (!controller.signal.aborted) fail(cause); } finally { polling = false; }
    }, 2500);
    return () => { controller.abort(); window.clearInterval(timer); };
  }, [active, base]);
  async function start() {
    if (!manifest || !selected.length) return;
    const body = { expected_revision: manifest.analysis_revision, version_id: manifest.version_id, mode,
      authority_feedback: { context_id: value.context_id || snapshot?.context_snapshot.id, review_id: value.id, review_sha256: value.review_sha256, findings: selected } };
    const payload = JSON.stringify(body); if (pending.current?.payload !== payload) pending.current = { payload, id: crypto.randomUUID().replaceAll('-', '') };
    setBusy(true); setError(''); setNotice('');
    try { const job = await post<AnalysisSuggestion>(base, { ...body, request_id: pending.current.id }); if (mounted.current) { update(job); pending.current = null; } }
    catch (cause) { if (mounted.current) { if (cause instanceof ApiError && [403, 404, 409].includes(cause.status)) fail(cause); else setError(messageOf(cause)); } } finally { if (mounted.current) setBusy(false); }
  }
  async function history(append = false) { setBusy(true); setError(''); try {
    const page = await request<AnalysisSuggestion[]>(`${base}?limit=10&offset=${append ? offset.current : 0}`, { cache: 'no-store' });
    if (mounted.current) { offset.current = (append ? offset.current : 0) + page.length;
      const visible = page.filter(job => Boolean(job.authority_feedback) || job.public_source_access === false);
      setJobs(old => append ? [...old, ...visible.filter(item => !old.some(job => job.id === item.id))] : visible); setMore(page.length === 10); }
    } catch (cause) { if (mounted.current) fail(cause); } finally { if (mounted.current) setBusy(false); } }
  async function action(job: AnalysisSuggestion, operation: 'adopt' | 'cancel') { setBusy(true); setError(''); try {
    const result = await post<AnalysisSuggestion>(`${base}/${encodeURIComponent(job.id)}/${operation}`, operation === 'adopt'
      ? { expected_revision: manifest?.analysis_revision, candidate_sha256: job.candidate_sha256, change_note: notes[job.id] || '' } : {});
    if (mounted.current) { if (operation === 'cancel') update(result); else { setJobs([]); setNotice('Öneri yeni İnceleme gerekli sürümüne alındı. Bulgular ve önceki taslak korunur.'); await onAdopt?.(); } }
    } catch (cause) { if (mounted.current) fail(cause); } finally { if (mounted.current) setBusy(false); } }
  if (!snapshot || !manifest || !value.public_source_access) return <Notice error>Kamu dayanağı içeriği bekletiliyor.</Notice>;
  const canRequest = value.freshness.status === 'current' && value.is_latest_review && Boolean(manifest.analysis_revision);
  return <><p>En fazla beş açık dayanak bulgusunu seçin. Yerel model yalnız bağlı uygulama ve geçici sonuç metinlerini önerebilir. Taslak ve bulgular otomatik değişmez.</p>
    <fieldset disabled={busy || Boolean(active) || !canRequest}><legend>Modele gönderilecek dayanak bulguları</legend>
      {snapshot.assessment.sources.map((source, index) => <Detail key={index} title={`${index + 1}. kamu dayanağı`}>{source.observations.map(item => {
        const checked = selected.some(value => value.source_index === index && value.dimension === item.dimension);
        return <label key={item.dimension} className="checkbox-label"><input type="checkbox" checked={checked} disabled={item.outcome === 'supported' || (!checked && selected.length >= 5)} onChange={() => setSelected(old => checked ? old.filter(value => value.source_index !== index || value.dimension !== item.dimension) : [...old, { source_index: index, dimension: item.dimension }])} />{snapshot.dimensions[item.dimension]} · {FINDING_OUTCOMES[item.outcome]}<span className="authored-text">{item.note}</span></label>;
      })}</Detail>)}
      <Field label="Dayanak önerisi bütçesi">{id => <select id={id} value={mode} onChange={event => setMode(event.target.value as typeof mode)}><option value="single">Tek geçiş · En fazla 120 sn</option><option value="repair">Kritik yapısal kontrol kalırsa bir ek geçiş · En fazla 240 sn</option></select>}</Field>
      <button className="button secondary" disabled={!selected.length} onClick={() => void start()}>Seçili dayanak bulguları için yerel öneri iste</button>
    </fieldset>
    <button className="text-button" disabled={busy} onClick={() => void history()}>Dayanak önerisi geçmişini getir</button>
    {jobs.map(job => <article className="practice-record" key={job.id}><Badge>{statusLabel(job.status)}</Badge>
      <p className="small">Model: {job.provider_pin.model} · En fazla {job.max_passes} geçiş · Hukuki onay verilmez.</p>
      {job.provider_pin.transport.uses_public_network && <p className="small">Onaylı dizüstü tüneli internet üzerinden yerel modele erişir; bu aktarım air-gapped değildir.</p>}
      {job.public_source_access === false && <Notice error>Kamu içeriği ve bunu içerebilen model metinleri bekletiliyor.</Notice>}
      {job.freshness.status === 'stale' && <Notice error>Dayanak bağları değişti; yeni taslağa alınamaz.</Notice>}
      {job.public_source_access !== false && job.authority_feedback && <AuthorityProposalSummary feedback={job.authority_feedback} responses={job.authority_responses} pass={job.authority_response_pass} />}
      {job.public_source_access !== false && job.candidate && <Detail title="Önerilen düzenlemeleri ve özel pasajları incele"><p>Değişen bölümler: {job.candidate.revision_comparison.changed_sections.join(' · ') || 'Yok'}</p>{job.candidate.applications.map(item => <p className="authored-text" key={item.id}>{item.id}: {item.rationale}</p>)}<p className="authored-text">{job.candidate.conclusion.text}</p><ul>{job.candidate.conclusion.uncertainty.map(item => <li key={item}>{item}</li>)}</ul>{job.candidate.evidence.map(source => <Detail key={source.evidence_id} title={`Özel pasaj: ${source.evidence_id}`}><blockquote>{source.text}</blockquote></Detail>)}</Detail>}
      {job.public_source_access !== false && job.authority_feedback && job.iterations?.map(pass => <Detail key={pass.pass} title={`Geçiş ${pass.pass} · ${pass.outcome}`}><p>{pass.provider_seconds} sn · {pass.prompt.utf8_bytes} UTF-8 bayt · {pass.prompt.completion_tokens} çıktı tokenı sınırı</p>{pass.patch?.authority_responses && <AuthorityProposalSummary feedback={job.authority_feedback!} responses={pass.patch.authority_responses} pass={pass.pass} />}</Detail>)}
      {isRunning(job.status) && <button className="text-button" disabled={busy} onClick={() => void action(job, 'cancel')}>Dayanak önerisini durdur</button>}
      {job.status === 'completed' && !job.adopted_version_id && <><Field label="Dayanak önerisini alma gerekçesi">{id => <input id={id} value={notes[job.id] || ''} maxLength={1000} disabled={!job.can_adopt || busy} onChange={event => setNotes(old => ({ ...old, [job.id]: event.target.value }))} />}</Field><button className="button secondary" disabled={busy || !job.can_adopt || (notes[job.id] || '').trim().length < 3} onClick={() => void action(job, 'adopt')}>Dayanak önerisini yeni taslağa al</button></>}
      {job.adopted_version_id && <p>Öneri yeni taslağa alındı; yeniden avukat incelemesi gerekli.</p>}
    </article>)}
    {more && <button className="text-button" disabled={busy} onClick={() => void history(true)}>Önceki dayanak önerilerini getir</button>}{notice && <Notice>{notice}</Notice>}{error && <Notice error>{error}</Notice>}
  </>;
}
