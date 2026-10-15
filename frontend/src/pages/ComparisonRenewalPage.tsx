import { useEffect, useRef, useState } from 'react';
import { request } from '../api';
import { Detail, Notice, PageHeader } from '../components';
import { messageOf } from '../utils';
import { usePortfolio, workspaceQuery } from '../workbench/portfolio';
import { portfolioPart, queueReturnHref, type ReturnIntent } from '../workbench/portfolioReturn';
import { successorIntent, verifyPreparedRenewal, verifyRenewalNavigation, type RenewalHandoff } from '../workbench/renewalHandoff';
import { renewalReceiptQuery, verifyRenewalObservation, type RenewalObservation, type RenewalReceipt } from '../workbench/renewalReconciliation';
import { completeRenewalAdmissions, independentReviewIntent, parentLineageIntent, reviewPreparationHref, verifySameRenewalLink } from '../workbench/renewalLineageNavigation';
import { type ReviewLineage } from './sourceReviewLineageTypes';
import { sourceContextHref, type NavigationMetadata } from './sourceContextNavigationTypes';
import { canonicalJson, SourceReadFence } from './matter/sourceReviewTypes';
import type { RenewalMetadata } from './matter/sourceRenewalTypes';
import AnalysisSourceReviews from './matter/AnalysisSourceReviews';
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
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [receipt, setReceipt] = useState<RenewalReceipt | null>(null);
  const [result, setResult] = useState<RenewalObservation | null>(null), [successor, setSuccessor] = useState<string | null>(null), [parentHref, setParentHref] = useState<string | null>(null), [reviewHref, setReviewHref] = useState<string | null>(null);
  const fence = useRef(new SourceReadFence());
  const matching = canonicalJson(filters) === canonicalJson(portfolioPart(intent.filters));
  const ready = prepared === revision && matching && !loading && !scopeError;
  const key = `${workspaceQuery(filters)}:${revision}`;
  const base = `/matters/${encodeURIComponent(intent.target.matter_id)}/analyses/${encodeURIComponent(intent.target.analysis_id)}/source-contexts/${encodeURIComponent(intent.target.context_id)}`;
  useEffect(() => { const gate = fence.current; return () => gate.invalidate(); }, []);
  function clear(cause?: unknown) { fence.current.invalidate(); setBusy(false); setProof(null); setEditor(false); setSuccessor(null); setParentHref(null); setReviewHref(null); setResult(null); if (cause) setReceipt(null); setError(cause ? messageOf(cause) : ''); }
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
  async function reconcile() {
    if (!ready || !receipt) return;
    clear(); const task = fence.current.begin(); setBusy(true);
    try {
      const value = await request<RenewalObservation>(`${base.slice(0, base.lastIndexOf('/'))}/renewal-reconciliation?${renewalReceiptQuery(receipt)}`, { signal: task.signal });
      verifyRenewalObservation(value, receipt, intent.target.matter_id, intent.target.analysis_id);
      if (task.current() && returns.getRenewal(token)) setResult(value);
    } catch (cause) { if (task.current()) clear(cause); } finally { if (task.current()) setBusy(false); }
  }
  async function observeRelated(kind: 'parent' | 'successor' | 'review') {
    if (!ready || !receipt || !result || !completeRenewalAdmissions(result)) return;
    const captured = result, task = fence.current.begin(); setBusy(true); setSuccessor(null); setParentHref(null); setReviewHref(null);
    try {
      const fresh = async () => {
        const value = await request<RenewalObservation>(`${base.slice(0, base.lastIndexOf('/'))}/renewal-reconciliation?${renewalReceiptQuery(receipt)}`, { signal: task.signal });
        verifySameRenewalLink(captured, value); return value;
      };
      await fresh(); if (!task.current()) return;
      const id = kind === 'parent' ? captured.lineage!.parent_context_id : captured.successor!.id;
      const targetBase = `/matters/${encodeURIComponent(intent.target.matter_id)}/analyses/${encodeURIComponent(intent.target.analysis_id)}/source-contexts/${encodeURIComponent(id)}`;
      let next: ReturnIntent;
      if (kind === 'parent') {
        const review = captured.lineage!.parent_review_id;
        const history = review ? await request<ReviewLineage>(`${targetBase}/reviews/${encodeURIComponent(review)}/navigation-context?window=1`, { signal: task.signal }) : null;
        if (!task.current()) return;
        const meta = history ? history.context_navigation : await request<NavigationMetadata>(`${targetBase}/navigation-context`, { signal: task.signal });
        next = parentLineageIntent(intent, captured, meta, history);
      } else {
        const meta = await request<NavigationMetadata>(`${targetBase}/navigation-context`, { signal: task.signal });
        if (meta.admission.context_state !== 'complete') throw new Error('Ardıl bağlamın kabulü doğrulanamadı.');
        next = successorIntent(intent, id, meta, captured.successor!);
        if (kind === 'review') next = independentReviewIntent(next, meta);
      }
      await fresh();
      if (task.current() && returns.getRenewal(token)) {
        const nextToken = returns.put(next), t = next.target;
        const href = kind === 'review' ? reviewPreparationHref(next, nextToken) : sourceContextHref(t.matter_id, t.analysis_id, t.context_id, t.review_id || undefined, nextToken);
        if (kind === 'parent') setParentHref(href); else if (kind === 'review') setReviewHref(href); else setSuccessor(href);
      }
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
      guard={async signal => { await validate(signal); }} onFailure={clear} onRenewalOutcome={saved => { clear(); setReceipt(saved); }} /></>}
    {ready && receipt && <Notice>İstek özeti korundu; sonuç ayrıca salt okunur gözlemlenir. İstek yeniden gönderilmez; eski karar devralınmaz.
      <p><button className="text-button" disabled={busy} onClick={() => void reconcile()}>Yenileme isteğinin sonucunu salt okunur gözle</button></p></Notice>}
    {ready && result && <RenewalOutcomeSummary value={result} />}
    {ready && result && completeRenewalAdmissions(result) && <div className="practice-record-actions">
      <button className="text-button" disabled={busy} onClick={() => void observeRelated('parent')}>Özgün tarihsel yenileme bağını ayrıca doğrula</button>
      <button className="text-button" disabled={busy} onClick={() => void observeRelated('successor')}>Doğrulanan ardılın güncel tam kimliğini ayrıca gözle</button>
      <button className="text-button" disabled={busy} onClick={() => void observeRelated('review')}>Ardıl bağımsız inceleme geçişini ayrıca doğrula</button>
    </div>}
    {ready && parentHref && <a className="button secondary" href={parentHref}>{result?.lineage?.parent_review_id ? 'Yakalanan özgün tarihsel kararı aç' : 'Özgün kaynak bağlamını karar devralmadan aç'}</a>}
    {ready && successor && <a className="button secondary" href={successor}>Ayrı yeni bağlamın tam kimliğini aç</a>}
    {ready && reviewHref && <><p className="small">Bu geçiş incelemeci yetkisi vermez. Farklı avukat kendi oturumunda aynı ardılı yetkili portföy seçimiyle yeniden açmalıdır; geçiş anahtarları paylaşılmaz.</p><a className="button secondary" href={reviewHref}>Ardıl için ayrı bağımsız inceleme hazırlığını aç</a></>}

  </>;
}

