import { useEffect, useRef, useState } from 'react';
import { request } from '../api';
import { Detail, Notice, PageHeader } from '../components';
import { messageOf } from '../utils';
import { usePortfolio, workspaceQuery } from '../workbench/portfolio';
import { portfolioPart, queueReturnHref, type ReturnIntent } from '../workbench/portfolioReturn';
import { verifyCommittedReview, verifyReviewPreparation, type ReviewCommitPin } from '../workbench/renewalLineageNavigation';
import { completeReviewAdmissions, reconciledReviewIntent, reconciledReviewReturnIntent, reviewReceiptQuery, verifyReviewObservation, verifySameReviewOutcome, type ReviewObservation, type ReviewReceipt } from '../workbench/reviewReconciliation';
import { ReturnFilterSummary } from './PortfolioReturnQueue';
import { NavigationSummary } from './SelectedSourceReviewPage';
import type { ReviewLineage } from './sourceReviewLineageTypes';
import { sourceContextHref, type NavigationMetadata } from './sourceContextNavigationTypes';
import { canonicalJson, SourceReadFence } from './matter/sourceReviewTypes';
import AnalysisSourceReviews from './matter/AnalysisSourceReviews';

export default function IndependentReviewPreparationPage({ intent, token }: { intent: ReturnIntent; token: string }) {
  const { filters, setFilters, revision, refresh, loading, error: scopeError, returns } = usePortfolio();
  const [prepared, setPrepared] = useState(-1), [proof, setProof] = useState<NavigationMetadata | null>(null), [editor, setEditor] = useState(false);
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [receipt, setReceipt] = useState<ReviewReceipt | null>(null);
  const [result, setResult] = useState<ReviewObservation | null>(null), [eventHref, setEventHref] = useState<string | null>(null), [returnHref, setReturnHref] = useState<string | null>(null);
  const fence = useRef(new SourceReadFence());
  const ready = prepared === revision && canonicalJson(filters) === canonicalJson(portfolioPart(intent.filters)) && !loading && !scopeError;
  const key = `${workspaceQuery(filters)}:${revision}`;
  const t = intent.target, base = `/matters/${encodeURIComponent(t.matter_id)}/analyses/${encodeURIComponent(t.analysis_id)}/source-contexts/${encodeURIComponent(t.context_id)}`;
  function clear(cause?: unknown) { fence.current.invalidate(); setProof(null); setEditor(false); setBusy(false); setResult(null); setEventHref(null); setReturnHref(null); setError(cause ? messageOf(cause) : ''); }
  useEffect(() => { const gate = fence.current; return () => gate.invalidate(); }, []);
  useEffect(() => { clear(); setReceipt(null); }, [key]);
  useEffect(() => { if (loading || scopeError) { clear(); setReceipt(null); } }, [loading, scopeError]);
  function prepare() { clear(); setReceipt(null); setFilters(portfolioPart(intent.filters)); setPrepared(revision + 1); refresh(); }
  async function read(signal: AbortSignal, before?: NavigationMetadata, committed?: ReviewCommitPin) {
    if (!returns.get(token)) throw new Error('Bağımsız inceleme geçişi kayboldu veya süresi doldu.');
    const history = committed ? await request<ReviewLineage>(`${base}/reviews/${encodeURIComponent(committed.id)}/navigation-context?window=1`, { signal }) : null;
    if (signal.aborted) throw new DOMException('Retired', 'AbortError');
    const meta = history ? history.context_navigation : await request<NavigationMetadata>(`${base}/navigation-context`, { signal });
    if (history && committed) {
      if (!before) throw new Error('Yeni karar için özgün hazırlık gözlemi gerekli.');
      verifyCommittedReview(intent, before, committed, history);
    } else verifyReviewPreparation(intent, meta, before);
    return meta;
  }
  async function observe() {
    if (!ready || receipt) return; clear(); const task = fence.current.begin(); setBusy(true);
    try { const meta = await read(task.signal); if (task.current()) setProof(meta); }
    catch (cause) { if (task.current()) clear(cause); } finally { if (task.current()) setBusy(false); }
  }
  async function observation(signal: AbortSignal) {
    if (!receipt || !returns.get(token)) throw new Error('Tam istek özeti veya oturum geçişi kayboldu.');
    const value = await request<ReviewObservation>(`${base}/reviews/reconciliation?${reviewReceiptQuery(receipt)}`, { signal });
    verifyReviewObservation(value, receipt, intent); return value;
  }
  async function reconcile() {
    if (!ready || !receipt) return; clear(); const task = fence.current.begin(); setBusy(true);
    try { const value = await observation(task.signal); if (task.current() && returns.get(token)) setResult(value); }
    catch (cause) { if (task.current()) clear(cause); } finally { if (task.current()) setBusy(false); }
  }
  async function observeFollowup(destination: 'event' | 'queue') {
    if (!ready || !receipt || !result || !completeReviewAdmissions(result)) return;
    const captured = result, task = fence.current.begin(); setBusy(true); setEventHref(null); setReturnHref(null);
    try {
      verifySameReviewOutcome(captured, await observation(task.signal), intent); if (!task.current()) return;
      const history = await request<ReviewLineage>(`${base}/reviews/${encodeURIComponent(captured.review!.id)}/navigation-context?window=1`, { signal: task.signal });
      if (!task.current()) return;
      const next = destination === 'queue' ? reconciledReviewReturnIntent(intent, captured, history) : reconciledReviewIntent(intent, captured, history);
      verifySameReviewOutcome(captured, await observation(task.signal), intent);
      if (task.current() && returns.get(token)) { const nextToken = returns.put(next);
        if (destination === 'queue') setReturnHref(queueReturnHref(nextToken)); else setEventHref(sourceContextHref(t.matter_id, t.analysis_id, t.context_id, next.target.review_id!, nextToken)); }
    } catch (cause) { if (task.current()) clear(cause); } finally { if (task.current()) setBusy(false); }
  }
  return <><PageHeader eyebrow="AYRI BAĞIMSIZ İNCELEME" title="Sabit kaynak bağlamını bağımsız incele" description="Eski kararlar korunur. Yeni karar için kaynaklar, güncel özel dayanaklar ve farklı incelemeci yetkisi ayrıca doğrulanır." />
    <a className="text-link" href={queueReturnHref(token)!}>İlk portföy seçimine dön</a><ReturnFilterSummary intent={intent} />
    <p className="reference-id">Seçilen bağlam: {t.context_id} · Sabit sürüm: {t.version_id}</p>
    <p>Bu hazırlık önceki kararı veya incelemeci yetkisini devralmaz. Başka avukat kendi oturumunda yetkili portföyünden aynı kaydı seçmelidir; geçiş anahtarı paylaşılmaz.</p>
    {error && <Notice error>{error} Korunan içerik ve inceleme formu temizlendi.</Notice>}{scopeError && <Notice error>{scopeError}</Notice>}
    {!ready ? <button className="button secondary" disabled={busy || loading} onClick={prepare}>Dönüş filtrelerini uygula ve incelemeyi hazırla</button> : !receipt && <button className="button secondary" disabled={busy} onClick={() => void observe()}>Bağımsız incelemenin tam kimliklerini gözle</button>}
    {ready && receipt && <Notice>İnceleme isteğinin yalnız kimlik özeti bu oturumda korundu. Sonuç ayrıca salt okunur gözlemlenir; karar yeniden gönderilmez. Notlar ve alıntılar temizlendi.
      <p><button className="text-button" disabled={busy} onClick={() => void reconcile()}>Bağımsız inceleme isteğinin sonucunu salt okunur gözle</button></p></Notice>}
    {ready && result && <ReviewOutcomeSummary value={result} />}
    {ready && result && completeReviewAdmissions(result) && <div className="practice-record-actions" role="group" aria-label="Doğrulanan inceleme sonucundan güvenli devam">
      <button className="text-button" disabled={busy} onClick={() => void observeFollowup('event')}>Doğrulanan tam kararın geçişini ayrıca doğrula</button>
      <button className="text-button" disabled={busy} onClick={() => void observeFollowup('queue')}>Seçilen kararı koruyarak portföy dönüşünü doğrula</button>
    </div>}
    {ready && eventHref && <a className="button secondary" href={eventHref}>Doğrulanan tam tarihsel kararı aç</a>}
    {ready && returnHref && <><p className="small muted">Seçilen karar ve ilk portföy gözlemleri ayrı korundu. Kuyruk açılışında tam filtreleri ayrıca uygulayın ve yeni sınırlı gözlemi açıkça başlatın; eski sonuçlar veya izinler yüklenmez.</p>
      <a className="button secondary" href={returnHref}>Seçilen tarihsel kararla aynı portföy kuyruğuna dön</a></>}
    {ready && proof && <><NavigationSummary value={proof} />{!editor ? <button className="button secondary" disabled={busy} onClick={() => setEditor(true)}>Yalnız yeni bağımsız inceleme araçlarını aç</button> : <>
      <button className="text-button" onClick={() => clear()}>Bağımsız inceleme hazırlığını kapat</button>
      <AnalysisSourceReviews matterId={t.matter_id} record={{ id: t.analysis_id, latest_version_id: proof.analysis.current_version_id! }} selectedContext={{ id: t.context_id, version_id: t.version_id!, manifest_sha256: t.manifest_sha256! }} reviewOnly
        guard={async (signal, committed) => { await read(signal, proof, committed); }} onFailure={clear}
        onReviewOutcome={saved => { clear(); setReceipt(saved); }} />
    </>}</>}
  </>;
}

