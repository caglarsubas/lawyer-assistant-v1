import { captureCarriedDestinationReturn } from '../workbench/carriedDestinationReturn';
import { compareCarriedArrivalEventDestination, validateCarriedArrivalEventHandoff, type CarriedArrivalEventHandoff } from '../workbench/carriedArrivalEventHandoff';
import CarriedArrivalEventDestinationPanel from './CarriedArrivalEventDestinationPanel';
import { useEffect, useRef, useState } from 'react';
import { compareOnwardEventDestination, validateOnwardEventHandoff, type OnwardEventHandoff } from '../workbench/onwardEventHandoff';
import { captureCarriedArrivalReturn } from '../workbench/carriedArrivalReturn';
import OnwardEventDestinationPanel from './OnwardEventDestinationPanel';
import { request } from '../api';
import { Detail, Loading, Notice, PageHeader } from '../components';
import { formatDate, messageOf } from '../utils';
import { usePortfolio, workspaceQuery } from '../workbench/portfolio';
import AnalysisSourceReviews, { type SourceSaveReceipt } from './matter/AnalysisSourceReviews';
import { SourceReadFence } from './matter/sourceReviewTypes';
import { sourceContextHref, verifyNavigation, type NavigationMetadata, type SourceSelection, type SourceTarget } from './sourceContextNavigationTypes';

import { departingReturn, queueReturnHref, returnMatches, type ReturnIntent } from '../workbench/portfolioReturn';
import { verifyReturnedEventTarget } from '../workbench/returnedReviewLineage';
import { verifyReturnSelection } from '../workbench/returnComparison';
import { compareReviewPathHandoff, validateReviewPathHandoff, type ReviewPathHandoff } from '../workbench/reviewPathHandoff';
import ReviewPathIdentityComparison from './ReviewPathIdentityComparison';
import { captureComparisonReturn } from '../workbench/comparisonReturn';
import { compareComparisonEventArrival, validateComparisonEventHandoff, type ComparisonEventHandoff } from '../workbench/comparisonEventHandoff';
import { captureArrivalReturn } from '../workbench/arrivalReturn';
import { compareArrivalEventDestination, validateArrivalEventHandoff, type ArrivalEventHandoff } from '../workbench/arrivalEventHandoff';
import { captureOnwardReturn } from '../workbench/onwardReturn';
import ArrivalEventDestinationPanel from './ArrivalEventDestinationPanel';
import ComparisonEventArrivalPanel from './ComparisonEventArrivalPanel';

