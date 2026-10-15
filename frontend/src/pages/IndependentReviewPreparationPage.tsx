import { useEffect, useRef, useState } from 'react';
import { request } from '../api';
import { Notice, PageHeader } from '../components';
import { messageOf } from '../utils';
import { usePortfolio, workspaceQuery } from '../workbench/portfolio';
import { portfolioPart, queueReturnHref, type ReturnIntent } from '../workbench/portfolioReturn';
import { verifyCommittedReview, verifyReviewPreparation, type ReviewCommitPin } from '../workbench/renewalLineageNavigation';
import { ReturnFilterSummary } from './PortfolioReturnQueue';
import { NavigationSummary } from './SelectedSourceReviewPage';
import type { ReviewLineage } from './sourceReviewLineageTypes';
import type { NavigationMetadata } from './sourceContextNavigationTypes';
import { canonicalJson, SourceReadFence } from './matter/sourceReviewTypes';
import AnalysisSourceReviews, { type SourceSaveReceipt } from './matter/AnalysisSourceReviews';

export default function IndependentReviewPreparationPage({ intent, token }: { intent: ReturnIntent; token: string }) {
  const { filters, setFilters, revision, refresh, loading, error: scopeError, returns } = usePortfolio();
  const [prepared, setPrepared] = useState(-1), [proof, setProof] = useState<NavigationMetadata | null>(null), [editor, setEditor] = useState(false);
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [receipt, setReceipt] = useState<SourceSaveReceipt | null>(null), [uncertain, setUncertain] = useState(false);
  const fence = useRef(new SourceReadFence());
  const ready = prepared === revision && canonicalJson(filters) === canonicalJson(portfolioPart(intent.filters)) && !loading && !scopeError;
  const key = `${workspaceQuery(filters)}:${revision}`;
  const t = intent.target, base = `/matters/${encodeURIComponent(t.matter_id)}/analyses/${encodeURIComponent(t.analysis_id)}/source-contexts/${encodeURIComponent(t.context_id)}`;
  function clear(cause?: unknown) { fence.current.invalidate(); setProof(null); setEditor(false); setBusy(false); setReceipt(null); setUncertain(false); setError(cause ? messageOf(cause) : ''); }
  useEffect(() => { const gate = fence.current; return () => gate.invalidate(); }, []);
  useEffect(() => { clear(); }, [key]);
  useEffect(() => { if (loading || scopeError) clear(); }, [loading, scopeError]);
  function prepare() { clear(); setFilters(portfolioPart(intent.filters)); setPrepared(revision + 1); refresh(); }
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
    if (!ready) return; clear(); const task = fence.current.begin(); setBusy(true);
    try { const meta = await read(task.signal); if (task.current()) setProof(meta); }
    catch (cause) { if (task.current()) clear(cause); } finally { if (task.current()) setBusy(false); }
  }
  return <><PageHeader eyebrow="AYRI BAĞIMSIZ İNCELEME" title="Sabit kaynak bağlamını bağımsız incele" description="Eski kararlar korunur. Yeni karar için kaynaklar, güncel özel dayanaklar ve farklı incelemeci yetkisi ayrıca doğrulanır." />
    <a className="text-link" href={queueReturnHref(token)!}>Aynı filtrelerle portföy kuyruğuna dön</a><ReturnFilterSummary intent={intent} />
    <p className="reference-id">Seçilen bağlam: {t.context_id} · Sabit sürüm: {t.version_id}</p>
    <p>Bu hazırlık önceki kararı veya incelemeci yetkisini devralmaz. Başka avukat kendi oturumunda yetkili portföyünden aynı kaydı seçmelidir; geçiş anahtarı paylaşılmaz.</p>
    {error && <Notice error>{error} Korunan içerik ve inceleme formu temizlendi.</Notice>}{scopeError && <Notice error>{scopeError}</Notice>}
    {!ready ? <button className="button secondary" disabled={busy || loading} onClick={prepare}>Dönüş filtrelerini uygula ve incelemeyi hazırla</button> : <button className="button secondary" disabled={busy} onClick={() => void observe()}>Bağımsız incelemenin tam kimliklerini gözle</button>}
    {ready && receipt && <Notice>Yeni bağımsız kararın tam kaydı doğrulandı. Önceki kararlar değişmedi; güncel izin ve hukuki uygulanabilirlik bu kayıtla garanti edilmez.<p className="reference-id">Karar: {receipt.id}</p></Notice>}
    {ready && uncertain && <Notice error>İnceleme isteğinin sonucu doğrulanamadı. İstek yeniden gönderilmez; tam kayıt kimliklerini ayrıca gözlemleyin. Bekleyen kabul tamamlanmaz.</Notice>}
    {ready && proof && <><NavigationSummary value={proof} />{!editor ? <button className="button secondary" disabled={busy} onClick={() => setEditor(true)}>Yalnız yeni bağımsız inceleme araçlarını aç</button> : <>
      <button className="text-button" onClick={() => clear()}>Bağımsız inceleme hazırlığını kapat</button>
      <AnalysisSourceReviews matterId={t.matter_id} record={{ id: t.analysis_id, latest_version_id: proof.analysis.current_version_id! }} selectedContext={{ id: t.context_id, version_id: t.version_id!, manifest_sha256: t.manifest_sha256! }} reviewOnly
        guard={async (signal, committed) => { await read(signal, proof, committed); }} onFailure={clear}
        onReviewUncertain={() => { clear(); setUncertain(true); }} onCommitted={saved => { clear(); if (saved.kind === 'review' && saved.state === 'confirmed') setReceipt(saved); else setUncertain(true); }} />
    </>}</>}
  </>;
}
