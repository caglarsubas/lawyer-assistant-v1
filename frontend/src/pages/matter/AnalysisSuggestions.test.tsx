import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { AnalysisSuggestions, ProposalReview } from './AnalysisSuggestions';
import { AnalysisContentView } from './AnalysisView';
import { analysisForm, type AnalysisContent, type AnalysisRecord, type AnalysisSuggestion } from './analysisTypes';

function candidate(): AnalysisContent {
  return {
    title: 'SYNTHETIC', issue: 'SYNTHETIC özel mesele', posture: '', event_date: null,
    evidence: [], premises: [], rules: [], applications: [], alternatives: [], fact_snapshots: [],
    conclusion: { text: '<script>untrusted</script>', requested_disposition: 'conditional', application_ids: [], alternative_ids: [], uncertainty: ['İnceleme gerekli.'], next_step: 'Kaynakları incele.' },
    checks: { recipe: 'private-rationale-checks-v1', scope: 'declared_structure_only', legal_approval: 'not_granted', effective_disposition: 'conditional', critical_count: 0, defects: [], dependency_nodes: [] },
    status: 'needs_review', authorship: 'model_proposal', legal_authority: false,
    revision_comparison: { previous_version_id: 'v1', changed_sections: ['conclusion'], changed_dependency_groups: [], checks_no_longer_triggered: [], new_check_ids: [], scope: 'structural_changes_only' },
  };
}

function job(): AnalysisSuggestion {
  return { id: 'j1', status: 'completed', phase: 'finished', mode: 'repair', max_passes: 2,
    created_at: '2026-10-07T00:00:00Z', deadline_at: '2026-10-07T00:04:00Z', budget_seconds: 240,
    provider_pin: { model: 'SYNTHETIC-local', recipe: 'private-analysis-proposals-v1', transport: { mode: 'private_network', uses_public_network: false } },
    source_version_id: 'v1', candidate: candidate(), candidate_sha256: 'a'.repeat(64), can_adopt: true,
    freshness: { status: 'current', reasons: [], scope: 'pinned_private_analysis_and_provider_policy' },
    review_notes: [{ target_id: 'conclusion', text: '<img src="untrusted">', evidence_ids: [], pass: 1 }],
    iterations: [{ pass: 1, provider_seconds: .2, prompt: { utf8_bytes: 3000, messages_sha256: 'b'.repeat(64), completion_tokens: 1000 }, outcome: 'rejected_new_critical_checks', new_critical_check_ids: ['defect'], checks: candidate().checks }],
  };
}

describe('local analysis proposal review', () => {
  it('renders a new unreviewed version with no review or pending selection after adoption', () => {
    const record: AnalysisRecord = { ...candidate(), id: 'a1', revision: 2, version: 2, latest_version_id: 'v2', created_at: '2026-10-07T00:00:00Z',
      freshness: { status: 'current', reasons: [], scope: 'private_draft' },
      review: { effective_state: 'unreviewed', latest: null, scope: 'conditional_private_draft_only', reasons: [] },
    };
    for (const review of [record.review, undefined]) {
      const html = renderToStaticMarkup(<AnalysisSuggestions matterId="m1" record={{ ...record, review }} onSource={() => {}} onAdopt={async () => {}} />);
      expect(html).toContain('Yerel model önerisi iste');
      expect(html).not.toContain('Modele iletilecek bulgular');
      expect(html).not.toContain('<details open');
    }
  });
  it('distinguishes unapproved model text, rejected changes, legal review and bounded work', () => {
    const html = renderToStaticMarkup(<ProposalReview job={job()} onSource={() => {}} />);
    for (const text of ['Modelin onaylanmamış düzenleme önerisi', 'Hukuki onay verilmedi', 'Yeni kritik kontrol nedeniyle', '1/2 saklanan geçiş', '240 saniye', '1.000 çıktı tokenı', 'Otomatik yeniden deneme yapılmaz', 'Kaynak analiz sürümü: v1']) expect(html).toContain(text);
    expect(html).not.toContain('<details open');
    expect(html).not.toContain('<script>untrusted'); expect(html).not.toContain('<img src');
    expect(html).toContain('&lt;script&gt;untrusted'); expect(html).toContain('&lt;img');
  });
  it('marks completed stale proposals withheld without claiming the job never completed', () => {
    const data = job(); data.freshness = { ...data.freshness, status: 'stale', reasons: ['Analiz sürümü değişti.'] };
    const html = renderToStaticMarkup(<ProposalReview job={data} onSource={() => {}} />);
    expect(html).toContain('Öneri artık güncel değil'); expect(html).toContain('Sonuç bekletiliyor');
    expect(html).toContain('Öneri çalışması tamamlandı.');
    expect(html).toContain('>Sonuç bekletiliyor</span>');
    expect(html).not.toContain('>Koşullu taslak</span>');
  });
  it('labels retained output from interrupted jobs as partial', () => {
    const data = job(); data.status = 'timed_out'; data.can_adopt = false;
    const html = renderToStaticMarkup(<ProposalReview job={data} onSource={() => {}} />);
    expect(html).toContain('saklanan kısmi öneri'); expect(html).not.toContain('Öneri çalışması tamamlandı.');
  });
  it('discloses approved internet transport when the local model uses a laptop tunnel', () => {
    const data = job(); data.provider_pin.transport = { mode: 'approved_laptop_tunnel', uses_public_network: true };
    expect(renderToStaticMarkup(<ProposalReview job={data} onSource={() => {}} />)).toContain('bu aktarım air-gapped değildir');
  });
  it('retains model provenance in the saved view while omitting server-owned fields from manual editor input', () => {
    const content = candidate(); content.authorship = 'user_with_ai_assistance';
    content.ai_assistance = { job_id: 'j1', source_version_id: 'v1', passes: 1, provider: { model: 'SYNTHETIC-local' }, review_notes: [{ target_id: 'conclusion', text: 'Doğrulanmamış not', pass: 1 }] };
    const html = renderToStaticMarkup(<AnalysisContentView content={content} onSource={() => {}} />);
    for (const text of ['Model önerisinden uyarlanmış avukat taslağı', 'Model katkısı ve kayıt sınırları', 'Doğrulanmamış not', 'SYNTHETIC-local']) expect(html).toContain(text);
    const form = analysisForm(content);
    expect(form).not.toHaveProperty('authorship'); expect(form).not.toHaveProperty('ai_assistance');
    expect(form.conclusion.text).toBe(content.conclusion.text);
  });
});
