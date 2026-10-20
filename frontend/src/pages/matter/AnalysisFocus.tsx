import { useEffect, useRef, useState } from 'react';
import { post, request } from '../../api';
import { Detail, Field, Notice } from '../../components';
import { messageOf } from '../../utils';
import { AnalysisContextBudget } from './AnalysisContextBudget';
import { AnalysisContentView } from './AnalysisView';
import type { AnalysisContent, AnalysisContextPreview, AnalysisRecord, AnalysisSelection } from './analysisTypes';

interface Preview { content: AnalysisContent; budget: AnalysisContextPreview }

export function AnalysisFocus({ matterId, record, onSource, onSaved }: {
  matterId: string; record: AnalysisRecord; onSource: (id: string) => void; onSaved: () => Promise<void>;
}) {
  const [title, setTitle] = useState(''); const [issue, setIssue] = useState('');
  const [application, setApplication] = useState(record.applications[0]?.id || '');
  const [alternatives, setAlternatives] = useState(record.alternatives.map(item => item.id));
  const [evidence, setEvidence] = useState<AnalysisSelection[]>(record.evidence.map(({ evidence_id, passage_sha256, document_revision, start, end }) => ({ evidence_id, passage_sha256, document_revision, start, end })));
  const [note, setNote] = useState(''); const [acknowledged, setAcknowledged] = useState(false);
  const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  const [preview, setPreview] = useState<{ key: string; value: Preview } | null>(null);
  const generation = useRef(0); const pending = useRef<{ payload: string; id: string } | null>(null);
  const body = { expected_revision: record.revision, version_id: record.latest_version_id, title, issue,
    application_id: application, alternative_ids: alternatives, evidence, omission_note: note, acknowledge_partial: acknowledged };
  const base = `/matters/${encodeURIComponent(matterId)}/analyses/${encodeURIComponent(record.id)}/focus`;
  const key = JSON.stringify({ base, body, review: record.review?.latest?.id, state: record.review?.effective_state, status: record.status });
  const latestKey = useRef(key); latestKey.current = key;
  const current = preview?.key === key ? preview.value : null;
  useEffect(() => { setPreview(null); setBusy(false); return () => { generation.current++; }; }, [key]);
  const eligible = !record.focus_lineage && !record.authority_contributions?.length && record.status !== 'stale';
  const valid = eligible && title.trim().length >= 3 && issue.trim().length >= 3 && note.trim().length >= 10 && acknowledged && application && evidence.length > 0;
  async function measure() {
    const observedKey = key; const turn = ++generation.current;
    setBusy(true); setError(''); setPreview(null);
    try {
      const value = await request<Preview>(`${base}/preview`, { method: 'POST', refreshPortfolio: false,
        body: JSON.stringify({ ...body, request_id: crypto.randomUUID().replaceAll('-', '') }) });
      if (turn === generation.current && latestKey.current === observedKey) setPreview({ key: observedKey, value });
    } catch (cause) { if (turn === generation.current && latestKey.current === observedKey) setError(messageOf(cause)); }
    finally { if (turn === generation.current) setBusy(false); }
  }
  async function save() {
    if (!current?.budget.fits) return;
    const observedKey = key; const turn = ++generation.current;
    const submission = { ...body, context_preview_sha256: current.budget.preview_sha256 };
    const payload = JSON.stringify(submission);
    if (pending.current?.payload !== payload) pending.current = { payload, id: crypto.randomUUID().replaceAll('-', '') };
    setBusy(true); setError('');
    try {
      await post(base, { ...submission, request_id: pending.current.id });
      pending.current = null;
      if (turn === generation.current && latestKey.current === observedKey) { setPreview(null); await onSaved(); }
    } catch (cause) { if (turn === generation.current && latestKey.current === observedKey) { setPreview(null); setError(messageOf(cause)); } }
    finally { if (turn === generation.current) setBusy(false); }
  }
  return <Detail title="Bağlama sığan ayrı odak analizi">
    <p>Tek uygulama adımı seçin. Ana analiz, özgün belgeler, önceki denemeler ve incelemeler korunur. Yeni kayıt hukuki inceleme almamış olarak başlar; model kendiliğinden çalışmaz.</p>
    {!eligible ? <p className="small muted">Önce güncel ana analizi açın. Kamu katkılı veya zaten odaklanmış analiz bu ilk akışta daraltılamaz.</p> : <>
      <Field label="Odak analizinin başlığı">{id => <input id={id} maxLength={200} value={title} disabled={busy} onChange={event => setTitle(event.target.value)} />}</Field>
      <Field label="Dar kapsamlı inceleme sorusu">{id => <textarea id={id} maxLength={500} value={issue} disabled={busy} onChange={event => setIssue(event.target.value)} />}</Field>
      <Field label="Korunacak uygulama adımı">{id => <select id={id} value={application} disabled={busy} onChange={event => setApplication(event.target.value)}>{record.applications.map(item => <option key={item.id} value={item.id}>{item.id} · {item.rule_id}</option>)}</select>}</Field>
      <Detail title="Ana sürümdeki seçili adım"><p className="authored-text">{record.rules.find(item => item.id === record.applications.find(step => step.id === application)?.rule_id)?.text}</p><p className="authored-text">{record.applications.find(item => item.id === application)?.rationale}</p></Detail>
      <p className="small muted">Bağlı kural, tüm koşul ve değerlendirme durumları, olgu rolleri ve olay tarihi aynen korunur. Önceki gerekçe, genel mesele, süreç ve sonuç kopyalanmaz; kapsam ve dışarıda kalanlar kaydedilir.</p>
      <fieldset disabled={busy}><legend>Alternatif ve karşı argümanlar · başlangıçta tümü seçili</legend>{record.alternatives.map(item => <label className="small" key={item.id}><input type="checkbox" checked={alternatives.includes(item.id)} onChange={event => setAlternatives(old => event.target.checked ? [...old, item.id] : old.filter(id => id !== item.id))} /> {item.id} · {item.text}</label>)}</fieldset>
      <Detail title="Dondurulmuş alıntıları açıkça seç ve sınırla">
        <p className="small muted">Tüm alıntılar başlangıçta korunur. Kural, olgu ve seçili alternatiflerin dayanakları çıkarılamaz. Unicode aralıkları sıfırdan başlar; son konum dahil değildir. Daha dar seçim hukuki yeterlilik sağlamaz.</p>
        {record.evidence.map(source => {
          const selection = evidence.find(item => item.evidence_id === source.evidence_id);
          function range(field: 'start' | 'end', value: number) { setEvidence(old => old.map(item => item.evidence_id === source.evidence_id ? { ...item, [field]: value } : item)); }
          return <fieldset key={source.evidence_id} disabled={busy}><legend>{source.name} · {source.evidence_id}</legend>
            <label><input type="checkbox" checked={Boolean(selection)} onChange={event => setEvidence(old => event.target.checked ? [...old, { evidence_id: source.evidence_id, passage_sha256: source.passage_sha256, document_revision: source.document_revision, start: source.start, end: source.end }] : old.filter(item => item.evidence_id !== source.evidence_id))} /> Alıntıyı koru</label>
            <p className="authored-text">{source.text}</p><button className="source-link" onClick={() => onSource(source.evidence_id)}>Özgün belgeyi aç</button>
            {selection && <><Field label={`${source.evidence_id} başlangıç`}>{id => <input id={id} type="number" min={source.start} max={source.end - 1} value={selection.start} onChange={event => range('start', Number(event.target.value))} />}</Field><Field label={`${source.evidence_id} bitiş`}>{id => <input id={id} type="number" min={selection.start + 1} max={source.end} value={selection.end} onChange={event => range('end', Number(event.target.value))} />}</Field><p className="authored-text">Seçilen metin: {Array.from(source.text).slice(selection.start - source.start, selection.end - source.start).join('')}</p></>}
          </fieldset>;
        })}
      </Detail>
      <Field label="Kapsam dışı kalanlar ve daraltma gerekçesi">{id => <textarea id={id} minLength={10} maxLength={500} value={note} disabled={busy} onChange={event => setNote(event.target.value)} />}</Field>
      <label><input type="checkbox" checked={acknowledged} disabled={busy} onChange={event => setAcknowledged(event.target.checked)} /> Dışarıda kalanları ana analizde inceleyeceğim; bu odak genel hukuki sonuç veya önceki incelemenin onayı değildir.</label>
      <div className="practice-record-actions"><button className="text-button" disabled={busy || !valid} onClick={() => void measure()}>Odak kapsamını ve bütçeyi önizle</button><button className="button secondary" disabled={busy || !valid || !current?.budget.fits} onClick={() => void save()}>Ayrı odak analizini kaydet</button></div>
      {current && <section aria-label="Odak analizi önizlemesi"><p className="small muted">Henüz kaydedilmedi. Bütçedeki kaynak sürüm ana analizdir. Kaydetmek model çağrısı yapmaz; yeni kayıtta başlatmadan önce bütçeyi yeniden hesaplayın.</p><AnalysisContextBudget value={current.budget} /><AnalysisContentView content={current.content} onSource={onSource} /></section>}
    </>}{error && <Notice error>{error}</Notice>}
  </Detail>;
}
