import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import AnalysisSourceReviews from './matter/AnalysisSourceReviews';
import { NavigationSummary } from './SelectedSourceReviewPage';
import { sourceContextHref, sourceNavigationSelection, verifyNavigation, type NavigationMetadata, type SourceTarget } from './sourceContextNavigationTypes';

const target: SourceTarget = { kind: 'selected', matter_id: 'matter1', analysis_id: 'analysis1', context_id: `sac-${'a'.repeat(20)}-${'b'.repeat(32)}` };
const meta = (): NavigationMetadata => ({ recipe: 'private-source-context-navigation-v1', matter_id: target.matter_id, analysis_id: target.analysis_id,
  context_id: target.context_id, observed_at: '2026-10-14T01:00:00Z', analysis: { id: target.analysis_id, current_version_id: 'new-version', revision: 3 },
  context: { id: target.context_id, version_id: 'old-version', manifest_sha256: 'c'.repeat(64), recorded_at: '2026-10-13T01:00:00Z' },
  admission: { context_state: 'complete', review_state: 'complete' }, historical_review: { state: 'reviewed_conditional', id: `sar-${'d'.repeat(20)}-${'e'.repeat(32)}`, recorded_at: '2026-10-13T02:00:00Z' },
  version_relation: 'different', integrity: 'verified', tools_available: true, source_verification: 'not_checked', legal_readiness: 'not_established', qualification_granted: false });
const query = `tab=source-review&analysis=${target.analysis_id}&source_context=${target.context_id}`;

describe('exact source context navigation', () => {
  it('round trips the complete local target without substituting list position or latest version', () => {
    const href = sourceContextHref(target.matter_id, target.analysis_id, target.context_id)!;
    const [path, params] = href.slice(1).split('?');
    expect(sourceNavigationSelection(path, new URLSearchParams(params))).toEqual(target);
    expect(sourceNavigationSelection('/workspaces/matter1', new URLSearchParams(query))).toEqual(target);
  });
  it.each(['', 'tab=practice', 'tab=documents&document=1'])('keeps ordinary browsing when there is no source selection intent', query => {
    expect(sourceNavigationSelection('/matters/matter1', new URLSearchParams(query))).toEqual({ kind: 'none' });
  });
  it.each([
    query + '&analysis=other', query + '&source_context=' + target.context_id, query + '&tab=source-review', query + '&document=other',
    query + '&work=other', query + '&new=1', query.replace('tab=source-review', 'tab=practice'), 'tab=source-review',
    query.replace(target.context_id, '../foreign'), query.replace('analysis=analysis1', 'analysis=%2Fforeign'),
  ])('rejects duplicate, incomplete or mixed selections without broad matter fallback', params => {
    expect(sourceNavigationSelection('/matters/matter1', new URLSearchParams(params))).toEqual({ kind: 'invalid' });
  });
  it.each(['/matters/%ZZ', '/matters/matter1/extra', '/work/matter1', '/matters/../', '/matters/'])('rejects malformed or unrelated route identities', path => {
    expect(sourceNavigationSelection(path, new URLSearchParams(query))).toEqual({ kind: 'invalid' });
  });
  it('shows independent historical status and both version identities, without source verdict or review action', () => {
    const value = meta(); verifyNavigation(value, target); const html = renderToStaticMarkup(<NavigationSummary value={value} />);
    expect(html).toContain(target.context_id); expect(html).toContain('old-version'); expect(html).toContain('new-version');
    expect(html).toContain('Koşullu inceleme kaydedildi'); expect(html).toContain('Kamu kaynakları kontrol edilmedi');
    expect(html).not.toContain('PRIVATE SOURCE NOTE'); expect(html).not.toContain('<form'); expect(html).not.toContain('indir');
  });
  it('distinguishes an incomplete review admission from a historical positive decision', () => {
    const value = meta(); value.admission.review_state = 'pending'; verifyNavigation(value, target);
    const html = renderToStaticMarkup(<NavigationSummary value={value} />);
    expect(html).toContain('Koşullu inceleme kaydedildi'); expect(html).toContain('Karar kabulü: Son izin kontrolü bekliyor');
  });
  it('pinned tools start without quotes, inputs or another source-context selector', () => {
    const value = meta(); const html = renderToStaticMarkup(<AnalysisSourceReviews matterId={target.matter_id}
      record={{ id: target.analysis_id, latest_version_id: value.analysis.current_version_id! }}
      selectedContext={{ id: target.context_id, version_id: value.context.version_id!, manifest_sha256: value.context.manifest_sha256! }} />);
    expect(html).toContain('Güncel kaynak ve karar bağlarını kontrol et'); expect(html).toContain('Bağımsız karar geçmişini getir');
    expect(html).not.toContain('Araştırma pasajlarını getir'); expect(html).not.toContain('Kaynak seçimi geçmişini getir');
    expect(html).not.toContain('Kaynak seçimini önizle'); expect(html).not.toContain('<textarea'); expect(html).not.toContain('TEST ONLY');
  });
  it.each([
    (v: NavigationMetadata) => { v.context_id = `sac-${'f'.repeat(20)}-${'a'.repeat(32)}`; },
    (v: NavigationMetadata) => { v.analysis.id = 'foreign'; }, (v: NavigationMetadata) => { v.context.manifest_sha256 = null; },
    (v: NavigationMetadata) => { v.version_relation = 'same'; }, (v: NavigationMetadata) => { v.tools_available = true; v.integrity = 'unavailable'; },
    (v: NavigationMetadata) => { v.source_verification = 'checked' as never; }, (v: NavigationMetadata) => { v.qualification_granted = true as never; },
    (v: NavigationMetadata) => { Object.assign(v.context, { quote: 'PRIVATE source' }); },
    (v: NavigationMetadata) => { Object.assign(v.historical_review, { note: 'PRIVATE review' }); },
    (v: NavigationMetadata) => { v.observed_at = 'unknown'; },
  ])('closes the handoff on identity/scope mismatches, forbidden content or false readiness', mutate => {
    const value = meta(); mutate(value); expect(() => verifyNavigation(value, target)).toThrow();
  });
  it('allows unavailable integrity metadata without inventing a fallback version', () => {
    const value = meta(); Object.assign(value, { integrity: 'unavailable', tools_available: false, version_relation: 'unknown' });
    Object.assign(value.context, { version_id: null, manifest_sha256: null }); value.analysis.current_version_id = null;
    value.admission.context_state = 'unavailable'; verifyNavigation(value, target);
  });
});
