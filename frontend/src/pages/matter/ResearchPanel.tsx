import { useEffect, useRef, useState, type FormEvent } from 'react';
import { ApiError, downloadProduct, post, request } from '../../api';
import { Badge, Detail, Empty, Field, Icon, JsonDetails, Loading, Notice, SectionIndex } from '../../components';
import type { AuthorityCandidates, Claim, Matter, ResearchRun } from '../../types';
import { formatDate, isRunning, locatorText, messageOf, statusLabel } from '../../utils';
import { EvidenceViewer } from './FactsPanel';
import { EvidenceContextPanel } from './EvidenceContextPanel';
import { SourceCandidatesPanel } from './SourceCandidatesPanel';
import { SourceExcerpt } from '../../SourceExcerpt';
import { ValidityDetails } from '../../ValidityDetails';
import { createProductReader, productSelectionKey, type ProductRead } from './researchProductRead';
import { ResearchOutputPicker } from './ResearchOutputPicker';
import GatewayPanel from './GatewayPanel';
import { researchReviewConflict, type ReviewConflict } from './researchReviewConflict';

type RecoveringReview = { conflict: ReviewConflict; version: number; claimId: string; note: string; reopened: boolean };

function ResearchReviewRecovery({ review, reading, canRestart, onRead, onRestart }: {
  review: RecoveringReview; reading: boolean; canRestart: boolean; onRead: () => void; onRestart: () => void;
}) {
  const { conflict } = review;
  const title = conflict.kind === 'saved' ? 'İnceleme kaydedildi, kaynak izni yeniden doğrulanmalı.'
    : conflict.kind === 'rejected' ? 'İnceleme kaydedilemedi.' : 'İncelemenin kaydedilip kaydedilmediği doğrulanamadı.';
  return <div className="conflict-state"><Notice error><strong>{title}</strong>
    <p>Sürüm {review.version}{conflict.kind === 'saved' ? ` · kaydedilen revizyon ${conflict.revision}` : ''}</p>
    {conflict.kind === 'rejected' && <p>{conflict.message}</p>}
    {review.reopened
      ? <p>Aşağıda bu sürümün son kaydı gösteriliyor. İnceleme durumunu ve kayıtlı notu kontrol edin.</p>
      : <p>Karar vermeden önce aynı çıktı sürümünü yeniden okuyun.</p>}
  </Notice>
    {review.note && <Detail title={conflict.kind === 'saved' ? 'Gönderilen inceleme notu' : 'Gönderilmeye çalışılan inceleme notu'} open>
      <p className="source-review-rationale">{review.note}</p>
    </Detail>}
    <div className="form-actions"><button type="button" className="button secondary" disabled={reading} onClick={onRead}>Seçili sürümü yeniden oku</button>
      {canRestart && <button type="button" className="button secondary" onClick={onRestart}>Taslağı bırak ve yeni incelemeye başla</button>}
    </div>
  </div>;
}

export default function ResearchPanel({ matter, onChange, demo }: { matter: Matter; onChange: () => Promise<void>; demo: boolean }) {
  return <ResearchWorkspace key={matter.id} matter={matter} onChange={onChange} demo={demo} />;
}

