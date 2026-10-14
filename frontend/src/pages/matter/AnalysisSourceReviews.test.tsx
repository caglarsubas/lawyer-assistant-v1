import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import AnalysisSourceReviews from './AnalysisSourceReviews';
import type { AnalysisRecord } from './analysisTypes';
import { SourceContextView } from './SourceReviewEvidence';
import { view } from './sourceReviewFixtures';

describe('lawyer-facing private source review', () => {
  it('loads no source content automatically and keeps the matter scope explicit', () => {
    const html = renderToStaticMarkup(<AnalysisSourceReviews matterId="matter1" record={{ id: 'analysis1', latest_version_id: 'v1' } as AnalysisRecord} />);
    expect(html).toContain('Araştırma pasajlarını getir'); expect(html).toContain('Kaynak seçimi geçmişini getir');
    expect(html).not.toContain('PRIVATE analysis step'); expect(html).not.toContain('<details open');
  });
  it('renders exact inert source text, separate interpretations and unknown legal effects', () => {
    const html = renderToStaticMarkup(<SourceContextView value={view()} />);
    expect(html).toContain('Özgün alıntı'); expect(html).toContain('&lt;img'); expect(html).not.toContain('<img'); expect(html).not.toContain('<script>');
    expect(html).toContain('Kaynak seçimini yapanın yorumu'); expect(html).toContain('Karşı dayanak adayı'); expect(html).toContain('Bağımsız incelemecinin kararı');
    expect(html).toContain('kesinleşme bilinmiyor'); expect(html).toContain('Ulusal derlemin tamlığı bilinmiyor'); expect(html).toContain('version-author');
  });
  it('withholds the full source, analysis target and review notes when a stale payload remains in memory', () => {
    for (const state of ['stale', 'withheld']) {
      const value = view(); value.freshness.status = state;
      const html = renderToStaticMarkup(<SourceContextView value={value} />);
      expect(html).toContain('Önceki kayıt korunur'); expect(html).not.toContain('PRIVATE analysis step'); expect(html).not.toContain('TEST ONLY review note');
      expect(html).not.toContain('urn:test:version'); expect(html).not.toContain('Özgün alıntı');
    }
    const value = view(); value.public_source_access = false;
    expect(renderToStaticMarkup(<SourceContextView value={value} />)).not.toContain('PRIVATE analysis step');
  });
  it('labels old decisions as history without promoting their export eligibility', () => {
    const value = view(); value.review.is_latest = false;
    expect(renderToStaticMarkup(<SourceContextView value={value} />)).toContain('Güncel kararın yerine geçmez');
  });
});
