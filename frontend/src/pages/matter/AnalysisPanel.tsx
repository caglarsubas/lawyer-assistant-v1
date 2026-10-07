import { useCallback, useEffect, useRef, useState } from 'react';
import { downloadAnalysis, request } from '../../api';
import { Badge, Detail, Loading, Notice } from '../../components';
import type { Matter } from '../../types';
import { FACT_LABELS, formatDate, locatorText, messageOf } from '../../utils';
import { EvidenceViewer } from './FactsPanel';
import { AnalysisEditor } from './AnalysisEditor';
import type { AnalysisChecks, AnalysisContent, AnalysisFreshness, AnalysisRecord, AnalysisVersion } from './analysisTypes';

export const ANALYSIS_LABELS: Record<string, string> = {
  fact: 'Olgu defterinden', assumption: 'Varsayım', unknown: 'Bilinmeyen',
  contract_clause: 'Sözleşme maddesi adayı', legal_norm: 'Mevzuat kuralı adayı · otorite doğrulanmadı',
  element: 'Koşul', exception: 'İstisna', jurisdiction: 'Yetki', burden: 'İspat yükü',
  met: 'Karşılanıyor', not_met: 'Karşılanmıyor',
  adverse_argument: 'Karşı argüman', alternative_classification: 'Alternatif sınıflandırma',
  material_distinction: 'Maddi ayrım', search_gap: 'Araştırma boşluğu',
  supported_candidate: 'Daha güçlü sonuç talebi · doğrulanmadı', conditional: 'Koşullu taslak', withheld: 'Sonuç bekletiliyor',
};

export function AnalysisCheckPanel({ checks, freshness }: { checks: AnalysisChecks; freshness?: AnalysisFreshness }) {
  const disposition = freshness?.status === 'stale' ? 'withheld' : checks.effective_disposition;
  return <div>
    <div className="practice-record-heading"><Badge>{ANALYSIS_LABELS[disposition]}</Badge><span className="small muted">{checks.critical_count} kritik kontrol · Hukuki onay verilmedi</span></div>
    {freshness?.status === 'stale' && <Notice error>Dayanaklar değişti. Önceki metin korunuyor; yeni sürümde inceleyin.{freshness.reasons.map((reason) => <p key={reason}>{reason}</p>)}</Notice>}
    <Detail title={`Kontrol ayrıntıları (${checks.defects.length})`}>
      <p className="small muted">Kontroller beyan edilen bağlantıları ve koşulları inceler. Pasajın yorumu, çıkarımın doğruluğu ve hukuki uygulanabilirlik avukat incelemesi gerektirir.</p>
      <ul>{checks.defects.map((defect) => <li key={defect.id}><strong>{defect.severity === 'critical' ? 'Kritik' : 'İnceleme'} · {defect.target_id}:</strong> {defect.message}</li>)}</ul>
    </Detail>
  </div>;
}

