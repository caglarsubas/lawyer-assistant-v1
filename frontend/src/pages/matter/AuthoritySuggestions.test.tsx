import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import AuthorityProposalSummary from './AuthorityProposalSummary';
import AuthoritySuggestions from './AuthoritySuggestions';
import { ProposalReview } from './AnalysisSuggestions';
import { AnalysisContentView } from './AnalysisView';
import type { AuthorityFeedback } from './authorityProposalTypes';
import type { AnalysisContent, AnalysisSuggestion } from './analysisTypes';
import type { FindingView } from './authorityFindingTypes';

const feedback = {
  recipe: 'source-bound-authority-proposals-v1', dependency: { context_id: 'context1', review_id: 'review1', review_sha256: 'a'.repeat(64) },
  findings: [{ finding_id: 'authority:0:history', authority_id: 'authority:0', dimension: 'history', outcome: 'unresolved', note: '<img src=x> SYNTHETIC unverified', target_ids: ['rule:r1'], editable_targets: ['conclusion'] }],
  sources: [{ id: 'authority:0', selection: { relationship: 'unresolved' }, evidence: { source_version_id: 'SYNTHETIC historical v1', locator: '§1', quote_sha256: 'b'.repeat(64), text: '<script>PUBLIC QUOTE</script>' }, temporal_alignment: { research_as_of: '2023-03-01', analysis_event_date: null, dates_equal: null, applicability: 'not_assessed' } }],
} as AuthorityFeedback;

describe('source-bound local authority proposals', () => {
  it('keeps earlier source citations attributed to their original model after a later private proposal', () => {
    const content = { issue: 'SYNTHETIC issue', fact_snapshots: [], evidence: [],
      premises: [], rules: [], applications: [], alternatives: [],
      conclusion: { text: 'SYNTHETIC later interpretation', uncertainty: [], application_ids: [], alternative_ids: [] },
      checks: { effective_disposition: 'conditional', critical_count: 0, defects: [] },
      revision_comparison: { previous_version_id: null },
      ai_assistance: { job_id: 'new-job', source_version_id: 'new-version', provider: { model: 'new-model' }, passes: 1 },
      authority_contributions: [{ job_id: 'original-public-job', source_version_id: 'original-version', provider_pin: { model: 'original-public-model' }, feedback, responses: [], response_pass: 1 }],
    } as unknown as AnalysisContent;
    const html = renderToStaticMarkup(<AnalysisContentView content={content} onSource={() => {}} />);
    expect(html).toContain('new-model'); expect(html).toContain('original-public-model');
    expect(html).toContain('original-public-job'); expect(html).toContain('PUBLIC QUOTE');
    expect(html).toContain('güncel model yanıtı değildir');
  });
  it('preserves unknown history and escapes untrusted quotes and review text', () => {
    const html = renderToStaticMarkup(<AuthorityProposalSummary feedback={feedback} responses={[{ finding_id: 'authority:0:history', outcome: 'requires_manual_work', edited_targets: [], text: 'SYNTHETIC legal effect still unknown', authority_ids: ['authority:0'] }]} pass={1} />);
    expect(html).toContain('Elle çalışma gerekli'); expect(html).toContain('SYNTHETIC historical v1');
    expect(html).toContain('PUBLIC QUOTE'); expect(html).toContain('not_assessed');
    expect(html).toContain('&lt;script&gt;'); expect(html).not.toContain('<script>');
    expect(html).not.toContain('<img src='); expect(html).toContain('otomatik giderilmiş sayılmaz');
  });
  it('withholds cached candidate, source notes and iteration bytes after denial', () => {
    const job = { public_source_access: false, authority_feedback: feedback, review_notes: [{ text: 'SECRET cached note' }], candidate: { conclusion: { text: 'SECRET cached candidate' } }, iterations: [{ patch: { authority_responses: [{ text: 'SECRET cached iteration' }] } }] } as unknown as AnalysisSuggestion;
    const html = renderToStaticMarkup(<ProposalReview job={job} onSource={() => {}} />);
    expect(html).toContain('Önceki aday gösterilmez'); expect(html).not.toContain('SECRET'); expect(html).not.toContain('PUBLIC QUOTE');
  });
  it('cannot request inference from a withheld source view', () => {
    const value = { public_source_access: false, snapshot: null } as FindingView;
    const html = renderToStaticMarkup(<AuthoritySuggestions matterId="m1" analysisId="a1" value={value} onUnavailable={() => {}} />);
    expect(html).toContain('içeriği bekletiliyor'); expect(html).not.toContain('yerel öneri iste');
  });
});