export function ReviewOutcomeSummary({ value }: { value: ReviewObservation }) {
  if (value.outcome !== 'verified') return <Notice>{value.outcome === 'not_observed' ? 'Bu incelemeci ve tam isteğe ait karar gözlenmedi. Bu sonuç kayıt yokluğunu veya yeniden gönderme iznini kanıtlamaz.' : 'Tam inceleme isteği veya değiştirilemez karar bağı doğrulanamadı. İçerik ve ilerleme kapalı.'}</Notice>;
  return <Detail title="Salt okunur bağımsız karar gözlemi" open><p>Tam istek, değiştirilemez karar ve önceki karar bağı doğrulandı. Güncel karar başı, kamu kaynaklarının izni ve hukuki uygulanabilirlik kontrol edilmedi.</p>
    <p className="reference-id">Karar: {value.review!.id} · Sıra: {value.review!.sequence} · Sabit sürüm: {value.context!.version_id}</p>
    <p>Kaydedilen incelemeci beyanı: {value.review!.state === 'changes_requested' ? 'Değişiklik istendi' : 'Koşullu inceleme kaydedildi'}. Bu beyan hukuki onay değildir.</p>
    <p>Bağlam kabulü: {value.admission!.context === 'complete' ? 'Tamamlanmış' : 'Bekliyor'} · Karar kabulü: {value.admission!.review === 'complete' ? 'Tamamlanmış' : 'Bekliyor'} · Önceki karar kabulü: {value.admission!.predecessor === 'not_recorded' ? 'Önceki karar yok' : value.admission!.predecessor === 'complete' ? 'Tamamlanmış' : 'Bekliyor'}.</p>
    <p>Bekleyen kabul tamamlanmaz; hiçbir karar yeniden gönderilmez. Tam tarihsel karara geçiş ve sonraki kaynak okuması ayrıca denetlenir.</p></Detail>;
}
