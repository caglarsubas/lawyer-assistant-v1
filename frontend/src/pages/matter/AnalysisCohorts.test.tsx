import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import AnalysisCohorts, { CohortRows, CohortSummary, FrozenCohort, cohortSeconds, reservedFamilyLabels } from './AnalysisCohorts';
import { SEMANTIC_LABELS } from './AnalysisAdjudication';
import type { CohortArm, CohortView } from './cohortTypes';

function fixture(): CohortView {
  const arm: CohortArm = { status: 'completed', retained_passes: 1, elapsed_seconds: 2.3, provider_round_trip_seconds: .125, gpu_compute_seconds: null,
    dimensions: Object.entries(SEMANTIC_LABELS).map(([dimension, label], index) => ({ dimension, label, outcome_difference: index === 0, unknown_observations: index ? 2 : 0,
      observations: index ? [] : [{ reviewer_id: 'reviewer1', reviewer_name: 'SYNTHETIC reviewer one', outcome: 'confirmed', note: 'SYNTHETIC <script>observation</script>', target_ids: ['conclusion'], source_refs: ['after:e1'] }, { reviewer_id: 'reviewer2', reviewer_name: 'SYNTHETIC reviewer two', outcome: 'needs_change', note: 'SYNTHETIC disagreement', target_ids: ['conclusion'], source_refs: [] }] })),
    findings: [{ finding_index: 0, target_id: 'conclusion', observations: [], outcome_difference: false, unresolved_or_missing: true }],
    active_effort: { arm: 'single_pass', preparation_seconds: 0, verification_seconds: null, correction_seconds: 20 }, active_effort_accounted: false,
    assessment_times: [{ reviewer_id: 'reviewer1', review_seconds: null }], unknown_assessment_observations: 10, outcome_difference_count: 1, unresolved_finding_count: 1 };
  const profile = { sample_kind: 'synthetic' as const, rubric_sha256: 'a'.repeat(64), provider_pin: { model: 'SYNTHETIC-local-model' }, arms: { single_pass: { max_passes: 1, budget_seconds: 120 }, bounded_correction: { max_passes: 2, budget_seconds: 240 } }, feedback_policy: { selected: false, recipe: null } };
  return { id: 'cohort-1', registered_at: '2026-10-08T00:00:00Z', manifest_sha256: 'c'.repeat(64), cohort_sha256: 'd'.repeat(64), freshness: { status: 'current', reasons: [] }, qualification_granted: false, production_qualified: false, benefit_established: false,
    manifest: { matter_id: 'private-workspace', title: 'SYNTHETIC inventory <script>title</script>', purpose: 'SYNTHETIC purpose <img src="untrusted">', selections: [{ analysis_id: 'a1', comparison_id: 'cmp1' }, { analysis_id: 'a2', comparison_id: 'cmp2' }], reserved_family_sha256: [], captures: [], reconciliation: {
      counts: { selected_records: 2, profile_groups: 2, declared_families: 2, current_source_records: 2, complete_capture_records: 2, current_reviewer_pairs: 2, accounted_effort_records: 0, records_with_outcome_differences: 2, records_with_unknown_assessments: 2, records_with_unresolved_findings: 2 },
      profiles: [{ profile_sha256: 'profile1', comparison_ids: ['cmp1'], profile }, { profile_sha256: 'profile2', comparison_ids: ['cmp2'], profile: { ...profile, sample_kind: 'real', provider_pin: { model: 'SYNTHETIC-other-model' } } }],
      families: [{ family_sha256: 'a'.repeat(64), comparison_ids: ['cmp1'], reserved_overlap: false }, { family_sha256: 'b'.repeat(64), comparison_ids: ['cmp2'], reserved_overlap: true }],
      duplicate_inputs: [{ task_input_sha256: 'x'.repeat(64), comparison_ids: ['cmp1', 'cmp2'] }], repeated_versions: [{ version_id: 'v1', content_sha256: 'y'.repeat(64), comparison_ids: ['cmp1', 'cmp2'] }], cross_family_sources: [{ document_id: 'private-source', selections: [{ comparison_id: 'cmp1', family_sha256: 'a'.repeat(64) }, { comparison_id: 'cmp2', family_sha256: 'b'.repeat(64) }] }], reserved_overlaps: ['b'.repeat(64)],
      rows: ['cmp1', 'cmp2'].map((comparison_id, index) => ({ comparison_id, analysis_id: 'a' + index, title: 'SYNTHETIC selected ' + index, capture_sha256: 'c'.repeat(64), profile_sha256: index ? 'profile2' : 'profile1', family_sha256: (index ? 'b' : 'a').repeat(64), sample_kind: index ? 'real' : 'synthetic', source_freshness: { status: 'current', reasons: [] }, capture_complete: true, current_reviewer_count: 2, unknown_assessment_observations: 20, outcome_difference_count: 2, unresolved_finding_count: 2, arms: { single_pass: arm, bounded_correction: { ...arm, retained_passes: 2, active_effort: null } } })),
      selection_is_exhaustive: false, held_out_qualified: false, reviewer_expertise_verified: false, legal_verdict: null, preparation_time_gain: null, qualification_granted: false, production_qualified: false, benefit_established: false,
    } },
  };
}

