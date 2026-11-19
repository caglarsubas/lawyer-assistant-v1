import { useEffect, useMemo, useRef, useState } from 'react';
import { ApiError, fetchSavedAnalysisOriginal, request } from '../../api';
import { Icon, Loading, Notice } from '../../components';
import { SourceExcerpt } from '../../SourceExcerpt';
import { locatorText, messageOf } from '../../utils';
import type { AnalysisContent, AnalysisReviewContext } from './analysisTypes';
import { PdfPreview } from './OriginalPreview';
import PunctuationObservations from './PunctuationObservations';
import type { PunctuationSourcePins } from './punctuationTypes';

export interface SavedAnalysisSourceSelection {
  analysisId: string;
  versionId: string;
  version: number;
  evidence: Omit<AnalysisContent['evidence'][number], 'full_passage_length'>;
  contentSha256?: string;
}

const isSha256 = (value: unknown): value is string => typeof value === 'string' && value.length === 64 && !/[^a-f0-9]/.test(value);

export async function loadSavedAnalysisSource(matterId: string, selection: SavedAnalysisSourceSelection, signal: AbortSignal) {
  const { analysisId, versionId, evidence } = selection;
  const locator = typeof evidence.locator === 'string' ? /^Sayfa ([1-9][0-9]{0,5})$/.exec(evidence.locator) : null;
  const unavailable = () => new ApiError('Analiz sürümünün özgün sayfa bağı doğrulanamadı.', 409);
  if (!locator || locator[0] !== evidence.locator || !isSha256(evidence.document_sha256)
      || !isSha256(evidence.quote_sha256) || !Number.isSafeInteger(evidence.document_revision)
      || evidence.document_revision < 1) throw unavailable();

  const base = `/matters/${encodeURIComponent(matterId)}/analyses/${encodeURIComponent(analysisId)}`;
  const context = await request<AnalysisReviewContext>(`${base}/reviews/context?version_id=${encodeURIComponent(versionId)}`, { signal, redirect: 'error' });
  signal.throwIfAborted();
  if (context?.version_id !== versionId || !isSha256(context.content_sha256) || !Array.isArray(context.sources)
      || (selection.contentSha256 !== undefined && selection.contentSha256 !== context.content_sha256)) throw unavailable();
  const sources = context.sources.filter((item) => item.evidence_id === evidence.evidence_id);
  const source = sources[0];
  if (sources.length !== 1
      || source.document_id !== evidence.document_id || source.name !== evidence.name || source.locator !== evidence.locator
      || source.start !== evidence.start || source.end !== evidence.end || source.quote_sha256 !== evidence.quote_sha256) throw unavailable();

  const page = Number(locator[1]);
  const original = await fetchSavedAnalysisOriginal(`${base}/versions/${encodeURIComponent(versionId)}/evidence/${encodeURIComponent(evidence.evidence_id)}/original/${page}`, {
    contentSha256: context.content_sha256, quoteSha256: evidence.quote_sha256, documentSha256: evidence.document_sha256,
    documentRevision: evidence.document_revision, page,
  }, signal);
  return { ...original, page, contentSha256: context.content_sha256, documentSha256: evidence.document_sha256 };
}

export default function SavedAnalysisSource({ matterId, selection, onClose }: {
  matterId: string; selection: SavedAnalysisSourceSelection; onClose: () => void;
}) {
  return <SavedAnalysisSourceScope key={JSON.stringify([matterId, selection])} matterId={matterId} selection={selection} onClose={onClose} />;
}

function SavedAnalysisSourceScope({ matterId, selection, onClose }: {
  matterId: string; selection: SavedAnalysisSourceSelection; onClose: () => void;
}) {
  const [result, setResult] = useState<Awaited<ReturnType<typeof loadSavedAnalysisSource>> | null>(null);
  const [error, setError] = useState('');
  const region = useRef<HTMLElement>(null);
  const { evidence, version } = selection;
  const punctuationPins = useMemo<PunctuationSourcePins | null>(() => result ? {
    matterId, analysisId: selection.analysisId, versionId: selection.versionId, evidenceId: evidence.evidence_id,
    contentSha256: result.contentSha256, quoteSha256: evidence.quote_sha256, documentId: evidence.document_id,
    documentRevision: evidence.document_revision, documentSha256: result.documentSha256,
    page: result.page, pageCount: result.pageCount, quote: evidence.text,
  } : null, [matterId, selection, evidence, result]);

  useEffect(() => {
    const previousFocus = document.activeElement;
    region.current?.focus();
    return () => {
      if (previousFocus instanceof HTMLElement && previousFocus.isConnected && !previousFocus.closest('[hidden]')) previousFocus.focus();
    };
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    loadSavedAnalysisSource(matterId, selection, controller.signal).then((value) => {
      if (!controller.signal.aborted) setResult(value);
    }).catch((cause) => {
      if (!controller.signal.aborted) setError(messageOf(cause));
    });
    return () => controller.abort();
  }, [matterId, selection]);

  return <section ref={region} tabIndex={-1} className="source-inspector" aria-label="Kaydedilen özgün dayanak">
    <div className="section-heading">
      <h3>Kaydedilen özgün dayanak</h3>
      <button type="button" className="button secondary" onClick={onClose}><Icon name="close" size={16} />Dayanağı kapat</button>
    </div>
    <SourceExcerpt name={evidence.name} location={`${locatorText(evidence.locator)} · Belge sürümü ${evidence.document_revision}`}
      label={`Analiz sürümü ${version}`} text={evidence.text} />
    {error ? <Notice error>{error}</Notice> : result ?
      <>
      {punctuationPins && <PunctuationObservations pins={punctuationPins} />}
      <div className="original-preview">
        <p className="preview-caption">Alıntıyı özgün sayfayla karşılaştırın. Sayfanın tamamı gösterilir.</p>
        <PdfPreview blob={result.blob} name={evidence.name} initialPage={result.page} exactPageCount={result.pageCount} />
      </div></> : <Loading label="Kaydedilen özgün sayfa doğrulanıyor…" />}
  </section>;
}