function ResearchWorkspace({ matter, onChange, demo }: { matter: Matter; onChange: () => Promise<void>; demo: boolean }) {
  const [question, setQuestion] = useState(''); const [asOf, setAsOf] = useState(matter.relevant_date || ''); const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  const [runs, setRuns] = useState<ResearchRun[]>(matter.research_runs || []); const [pollError, setPollError] = useState('');
  const [selectedId, setSelectedId] = useState(matter.products?.[0]?.id || '');
  const [productState, setProductState] = useState<ProductRead | null>(null);
  const productReader = useRef<ReturnType<typeof createProductReader> | null>(null);
  const [recovering, setRecovering] = useState<Record<string, RecoveringReview>>({});
  const [reviewing, setReviewing] = useState(false);
  const reviewInFlight = useRef(false);
  const listedProduct = matter.products?.find(item => item.id === selectedId);
  const expectedVersion = listedProduct?.version;
  const selectionKey = productSelectionKey({ matterId: matter.id, productId: selectedId, version: expectedVersion });
  const selectedRead = productState?.key === selectionKey ? productState : null;
  const fetchedProduct = selectedRead?.status === 'ready' ? selectedRead.value : null;
  const recovery = recovering[selectedId];
  const minimumRevision = recovery?.conflict.kind === 'saved' ? recovery.conflict.revision : undefined;
  const behindReceipt = fetchedProduct && minimumRevision !== undefined && (fetchedProduct.revision ?? 0) < minimumRevision;
  const wrongRecoveryVersion = fetchedProduct && recovery && fetchedProduct.version !== recovery.version;
  const product = behindReceipt || wrongRecoveryVersion || (recovery && !recovery.reopened) ? null : fetchedProduct;
  const canReview = product && !['stale', 'invalidated', 'reviewed'].includes(product.status);
  const productLoading = Boolean(selectedId && (!selectedRead || selectedRead.status === 'loading'));
  const [source, setSource] = useState<string | null>(null); const [exporting, setExporting] = useState('');
  const listedRevision = listedProduct?.revision;
  const listedStatus = listedProduct?.status;
  const base = `/matters/${encodeURIComponent(matter.id)}`;
  useEffect(() => { setRuns(matter.research_runs || []); if (!selectedId && matter.products?.length) setSelectedId(matter.products[0].id); }, [matter.research_runs, matter.products, selectedId]);
  useEffect(() => {
    const active = runs.filter((run) => isRunning(run.status)); if (!active.length) return;
    let alive = true; let polling = false; let failures = 0;
    const timer = window.setInterval(async () => {
      if (polling) return; polling = true;
      try {
        const updated = await Promise.all(active.map((run) => request<ResearchRun>(`${base}/research/${encodeURIComponent(run.id)}`)));
        if (!alive) return;
        failures = 0; setPollError(''); setRuns((old) => old.map((run) => updated.find((item) => item.id === run.id) || run));
        const completed = updated.find((run) => run.product_id && !isRunning(run.status));
        if (completed?.product_id) setSelectedId(current => current || completed.product_id!);
        if (updated.some((run) => !isRunning(run.status))) await onChange();
      } catch (cause) { if (alive) { failures += 1; setPollError(messageOf(cause)); if (failures >= 3) window.clearInterval(timer); } }
      finally { polling = false; }
    }, 2500);
    return () => { alive = false; window.clearInterval(timer); };
  }, [runs, base, onChange]);
  useEffect(() => {
    setSource(null);
    if (!selectedId) { setProductState(null); productReader.current = null; return; }
    setRecovering(records => {
      const record = records[selectedId];
      return record?.reopened ? { ...records, [selectedId]: { ...record, reopened: false } } : records;
    });
    const reader = createProductReader({ matterId: matter.id, productId: selectedId, version: expectedVersion }, state => {
      if (state.status !== 'ready') setSource(null);
      if (state.status === 'failed' && state.accessUnavailable) forgetRecovery(selectedId);
      setProductState(state);
    });
    productReader.current = reader; void reader.load();
    return () => { reader.close(); if (productReader.current === reader) productReader.current = null; };
  }, [selectedId, matter.id, expectedVersion, listedRevision, listedStatus]);
  async function start(event: FormEvent) { event.preventDefault(); setBusy(true); setError(''); try { const run = await post<ResearchRun>(`${base}/research`, { question, as_of: asOf || null }); setRuns((prev) => [run, ...prev]); if (run.product_id) setSelectedId(run.product_id); await onChange(); setQuestion(''); } catch (cause) { setError(messageOf(cause)); } finally { setBusy(false); } }
  async function cancel(run: ResearchRun) { setError(''); try { const updated = await post<ResearchRun>(`${base}/research/${encodeURIComponent(run.id)}/cancel`, {}); setRuns((old) => old.map((item) => item.id === updated.id ? updated : item)); await onChange(); } catch (cause) { setError(messageOf(cause)); } }
  async function review(claimId: string, decision: 'approve' | 'reject', note: string) {
    const reader = productReader.current;
    if (!product || !canReview || recovery || reviewInFlight.current || !reader?.active || reader.key !== selectionKey) return;
    reviewInFlight.current = true;
    setReviewing(true);
    setError('');
    try {
      try {
        await post(`${base}/products/${encodeURIComponent(product.id)}/review`, { claim_id: claimId, decision, note });
      } catch (cause) {
        const accessError = cause instanceof ApiError && [401, 403, 404].includes(cause.status);
        const conflict = accessError ? { kind: 'rejected' as const, message: cause.message } : researchReviewConflict(cause, product.id);
        if (!conflict) throw cause;
        setRecovering(records => ({ ...records, [product.id]: { conflict, version: product.version, claimId, note: accessError ? '' : note, reopened: false } }));
        if (accessError && productReader.current === reader && reader.active) await reader.load();
        return;
      }
      if (productReader.current !== reader || !reader.active) return;
      await reader.load();
      if (productReader.current === reader && reader.active) {
        try { await onChange(); }
        catch { if (productReader.current === reader && reader.active) setError('İnceleme kaydedildi. Çalışma alanı listesi yenilenemedi.'); }
      }
    } finally {
      reviewInFlight.current = false;
      setReviewing(false);
    }
  }
  async function reopenReview() {
    const reader = productReader.current;
    if (!recovery || !reader?.active || reader.key !== selectionKey) return;
    const reopened = await reader.load(minimumRevision);
    if (reopened && productReader.current === reader && reader.active) {
      setRecovering(records => records[selectedId] === recovery
        ? { ...records, [selectedId]: { ...recovery, reopened: true } } : records);
    }
  }
  function restartReview() {
    if (!recovery?.reopened || !canReview || !product?.claims.some(claim => claim.id === recovery.claimId)) return;
    forgetRecovery(selectedId);
  }
  function forgetRecovery(id: string) {
    setRecovering(records => {
      if (!records[id]) return records;
      const remaining = { ...records };
      delete remaining[id];
      return remaining;
    });
  }
  async function exportFile(format: 'docx' | 'pdf') {
    const reader = productReader.current;
    if (!product || !reader?.active || reader.key !== selectionKey) return;
    setExporting(format);
    setError('');
    try {
      await downloadProduct(matter.id, product.id, format);
    } catch (cause) {
      if (productReader.current !== reader || !reader.active) return;
      setError(messageOf(cause));
      if (cause instanceof ApiError && [401, 403, 404, 409].includes(cause.status)) await reader.load(minimumRevision);
    } finally {
      setExporting('');
    }
  }
  return <section className="research-workspace">
    <div className="section-heading"><div><h2>Araştırma ve hazırlık</h2><p className="small muted">Sorunuzu, kullanılacak tarihi ve beklediğiniz çıktıyı tanımlayın.</p></div>{demo && <Badge>Örnek çıktı modu</Badge>}</div>
    <SectionIndex items={[{id:'research-question',label:'Yeni araştırma'},{id:'research-runs',label:'Çalışmalar'},{id:'research-output',label:'Kayıtlı çıktı'},{id:'research-gateway',label:'Dış kaynak denetimi'}]} />
    {error && <Notice error>{error}</Notice>}
    <section id="research-question" tabIndex={-1} aria-label="Yeni araştırma"><form className="research-form" onSubmit={start}><Field label="Çalışma sorunuz">{(id) => <textarea id={id} required rows={3} placeholder="Örn. Belgelerdeki ödeme yükümlülüklerini ve eksik dayanakları inceleyerek bir hazırlık notu oluştur." value={question} onChange={(event) => setQuestion(event.target.value)} />}</Field><div className="research-form-bottom"><Field label="Hukukun uygulanacağı tarih" hint="Araştırılacak hukuk tarihi; belgenin yüklenme tarihi değildir.">{(id) => <input id={id} type="date" value={asOf} onChange={(event) => setAsOf(event.target.value)} />}</Field><button className="button primary" disabled={busy}>{busy ? 'Başlatılıyor…' : 'Hazırlığı başlat'}<Icon name="arrow" size={17} /></button></div>{demo && <p className="small muted">Demo çalışması arayüz akışını gösterir. Üretilen örnek metin bir hukuki değerlendirme veya canlı model kanıtı değildir.</p>}</form></section>
    <section id="research-runs" tabIndex={-1} aria-label="Araştırma çalışmaları">{pollError && <Notice error>Çalışma durumu yenilenemedi: {pollError} <button className="text-button" onClick={() => { setPollError(''); onChange().catch((cause) => setPollError(messageOf(cause))); }}>Durumu yenile</button></Notice>}
    {runs.length > 0 && <Detail title={`Araştırma çalışmaları (${runs.length})`} open={runs.some((run) => isRunning(run.status))}><div className="run-list">{runs.map((run) => <div className="run-row" key={run.id}><div><strong>{run.question}</strong><span className="small muted">{formatDate(run.created_at, true)}</span>{run.error && <p className="error-text">{run.error}</p>}{run.status === 'cancelling' && <p className="small muted" role="status">İptal isteği alındı. Devam eden işlemin bitmesi bekleniyor; yeni çıktı kaydedilmeyecek.</p>}</div><Badge status={run.status} />{isRunning(run.status) ? <button className="text-button" disabled={run.status === 'cancelling'} onClick={() => void cancel(run)}>{run.status === 'cancelling' ? 'Durduruluyor…' : 'İptal et'}</button> : run.product_id ? <button className="text-button" onClick={() => setSelectedId(run.product_id!)}>Çıktıyı aç<Icon name="arrow" size={15} /></button> : null}</div>)}</div></Detail>}
    {!runs.length && <p className="small muted">Henüz araştırma çalışması yok. Yeni çalışma başlatıldığında durumu burada izleyebilirsiniz.</p>}</section>
    <section id="research-output" tabIndex={-1} aria-label="Kayıtlı hazırlık çıktısı"><div className="section-heading"><h2>Kayıtlı hazırlık çıktısı</h2></div>
    <ResearchOutputPicker products={matter.products || []} selectedId={selectedId} onSelect={setSelectedId} />
    {recovery && !(selectedRead?.status === 'failed' && selectedRead.accessUnavailable) && <ResearchReviewRecovery review={recovery} reading={productLoading}
      canRestart={Boolean(recovery.reopened && canReview && product?.claims.some(claim => claim.id === recovery.claimId))}
      onRead={() => void reopenReview()} onRestart={restartReview} />}
    {productLoading ? <Loading label="Hazırlık çıktısı açılıyor…" /> : selectedRead?.status === 'failed' ? <Notice error><strong>Seçili çıktı açılamadı.</strong><p>{selectedRead.message}</p><p>Önceki çıktı gösterilmiyor. Seçiminizi koruyarak yeniden deneyebilirsiniz.</p><button className="button secondary" onClick={() => void productReader.current?.load(minimumRevision)}>Seçili çıktıyı yeniden aç</button></Notice> : product ? <article className="preparation-product"><header className="product-heading"><div><p className="eyebrow">HAZIRLIK ÇIKTISI · SÜRÜM {product.version}</p><h2>{product.title}</h2><span className="small muted">{formatDate(product.created_at, true)}</span></div><Badge status={product.status} /></header>{['stale', 'invalidated'].includes(product.status) && <Notice error>{product.stale_reason || 'Bu çalışmanın dayanakları değişti. Güncel dayanaklarla yeni bir araştırma başlatın.'}</Notice>}<p className="product-summary">{product.summary}</p>
    <div className="section-heading compact"><h3>İddialar ve dayanaklar</h3><span className="small muted">{product.claims.filter((claim) => claim.review_status === 'approved').length} / {product.claims.length} uygun bulundu</span></div>{product.claims.length ? <div className="claim-list">{product.claims.map((claim, index) => <ClaimReview key={`${selectionKey}:${claim.id}`} claim={claim} index={index} onReview={review} onSource={setSource} stale={!canReview || Boolean(recovery) || reviewing} />)}</div> : <Empty title="İncelenecek iddia oluşturulmadı.">Mevcut veriyle desteklenebilir bir sonuç bulunmamış olabilir. Kapsam ve eksik bilgi bölümünü inceleyin.</Empty>}
    {product.issues.length > 0 && <Detail title={`Hukuki meseleler ve eksik bilgiler (${product.issues.length})`}><div className="issue-list">{product.issues.map((issue, index) => <section key={index}><h4>{issue.label}</h4>{issue.missing_facts.length > 0 && <><span className="small-label">EKSİK OLGULAR</span><ul>{issue.missing_facts.map((item, itemIndex) => <li key={itemIndex}>{item}</li>)}</ul></>}{issue.counterarguments.length > 0 && <><span className="small-label">KARŞI ARGÜMANLAR</span><ul>{issue.counterarguments.map((item, itemIndex) => <li key={itemIndex}>{item}</li>)}</ul></>}</section>)}</div></Detail>}
    <Detail title="Bu çalışmanın kaynak kapsamı" open={product.coverage.gaps.length > 0}><div className="two-column-details"><div><h4>Aranan kaynaklar</h4>{product.coverage.searched.length ? <ul>{product.coverage.searched.map((item, index) => <li key={index}>{item}</li>)}</ul> : <p>Aranan kaynak kaydı bulunmuyor.</p>}</div><div><h4>Kapsam ve bilgi eksikleri</h4>{product.coverage.gaps.length ? <ul>{product.coverage.gaps.map((item, index) => <li key={index}>{item}</li>)}</ul> : <p>Bildirilen boşluk yok. Bu durum kapsamın eksiksiz olduğunu göstermez.</p>}</div></div></Detail>
    {product.context_pack && <EvidenceContextPanel pack={product.context_pack} evidence={product.evidence || []} onSource={setSource} />}
    {product.graph_paths !== undefined && <JsonDetails value={product.graph_paths} title="Referans keşfinde kullanılan graf yolları" />}
    {product.authority_candidates && <AuthorityCandidatesPanel candidates={product.authority_candidates} />}
    {product.source_candidates && <SourceCandidatesPanel candidates={product.source_candidates} />}
    <JsonDetails value={product.snapshots} title="Çalışmada kullanılan sürümler" />
    <div className="export-bar"><div><strong>Çalışmanızı dışa aktarın.</strong><p className="small muted">İnceleme durumu ve kaynaklar çıktıyla birlikte korunur.</p></div><div className="button-group"><button className="button secondary" disabled={Boolean(exporting)} onClick={() => void exportFile('docx')}><Icon name="download" size={17} />{exporting === 'docx' ? 'Hazırlanıyor…' : 'Word'}</button><button className="button secondary" disabled={Boolean(exporting)} onClick={() => void exportFile('pdf')}><Icon name="download" size={17} />{exporting === 'pdf' ? 'Hazırlanıyor…' : 'PDF'}</button></div></div>
    </article> : wrongRecoveryVersion ? <Notice error>Okunan çıktı sürümü, inceleme isteğiyle eşleşmiyor.</Notice> : recovery ? null : <Empty title="Hazırlık çıktınız burada oluşacak.">Sorunuzu belirlediğinizde çalışma durumu, dayanaklar, eksikler ve inceleme adımları bu alanda görünür.</Empty>}</section>
    {product && source && <EvidenceViewer key={`${selectionKey}:${source}`} matter={matter} evidenceId={source} onClose={() => setSource(null)} />}
    <section id="research-gateway" tabIndex={-1} aria-label="Dış kaynak denetimi"><GatewayPanel matterId={matter.id} /></section>
  </section>;
}

