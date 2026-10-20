import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { AnalysisFocus } from './AnalysisFocus';
import { AnalysisContentView } from './AnalysisView';
import { analysisForm, type AnalysisFocusLineage, type AnalysisRecord } from './analysisTypes';

function record(): AnalysisRecord {
  return { ...analysisForm(), id: 'SYNTHETIC-analysis', revision: 1, version: 1, latest_version_id: 'SYNTHETIC-v1', created_at: '',
    status: 'needs_review', authorship: 'user', legal_authority: false, fact_snapshots: [],
    freshness: { status: 'current', reasons: [], scope: 'selected_private_dependencies_only' },
    applications: [{ id: 'a1', rule_id: 'r1', premise_ids: [], rationale: 'SYNTHETIC', assessments: [] }],
    alternatives: [{ id: 'alt1', kind: 'adverse_argument', text: '<script>SYNTHETIC adverse</script>', evidence_ids: [] }],
    evidence: [{ evidence_id: 'SYNTHETIC-source', document_id: 'SYNTHETIC-document', document_sha256: 'a'.repeat(64),
      document_revision: 1, passage_sha256: 'b'.repeat(64), quote_sha256: 'c'.repeat(64), name: 'SYNTHETIC.docx',
      locator: 'SYNTHETIC §1', text: '📄 SYNTHETIC exact quote', start: 2, end: 24, full_passage_length: 30 }],
    checks: { recipe: 'private-rationale-checks-v1', scope: 'declared_structure_only', legal_approval: 'not_granted',
      effective_disposition: 'withheld', critical_count: 0, defects: [], dependency_nodes: [] },
    revision_comparison: { previous_version_id: null, changed_sections: [], changed_dependency_groups: [], checks_no_longer_triggered: [], new_check_ids: [], scope: 'structural_changes_only' } };
}

function lineage(): AnalysisFocusLineage {
  return { recipe: 'private-analysis-focus-v1', scope: 'creation_selection_only', parent_analysis_id: 'SYNTHETIC-parent',
    parent_version_id: 'SYNTHETIC-parent-v1', parent_revision: 2, parent_content_sha256: 'd'.repeat(64), parent_review_id: 'SYNTHETIC-review',
    derived_ai: true, application_id: 'a1', omission_note: '<img src="SYNTHETIC">', limitation: 'SYNTHETIC limitation',
    review_transferred: false, omitted: { alternatives: ['SYNTHETIC-omitted'], evidence: [] }, replaced_sections: ['conclusion'],
    narrowed_ranges: [{ evidence_id: 'SYNTHETIC-source', parent_start: 2, parent_end: 24, start: 3, end: 20 }] };
}

describe('explicit focused analysis flow', () => {
  it('defaults to retained alternatives and quotes, requires explicit scope and disables unpreviewed save', () => {
    const html = renderToStaticMarkup(<AnalysisFocus matterId="SYNTHETIC-matter" record={record()} onSource={() => {}} onSaved={async () => {}} />);
    for (const text of ['Bağlama sığan ayrı odak analizi', 'özgün belgeler', 'model kendiliğinden çalışmaz', 'başlangıçta tümü seçili',
      'Kapsam dışı kalanlar', 'Unicode aralıkları', 'Seçilen metin:', 'SYNTHETIC.docx', 'Odak kapsamını ve bütçeyi önizle']) expect(html).toContain(text);
    expect(html).toMatch(/disabled="">Ayrı odak analizini kaydet/);
    expect(html.match(/checked=""/g)?.length).toBe(2);
    expect(html).not.toContain('<script>'); expect(html).toContain('&lt;script&gt;');
    expect(html).not.toContain('<details open');
  });
  it.each(['stale', 'nested', 'public'] as const)('withholds the unsupported %s narrowing path', kind => {
    const data = record();
    if (kind === 'stale') data.status = 'stale';
    if (kind === 'nested') data.focus_lineage = lineage();
    if (kind === 'public') data.authority_contributions = [{}] as AnalysisRecord['authority_contributions'];
    const html = renderToStaticMarkup(<AnalysisFocus matterId="SYNTHETIC" record={data} onSource={() => {}} onSaved={async () => {}} />);
    expect(html).toContain('bu ilk akışta daraltılamaz'); expect(html).not.toContain('Ayrı odak analizini kaydet');
  });
  it('shows exact historical origin, explicit omissions and partial ranges without importing review approval', () => {
    const data = record(); data.focus_lineage = lineage();
    const html = renderToStaticMarkup(<AnalysisContentView content={data} onSource={() => {}} />);
    for (const text of ['SYNTHETIC-parent-v1', 'SYNTHETIC-review', 'İçerik SHA-256:', 'SYNTHETIC-omitted',
      '[2, 24) → [3, 20)', 'inceleme kararları aktarılmadı', 'yalnız oluşturma seçimini', 'model katkısı ayrıca incelenmelidir']) expect(html).toContain(text);
    expect(html).not.toContain('<img'); expect(html).toContain('&lt;img');
  });
});