export function AnalysisContentView({ content, freshness, onSource }: { content: AnalysisContent; freshness?: AnalysisFreshness; onSource: (id: string) => void }) {
  const facts = new Map(content.fact_snapshots.map((fact) => [fact.id, fact]));
  return <>
    <p className="authored-text"><strong>Mesele:</strong> {content.issue}</p>
    <AnalysisCheckPanel checks={content.checks} freshness={freshness} />
    <Detail title="Öncül → kural → uygulama → alternatif → geçici sonuç">
      <p className="small muted">Avukat tarafından yazılmış gerekçe. Otomatik hukuki sonuç veya modelin düşünce kaydı değildir.</p>
      <p><strong>Süreç:</strong> {content.posture || 'Belirtilmedi'} · <strong>Olay tarihi:</strong> {content.event_date || 'Bilinmiyor'}</p>
      <h4>Öncüller</h4>{content.premises.map((item) => { const fact = facts.get(item.fact_id || ''); return <div key={item.id}><p className="authored-text"><strong>{item.id} · {fact ? FACT_LABELS[fact.status as keyof typeof FACT_LABELS] || fact.status : ANALYSIS_LABELS[item.kind]}:</strong> {fact?.text || item.text}</p>{fact?.evidence_id && <button className="source-link" onClick={() => onSource(fact.evidence_id!)}>Öncülün özgün dayanağı</button>}</div>; })}
      <h4>Kural adayları ve koşullar</h4>{content.rules.map((rule) => <div key={rule.id}><p className="authored-text"><strong>{rule.id} · {ANALYSIS_LABELS[rule.kind]}:</strong> {rule.text}</p><ul>{rule.conditions.map((item) => <li key={item.id}>{item.id} · {ANALYSIS_LABELS[item.kind]}: {item.text} · Gereken durum: {ANALYSIS_LABELS[item.required_status]}</li>)}</ul><p className="reference-id">Dayanaklar: {rule.evidence_ids.join(', ') || 'Bağlanmadı'}</p></div>)}
      <h4>Uygulama</h4>{content.applications.map((item) => <div key={item.id}><p className="authored-text"><strong>{item.id} · {item.rule_id} / {item.premise_ids.join(', ') || 'Öncül yok'}:</strong> {item.rationale}</p><ul>{item.assessments.map((assessment) => <li key={assessment.condition_id}>{assessment.condition_id}: {ANALYSIS_LABELS[assessment.status]} · Öncüller: {assessment.premise_ids.join(', ') || 'Bağlanmadı'}</li>)}</ul></div>)}
      <h4>Alternatifler</h4>{content.alternatives.map((item) => <p className="authored-text" key={item.id}><strong>{item.id} · {ANALYSIS_LABELS[item.kind]}:</strong> {item.text} <span className="reference-id">{item.evidence_ids.join(', ')}</span></p>)}
      <h4>Avukatın geçici sonuç metni</h4><p className="authored-text">{content.conclusion.text}</p><p className="small muted">Talep edilen değerlendirme: {ANALYSIS_LABELS[content.conclusion.requested_disposition]}. Kontrol sonucu yukarıda ayrıca gösterilir.</p><p className="reference-id">Uygulamalar: {content.conclusion.application_ids.join(', ') || 'Bağlanmadı'} · Alternatifler: {content.conclusion.alternative_ids.join(', ') || 'Bağlanmadı'}</p>
      <ul>{content.conclusion.uncertainty.map((item, index) => <li key={index}>{item}</li>)}</ul><p><strong>Sonraki adım:</strong> {content.conclusion.next_step}</p>
    </Detail>
    <Detail title={`Özgün belge alıntıları (${content.evidence.length})`}>
      <p className="small muted">Unicode aralıkları sıfırdan başlar; son konum dahil değildir. Bir pasaj bağlamak, yazdığınız yorumun o pasajdan çıktığını kanıtlamaz.</p>
      <p className="small muted">Alıntılar saklanan sürümdendir. Kaynak düğmesi belgenin güncel görünümünü açar; değişmişse saklanan metinle karşılaştırın.</p>
      {content.evidence.map((item) => <div key={item.evidence_id}><button className="source-link" onClick={() => onSource(item.evidence_id)}>{item.name} · {locatorText(item.locator)} · Özgün pasajı aç</button><p className="small muted">[{item.start}, {item.end}) / {item.full_passage_length}</p><p className="authored-text">{item.text}</p></div>)}
    </Detail>
    {content.revision_comparison.previous_version_id && <Detail title="Önceki sürüme göre değişiklikler"><p>Değişen bölümler: {content.revision_comparison.changed_sections.join(', ') || 'Yok'} · Değişen dayanak grupları: {content.revision_comparison.changed_dependency_groups.join(', ') || 'Yok'}</p><p>{content.revision_comparison.checks_no_longer_triggered.length} kontrol artık tetiklenmiyor; {content.revision_comparison.new_check_ids.length} yeni kontrol.</p><p className="small muted">Bu karşılaştırma, bir hukuki kusurun düzeltildiğini veya kaldırılan bir adımın gereksiz olduğunu doğrulamaz.</p></Detail>}
  </>;
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
    {records.map((record) => <article className="practice-record" key={record.latest_version_id}><div className="practice-record-heading"><h3>{record.title}</h3><span className="small muted">Sürüm {record.version} · {record.status === 'stale' ? 'Güncelliğini yitirdi' : 'İnceleme gerekli'}</span></div><AnalysisContentView content={record} freshness={record.freshness} onSource={setSource} /><div className="practice-record-actions"><button className="text-button" onClick={() => setEditor(record)}>Yeni sürüm yaz</button><AnalysisDownloads matterId={matter.id} recordId={record.id} versionId={record.latest_version_id} /></div><AnalysisHistory key={`${record.latest_version_id}:${freshnessRead}`} matter={matter} record={record} onSource={setSource} /></article>)}
    {more && <button className="button secondary" disabled={busy} onClick={() => void nextPage()}>Daha fazla analiz getir</button>}
    {source && <EvidenceViewer key={source} matter={matter} evidenceId={source} onClose={() => setSource(null)} />}
  </Detail>;
}
