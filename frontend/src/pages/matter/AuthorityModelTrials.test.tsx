import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import AuthorityModelTrials, { TrialSummary } from './AuthorityModelTrials';
import type { ModelTrialCapture, TrialSourceInput } from './authorityModelTypes';
import { renewedTrialSelection } from './authorityModelTypes';

describe('registered authority model trials', () => {
  it('maps sealed renewal dependencies to the exact strict selection fields', () => {
    const dependency = { context_id: 'c1', review_id: 'r1', review_sha256: 'a'.repeat(64),
      recipe: 'retained-original-recipe', source_version_id: 'v1', public_basis_sha256: 'b'.repeat(64) };
    expect(renewedTrialSelection(dependency, { id: 'renewal1', sha256: 'c'.repeat(64) })).toEqual({
      kind: 'admitted_renewal', context_id: 'c1', review_id: 'r1', review_sha256: 'a'.repeat(64),
      renewal_id: 'renewal1', renewal_sha256: 'c'.repeat(64),
    });
  });
  it('requires explicit input and history actions before fetching or inference', () => {
    const html = renderToStaticMarkup(<AuthorityModelTrials matterId="m1" analysisId="a1" />);
    expect(html).toContain('Kayıtlı model dayanak denemelerini getir');
    expect(html).not.toContain('<form');
    expect(html).not.toContain('Kayıtlı iki kolu yerel modelde çalıştır');
  });
  it('shows human findings without selecting one automatically', () => {
    const sourceInput: TrialSourceInput = { selection: { kind: 'original_review', context_id: 'c1', review_id: 'r1', review_sha256: 'a'.repeat(64) },
      dimensions: { applicability: 'Uygulanabilirlik', history: 'Tarih', conditions: 'Koşullar', relationship: 'İlişki', adverse: 'Karşı dayanak', certainty: 'Kesinlik' },
      assessment: { note: 'Fixture only', review_seconds: null, sources: [{ assertion_id: 's1', passage_id: 'p1', authority_id: 'law1', target_ids: ['conclusion'], observations: [{ dimension: 'history', outcome: 'unresolved', note: 'History remains unknown' }] }] } };
    const html = renderToStaticMarkup(<AuthorityModelTrials matterId="m1" analysisId="a1" sourceInput={sourceInput} />);
    expect(html).toContain('History remains unknown'); expect(html).toContain('En fazla beş');
    expect(html).not.toContain('checked=""'); expect(html).not.toContain('value="real"');
    expect(html).toContain('disabled=""');
  });
  it('withholds protocol text even if the server supplied residual fields', () => {
    const value = { public_source_access: false, protocol: { title: 'SECRET fixture title' } } as ModelTrialCapture;
    const html = renderToStaticMarkup(<TrialSummary value={value} />);
    expect(html).toContain('bekletiliyor'); expect(html).not.toContain('SECRET');
  });
});
