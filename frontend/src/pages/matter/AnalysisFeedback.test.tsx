import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { FeedbackSummary, ReviewFindingPicker } from './AnalysisFeedback';
import type { AnalysisFeedback, AnalysisReviewEvent, FeedbackResponse } from './analysisTypes';

function review(): AnalysisReviewEvent {
  return { id: 'SYNTHETIC-review', version_id: 'v1', created_at: '2026-10-07T00:00:00Z', sequence: 1,
    content_sha256: 'a'.repeat(64), decision: 'changes_requested', reviewer_id: 'u1', reviewer_name: 'SYNTHETIC lawyer',
    note: 'Unselected review summary', criteria: [], scope: 'conditional_private_draft_only', recipe: 'private-lawyer-review-v1',
    findings: Array.from({ length: 6 }, (_, index) => ({ target_id: 'conclusion', severity: 'major', text: `<script>finding ${index}</script>`, suggested_change: 'SYNTHETIC requested edit', evidence_ids: ['source1'] })),
  };
}

describe('opt-in immutable review feedback', () => {
  it('starts with no selection and renders source-linked findings as escaped data', () => {
    const html = renderToStaticMarkup(<ReviewFindingPicker review={review()} indices={[]} disabled={false} onChange={() => {}} onSource={() => {}} />);
    expect(html).toContain('0/5 bulgu seçildi'); expect(html).toContain('Seçim yapmazsanız inceleme metni eklenmez');
    expect(html.match(/type="checkbox"/g)).toHaveLength(6); expect(html).not.toContain('checked=""');
    expect(html).not.toContain('<details open'); expect(html).not.toContain('<script>');
    expect(html).toContain('&lt;script&gt;finding 0'); expect(html).toContain('Bulgunun özgün dayanağı');
    expect(html).not.toContain('Unselected review summary');
  });
  it('caps new selections at five while preserving the ability to unselect', () => {
    const html = renderToStaticMarkup(<ReviewFindingPicker review={review()} indices={[0, 1, 2, 3, 4]} disabled={false} onChange={() => {}} onSource={() => {}} />);
    expect(html).toContain('5/5 bulgu seçildi'); expect(html.match(/checked=""/g)).toHaveLength(5);
    expect(html.match(/disabled=""/g)).toHaveLength(1);
  });
  it('disables selection while busy and distinguishes proposed/manual/unresolved responses from resolution', () => {
    expect(renderToStaticMarkup(<ReviewFindingPicker review={review()} indices={[]} disabled onChange={() => {}} onSource={() => {}} />)).toContain('<fieldset disabled=""');
    const event = review();
    const feedback: AnalysisFeedback = { review_id: event.id, source_version_id: event.version_id, content_sha256: event.content_sha256, review_recipe: event.recipe,
      findings: event.findings.slice(0, 3).map((item, index) => ({ ...item, index, finding_id: `finding:${index}`, editable_targets: ['conclusion'] })),
    };
    const responses: FeedbackResponse[] = [
      { finding_id: 'finding:0', outcome: 'proposed_change', edited_targets: ['conclusion'], text: '<img src="untrusted">', evidence_ids: ['source1'] },
      { finding_id: 'finding:1', outcome: 'requires_manual_work', edited_targets: [], text: 'SYNTHETIC revise fixed rule manually', evidence_ids: [] },
      { finding_id: 'finding:2', outcome: 'unresolved', edited_targets: [], text: 'SYNTHETIC evidence missing', evidence_ids: [] },
    ];
    const html = renderToStaticMarkup(<FeedbackSummary feedback={feedback} responses={responses} pass={1} onSource={() => {}} />);
    for (const text of ['SYNTHETIC-review', 'Düzenleme adayı', 'Elle çalışma gerekli', 'Çözülmedi', 'bulgunun giderildiğini veya hukuken onaylandığını göstermez', 'Önceki inceleme ve bulguları korunur', 'yanıt geçişi: 1', 'Yanıtın özgün dayanağı']) expect(html).toContain(text);
    expect(html).toContain('&lt;img'); expect(html).not.toContain('<img src'); expect(html).not.toContain('<details open');
  });
});