export function AuthorityCandidatesPanel({ candidates }: { candidates: AuthorityCandidates }) {
  return <section className="authority-candidates">
    <Detail title="Kamu kaynak adayları">
      <p className="small muted">Yerel kamu kaynaklarında bulunan bu pasajlar araştırma adayıdır. Bir pasajın bulunması veya kaynak inceleme durumu, bu dosyaya hukuken uygulanabilir olduğunu göstermez.</p>
      {candidates.hits.length > 0 ? <div className="authority-candidate-list">{candidates.hits.map((hit) => <article className="authority-candidate" key={`${hit.source_version_id}:${hit.passage_id}`}>
        <div className="section-heading compact"><h3>{hit.title || 'Başlıksız kaynak'}</h3><Badge status={hit.review_status} /></div>
        <SourceExcerpt name={hit.title || 'Başlıksız kaynak'} location={locatorText(hit.locator)} text={hit.text} label="Araştırma adayı" />
        <Detail title="Kaynak ve sürüm bilgileri"><dl className="definition-grid">
          <div><dt>Kaynak kimliği</dt><dd className="reference-id">{hit.authority_id || 'Belirtilmedi'}</dd></div>
          <div><dt>Pasaj kimliği</dt><dd className="reference-id">{hit.passage_id}</dd></div>
          <div><dt>Kaynak sürümü</dt><dd className="reference-id">{hit.source_version_id || 'Belirtilmedi'}</dd></div>
          <div><dt>Kaynak özeti (SHA-256)</dt><dd className="reference-id">{hit.source_sha256 || 'Belirtilmedi'}</dd></div>
          <div><dt>Geçerlilik başlangıcı</dt><dd>{formatDate(hit.valid_from)}</dd></div>
          <div><dt>Geçerlilik sonu</dt><dd>{hit.validity_end_status === 'open_ended' ? 'Açık uçlu · denetim tarihiyle sınırlı' : formatDate(hit.valid_to)}</dd></div>
          {hit.source_url && <div className="span-full"><dt>Kaynak adresi · yalnızca kayıt bilgisi</dt><dd className="reference-id">{hit.source_url}</dd></div>}
        </dl><p className="small muted">Dış kaynağa erişim, araştırma geçidinin denetimine tabidir.</p></Detail><ValidityDetails validity={hit} />
      </article>)}</div> : <p className="small muted">Bu çalışma için nitelikli kamu kaynağı adayı alınamadı. Yerel derlemin edinim ve doğrulama durumunu kontrol edin.</p>}
      {candidates.limitations.length > 0 && <><h4>Aramanın sınırlılıkları</h4><ul>{candidates.limitations.map((limitation, index) => <li key={index}>{limitation}</li>)}</ul></>}
      <JsonDetails title="Arama kapsamı ve sürüm kaydı" value={{ coverage: candidates.coverage, snapshot: candidates.snapshot }} />
    </Detail>
    {candidates.hits.length === 0 && <p className="small muted authority-empty-note">Kamu kaynağı adayı bulunmadı. Bu durum, ilgili mevzuat veya emsal olmadığı anlamına gelmez.</p>}
  </section>;
}

