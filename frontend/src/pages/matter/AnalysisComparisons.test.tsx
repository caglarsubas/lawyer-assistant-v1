import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { ComparisonEffortForm, ComparisonResults, ComparisonSummary, effortPayload, ObservationForm, RegistrationForm } from './AnalysisComparisons';
import { SEMANTIC_LABELS } from './AnalysisAdjudication';
import type { AnalysisContent, RevisionComparison } from './analysisTypes';
import type { ComparisonCapture, RegistrationContext } from './comparisonTypes';

function fixture(): ComparisonCapture {
  const content: AnalysisContent = { title: 'SYNTHETIC draft', issue: 'SYNTHETIC issue', posture: '', event_date: null,
    evidence: [], premises: [], rules: [], applications: [], alternatives: [], fact_snapshots: [],
    conclusion: { text: 'SYNTHETIC unreviewed', requested_disposition: 'conditional', application_ids: [], alternative_ids: [], uncertainty: [], next_step: 'SYNTHETIC inspect' },
    checks: { recipe: 'private-rationale-checks-v1', scope: 'declared_structure_only', legal_approval: 'not_granted', effective_disposition: 'conditional', critical_count: 1, defects: [], dependency_nodes: [] }, status: 'needs_review', authorship: 'user', legal_authority: false, revision_comparison: { previous_version_id: null, changed_sections: [], changed_dependency_groups: [], checks_no_longer_triggered: [], new_check_ids: [], scope: 'structural_changes_only' } };
  const comparison: RevisionComparison = { recipe: 'private-revision-adjudication-v1', scope: 'selected_private_evidence_only', review_recipe: 'private-lawyer-review-v1', comparison_sha256: 'c'.repeat(64), base_version_id: 'v1', base_version: 1, base_content_sha256: 'a'.repeat(64), base_review_id: 'r1', candidate_version_id: 'proposal:job1', candidate_version: null, candidate_kind: 'unadopted_model_proposal', candidate_content_sha256: 'b'.repeat(64), candidate_disposition: 'conditional', targets: ['conclusion'], changes: [{ target_id: 'conclusion', before: 'SYNTHETIC original', after: 'SYNTHETIC unreviewed <script>text</script>' }], findings: [{ finding_index: 0, target_id: 'conclusion', severity: 'critical', text: 'SYNTHETIC unresolved issue', suggested_change: '', evidence_ids: ['e1'] }], sources: [{ source_ref: 'after:e1', evidence_id: 'e1', document_id: 'd1', document_revision: 1, document_sha256: 'd'.repeat(64), name: 'SYNTHETIC.txt', locator: 'SYNTHETIC §1', passage_sha256: 'e'.repeat(64), quote_sha256: 'f'.repeat(64), start: 0, end: 14, text: 'SYNTHETIC quote' }], dimensions: SEMANTIC_LABELS, freshness: { status: 'current', reasons: [] }, public_adverse_authority_qualified: false, benefit_established: false };
  const arm = { status: 'completed', job: null, comparison, elapsed_seconds: 1.23, provider_round_trip_seconds: .12, gpu_compute_seconds: null };
  return { id: 'cmp1', execution_sha256: 'e'.repeat(64), sample_kind: 'synthetic', exported_at: '2026-10-07T00:01:00Z',
    protocol: { title: 'SYNTHETIC private comparison', question: 'SYNTHETIC registered question', rubric_text: 'SYNTHETIC rubric <img src="untrusted">', rubric_sha256: 'b'.repeat(64), protocol_sha256: 'c'.repeat(64), registered_at: '2026-10-07T00:00:00Z', registered_by: 'operator', source_version: 1, source_version_id: 'v1', source_content: content, task_input_sha256: 'a'.repeat(64), reviewer_ids: ['reviewer1', 'reviewer2'], provider_pin: { model: 'SYNTHETIC-local' }, arms: { single_pass: { max_passes: 1, budget_seconds: 120 }, bounded_correction: { max_passes: 2, budget_seconds: 240 } } },
    arms: { single_pass: { ...arm }, bounded_correction: { ...arm } }, freshness: { status: 'current', reasons: [] }, observations: [], effort_history: [], current_reviewer_count: 0, effort_accounted: false, capture_complete: false, can_run: false, can_observe: false, can_record_effort: true, previous_observation_id: null, previous_effort_id: null, qualification_granted: false, benefit_established: false };
}

