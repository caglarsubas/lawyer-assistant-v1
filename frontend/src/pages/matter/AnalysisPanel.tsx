import { lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react';
import { downloadAnalysis, request } from '../../api';
import { Detail, Loading, Notice } from '../../components';
import type { Matter } from '../../types';
import { formatDate, messageOf } from '../../utils';
import { EvidenceViewer } from './FactsPanel';
import { AnalysisEditor } from './AnalysisEditor';
import { AnalysisContentView } from './AnalysisView';
import { AnalysisSuggestions } from './AnalysisSuggestions';
import { AnalysisComparisons } from './AnalysisComparisons';
import { AnalysisReviews, ReviewHistory, ReviewSummary } from './AnalysisReviews';
import type { AnalysisRecord, AnalysisVersion } from './analysisTypes';

const AnalysisAuthorities = lazy(() => import('./AnalysisAuthorities'));
function AuthorityContextPanel({ matterId, record }: { matterId: string; record: AnalysisRecord }) {
  const [loaded, setLoaded] = useState(false);
  return <Detail title="Kamu dayanak bağlamları"><p className="small muted">Kaynak ilişkilerini bu özel analiz sürümüne açıkça bağlayın. Kaynak ve tarih incelemesi ayrıca gerekir.</p>{loaded ? <Suspense fallback={<Loading label="Dayanak bağlamı araçları açılıyor…" />}><AnalysisAuthorities matterId={matterId} record={record} /></Suspense> : <button className="text-button" onClick={() => setLoaded(true)}>Dayanak bağlamı araçlarını aç</button>}</Detail>;
}

function AnalysisDownloads({ matterId, recordId, versionId }: { matterId: string; recordId: string; versionId: string }) {
  const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  async function download(format: 'docx' | 'pdf') { setBusy(true); setError(''); try { await downloadAnalysis(matterId, recordId, versionId, format); } catch (cause) { setError(messageOf(cause)); } finally { setBusy(false); } }
  return <><button className="text-button" disabled={busy} onClick={() => void download('docx')}>DOCX</button><button className="text-button" disabled={busy} onClick={() => void download('pdf')}>PDF</button>{error && <Notice error>{error}</Notice>}</>;
}

function AnalysisHistory({ matter, record, onSource }: { matter: Matter; record: AnalysisRecord; onSource: (id: string) => void }) {
  const [history, setHistory] = useState<AnalysisVersion[]>([]); const [more, setMore] = useState(true); const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  async function load() { setBusy(true); setError(''); try { const page = await request<AnalysisVersion[]>(`/matters/${encodeURIComponent(matter.id)}/analyses/${encodeURIComponent(record.id)}/versions?limit=20&offset=${history.length}`); setHistory((old) => [...old, ...page]); setMore(page.length === 20); } catch (cause) { setError(messageOf(cause)); } finally { setBusy(false); } }
  return <Detail title="Değiştirilemez sürüm geçmişi">
    {history.map((version) => <Detail key={version.id} title={`Sürüm ${version.version} · ${formatDate(version.created_at, true)}`}><p><strong>Değişiklik gerekçesi:</strong> {version.change_note || 'İlk kayıt'}</p><ReviewSummary review={version.review} onSource={onSource} /><AnalysisContentView content={version.content} freshness={version.freshness} review={version.review} onSource={onSource} /><AnalysisDownloads matterId={matter.id} recordId={record.id} versionId={version.id} /><ReviewHistory matterId={matter.id} analysisId={record.id} versionId={version.id} onSource={onSource} /></Detail>)}
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
    <p>Bir meseleyi öncüller, kural adayları, koşullar, uygulama ve alternatiflerle inceleyin. Özel belge pasajlarını ve ayrı kamu dayanak bağlamlarını inceleyin; hukuki uygulanabilirlik ve otomatik sentez henüz doğrulanmaz.</p>
    <div className="practice-record-actions"><button className="button secondary" onClick={() => { setEditor('new'); setNotice(''); }}>Analiz taslağı oluştur</button><button className="text-button" disabled={busy} onClick={() => void refresh()}>Güncelliği kontrol et</button></div>
    {notice && <Notice>{notice}</Notice>}{error && <Notice error>{error}</Notice>}
    {editor && <AnalysisEditor key={editor === 'new' ? 'new' : editor.latest_version_id} matter={matter} record={editor === 'new' ? undefined : editor} onCancel={() => setEditor(null)} onSave={async () => { setEditor(null); setNotice('Analiz sürümü saklandı. Önceki içerik korunur; hukuki onay verilmez.'); await load(); await onChange(); }} />}
    {!records.length && !editor && !busy && <p className="practice-empty">Henüz analiz taslağı yok.</p>}{busy && !records.length && <Loading label="Analiz taslakları açılıyor…" />}
    {records.map((record) => <article className="practice-record" key={record.latest_version_id}><div className="practice-record-heading"><h3>{record.title}</h3><span className="small muted">Sürüm {record.version} · {record.status === 'stale' ? 'Güncelliğini yitirdi' : record.review?.latest ? 'İnceleme kararı kayıtlı' : 'İnceleme gerekli'}</span></div><ReviewSummary review={record.review} onSource={setSource} /><AnalysisContentView content={record} freshness={record.freshness} review={record.review} onSource={setSource} /><div className="practice-record-actions"><button className="text-button" onClick={() => setEditor(record)}>Yeni sürüm yaz</button><AnalysisDownloads matterId={matter.id} recordId={record.id} versionId={record.latest_version_id} /></div><AnalysisReviews key={`review:${record.latest_version_id}:${freshnessRead}`} matterId={matter.id} record={record} onSource={setSource} onSaved={async () => { await onChange(); await load(); }} /><AnalysisSuggestions matterId={matter.id} record={record} onSource={setSource} onAdopt={async () => { await onChange(); await load(); }} /><AnalysisComparisons key={`comparisons:${record.latest_version_id}:${freshnessRead}`} matterId={matter.id} record={record} onSource={setSource} /><AuthorityContextPanel key={`authorities:${record.latest_version_id}:${freshnessRead}`} matterId={matter.id} record={record} /><AnalysisHistory key={`${record.latest_version_id}:${freshnessRead}`} matter={matter} record={record} onSource={setSource} /></article>)}
    {more && <button className="button secondary" disabled={busy} onClick={() => void nextPage()}>Daha fazla analiz getir</button>}
    {source && <EvidenceViewer key={source} matter={matter} evidenceId={source} onClose={() => setSource(null)} />}
  </Detail>;
}
