import { lazy, Suspense, useCallback, useEffect, useId, useRef, useState } from 'react';
import { downloadAnalysis, request } from '../../api';
import { Badge, Detail, Field, Icon, Loading, Notice } from '../../components';
import type { Matter } from '../../types';
import { formatDate, messageOf } from '../../utils';
import { EvidenceViewer } from './FactsPanel';
import { AnalysisEditor } from './AnalysisEditor';
import { AnalysisContentView, AnalysisEvidence, AnalysisOverview } from './AnalysisView';
import { AnalysisSuggestions } from './AnalysisSuggestions';
import { AnalysisFocus } from './AnalysisFocus';
import { AnalysisComparisons } from './AnalysisComparisons';
import { AnalysisReviews, ReviewHistory, ReviewSummary } from './AnalysisReviews';
import type { AnalysisRecord, AnalysisVersion } from './analysisTypes';

const AuthorityModelTrials = lazy(() => import('./AuthorityModelTrials'));
function ModelTrialPanel({ matterId, record }: { matterId: string; record: AnalysisRecord }) {
  const [open, setOpen] = useState(false);
  return <Detail title="Kayıtlı yerel model dayanak denemeleri">{open ? <Suspense fallback={<Loading label="Denemeler açılıyor…" />}><AuthorityModelTrials matterId={matterId} analysisId={record.id} /></Suspense> : <button className="text-button" onClick={() => setOpen(true)}>Deneme geçmişi araçlarını aç</button>}</Detail>;
}

const AuthorityLineage = lazy(() => import('./AuthorityLineage'));
function LineagePanel({ matterId, record, onSaved }: { matterId: string; record: AnalysisRecord; onSaved: () => Promise<void> }) {
  const [open, setOpen] = useState(false);
  if (!record.authority_contributions?.length) return null;
  return <Detail title="Saklanan kaynak bağlarının yeniden incelenmesi">{open ? <Suspense fallback={<Loading label="Yeniden inceleme araçları açılıyor…" />}><AuthorityLineage matterId={matterId} analysisId={record.id} onSaved={onSaved} /></Suspense> : <button className="text-button" onClick={() => setOpen(true)}>Kaynak bağı yenileme araçlarını aç</button>}</Detail>;
}

const AnalysisAuthorities = lazy(() => import('./AnalysisAuthorities'));
const AnalysisSourceReviews = lazy(() => import('./AnalysisSourceReviews'));
function SourceReviewPanel({ matterId, record }: { matterId: string; record: AnalysisRecord }) {
  const [open, setOpen] = useState(false);
  return <Detail title="Kaynak seçimi ve bağımsız inceleme">{open ? <Suspense fallback={<Loading label="Kaynak incelemesi açılıyor…" />}><AnalysisSourceReviews matterId={matterId} record={record} /></Suspense>
    : <button className="text-button" onClick={() => setOpen(true)}>Kaynak seçimi ve bağımsız inceleme araçlarını aç</button>}</Detail>;
}
function AuthorityContextPanel({ matterId, record, onAdopt }: { matterId: string; record: AnalysisRecord; onAdopt?: () => Promise<void> }) {
  const [loaded, setLoaded] = useState(false);
  return <Detail title="Kamu dayanak bağlamları"><p className="small muted">Kaynak ilişkilerini bu özel analiz sürümüne açıkça bağlayın. Kaynak ve tarih incelemesi ayrıca gerekir.</p>{loaded ? <Suspense fallback={<Loading label="Dayanak bağlamı araçları açılıyor…" />}><AnalysisAuthorities matterId={matterId} record={record} onAdopt={onAdopt} /></Suspense> : <button className="text-button" onClick={() => setLoaded(true)}>Dayanak bağlamı araçlarını aç</button>}</Detail>;
}

function AnalysisDownloads({ matterId, recordId, versionId, onFailure }: { matterId: string; recordId: string; versionId: string; onFailure?: () => void }) {
  const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  async function download(format: 'docx' | 'pdf') { setBusy(true); setError(''); try { await downloadAnalysis(matterId, recordId, versionId, format); } catch (cause) { setError(messageOf(cause)); onFailure?.(); } finally { setBusy(false); } }
  return <><button className="text-button" disabled={busy} onClick={() => void download('docx')}>DOCX</button><button className="text-button" disabled={busy} onClick={() => void download('pdf')}>PDF</button>{error && <Notice error>{error}</Notice>}</>;
}