export function RenewalOutcomeSummary({ value }: { value: RenewalObservation }) {
  if (value.outcome !== 'verified') return <Notice>{value.outcome === 'not_observed' ? 'Bu tam isteğe ait kayıt gözlenmedi. Bu sonuç kayıt yokluğunu veya yeniden gönderme iznini kanıtlamaz.' : 'Tam istek veya tarihsel yenileme bağı doğrulanamadı. İçerik ve ilerleme kapalı.'}</Notice>;
  return <Detail title="Salt okunur istek ve tarihsel yenileme bağı" open><p>İstek kaydı ve tek tarihsel yenileme bağı doğrulandı. Güncel ebeveyn karar başı ve kaynak izni kontrol edilmedi; hukuki eşdeğerlik değerlendirilmedi.</p>
    <p className="reference-id">Ardıl: {value.successor!.id} · Sabit sürüm: {value.successor!.version_id}</p>
    <p className="small">Ardıl kabulü: {value.admission!.successor === 'complete' ? 'Tamamlanmış' : 'Bekliyor'} · Özgün kabul: {value.admission!.parent === 'complete' ? 'Tamamlanmış' : 'Bekliyor'} · Tarihsel karar kabulü: {value.admission!.parent_review === 'not_recorded' ? 'Karar kaydı yok' : value.admission!.parent_review === 'complete' ? 'Tamamlanmış' : 'Bekliyor'}.</p>
    <p>Bekleyen kabul tamamlanmaz. Önceki karar veya izin aktarılmaz; yeni bağımsız inceleme gerekir.</p></Detail>;
}
