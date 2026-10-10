import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import AuthorityModelCohorts, { ModelCohortContent, ModelCohortSummary } from './AuthorityModelCohorts';
import { pendingModelCohort } from './authorityModelCohortTypes';
import type { ModelCohortReport, ModelCohortView } from './authorityModelCohortTypes';

describe('confidential model authority groups', () => {
  it('does not select or fetch trials before explicit action', () => {
    const html = renderToStaticMarkup(<AuthorityModelCohorts matterId="synthetic-case" />);
    expect(html).toContain('Model dayanak denemelerini getir');
    expect(html).not.toContain('checked=""'); expect(html).toContain('disabled=""');
    expect(html).not.toContain('Kayıtlı iki kolu yerel modelde çalıştır');
  });
  it('withholds residual captured text on denied access or pending admission', () => {
    for (const status of ['current', 'withheld'] as const) {
      const value = { public_source_access: false, freshness: { status, reasons: [] }, manifest: { title: 'SECRET fixture quote' } } as unknown as ModelCohortView;
      const html = renderToStaticMarkup(<ModelCohortContent value={value} />);
      expect(html).toContain('bekletiliyor'); expect(html).not.toContain('SECRET');
    }
  });
  it('reports explicit denominators and missing judgments without a correctness score', () => {
    const report = { counts: { selected_records: 2, profile_groups: 2, declared_families: 1, captures_present: 0, complete_capture_records: 0,
      current_reviewer_pairs: 0, accounted_effort_records: 0, records_with_outcome_differences: 0, records_with_unknown_observations: 2 },
      duplicate_inputs: [], repeated_versions: [], cross_family_private_sources: [], repeated_public_passages: [], reserved_overlaps: [], families: [] } as unknown as ModelCohortReport;
    const html = renderToStaticMarkup(<ModelCohortSummary report={report} />);
    expect(html).toContain('0/2 güncel görüş çifti'); expect(html).toContain('2 ayrı ayar grubu');
    expect(html).toContain('Tam kayıt hukuki doğruluk'); expect(html).not.toContain('NaN');
  });
  it('recognizes only receipts for this model-group workflow', () => {
    const data = { outcome: 'committed_needs_revalidation', needs_revalidation: true, id: `amc-${'a'.repeat(20)}-${'b'.repeat(32)}` };
    expect(pendingModelCohort(data)).toBe(true);
    expect(pendingModelCohort({ ...data, id: `atc-${'a'.repeat(20)}-${'b'.repeat(32)}` })).toBe(false);
    expect(pendingModelCohort({ ...data, needs_revalidation: false })).toBe(false);
  });
});
