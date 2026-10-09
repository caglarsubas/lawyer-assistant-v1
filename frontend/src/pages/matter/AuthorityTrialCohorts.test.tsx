import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import AuthorityTrialCohorts, { AuthorityCohortContent, AuthorityCohortRows, AuthorityCohortSummary } from './AuthorityTrialCohorts';
import { authorityReservedFamilies, pendingAuthorityCohort } from './authorityCohortTypes';
import type { AuthorityCohortView } from './authorityCohortTypes';

const fixture = (): AuthorityCohortView => ({ id: 'atc-' + 'a'.repeat(20) + '-' + 'b'.repeat(32), registered_at: '2026-10-09T01:00:00Z', owner_id: 'operator', public_source_access: true, manifest_sha256: 'c'.repeat(64), freshness: { status: 'current', reasons: [] }, manifest: {
  title: 'SYNTHETIC <script>group</script>', purpose: 'SYNTHETIC confidential purpose', selections: [], reserved_family_sha256: [], entries: [], reconciliation: {
    counts: { selected_records: 2, profile_groups: 2, declared_families: 2, current_source_records: 2, captures_present: 1, complete_capture_records: 0, current_reviewer_pairs: 0, accounted_effort_records: 0, records_with_outcome_differences: 0, records_with_unknown_observations: 2 },
    profiles: [{ profile_sha256: 'd'.repeat(64), trial_ids: ['one'], profile: { sample_kind: 'synthetic', semantic_dimensions_sha256: 'a'.repeat(64), finding_dimensions_sha256: 'b'.repeat(64), workflow: 'human_revision_fixed_evidence', model_use: 'none' } }], families: [], duplicate_inputs: [], repeated_versions: [], cross_family_private_sources: [], repeated_public_passages: [], reserved_overlaps: [], rows: [{ trial_id: 'one', title: 'SYNTHETIC captured trial', profile_sha256: 'd'.repeat(64), entry_sha256: 'e'.repeat(64), family_sha256: 'f'.repeat(64), sample_kind: 'synthetic', source_freshness: { status: 'current', reasons: [] }, capture_id: null, capture_present: false, capture_complete: false, current_reviewer_count: 0,
      semantic: [{ dimension: 'meaning', label: 'Pasaj anlamı', observations: [], outcome_difference: null, unknown_observations: 2 }], findings: [], semantic_observation_slots: 12, finding_observation_slots: 12, unknown_semantic_observations: 12, unknown_finding_observations: 12, outcome_difference_count: null, recorded_effort: { note: 'SYNTHETIC', arms: [{ arm: 'original', preparation_seconds: null, verification_seconds: 0, correction_seconds: null }, { arm: 'revised', preparation_seconds: null, verification_seconds: null, correction_seconds: null }], shared_setup_included: false, verification_and_correction_included: false, non_overlapping_active_time: false }, effort_accounted: false, assessment_times: [{ reviewer_id: 'reviewer', review_seconds: null }], adverse_scopes: [] }],
  },
} });

describe('confidential human authority-trial cohort inventory', () => {
  it('starts without requests, selected records, reserved families or saved content', () => {
    const html = renderToStaticMarkup(<AuthorityTrialCohorts matterId="private workspace" />);
    expect(html).toContain('Dayanak denemelerini getir'); expect(html).toContain('Açık seçim');
    expect(html).not.toContain('checked'); expect(html).not.toContain('SYNTHETIC'); expect(html).not.toContain('Kaydedilmemiş dayanak grubu önizlemesi');
  });
  it('uses selected-record denominators without declaring quality or savings', () => {
    const html = renderToStaticMarkup(<AuthorityCohortSummary report={fixture().manifest!.reconciliation} />);
    for (const label of ['2 seçilmiş deneme', '2 ayrı ayar grubu', '1/2 saklanan', '0/2 güncel görüş', 'kayıtlar incelenir', 'insan revizyonudur']) expect(html).toContain(label);
  });
  it('keeps stale frozen notes inspectable and export closed', () => {
    const value = fixture(); value.freshness = { status: 'stale', reasons: [{ trial_id: 'one', code: 'selected_trial_changed_or_stale' }] };
    const html = renderToStaticMarkup(<AuthorityCohortContent value={value} />);
    expect(html).toContain('Aktarım kapalı'); expect(html).toContain('Önceki'); expect(html).toContain('&lt;script&gt;'); expect(html).not.toContain('<script>');
  });
  it('withholding hides even accidentally cached complete manifests and notes', () => {
    const value = fixture(); value.public_source_access = false;
    const html = renderToStaticMarkup(<AuthorityCohortContent value={value} />);
    expect(html).toContain('bekletiliyor'); expect(html).not.toContain('SYNTHETIC'); expect(html).not.toContain('confidential');
    value.public_source_access = true; value.freshness = { status: 'withheld', reasons: [] };
    expect(renderToStaticMarkup(<AuthorityCohortContent value={value} />)).not.toContain('SYNTHETIC');
  });
  it('displays unknown separately from explicit zero and missing pairs', () => {
    const html = renderToStaticMarkup(<AuthorityCohortRows manifest={fixture().manifest!} />);
    for (const label of ['Hazırlama: Bilinmiyor', 'İnceleme: 0 saniye', 'Farklı beyan: Bilinmiyor', 'Görüş çifti eksik', 'GPU hesap süresi bilinmiyor']) expect(html).toContain(label);
  });
  it('validates bounded distinct reserved labels without inferring a reserved protocol', () => {
    expect(authorityReservedFamilies('')).toEqual([]); expect(authorityReservedFamilies(' family \nother\n')).toEqual(['family', 'other']);
    for (const bad of ['same\nsame', 'x'.repeat(201), Array.from({ length: 61 }, (_, index) => `${index}`).join('\n')]) expect(() => authorityReservedFamilies(bad)).toThrow();
  });
  it('only accepts an exact pending group receipt', () => {
    expect(pendingAuthorityCohort({ id: fixture().id, outcome: 'committed_needs_revalidation', needs_revalidation: true })).toBe(true);
    expect(pendingAuthorityCohort({ id: '../private', outcome: 'committed_needs_revalidation', needs_revalidation: true })).toBe(false);
  });
});
