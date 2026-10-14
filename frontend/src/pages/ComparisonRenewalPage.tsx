import { useEffect, useRef, useState } from 'react';
import { request } from '../api';
import { Detail, Notice, PageHeader } from '../components';
import { messageOf } from '../utils';
import { usePortfolio, workspaceQuery } from '../workbench/portfolio';
import { portfolioPart, queueReturnHref, type ReturnIntent } from '../workbench/portfolioReturn';
import { successorIntent, verifyPreparedRenewal, verifyRenewalNavigation, type RenewalHandoff } from '../workbench/renewalHandoff';
import { sourceContextHref, type NavigationMetadata } from './sourceContextNavigationTypes';
import { canonicalJson, SourceReadFence } from './matter/sourceReviewTypes';
import type { RenewalMetadata } from './matter/sourceRenewalTypes';
import AnalysisSourceReviews, { type SourceSaveReceipt } from './matter/AnalysisSourceReviews';
import { ReturnFilterSummary } from './PortfolioReturnQueue';

export function RenewalHandoffSummary({ intent, handoff }: { intent: ReturnIntent; handoff: RenewalHandoff }) {
  return <><p>Özgün kaynak bağlamı seçili kalır. Yeni hedef için güncel araştırma, açık pasaj eşlemesi ve yeni bağımsız inceleme gerekir.</p>
    <Detail title="Özgün kanıt ve karşılaştırmada gözlenen hedef" open>
      <p className="reference-id">Özgün bağlam: {intent.target.context_id} · Sabit sürüm: {intent.target.version_id}</p>
      <p className="reference-id">Hedef analiz sürümü: {handoff.version_id} · Gözlenen karar başı: {handoff.head_id || 'Henüz kayıt yok'}</p>
      <p className="small muted">Bu seçim izin veya onay değildir. Önceki alıntılar ve yorumlar açılmaz; eski karar yeni kayda aktarılmaz. Hedef değişirse karşılaştırmaya dönüp yeniden gözlemleyin.</p>
    </Detail></>;
}
export default function ComparisonRenewalPage({ intent, handoff, token }: { intent: ReturnIntent; handoff: RenewalHandoff; token: string }) {
  const { filters, setFilters, revision, refresh, loading, error: scopeError, returns } = usePortfolio();
  const [prepared, setPrepared] = useState(-1), [proof, setProof] = useState<RenewalMetadata | null>(null), [editor, setEditor] = useState(false);
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [receipt, setReceipt] = useState<SourceSaveReceipt | null>(null);
  const [successor, setSuccessor] = useState<string | null>(null), [unverifiedParent, setUnverifiedParent] = useState(false);
  const fence = useRef(new SourceReadFence());
  const matching = canonicalJson(filters) === canonicalJson(portfolioPart(intent.filters));
  const ready = prepared === revision && matching && !loading && !scopeError;
  const key = `${workspaceQuery(filters)}:${revision}`;
  const base = `/matters/${encodeURIComponent(intent.target.matter_id)}/analyses/${encodeURIComponent(intent.target.analysis_id)}/source-contexts/${encodeURIComponent(intent.target.context_id)}`;
  useEffect(() => { const gate = fence.current; return () => gate.invalidate(); }, []);
  function clear(cause?: unknown) { fence.current.invalidate(); setBusy(false); setProof(null); setEditor(false); setSuccessor(null); if (cause) setReceipt(null); setError(cause ? messageOf(cause) : ''); }
  useEffect(() => { clear(); setReceipt(null); }, [key]);
  useEffect(() => { if (loading || scopeError) { clear(); setReceipt(null); } }, [loading, scopeError]);
  function prepare() { clear(); setReceipt(null); setFilters(portfolioPart(intent.filters)); setPrepared(revision + 1); refresh(); }
  async function validate(signal: AbortSignal) {
    if (!returns.getRenewal(token)) throw new Error('Yenileme geçişi kayboldu veya süresi doldu.');
    const before = await request<NavigationMetadata>(`${base}/navigation-context`, { signal }); verifyRenewalNavigation(intent, handoff, before);
    if (signal.aborted) throw new DOMException('Aborted', 'AbortError');
    const meta = await request<RenewalMetadata>(`${base}/renewal-context`, { signal });
    if (signal.aborted) throw new DOMException('Aborted', 'AbortError');
    const after = await request<NavigationMetadata>(`${base}/navigation-context`, { signal }); verifyPreparedRenewal(intent, handoff, before, meta, after);
    return meta;
  }
  async function observe() {
    if (!ready) return; clear(); const task = fence.current.begin(); setBusy(true); setReceipt(null);
    try { const meta = await validate(task.signal); if (task.current()) setProof(meta); }
    catch (cause) { if (task.current()) clear(cause); } finally { if (task.current()) setBusy(false); }
  }
  async function observeSuccessor() {
    if (!ready || !receipt || receipt.kind !== 'context') return;
    clear(); const task = fence.current.begin(); setBusy(true);
    try {
      const meta = await request<NavigationMetadata>(`/matters/${encodeURIComponent(intent.target.matter_id)}/analyses/${encodeURIComponent(intent.target.analysis_id)}/source-contexts/${encodeURIComponent(receipt.id)}/navigation-context`, { signal: task.signal });
      const next = successorIntent(intent, receipt.id, meta, receipt.state === 'confirmed' ? receipt.context : undefined);
      if (task.current() && returns.get(token)) { const nextToken = returns.put(next); setSuccessor(sourceContextHref(next.target.matter_id, next.target.analysis_id, next.target.context_id, undefined, nextToken)); setUnverifiedParent(receipt.state !== 'confirmed' || !receipt.context); }
    } catch (cause) { if (task.current()) clear(cause); } finally { if (task.current()) setBusy(false); }
  }
  return <><PageHeader eyebrow="AYRI YENİLEME HAZIRLIĞI" title="Karşılaştırmadan kaynak yenilemeye" description="Özgün kayıt, yeni hedef ve bağımsız inceleme ayrı tutulur. Hazırlık açıkça başlatılır." />
    <a className="text-link" href={queueReturnHref(token)!}>Aynı filtrelerle portföy karşılaştırmasına dön</a>
    <ReturnFilterSummary intent={intent} /><RenewalHandoffSummary intent={intent} handoff={handoff} />
    {error && <Notice error>{error} Hazırlık ve korunan içerik temizlendi.</Notice>}{scopeError && <Notice error>{scopeError}</Notice>}
    {!ready ? <button className="button secondary" disabled={busy || loading} onClick={prepare}>Dönüş filtrelerini uygula ve hazırla</button> : <button className="button secondary" disabled={busy} onClick={() => void observe()}>Yenileme kimliklerini yeniden doğrula</button>}
    {ready && proof && !editor && <><p>Özgün bağlar ve hedef kimlikleri ayrı okumalarda doğrulandı. Bunlar atomik bir izin kaydı veya kaynak kontrolü değildir; sonraki işlemler yeniden denetlenir.</p><button className="button secondary" disabled={busy} onClick={() => setEditor(true)}>Yeni kaynak seçimi için yenileme araçlarını aç</button></>}
    {ready && proof && editor && <><button className="text-button" onClick={() => clear()}>Yenileme hazırlığını kapat</button><AnalysisSourceReviews matterId={intent.target.matter_id} record={{ id: intent.target.analysis_id, latest_version_id: handoff.version_id }}
      selectedContext={{ id: intent.target.context_id, version_id: intent.target.version_id!, manifest_sha256: intent.target.manifest_sha256! }} preparedRenewal={proof}
      guard={async signal => { await validate(signal); }} onFailure={clear} onCommitted={saved => { clear(); setReceipt(saved); }} /></>}
    {ready && receipt && <Notice>{receipt.state === 'confirmed' ? 'Ayrı bağlam kaydı doğrulandı; yeni bağımsız inceleme gerekir.' : 'Bir bağlam kaydı bildirildi; tamamlanma ve özgün yenileme bağı henüz doğrulanmadı. Yeniden gönderilmez.'}
      <p><button className="text-button" disabled={busy} onClick={() => void observeSuccessor()}>Bildirilen yeni kaydın tam kimliğini gözle</button></p></Notice>}
    {ready && successor && <>{unverifiedParent && <Notice>Kayıt kimliği gözlendi; özgün yenileme bağı doğrulanmadı. Eski karar veya izin devralınmaz.</Notice>}<a className="button secondary" href={successor}>Ayrı yeni bağlamın tam kimliğini aç</a></>}
  </>;
}
