import { useCallback, useEffect, useRef, useState } from 'react';
import { downloadAnalysis, request } from '../../api';
import { Detail, Loading, Notice } from '../../components';
import type { Matter } from '../../types';
import { formatDate, messageOf } from '../../utils';
import { EvidenceViewer } from './FactsPanel';
import { AnalysisEditor } from './AnalysisEditor';
import { AnalysisContentView } from './AnalysisView';
import { AnalysisSuggestions } from './AnalysisSuggestions';
import type { AnalysisRecord, AnalysisVersion } from './analysisTypes';

function AnalysisDownloads({ matterId, recordId, versionId }: { matterId: string; recordId: string; versionId: string }) {
  const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  async function download(format: 'docx' | 'pdf') { setBusy(true); setError(''); try { await downloadAnalysis(matterId, recordId, versionId, format); } catch (cause) { setError(messageOf(cause)); } finally { setBusy(false); } }
  return <><button className="text-button" disabled={busy} onClick={() => void download('docx')}>DOCX</button><button className="text-button" disabled={busy} onClick={() => void download('pdf')}>PDF</button>{error && <Notice error>{error}</Notice>}</>;
}

function AnalysisHistory({ matter, record, onSource }: { matter: Matter; record: AnalysisRecord; onSource: (id: string) => void }) {
  const [history, setHistory] = useState<AnalysisVersion[]>([]); const [more, setMore] = useState(true); const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  async function load() { setBusy(true); setError(''); try { const page = await request<AnalysisVersion[]>(`/matters/${encodeURIComponent(matter.id)}/analyses/${encodeURIComponent(record.id)}/versions?limit=20&offset=${history.length}`); setHistory((old) => [...old, ...page]); setMore(page.length === 20); } catch (cause) { setError(messageOf(cause)); } finally { setBusy(false); } }
  return <Detail title="Değiştirilemez sürüm geçmişi">
    {history.map((version) => <Detail key={version.id} title={`Sürüm ${version.version} · ${formatDate(version.created_at, true)}`}><p><strong>Değişiklik gerekçesi:</strong> {version.change_note || 'İlk kayıt'}</p><AnalysisContentView content={version.content} freshness={version.freshness} onSource={onSource} /><AnalysisDownloads matterId={matter.id} recordId={record.id} versionId={version.id} /></Detail>)}
    {more && <button className="text-button" disabled={busy} onClick={() => void load()}>{busy ? 'Yükleniyor…' : history.length ? 'Önceki sürümleri getir' : 'Sürümleri getir'}</button>}{error && <Notice error>{error}</Notice>}
  </Detail>;
}

export default function AnalysisPanel({ matter, onChange }: { matter: Matter; onChange: () => Promise<void> }) {
  const [records, setRecords] = useState<AnalysisRecord[]>([]); const [editor, setEditor] = useState<AnalysisRecord | 'new' | null>(null); const [source, setSource] = useState<string | null>(null);
  const [busy, setBusy] = useState(true); const [more, setMore] = useState(false); const [error, setError] = useState(''); const [notice, setNotice] = useState('');
  const [freshnessRead, setFreshnessRead] = useState(0);
  const generation = useRef(0);
  const base = `/matters/${encodeURIComponent(matter.id)}/analyses`;
  const load = useCallback(async (signal?: AbortSignal) => { const turn = ++generation.current; setBusy(true); setError(''); try { const page = await request<AnalysisRecord[]>(`${base}?limit=20`, { signal }); if (generation.current === turn) { setRecords(page); setMore(page.length === 20); setFreshnessRead((value) => value + 1); } } catch (cause) { if (generation.current === turn && !signal?.aborted) { setError(messageOf(cause)); setRecords([]); } } finally { if (generation.current === turn) setBusy(false); } }, [base]);
  useEffect(() => { const controller = new AbortController(); void load(controller.signal); return () => { generation.current++; controller.abort(); }; }, [load, matter.facts]);
  async function refresh() { setError(''); try { await onChange(); await load(); } catch (cause) { setError(messageOf(cause)); } }
  async function nextPage() { const turn = ++generation.current; setBusy(true); setError(''); try { const page = await request<AnalysisRecord[]>(`${base}?limit=20&offset=${records.length}`); if (generation.current === turn) { setRecords((old) => [...old, ...page]); setMore(page.length === 20); } } catch (cause) { if (generation.current === turn) setError(messageOf(cause)); } finally { if (generation.current === turn) setBusy(false); } }
  return <Detail title={`Yapılandırılmış analiz taslakları (${records.length}${more ? '+' : ''})`}>
    <p>Bir meseleyi öncüller, kural adayları, koşullar, uygulama ve alternatiflerle inceleyin. Kaynaklar özel belge pasajlarıdır; kamu hukuku otoritesi ve otomatik hukuki sentez henüz doğrulanmaz.</p>
    <div className="practice-record-actions"><button className="button secondary" onClick={() => { setEditor('new'); setNotice(''); }}>Analiz taslağı oluştur</button><button className="text-button" disabled={busy} onClick={() => void refresh()}>Güncelliği kontrol et</button></div>
    {notice && <Notice>{notice}</Notice>}{error && <Notice error>{error}</Notice>}
    {editor && <AnalysisEditor key={editor === 'new' ? 'new' : editor.latest_version_id} matter={matter} record={editor === 'new' ? undefined : editor} onCancel={() => setEditor(null)} onSave={async () => { setEditor(null); setNotice('Analiz sürümü saklandı. Önceki içerik korunur; hukuki onay verilmez.'); await load(); await onChange(); }} />}
    {!records.length && !editor && !busy && <p className="practice-empty">Henüz analiz taslağı yok.</p>}{busy && !records.length && <Loading label="Analiz taslakları açılıyor…" />}
    {records.map((record) => <article className="practice-record" key={record.latest_version_id}><div className="practice-record-heading"><h3>{record.title}</h3><span className="small muted">Sürüm {record.version} · {record.status === 'stale' ? 'Güncelliğini yitirdi' : 'İnceleme gerekli'}</span></div><AnalysisContentView content={record} freshness={record.freshness} onSource={setSource} /><div className="practice-record-actions"><button className="text-button" onClick={() => setEditor(record)}>Yeni sürüm yaz</button><AnalysisDownloads matterId={matter.id} recordId={record.id} versionId={record.latest_version_id} /></div><AnalysisSuggestions matterId={matter.id} record={record} onSource={setSource} onAdopt={async () => { await onChange(); await load(); }} /><AnalysisHistory key={`${record.latest_version_id}:${freshnessRead}`} matter={matter} record={record} onSource={setSource} /></article>)}
    {more && <button className="button secondary" disabled={busy} onClick={() => void nextPage()}>Daha fazla analiz getir</button>}
    {source && <EvidenceViewer key={source} matter={matter} evidenceId={source} onClose={() => setSource(null)} />}
  </Detail>;
}