function AnalysisHistory({ matter, record, onSource, onFailure }: { matter: Matter; record: AnalysisRecord; onSource: (id: string) => void; onFailure?: () => void }) {
  const [history, setHistory] = useState<AnalysisVersion[]>([]); const [more, setMore] = useState(true); const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  async function load() { setBusy(true); setError(''); try { const page = await request<AnalysisVersion[]>(`/matters/${encodeURIComponent(matter.id)}/analyses/${encodeURIComponent(record.id)}/versions?limit=20&offset=${history.length}`); setHistory((old) => [...old, ...page]); setMore(page.length === 20); } catch (cause) { setHistory([]); setError(messageOf(cause)); onFailure?.(); } finally { setBusy(false); } }
  return <Detail title="Değiştirilemez sürüm geçmişi">
    {history.map((version) => <Detail key={version.id} title={`Sürüm ${version.version} · ${formatDate(version.created_at, true)}`}><p><strong>Değişiklik gerekçesi:</strong> {version.change_note || 'İlk kayıt'}</p><ReviewSummary review={version.review} onSource={onSource} /><AnalysisContentView content={version.content} freshness={version.freshness} review={version.review} onSource={onSource} /><AnalysisDownloads matterId={matter.id} recordId={record.id} versionId={version.id} onFailure={onFailure} /><ReviewHistory matterId={matter.id} analysisId={record.id} versionId={version.id} onSource={onSource} /></Detail>)}
    {more && <button className="text-button" disabled={busy} onClick={() => void load()}>{busy ? 'Yükleniyor…' : history.length ? 'Önceki sürümleri getir' : 'Sürümleri getir'}</button>}{error && <Notice error>{error}</Notice>}
  </Detail>;
}

export default function AnalysisPanel({ matter, onChange }: { matter: Matter; onChange: () => Promise<void> }) {
  const [records, setRecords] = useState<AnalysisRecord[]>([]); const [editor, setEditor] = useState<AnalysisRecord | 'new' | null>(null); const [source, setSource] = useState<string | null>(null);
  const [busy, setBusy] = useState(true); const [more, setMore] = useState(false); const [error, setError] = useState(''); const [notice, setNotice] = useState('');
  const [freshnessRead, setFreshnessRead] = useState(0);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const generation = useRef(0);
  const base = `/matters/${encodeURIComponent(matter.id)}/analyses`;
  const load = useCallback(async (signal?: AbortSignal) => { const turn = ++generation.current; setBusy(true); setError(''); try { const page = await request<AnalysisRecord[]>(`${base}?limit=20`, { signal }); if (generation.current === turn) { setRecords(page); setMore(page.length === 20); setFreshnessRead((value) => value + 1); } } catch (cause) { if (generation.current === turn && !signal?.aborted) { setError(messageOf(cause)); setRecords([]); setEditor(null); } } finally { if (generation.current === turn) setBusy(false); } }, [base]);
  useEffect(() => { const controller = new AbortController(); void load(controller.signal); return () => { generation.current++; controller.abort(); }; }, [load, matter.facts]);
  async function refresh() { setError(''); try { await onChange(); await load(); } catch (cause) { setError(messageOf(cause)); } }
  async function nextPage() { const turn = ++generation.current; setBusy(true); setError(''); try { const page = await request<AnalysisRecord[]>(`${base}?limit=20&offset=${records.length}`); if (generation.current === turn) { setRecords((old) => [...old, ...page]); setMore(page.length === 20); } } catch (cause) { if (generation.current === turn) { setError(messageOf(cause)); setRecords([]); setEditor(null); } } finally { if (generation.current === turn) setBusy(false); } }
  const selected = records.find((record) => record.id === selectedId) || records[0];
  return <section className="analysis-workspace" aria-label="Kayıtlı analizler">
    <div className="analysis-toolbar">
      <div><h2>Analizler</h2><p className="small muted">Taslağı okuyun, dayanaklarını açın ve değerlendirmenizi kaydedin.</p></div>
      <div className="button-group"><button className="text-button" disabled={busy} onClick={() => void refresh()}>Yenile</button><button className="button secondary" onClick={() => { setEditor('new'); setNotice(''); }}><Icon name="plus" size={16} />Yeni analiz</button></div>
    </div>
    {!!records.length && <Field label={`Kayıtlı analizler · ${records.length}${more ? '+' : ''}`} className="analysis-picker">{(id) => <select id={id} value={selected?.id || ''} onChange={(event) => setSelectedId(event.target.value)}>{records.map((record) => <option key={record.id} value={record.id}>{record.title} · Sürüm {record.version}</option>)}</select>}</Field>}
    {notice && <Notice>{notice}</Notice>}{error && <Notice error>{error}</Notice>}
    {editor && <AnalysisEditor key={editor === 'new' ? 'new' : editor.latest_version_id} matter={matter} record={editor === 'new' ? undefined : editor} onCancel={() => setEditor(null)} onSave={async () => { setEditor(null); setNotice('Analiz sürümü saklandı. Önceki içerik korunur; hukuki onay verilmez.'); await load(); await onChange(); }} />}
    {!records.length && !editor && !busy && <p className="practice-empty">Henüz analiz taslağı yok.</p>}{busy && !records.length && <Loading label="Analiz taslakları açılıyor…" />}
    {records.map((record) => <div key={`${record.latest_version_id}:${freshnessRead}`} hidden={record.id !== selected?.id}>
      <AnalysisWorkspace matter={matter} record={record} onSource={setSource} onEdit={() => setEditor(record)} onRefresh={refresh} onFailure={() => void load()} />
    </div>)}
    {more && <button className="button secondary" disabled={busy} onClick={() => void nextPage()}>Daha fazla analiz getir</button>}
    {source && <EvidenceViewer key={source} matter={matter} evidenceId={source} onClose={() => setSource(null)} />}
  </section>;
}