describe('confidential cohort reconciliation boundaries', () => {
  it('requires explicit current-workspace selection with blank declarations and no preselected records', () => {
    const html = renderToStaticMarkup(<AnalysisCohorts matterId="private-workspace" onSource={() => {}} />);
    for (const text of ['Bu çalışma alanının denemelerini getir', '2–12 kayıt seçin', '0 seçildi', 'model çağrısı yapılmaz', 'Boş bırakılırsa', 'disabled=""']) expect(html).toContain(text);
    expect(html).not.toContain('checked=""'); expect(html).not.toContain('<details open');
  });
  it('parses exact declared family labels without discovering, merging or silently deduplicating them', () => {
    expect(reservedFamilyLabels('  İş sözleşmesi  \n\n Aile-2\n')).toEqual(['İş sözleşmesi', 'Aile-2']);
    expect(reservedFamilyLabels('')).toEqual([]);
    for (const text of ['same\n same ', 'a'.repeat(201), Array.from({ length: 61 }, (_, i) => `family-${i}`).join('\n')]) expect(() => reservedFamilyLabels(text)).toThrow();
  });
  it('keeps unknown time distinct from explicit zero and actual provider round-trip time', () => {
    expect(cohortSeconds(null)).toBe('Bilinmiyor'); expect(cohortSeconds(0)).toBe('0.000 sn');
    const html = renderToStaticMarkup(<CohortRows manifest={fixture().manifest} onSource={() => {}} />);
    for (const text of ['2.300 sn', '0.125 sn', 'GPU hesap süresi: Bilinmiyor', 'Aktif hazırlık: 0.000 sn', 'Doğrulama/inceleme: Bilinmiyor', 'Ayrı değerlendirme: Bilinmiyor', 'toplam çağrı maliyeti bilinmiyor']) expect(html).toContain(text);
  });
  it('never treats complete records or distinct declared families as expert qualification or a measured gain', () => {
    const html = renderToStaticMarkup(<CohortSummary report={fixture().manifest.reconciliation} />);
    for (const text of ['Tam kayıt: 2/2', 'Aktif süre hesabı: 0/2', 'Çözülmemiş/eksik bulgu: 2/2', 'süre kazancı kanıtı sağlamaz', 'Seçim tüm denemeleri temsil etmez', 'Ayrılmış aileyle örtüşme: 1']) expect(html).toContain(text);
    expect(html).not.toContain('100%'); expect(html).not.toContain('<details open');
  });
  it('preserves different outcomes, source-family overlap and real/synthetic profiles without a winner', () => {
    const value = fixture(); const html = renderToStaticMarkup(<FrozenCohort value={value} base="/matters/private-workspace/analysis-cohorts" busy={false} onSource={() => {}} />);
    for (const text of ['SYNTHETIC-local-model', 'SYNTHETIC-other-model', 'Gerçek beyanı', 'Kurgusal', 'Farklı sonuçlar', 'SYNTHETIC reviewer one', 'SYNTHETIC reviewer two', 'Çözülmemiş veya eksik gözlem', 'Farklı ailelerde ortak özel belge: 1']) expect(html).toContain(text);
    expect(html).not.toContain('Kazanan'); expect(html).not.toContain('<script>'); expect(html).not.toContain('<img src="untrusted"');
  });
  it('labels later changes separately from the immutable report and withholds a currentness claim', () => {
    const value = fixture(); value.freshness = { status: 'stale', reasons: [{ comparison_id: 'cmp1', code: 'selected_record_unavailable' }] };
    const html = renderToStaticMarkup(<FrozenCohort value={value} base="/matters/private-workspace/analysis-cohorts" busy={false} onSource={() => {}} />);
    for (const text of ['Grup dayanağı değişti', 'önceki sabit kaydı gösterir', 'yeni önizleme', 'Seçilen kayıt kullanılamıyor', 'Sabit kayıtta güncel dayanak: 2/2']) expect(html).toContain(text);
    expect(html).not.toContain('Sabit kayıtla güncel durum eşleşiyor');
  });
  it('uses a same-origin server attachment and disables its link during a pending action', () => {
    const props = { value: fixture(), base: '/matters/private-workspace/analysis-cohorts', onSource: () => {} };
    expect(renderToStaticMarkup(<FrozenCohort {...props} busy={false} />)).toContain('href="/api/v1/matters/private-workspace/analysis-cohorts/cohort-1/export"');
    expect(renderToStaticMarkup(<FrozenCohort {...props} busy />)).not.toContain('href=');
  });
  it('renders capture inspection controls without mounting copied private evidence before it is explicitly opened', () => {
    const html = renderToStaticMarkup(<CohortRows manifest={fixture().manifest} onSource={() => {}} />);
    expect(html).toContain('Özgün deneme ve alıntıları aç'); expect(html).not.toContain('Taslak ve model adayının saklanan alıntıları');
    expect(html).not.toContain('<details open');
  });
});