function ClaimReview({ claim, index, onReview, onSource, stale }: { claim: Claim; index: number; onReview: (id: string, decision: 'approve' | 'reject', note: string) => Promise<void>; onSource: (id: string) => void; stale: boolean }) {
  const [editing, setEditing] = useState(false); const [note, setNote] = useState(claim.review_note || ''); const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  async function decide(decision: 'approve' | 'reject') { setBusy(true); setError(''); try { await onReview(claim.id, decision, note); setEditing(false); } catch (cause) { setError(messageOf(cause)); } finally { setBusy(false); } }
  return <section className="claim"><span className="claim-number">{String(index + 1).padStart(2, '0')}</span><div className="claim-content"><div className="claim-meta"><span className="small-label">{statusLabel(claim.kind)}</span><Badge status={claim.review_status} /></div><p>{claim.text}</p><div className="claim-sources">{claim.evidence_ids.length ? claim.evidence_ids.map((id, sourceIndex) => <button key={id} className="source-link" onClick={() => onSource(id)}><Icon name="file" size={14} />Dayanak {sourceIndex + 1}</button>) : <span className="small error-text">Kaynak bağlantısı yok</span>}</div>{claim.review_note && !editing && <p className="review-note"><strong>İnceleme notu:</strong> {claim.review_note}</p>}{error && <Notice error>{error}</Notice>}{editing && <Field label="İnceleme notunuz">{(id) => <textarea id={id} autoFocus rows={2} maxLength={2000} disabled={busy || stale} value={note} onChange={(event) => setNote(event.target.value)} placeholder="Düzeltilmesi gereken noktayı ve gerekçesini belirtin." />}</Field>}<div className="claim-actions"><button className="text-button" disabled={busy || stale || claim.review_status === 'approved'} onClick={() => void decide('approve')}><Icon name="check" size={16} />{busy ? 'Kaydediliyor…' : 'Uygun bul'}</button>{editing ? <><button className="text-button danger" disabled={busy || !note.trim() || stale} onClick={() => void decide('reject')}>Düzeltme notunu kaydet</button><button className="text-button" disabled={busy} onClick={() => setEditing(false)}>Vazgeç</button></> : <button className="text-button" disabled={busy || stale} onClick={() => setEditing(true)}>Düzeltme iste</button>}</div></div></section>;
}
