import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import AuthorityLineage from './AuthorityLineage';
import { pendingLineageReceipt, sourceBindingReason } from './lineageTypes';

describe('retained source binding renewal', () => {
  it('opens only on explicit action, declares limits, and does not fetch or render cached sources', () => {
    const html = renderToStaticMarkup(<AuthorityLineage matterId="m1" analysisId="a1" onSaved={async () => {}} />);
    expect(html).toContain('Yeniden inceleme için güncel taslak ve kaynakları getir');
    expect(html).toContain('Değişmiş veya izni kaldırılmış kaynaklar');
    expect(html).not.toContain('<form'); expect(html).not.toContain('<details open');
  });
  it('explains changed bindings in lawyer-facing terms and retains existing private messages', () => {
    expect(sourceBindingReason('authority_reviewer_access_changed')).toContain('inceleme erişimi değişti');
    expect(sourceBindingReason('authority_revalidated_analysis_changed')).toContain('taslak veya model katkısı değişti');
    expect(sourceBindingReason('Bağlı belge değişti.')).toBe('Bağlı belge değişti.');
  });
  it('recognizes only an exact committed pending renewal receipt', () => {
    const id = `arl-${'a'.repeat(20)}-${'b'.repeat(32)}`;
    expect(pendingLineageReceipt({ id, outcome: 'committed_needs_revalidation', needs_revalidation: true })).toBe(id);
    for (const value of [null, { id }, { id, outcome: 'failed', needs_revalidation: true }, { id: '../private', outcome: 'committed_needs_revalidation', needs_revalidation: true }]) expect(pendingLineageReceipt(value)).toBeNull();
  });
});
