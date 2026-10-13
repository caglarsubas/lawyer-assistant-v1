import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import type { SourceCandidates } from '../../types';
import { SourceCandidatesPanel } from './SourceCandidatesPanel';

const candidates: SourceCandidates = {
  hits: [{ passage_id: 'urn:test:passage', document_id: 'urn:test:source', source_version_id: 'urn:test:text',
    text: '<img src=x onerror=alert(1)> TEST ONLY quoted source', locator: 'page 1',
    source_sha256: 'a'.repeat(64), quote_sha256: 'b'.repeat(64), start_offset: 0, end_offset: 20 }],
  coverage: { status: 'partial', scan_complete: false }, snapshot: { release_id: 'c'.repeat(64) },
  limitations: ['TEST ONLY limited corpus'],
};

describe('independent source nominations', () => {
  it('shows inert exact quotations, unknown legal effects and explicit coverage limits', () => {
    const html = renderToStaticMarkup(<SourceCandidatesPanel candidates={candidates} />);
    expect(html).toContain('&lt;img');
    expect(html).not.toContain('<img');
    expect(html).not.toContain('<a ');
    expect(html).toContain('urn:test:text');
    expect(html).toContain('Değerlendirilmedi');
    expect(html).toContain('Bilinmiyor');
    expect(html).toContain('Ulusal hukuk derleminin tamlığı bilinmiyor');
    expect(html).toContain('Tarama veya çıktı sınırına ulaşıldı');
  });
  it('shows permission withholding without treating no hits as absence of relevant law', () => {
    const html = renderToStaticMarkup(<SourceCandidatesPanel candidates={{ ...candidates, hits: [], coverage: { status: 'unavailable' } }} />);
    expect(html).toContain('kaynak pasajları gösterilmiyor');
    expect(html).toContain('ilgili mevzuat veya emsal bulunmadığını göstermez');
    expect(html).not.toContain('TEST ONLY quoted source');
  });
});