import SourceReviewLineagePanel from './SourceReviewLineagePanel';
import { verifyReviewLineage, type ReviewLineage } from './sourceReviewLineageTypes';
import ComparisonRenewalPage from './ComparisonRenewalPage';
import IndependentReviewPreparationPage from './IndependentReviewPreparationPage';
import { independentReviewIntent, reviewPreparationHref } from '../workbench/renewalLineageNavigation';

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
function SelectedWorkspace({ target, blocked, revision, returnIntent, pathHandoff, comparisonHandoff, arrivalHandoff, onwardHandoff, carriedHandoff }: { carriedHandoff: CarriedArrivalEventHandoff | null; onwardHandoff: OnwardEventHandoff | null; arrivalHandoff: ArrivalEventHandoff | null; comparisonHandoff: ComparisonEventHandoff | null; pathHandoff: ReviewPathHandoff | null; target: SourceTarget; blocked: boolean; revision: number; returnIntent: ReturnIntent | null }) {
  const { returns } = usePortfolio();
  const pathLocked = pathHandoff !== null || comparisonHandoff !== null || arrivalHandoff !== null || onwardHandoff !== null || carriedHandoff !== null;
  const [value, setValue] = useState<NavigationMetadata | null>(null); const [error, setError] = useState('');
  const [lineage, setLineage] = useState<ReviewLineage | null>(null);
  const [observedRevision, setObservedRevision] = useState(-1);
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
        if (pathHandoff && returnIntent) compareReviewPathHandoff(returnIntent, pathHandoff, result);
        if (carriedHandoff && returnIntent) compareCarriedArrivalEventDestination(returnIntent, carriedHandoff, target, result);
        if (onwardHandoff && returnIntent) compareOnwardEventDestination(returnIntent, onwardHandoff, target, result);
        if (arrivalHandoff && returnIntent) compareArrivalEventDestination(returnIntent, arrivalHandoff, target, result);
        if (comparisonHandoff && returnIntent) compareComparisonEventArrival(returnIntent, comparisonHandoff, target, result);
        if (task.current()) { setValue(result.context_navigation); setLineage(result); setObservedRevision(revision); }
      } else {
        const result = await request<NavigationMetadata>(`${base}/navigation-context`, { signal: task.signal });
        verifyNavigation(result, target); if (returnIntent) verifyReturnSelection(returnIntent, result, null);
        if (task.current()) { setValue(result); setObservedRevision(revision); }
      }
    } catch (cause) { if (task.current()) clear(cause); } finally { if (task.current()) setBusy(false); }
  }
  useEffect(() => { const gate = fence.current; if (blocked) clear(); else void load(true); return () => gate.invalidate(); }, [blocked, revision]);
  return <><PageHeader eyebrow="ÖZEL KAYNAK İNCELEMESİ" title={target.review_id ? 'Seçilen tarihsel inceleme' : 'Seçilen kaynak bağlamı'} description="Tam çalışma alanı, analiz ve değiştirilemez kaynak kaydı üzerinden güvenli incelemeye devam edin." />
    <a className="text-link" href={queueReturnHref(target.return_token)!} onClick={event => {
      if (!returnIntent) return;
      event.preventDefault();
      try {
        if (!target.return_token || !returns.get(target.return_token)) throw new Error('Dönüş bağı artık geçerli değil.');
        let token: string;
        if (carriedHandoff) {
          const available = !blocked && !busy && observedRevision === revision;
          const next = captureCarriedDestinationReturn(returnIntent, carriedHandoff, target, available ? value : null, available ? lineage : null);
          token = next.observation ? returns.putCarriedDestinationReturn(next.intent, next.observation) : returns.put(next.intent);
        } else if (onwardHandoff) {
          const available = !blocked && !busy && observedRevision === revision;
          const next = captureCarriedArrivalReturn(returnIntent, onwardHandoff, target, available ? value : null, available ? lineage : null);
          token = next.observation ? returns.putCarriedArrivalReturn(next.intent, next.observation) : returns.put(next.intent);
        } else if (arrivalHandoff) {
          const available = !blocked && !busy && observedRevision === revision;
          const next = captureOnwardReturn(returnIntent, arrivalHandoff, target, available ? value : null, available ? lineage : null);
          token = next.observation ? returns.putOnwardReturn(next.intent, next.observation) : returns.put(next.intent);
        } else if (comparisonHandoff) {
          const available = !blocked && !busy && observedRevision === revision;
          const next = captureArrivalReturn(returnIntent, comparisonHandoff, target, available ? value : null, available ? lineage : null);
          token = next.observation ? returns.putArrivalReturn(next.intent, next.observation) : returns.put(next.intent);
        } else if (pathHandoff) {
          const available = !blocked && !busy && observedRevision === revision;
          const next = captureComparisonReturn(returnIntent, pathHandoff, target, available ? value : null, available ? lineage : null);
          token = next.receipt ? returns.putComparisonReturn(next.intent, next.receipt) : returns.put(next.intent);
        } else token = returns.put(departingReturn(returnIntent, value, lineage, target.review_id));
        window.location.hash = queueReturnHref(token)!;
      }
      catch (cause) { clear(cause); }
    }}>Portföy kaynak kuyruğuna dön</a>
    {error && <Notice error>{error} Kimlik, erişim ve kayıt yeniden doğrulanmadan incelemeye devam edilemez.</Notice>}
    <div className="practice-record-actions"><button className="button secondary" disabled={busy || blocked} onClick={() => void load()}>Tam kayıt kimliğini yeniden doğrula</button></div>
    {busy && <Loading label="Seçilen kayıt kimliği doğrulanıyor…" />}
    {value && observedRevision === revision && !blocked && <>{receipt && <Notice>{receipt.state === 'pending' ? 'Kayıt saklandı; son izin kontrolü tamamlanamadı. Kabul ve bağımsız inceleme ayrıca gerekir.' : 'Kayıt saklandı; tam kimlik gözlemi güncellendi. İnceleme araçlarını yeniden açın.'}<p className="reference-id">Kayıt: {receipt.id}</p>{receipt.kind === 'context' && sourceContextHref(target.matter_id, target.analysis_id, receipt.id) && <a className="text-link" href={sourceContextHref(target.matter_id, target.analysis_id, receipt.id)!}>Yeni bağlamın tam kimliğini aç</a>}</Notice>}{lineage && pathHandoff && returnIntent && <ReviewPathIdentityComparison value={compareReviewPathHandoff(returnIntent, pathHandoff, lineage)} />}
      {lineage && carriedHandoff && returnIntent && <CarriedArrivalEventDestinationPanel handoff={carriedHandoff} value={compareCarriedArrivalEventDestination(returnIntent, carriedHandoff, target, lineage)} />}
      {lineage && onwardHandoff && returnIntent && <OnwardEventDestinationPanel handoff={onwardHandoff} value={compareOnwardEventDestination(returnIntent, onwardHandoff, target, lineage)} />}
      {lineage && arrivalHandoff && returnIntent && <ArrivalEventDestinationPanel handoff={arrivalHandoff} value={compareArrivalEventDestination(returnIntent, arrivalHandoff, target, lineage)} />}
      {lineage && comparisonHandoff && returnIntent && <ComparisonEventArrivalPanel handoff={comparisonHandoff} value={compareComparisonEventArrival(returnIntent, comparisonHandoff, target, lineage)} />}
      {lineage && <SourceReviewLineagePanel value={lineage} returnToken={target.return_token} lockedSelection={pathLocked} />}<NavigationSummary value={value} historicalSelection={!!lineage} />
      {!(lineage ? lineage.tools_available : value.tools_available) ? <Notice error>Sabit bağlam, sürüm veya tarihsel karar bağları doğrulanamadı. İnceleme araçları kapalı; başka kayıt seçilmez.</Notice> : tools ? <AnalysisSourceReviews key={generation} matterId={target.matter_id} record={{ id: target.analysis_id, latest_version_id: value.analysis.current_version_id! }}
        selectedContext={{ id: target.context_id, manifest_sha256: value.context.manifest_sha256!, version_id: value.context.version_id! }} returnToken={target.return_token} selectedReview={lineage ? { id: lineage.selected_review.id, packet_sha256: lineage.selected_review.packet_sha256! } : undefined} onFailure={clear} onCommitted={saved => { setReceipt(saved); window.dispatchEvent(new Event('portfolio-updated')); }} />
        : <button className="button secondary" onClick={() => setTools(true)}>{target.review_id ? 'Seçilen tarihsel kararın inceleme araçlarını aç' : 'Seçilen kaydın inceleme araçlarını aç'}</button>}
      {!target.review_id && returnIntent && value.tools_available && value.version_relation === 'same' && value.admission.context_state === 'complete' && ['complete', 'not_recorded'].includes(value.admission.review_state) && <button className="text-button" disabled={busy} onClick={() => {
        try { const next = independentReviewIntent(returnIntent, value), token = returns.put(next); window.location.hash = reviewPreparationHref(next, token)!; }
        catch (cause) { clear(cause); }
      }}>Ayrı bağımsız incelemeyi hazırla</button>}
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
  const pathHandoff = token ? returns.getReviewPath(token) : null;
  const comparisonHandoff = token ? returns.getComparisonEvent(token) : null;
  const carriedHandoff = token ? returns.getCarriedArrivalEvent(token) : null;
  const onwardHandoff = token ? returns.getOnwardEvent(token) : null;
  const arrivalHandoff = token ? returns.getArrivalEvent(token) : null;
  const pathLocked = !!token && returns.isReviewPath(token) || comparisonHandoff !== null || arrivalHandoff !== null || onwardHandoff !== null || carriedHandoff !== null;
  if (pathLocked) {
    try { if (!intent) throw new Error(); verifyReturnedEventTarget(intent, selection); if (carriedHandoff) validateCarriedArrivalEventHandoff(carriedHandoff, intent); else if (onwardHandoff) validateOnwardEventHandoff(onwardHandoff, intent); else if (arrivalHandoff) validateArrivalEventHandoff(arrivalHandoff, intent); else if (comparisonHandoff) validateComparisonEventHandoff(comparisonHandoff, intent); else { if (!pathHandoff) throw new Error(); validateReviewPathHandoff(pathHandoff, intent); } }
    catch { return <Notice error>Zincir geçişi başka kayda veya hazırlığa yönlendirilemez. Kaynak okunmadı. <a href={queueReturnHref(token)!}>Aynı filtrelerle portföye dön</a></Notice>; }
  }
  if (selection.prepare === 'renewal') {
    const handoff = token ? returns.getRenewal(token) : null;
    if (!token || !intent || !handoff) return <Notice error>Yenileme geçişi için yeni portföy karşılaştırması gerekli. Kaynak veya hazırlık açılmadı. <a href={queueReturnHref()!}>Yeni kaynak kuyruğunu açıkça hazırla</a></Notice>;
    return <ComparisonRenewalPage key={token} intent={intent} handoff={handoff} token={token} />;
  }
  if (selection.prepare === 'review') {
    if (!token || !intent || intent.target.review_id !== null || !intent.target.version_id || !intent.target.manifest_sha256) return <Notice error>Yeni bağımsız inceleme için tam ve ayrı portföy seçimi gerekli. İçerik açılmadı.</Notice>;
    return <IndependentReviewPreparationPage key={token} intent={intent} token={token} />;
  }
  return <SelectedWorkspace carriedHandoff={carriedHandoff} onwardHandoff={onwardHandoff} arrivalHandoff={arrivalHandoff} comparisonHandoff={comparisonHandoff} pathHandoff={pathHandoff} returnIntent={intent} key={`${selection.matter_id}:${selection.analysis_id}:${selection.context_id}:${selection.review_id}:${selection.return_token || ''}:${workspaceQuery(filters)}`} target={selection} revision={revision} blocked={loading || !!error} />;
}