const ANALYSIS_SECTIONS = [
  { id: 'overview', label: 'Özet' },
  { id: 'evidence', label: 'Belgeler' },
  { id: 'review', label: 'İnceleme' },
  { id: 'history', label: 'Geçmiş' },
  { id: 'tools', label: 'Araçlar' },
] as const;
type AnalysisSection = typeof ANALYSIS_SECTIONS[number]['id'];

export function AnalysisWorkspace({ matter, record, onSource, onEdit, onRefresh, onFailure }: {
  matter: Matter; record: AnalysisRecord; onSource: (id: string) => void;
  onEdit: () => void; onRefresh: () => Promise<void>; onFailure: () => void;
}) {
  const id = useId();
  const [section, setSection] = useState<AnalysisSection>('overview');
  const [reviewOpened, setReviewOpened] = useState(false);
  const [toolsOpened, setToolsOpened] = useState(false);
  const nav = useRef<HTMLElement>(null);
  function selectSection(next: AnalysisSection) {
    setSection(next);
    if (next === 'review') setReviewOpened(true);
    if (next === 'tools') setToolsOpened(true);
  }
  const stale = record.status === 'stale' || record.freshness.status === 'stale' || record.review?.effective_state === 'stale';
  const changes = record.review?.latest?.decision === 'changes_requested';
  const reviewed = record.review?.effective_state === 'reviewed_conditional';
  const status = stale ? 'Yeniden inceleme gerekli' : changes ? 'Düzeltme istendi' : reviewed ? 'Koşullu olarak incelendi' : 'İncelemeniz bekleniyor';
  return <article className="analysis-reader">
    <header className="analysis-reader-header"><div><span className="small muted">Sürüm {record.version}</span><h3>{record.title}</h3></div><Badge status={stale || changes ? 'stale' : reviewed ? 'reviewed' : undefined}>{status}</Badge></header>
    {stale && <Notice error>Bu analizin dayanakları değişti. Güncel kaynakları ve önceki değerlendirmeyi inceleyerek yeni sürüm hazırlayın.</Notice>}
    <nav ref={nav} className="analysis-sections" role="tablist" aria-label="Analiz bölümleri" onKeyDown={(event) => {
      const index = ANALYSIS_SECTIONS.findIndex((item) => item.id === section);
      const next = event.key === 'ArrowRight' ? (index + 1) % ANALYSIS_SECTIONS.length : event.key === 'ArrowLeft' ? (index + ANALYSIS_SECTIONS.length - 1) % ANALYSIS_SECTIONS.length : event.key === 'Home' ? 0 : event.key === 'End' ? ANALYSIS_SECTIONS.length - 1 : null;
      if (next === null) return;
      event.preventDefault(); selectSection(ANALYSIS_SECTIONS[next].id);
      nav.current?.querySelectorAll<HTMLButtonElement>('[role="tab"]')[next]?.focus();
    }}>
      {ANALYSIS_SECTIONS.map((item) => <button key={item.id} id={`${id}-${item.id}-tab`} role="tab" aria-selected={section === item.id} aria-controls={`${id}-${item.id}-panel`} tabIndex={section === item.id ? 0 : -1} onClick={() => selectSection(item.id)}>{item.label}{item.id === 'evidence' && <span className="count">{record.evidence.length}</span>}</button>)}
    </nav>
    <section id={`${id}-overview-panel`} role="tabpanel" aria-labelledby={`${id}-overview-tab`} hidden={section !== 'overview'} tabIndex={0}>
      <div className="analysis-disposition"><span>{stale || changes || record.checks.effective_disposition === 'withheld' ? 'Sonuç bekletiliyor' : 'Koşullu taslak'}</span><span>{record.checks.critical_count > 0 ? `${record.checks.critical_count} kritik kontrol` : 'Hukuki değerlendirme incelemeye bağlı'}</span></div>
      <AnalysisOverview record={record} onSource={onSource} onReview={() => { selectSection('review'); nav.current?.querySelector<HTMLButtonElement>(`[id="${id}-review-tab"]`)?.focus(); }} />
    </section>
    <section id={`${id}-evidence-panel`} role="tabpanel" aria-labelledby={`${id}-evidence-tab`} hidden={section !== 'evidence'} tabIndex={0}>
      <h4 className="analysis-section-title">Analizde kullanılan belgeler</h4><AnalysisEvidence content={record} onSource={onSource} />
    </section>
    <section id={`${id}-review-panel`} role="tabpanel" aria-labelledby={`${id}-review-tab`} hidden={section !== 'review'} tabIndex={0}>
      {reviewOpened && <><ReviewSummary review={record.review} onSource={onSource} /><AnalysisReviews matterId={matter.id} record={record} onSource={onSource} onSaved={onRefresh} inline /></>}
    </section>
    <section id={`${id}-history-panel`} role="tabpanel" aria-labelledby={`${id}-history-tab`} hidden={section !== 'history'} tabIndex={0}>
      <h4 className="analysis-section-title">Sürümler ve inceleme kararları</h4>
      <ReviewHistory matterId={matter.id} analysisId={record.id} versionId={record.latest_version_id} onSource={onSource} />
      <AnalysisHistory matter={matter} record={record} onSource={onSource} onFailure={onFailure} />
    </section>
    <section id={`${id}-tools-panel`} role="tabpanel" aria-labelledby={`${id}-tools-tab`} hidden={section !== 'tools'} tabIndex={0}>
      {toolsOpened && <><h4 className="analysis-section-title">Analizi geliştirme araçları</h4>
      <button className="button secondary" onClick={onEdit}><Icon name="edit" size={16} />Yeni sürüm yaz</button>
      <AnalysisSuggestions matterId={matter.id} record={record} onSource={onSource} onAdopt={onRefresh} />
      <AnalysisFocus matterId={matter.id} record={record} onSource={onSource} onSaved={onRefresh} />
      <AnalysisComparisons matterId={matter.id} record={record} onSource={onSource} />
      <SourceReviewPanel matterId={matter.id} record={record} />
      <AuthorityContextPanel matterId={matter.id} record={record} onAdopt={onRefresh} />
      <ModelTrialPanel matterId={matter.id} record={record} />
      <LineagePanel matterId={matter.id} record={record} onSaved={onRefresh} /></>}
    </section>
    <footer className="analysis-export"><span className="small muted">Bu sürümü indir</span><AnalysisDownloads matterId={matter.id} recordId={record.id} versionId={record.latest_version_id} onFailure={onFailure} /></footer>
  </article>;
}
