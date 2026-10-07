import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { AnalysisReviewForm, REVIEW_LABELS, ReviewEventDetails, ReviewHistory, ReviewSummary } from './AnalysisReviews';
import { AnalysisCheckPanel } from './AnalysisView';
import type { AnalysisReviewContext, AnalysisReviewEvent, ReviewCriterionKey } from './analysisTypes';

function event(): AnalysisReviewEvent {
  return { id: 'review1', version_id: 'version1', created_at: '2026-10-07T00:00:00Z', sequence: 1,
    content_sha256: 'a'.repeat(64), decision: 'reviewed_conditional', reviewer_id: 'lawyer1', reviewer_name: 'SYNTHETIC reviewer',
    note: '<script>untrusted review</script>', criteria: (Object.keys(REVIEW_LABELS) as ReviewCriterionKey[]).map((criterion) => ({ criterion, outcome: 'confirmed', note: '' })),
    findings: [{ target_id: 'application:a1', severity: 'note', text: '<img src="untrusted">', suggested_change: 'Kaynağın bağlamını koruyun.', evidence_ids: ['source1'] }],
    scope: 'conditional_private_draft_only', recipe: 'private-lawyer-review-v1' };
}

function context(): AnalysisReviewContext {
  return { version_id: 'version1', expected_revision: 1, content_sha256: 'a'.repeat(64), expected_review_id: null,
    recipe: 'private-lawyer-review-v1', criteria: REVIEW_LABELS, ai_contribution_required: false,
    current_version: true, can_record: true, can_accept: true, critical_count: 0,
    freshness: { status: 'current', reasons: [], scope: 'selected_private_dependencies_only' },
    review: { effective_state: 'unreviewed', scope: 'conditional_private_draft_only', latest: null, reasons: [] },
    targets: ['analysis', 'conclusion', 'application:a1'], sources: [{ evidence_id: 'source1', document_id: 'document1',
      name: 'SYNTHETIC.txt', locator: '§1', start: 2, end: 60, quote_sha256: 'b'.repeat(64) }] };
}

describe('version-bound human review', () => {
  it('keeps the private conditional decision distinct from public authority and machine approval', () => {
    const html = renderToStaticMarkup(<ReviewSummary review={{ effective_state: 'reviewed_conditional', scope: 'conditional_private_draft_only', latest: event(), reasons: [] }} onSource={() => {}} />);
    for (const text of ['Avukat inceledi · Koşullu özel taslak', 'Avukatın beyanıdır', 'makine hukuki onayı değildir', 'SYNTHETIC reviewer', 'İçerik SHA-256', 'Özgün kaynaklar', 'Model katkısı']) expect(html).toContain(text);
    expect(html).not.toContain('<details open');
  });
  it('preserves the previous declaration when revalidation makes its projection stale', () => {
    const html = renderToStaticMarkup(<ReviewSummary review={{ effective_state: 'stale', scope: 'conditional_private_draft_only', latest: event(), reasons: ['Bağlı olgu değişti.'] }} onSource={() => {}} />);
    for (const text of ['Önceki avukat incelemesi güncel değil', 'Bağlı olgu değişti', 'Önceki karar korunur', 'Koşullu özel taslak incelemesi kaydedildi.']) expect(html).toContain(text);
    expect(html).not.toContain('>Avukat inceledi · Koşullu özel taslak</span>');
  });
  it('escapes reviewer and finding text and retains source inspection and proposed corrections', () => {
    const html = renderToStaticMarkup(<ReviewEventDetails event={event()} onSource={() => {}} />);
    expect(html).not.toContain('<script>untrusted'); expect(html).not.toContain('<img src');
    expect(html).toContain('&lt;script&gt;untrusted'); expect(html).toContain('&lt;img');
    expect(html).toContain('Bulgunun özgün dayanağı'); expect(html).toContain('Kaynağın bağlamını koruyun.');
  });
  it('starts with no attested criteria and a disabled save, explaining the exact source comparison', () => {
    const html = renderToStaticMarkup(<AnalysisReviewForm context={context()} onSource={() => {}} onSubmit={async () => {}} busy={false} />);
    expect(html).toContain('value="changes_requested" selected');
    expect(html).not.toContain('value="confirmed" selected');
    expect(html).not.toContain('value="reviewed_conditional" selected');
    expect(html).toMatch(/type="submit" disabled=""/);
    for (const text of ['SYNTHETIC.txt', '[2, 60)', 'basmak inceleme yaptığınızı kanıtlamaz', 'Bu sürümde model katkısı yok', 'Yeni metin sürümü yeniden inceleme gerektirir']) expect(html).toContain(text);
  });
  it('disallows conditional acceptance for critical drafts and forbids skipping AI contribution review', () => {
    const data = context(); data.critical_count = 2; data.can_accept = false; data.ai_contribution_required = true;
    const html = renderToStaticMarkup(<AnalysisReviewForm context={data} onSource={() => {}} onSubmit={async () => {}} busy={false} />);
    expect(html).toContain('2 kritik yapısal kontrol var');
    expect(html).toMatch(/value="reviewed_conditional" disabled=""/);
    expect(html).not.toContain('value="not_applicable"');
    data.can_record = false; data.current_version = false;
    const historical = renderToStaticMarkup(<AnalysisReviewForm context={data} onSource={() => {}} onSubmit={async () => {}} busy={false} />);
    expect(historical).toContain('güncel sürüm değil; karar kaydedilemez');
  });
  it('loads immutable history explicitly and avoids inventing a review for an unreviewed version', () => {
    expect(renderToStaticMarkup(<ReviewSummary review={context().review} onSource={() => {}} />)).toBe('');
    const html = renderToStaticMarkup(<ReviewHistory matterId="m1" analysisId="a1" versionId="v1" onSource={() => {}} />);
    expect(html).toContain('İncelemeleri getir'); expect(html).not.toContain('<details open');
    expect(html).toContain('önceki kararlar ve bulgular korunur');
  });
  it('withholds an otherwise conditional assessment when the lawyer requests changes, preserving machine checks', () => {
    const data = event(); data.decision = 'changes_requested'; data.findings[0].severity = 'critical';
    const checks = { recipe: 'private-rationale-checks-v1', scope: 'declared_structure_only' as const, legal_approval: 'not_granted' as const, effective_disposition: 'conditional' as const, critical_count: 0, defects: [], dependency_nodes: [] };
    const html = renderToStaticMarkup(<AnalysisCheckPanel checks={checks} freshness={context().freshness} review={{ effective_state: 'changes_requested', scope: 'conditional_private_draft_only', latest: data, reasons: [] }} />);
    expect(html).toContain('Sonuç bekletiliyor'); expect(html).toContain('Avukat değişiklik istedi');
    expect(html).toContain('0 kritik kontrol'); expect(html).not.toContain('>Koşullu taslak</span>');
    expect(checks.effective_disposition).toBe('conditional');
  });
});
