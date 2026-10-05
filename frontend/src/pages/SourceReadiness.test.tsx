import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { onUnauthorized } from '../api';
import type { PublicSourceCatalog } from '../types';
import { fetchSourceCatalog, servingReleaseFromCoverage, ServingRelease, SourceCatalog } from './SourceReadiness';

const catalog: PublicSourceCatalog = {
  items: [{ id: 'source-1', title: '<script>untrusted source title</script>', source_url: 'javascript:alert(1)', source_version_id: 'version-1', domain: 'contracts', acquired_at: '2026-10-04T08:00:00Z', rights_status: 'rights_pending', review_status: 'legal_review_pending', passage_count: 200, publication_status: 'staged' }],
  limitations: ['Hazırlık kayıtları araştırmada yayımlanmış hukuki dayanak değildir.'],
};

describe('source release and staging evidence', () => {
  const fetchMock = vi.fn<typeof fetch>();
  beforeEach(() => { vi.stubGlobal('fetch', fetchMock); fetchMock.mockReset(); onUnauthorized(); });
  afterEach(() => { vi.unstubAllGlobals(); onUnauthorized(); });

  it('keeps missing or malformed release observations unknown instead of declaring no release exists', () => {
    for (const value of [null, {}, { serving_release: null }, { serving_release: { status: 'something_else' } }]) {
      expect(servingReleaseFromCoverage(value)).toBeNull();
    }
    expect(renderToStaticMarkup(<ServingRelease release={null} />)).toContain('Sürüm durumu bilinmiyor');
    const release = servingReleaseFromCoverage({ serving_release: { status: 'verified', legal_review_verified: 'true', release_id: 'a'.repeat(64) } });
    expect(release?.legal_review_verified).toBeUndefined();
  });

  it('separates an immutable verified release from legal review and legal correctness', () => {
    const markup = renderToStaticMarkup(<ServingRelease release={{ status: 'verified', release_id: 'a'.repeat(64), ontology_sha256: 'b'.repeat(64), legal_review_verified: false }} />);
    expect(markup).toContain('Sürüm bütünlüğü doğrulandı');
    expect(markup).toContain('Hukuki inceleme kaydı</dt><dd>Doğrulanmadı');
    expect(markup).toContain('hukuki sonuçların doğruluğunu garanti etmez');
    expect(markup).toContain('a'.repeat(64));
    expect(markup).not.toContain('<details class="details" open');
  });

  it('distinguishes an unconfigured serving release from a failed verification', () => {
    const missing = renderToStaticMarkup(<ServingRelease release={{ status: 'unconfigured' }} />);
    const failed = renderToStaticMarkup(<ServingRelease release={{ status: 'unavailable', reason: 'Beklenen sürüm kaydı eşleşmiyor.' }} />);
    expect(missing).toContain('Etkin sürüm tanımlanmadı');
    expect(failed).toContain('Sürüm doğrulanamadı');
    expect(failed).toContain('Beklenen sürüm kaydı eşleşmiyor.');
    expect(failed).not.toContain('Sürüm bütünlüğü doğrulandı');
  });

  it('shows staging, rights and review independently and never turns provenance into executable content or external navigation', () => {
    const markup = renderToStaticMarkup(<SourceCatalog state={{ status: 'loaded', catalog }} onRetry={() => undefined} />);
    expect(markup).toContain('Hazırlık kaydı');
    expect(markup).toContain('Kullanım hakları inceleme bekliyor');
    expect(markup).toContain('Hukuki inceleme bekliyor');
    expect(markup).toContain('Hazırlanan pasajlar</dt><dd>200');
    expect(markup).toContain('derlemin tamlığı anlamına gelmez');
    expect(markup).toContain('&lt;script&gt;');
    expect(markup).not.toContain('<script>');
    expect(markup).not.toContain('href="javascript:');
    expect(markup).not.toContain('<details class="details" open');
  });

  it('converts staging-only 403 into a useful limited-access state without ending the lawyer session', async () => {
    const expired = vi.fn(); onUnauthorized(expired);
    fetchMock.mockResolvedValue(new Response(JSON.stringify({ detail: 'Curator role required' }), { status: 403 }));
    const state = await fetchSourceCatalog();
    expect(fetchMock.mock.calls[0][0]).toBe('/api/v1/public-sources');
    expect(state).toEqual({ status: 'restricted' });
    expect(expired).not.toHaveBeenCalled();
    const markup = renderToStaticMarkup(<><ServingRelease release={{ status: 'unconfigured' }} /><SourceCatalog state={state} onRetry={() => undefined} /></>);
    expect(markup).toContain('yalnızca yönetici ve küratörler');
    expect(markup).toContain('incelemeye devam edebilirsiniz');
    expect(markup).toContain('Etkin sürüm tanımlanmadı');
    expect(markup).not.toContain('Henüz görünür hazırlık kaydı yok');
  });

  it('does not convert an unavailable staging service into an empty catalog or restricted access', async () => {
    fetchMock.mockResolvedValue(new Response(JSON.stringify({ detail: 'Kaynak deposuna ulaşılamıyor.' }), { status: 503 }));
    const state = await fetchSourceCatalog();
    expect(state).toEqual({ status: 'failed', message: 'Kaynak deposuna ulaşılamıyor.' });
    const markup = renderToStaticMarkup(<SourceCatalog state={state} onRetry={() => undefined} />);
    expect(markup).toContain('Kaynak kaydını yenile');
    expect(markup).not.toContain('Henüz görünür hazırlık kaydı yok');
  });

  it('keeps an empty acquisition catalog distinct from the absence of legal authorities', () => {
    const markup = renderToStaticMarkup(<SourceCatalog state={{ status: 'loaded', catalog: { items: [], limitations: [] } }} onRetry={() => undefined} />);
    expect(markup).toContain('Henüz görünür hazırlık kaydı yok');
    expect(markup).toContain('kaynak bulunmadığı anlamına gelmez');
  });
});