describe('registered private comparison evidence boundaries', () => {
  it('preserves unknown effort separately from explicitly declared zero and rejects invalid durations', () => {
    const input = { single_pass: ['', '', ''], bounded_correction: ['0', '20', '30'] };
    expect(effortPayload(input)).toEqual([{ arm: 'single_pass', preparation_seconds: null, verification_seconds: null, correction_seconds: null }, { arm: 'bounded_correction', preparation_seconds: 0, verification_seconds: 20, correction_seconds: 30 }]);
    for (const value of ['-1', '1.5', '28801', 'NaN']) { input.single_pass[0] = value; expect(effortPayload(input)).toBeNull(); }
  });
  it('requires explicit accounting declarations and keeps all phases blank on first inspection', () => {
    const html = renderToStaticMarkup(<ComparisonEffortForm value={fixture()} busy={false} onSave={() => {}} />);
    for (const text of ['Model bekleme süresini eklemeyin', 'çakışmayan aktif çalışma', 'Bağımsız değerlendirme', 'Boş: bilinmiyor', 'Sıfır yalnız', 'süre kazanımı hesaplanmaz']) expect(html).toContain(text);
    expect(html.match(/type="number"[^>]*value=""/g)).toHaveLength(6);
    expect(html).not.toContain('checked=""'); expect(html).not.toContain('<details open');
  });
  it('requires two existing reviewers and an explicit sample origin before registration without a model call', () => {
    const context: RegistrationContext = { context_sha256: 'c'.repeat(64), version_id: 'v1', expected_revision: 1, eligible_reviewers: [{ id: 'private-id-1', name: 'SYNTHETIC reviewer one' }, { id: 'private-id-2', name: 'SYNTHETIC reviewer two' }], synthetic_only: true, can_register: true, provider_model: 'SYNTHETIC', research_budget_seconds: 300 };
    const html = renderToStaticMarkup(<RegistrationForm context={context} busy={false} onSave={() => {}} />);
    for (const text of ['SYNTHETIC reviewer one', 'SYNTHETIC reviewer two', 'aynı belge/dosya', 'Henüz model çağrılmaz', 'value="" selected', 'disabled=""']) expect(html).toContain(text);
    expect(html).not.toContain('private-id-1'); expect(html).not.toContain('value="real"'); expect(html).not.toContain('checked=""');
  });
  it('does not convert complete capture, real origin or declared timings into a quality or independence claim', () => {
    const value = fixture(); value.capture_complete = true; value.current_reviewer_count = 2; value.effort_accounted = true; value.sample_kind = 'real';
    const html = renderToStaticMarkup(<ComparisonSummary value={value} />);
    for (const text of ['Karşılaştırma kaydı tamamlandı', 'Gerçek örnek beyanı', 'hukuki doğruluk', 'bağımsız uzmanlık', 'model faydasını kanıtlamaz', 'Adaylar çalışma taslağına uygulanmaz', 'daha derin hukuki araştırma', 'Kamu/karşı içtihat araştırması']) expect(html).toContain(text);
    expect(html).not.toContain('<img src'); expect(html).not.toContain('<details open');
    value.freshness = { status: 'stale', reasons: ['SYNTHETIC changed basis'] };
    expect(renderToStaticMarkup(<ComparisonSummary value={value} />)).toContain('Deneme güncel değil');
  });
  it('shows exact virtual candidate quotations without inventing a saved revision or GPU measurements', () => {
    const html = renderToStaticMarkup(<ComparisonResults value={fixture()} onSource={() => {}} />);
    for (const text of ['kaydedilmemiş model adayı', 'SYNTHETIC original', 'SYNTHETIC unreviewed', 'SYNTHETIC quote', '[0, 14)', '1.230 sn', '0.120 sn', 'GPU hesap süresi: Ölçülmedi']) expect(html).toContain(text);
    expect(html).not.toContain('Gösterilen sürüm'); expect(html).toContain('Taslak ve model adayının saklanan alıntıları'); expect(html).not.toContain('<script>text'); expect(html).not.toContain('<details open');
  });
  it('keeps failed and missing arms visible without counting retained passes as total calls or cost', () => {
    const value = fixture(); value.arms.single_pass = { status: 'cancelled', job: null, comparison: null, elapsed_seconds: null, provider_round_trip_seconds: null, gpu_compute_seconds: null };
    value.arms.bounded_correction = { ...value.arms.single_pass, status: 'not_started' };
    const html = renderToStaticMarkup(<ComparisonResults value={value} onSource={() => {}} />);
    for (const text of ['Başlatılmadı', 'İptal edildi', 'toplam çağrı maliyeti bilinmiyor', 'bütün denemelerin sayısı sayılmaz', 'Sağlayıcı gidiş/dönüşü: Ölçülmedi']) expect(html).toContain(text);
    expect(html).not.toContain('0.000 sn');
  });
  it('does not infer semantic verdicts or repair findings for the assigned reviewer', () => {
    const html = renderToStaticMarkup(<ObservationForm value={fixture()} busy={false} onSource={() => {}} onSave={() => {}} />);
    for (const text of ['kendi değerlendirmenizi', 'kör değerlendirme sağlamaz', 'uzmanlık veya fiili bağımsızlık', 'inceleme kararını değiştirmez', 'Önceki bulgu 1']) expect(html).toContain(text);
    expect(html).not.toContain('value="confirmed" selected'); expect(html).not.toContain('value="repaired" selected'); expect(html).not.toContain('<details open');
  });
  it('discloses the already approved laptop tunnel before trial dispatch', () => {
    const value = fixture(); value.protocol.provider_pin.transport = { mode: 'approved_laptop_tunnel', uses_public_network: true };
    const html = renderToStaticMarkup(<ComparisonSummary value={value} />);
    expect(html).toContain('Onaylı dizüstü tüneli'); expect(html).toContain('bu aktarım air-gapped değildir');
  });
});
