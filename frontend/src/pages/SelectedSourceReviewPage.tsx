import { useEffect, useRef, useState } from 'react';
import { request } from '../api';
import { Detail, Loading, Notice, PageHeader } from '../components';
import { formatDate, messageOf } from '../utils';
import { usePortfolio, workspaceQuery } from '../workbench/portfolio';
import AnalysisSourceReviews, { type SourceSaveReceipt } from './matter/AnalysisSourceReviews';
import { SourceReadFence } from './matter/sourceReviewTypes';
import { sourceContextHref, verifyNavigation, type NavigationMetadata, type SourceSelection, type SourceTarget } from './sourceContextNavigationTypes';

import { departingReturn, queueReturnHref, returnMatches, type ReturnIntent } from '../workbench/portfolioReturn';
import { verifyReturnSelection } from '../workbench/returnComparison';

import SourceReviewLineagePanel from './SourceReviewLineagePanel';
import { verifyReviewLineage, type ReviewLineage } from './sourceReviewLineageTypes';

const ADMISSION = { complete: 'Tamamlandı', pending: 'Son izin kontrolü bekliyor', unavailable: 'Doğrulanamadı', unknown: 'Bilinmiyor', not_recorded: 'Henüz karar yok' };
const REVIEW = { unknown: 'Doğrulanamadı', unreviewed: 'Henüz kaydedilmedi', changes_requested: 'Değişiklik istendi', reviewed_conditional: 'Koşullu inceleme kaydedildi' };
export function NavigationSummary({ value, historicalSelection = false }: { value: NavigationMetadata; historicalSelection?: boolean }) {
  return <section aria-label="Tam kaynak bağlamı kimliği">
    <p className="small muted">Gözlem: {formatDate(value.observed_at, true)}. Bu ekran yalnızca özel kayıt kimliğini doğrular. Kamu kaynakları kontrol edilmedi; saklanan karar güncel izin veya hukuki onay değildir.</p>
    <Detail title="Seçilen kayıt ve sürümler" open={!historicalSelection}>
      <p className="reference-id">Çalışma alanı: {value.matter_id}</p><p className="reference-id">Analiz: {value.analysis_id}</p><p className="reference-id">Bağlam: {value.context_id}</p>
      <p className="reference-id">Sabit analiz sürümü: {value.context.version_id || 'Doğrulanamadı'}</p><p className="reference-id">Mevcut son sürüm: {value.analysis.current_version_id || 'Doğrulanamadı'}</p>
      <p>{value.version_relation === 'different' ? 'Sabit kayıt başka bir analiz sürümüne aittir. Son sürüme taşınmaz; yenileme ve yeni bağımsız inceleme ayrıca gerekir.' : value.version_relation === 'same' ? 'Sabit sürüm ve mevcut son sürüm kimlikleri aynı. İçeriğin güncelliği ayrıca kontrol edilir.' : 'Sürüm ilişkisi doğrulanamadı.'}</p>
      <p>{historicalSelection ? 'Bağlamın gözlenen son karar başı' : 'Saklanan bağımsız karar'}: {REVIEW[value.historical_review.state]}{value.historical_review.recorded_at && ` · ${formatDate(value.historical_review.recorded_at, true)}`}</p>
      {value.historical_review.id && <p className="reference-id">Karar kaydı: {value.historical_review.id}</p>}
      <p>Kayıt kabulü: {ADMISSION[value.admission.context_state]}. Bu gözlem bekleyen kabulü tamamlamaz.</p><p>Karar kabulü: {ADMISSION[value.admission.review_state]}.</p>
    </Detail>
  </section>;
}
function SelectedWorkspace({ target, blocked, revision, returnIntent }: { target: SourceTarget; blocked: boolean; revision: number; returnIntent: ReturnIntent | null }) {
  const { returns } = usePortfolio();
  const [value, setValue] = useState<NavigationMetadata | null>(null); const [error, setError] = useState('');
  const [lineage, setLineage] = useState<ReviewLineage | null>(null);
  const [receipt, setReceipt] = useState<SourceSaveReceipt | null>(null);
  const [busy, setBusy] = useState(false); const [tools, setTools] = useState(false); const [generation, setGeneration] = useState(0);
  const fence = useRef(new SourceReadFence());
  function clear(cause?: unknown) { fence.current.invalidate(); setValue(null); setLineage(null); setTools(false); setBusy(false); setGeneration(old => old + 1); setError(cause ? messageOf(cause) : ''); if (cause) setReceipt(null); }
  async function load(keepReceipt = false) {
    if (blocked) return; if (!keepReceipt) setReceipt(null); clear(); const task = fence.current.begin(); setBusy(true);
    try {
      const base = `/matters/${encodeURIComponent(target.matter_id)}/analyses/${encodeURIComponent(target.analysis_id)}/source-contexts/${encodeURIComponent(target.context_id)}`;
      if (target.review_id) {
        const result = await request<ReviewLineage>(`${base}/reviews/${encodeURIComponent(target.review_id)}/navigation-context`, { signal: task.signal });
        verifyReviewLineage(result, target); if (returnIntent) verifyReturnSelection(returnIntent, result.context_navigation, result, target.review_id);
        if (task.current()) { setValue(result.context_navigation); setLineage(result); }
      } else {
        const result = await request<NavigationMetadata>(`${base}/navigation-context`, { signal: task.signal });
        verifyNavigation(result, target); if (returnIntent) verifyReturnSelection(returnIntent, result, null);
        if (task.current()) setValue(result);
      }
    } catch (cause) { if (task.current()) clear(cause); } finally { if (task.current()) setBusy(false); }
  }
  useEffect(() => { const gate = fence.current; if (blocked) clear(); else void load(true); return () => gate.invalidate(); }, [blocked, revision]);
  return <><PageHeader eyebrow="ÖZEL KAYNAK İNCELEMESİ" title={target.review_id ? 'Seçilen tarihsel inceleme' : 'Seçilen kaynak bağlamı'} description="Tam çalışma alanı, analiz ve değiştirilemez kaynak kaydı üzerinden güvenli incelemeye devam edin." />
    <a className="text-link" href={queueReturnHref(target.return_token)!} onClick={event => {
      if (!returnIntent) return;
      event.preventDefault();
      try { const token = returns.put(departingReturn(returnIntent, value, lineage, target.review_id)); window.location.hash = queueReturnHref(token)!; }
      catch (cause) { clear(cause); }
    }}>Portföy kaynak kuyruğuna dön</a>
    {error && <Notice error>{error} Kimlik, erişim ve kayıt yeniden doğrulanmadan incelemeye devam edilemez.</Notice>}
    <div className="practice-record-actions"><button className="button secondary" disabled={busy || blocked} onClick={() => void load()}>Tam kayıt kimliğini yeniden doğrula</button></div>
    {busy && <Loading label="Seçilen kayıt kimliği doğrulanıyor…" />}
    {value && !blocked && <>{receipt && <Notice>{receipt.state === 'pending' ? 'Kayıt saklandı; son izin kontrolü tamamlanamadı. Kabul ve bağımsız inceleme ayrıca gerekir.' : 'Kayıt saklandı; tam kimlik gözlemi güncellendi. İnceleme araçlarını yeniden açın.'}<p className="reference-id">Kayıt: {receipt.id}</p>{receipt.kind === 'context' && sourceContextHref(target.matter_id, target.analysis_id, receipt.id) && <a className="text-link" href={sourceContextHref(target.matter_id, target.analysis_id, receipt.id)!}>Yeni bağlamın tam kimliğini aç</a>}</Notice>}{lineage && <SourceReviewLineagePanel value={lineage} returnToken={target.return_token} />}<NavigationSummary value={value} historicalSelection={!!lineage} />
      {!(lineage ? lineage.tools_available : value.tools_available) ? <Notice error>Sabit bağlam, sürüm veya tarihsel karar bağları doğrulanamadı. İnceleme araçları kapalı; başka kayıt seçilmez.</Notice> : tools ? <AnalysisSourceReviews key={generation} matterId={target.matter_id} record={{ id: target.analysis_id, latest_version_id: value.analysis.current_version_id! }}
        selectedContext={{ id: target.context_id, manifest_sha256: value.context.manifest_sha256!, version_id: value.context.version_id! }} returnToken={target.return_token} selectedReview={lineage ? { id: lineage.selected_review.id, packet_sha256: lineage.selected_review.packet_sha256! } : undefined} onFailure={clear} onCommitted={saved => { setReceipt(saved); window.dispatchEvent(new Event('portfolio-updated')); }} />
        : <button className="button secondary" onClick={() => setTools(true)}>{target.review_id ? 'Seçilen tarihsel kararın inceleme araçlarını aç' : 'Seçilen kaydın inceleme araçlarını aç'}</button>}
    </>}
  </>;
}
export default function SelectedSourceReviewPage({ selection }: { selection: SourceSelection }) {
  const { filters, revision, loading, error, returns } = usePortfolio();
  const [expired, setExpired] = useState(false);
  const token = selection.kind === 'selected' ? selection.return_token : undefined;
  useEffect(() => { setExpired(false); if (!token) return; const timer = setTimeout(() => setExpired(true), returns.remaining(token)); return () => clearTimeout(timer); }, [token, returns]);
  const intent = token ? returns.get(token) : null;
  if (selection.kind !== 'selected') return <Notice error>Kaynak bağlamı bağlantısı eksik veya belirsiz. Portföy kuyruğundan tam kaydı yeniden seçin. <a href="#/work">İşlerime dön</a></Notice>;
  if (token && (expired || !intent || !returnMatches(intent, selection))) return <Notice error>Portföy dönüş bağı yok, süresi doldu veya başka kayda ait. İçerik açılmadı. <a href={queueReturnHref()!}>Yeni kaynak kuyruğunu açıkça hazırla</a></Notice>;
  return <SelectedWorkspace returnIntent={intent} key={`${selection.matter_id}:${selection.analysis_id}:${selection.context_id}:${selection.review_id}:${workspaceQuery(filters)}`} target={selection} revision={revision} blocked={loading || !!error} />;
}
