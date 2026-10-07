import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { AnalysisCheckPanel, AnalysisContentView } from './AnalysisView';
import { AnalysisEditor } from './AnalysisEditor';
import { analysisForm, type AnalysisContent } from './analysisTypes';
import type { Matter } from '../../types';

function fixture(): AnalysisContent {
  return {
    title: 'SYNTHETIC analiz', issue: 'Ödeme ve teslim ilişkisi <script>private</script>', posture: 'Hazırlık', event_date: null,
    premises: [{ id: 'p1', kind: 'fact', fact_id: 'fact1', fact_revision: 2, text: '' }, { id: 'p2', kind: 'assumption', fact_id: null, fact_revision: null, text: 'Kabulün yapıldığı varsayılsın.' }],
    rules: [{ id: 'r1', kind: 'legal_norm', text: 'Avukatın doğrulanmamış kural yorumu', evidence_ids: ['e1'], conditions: [{ id: 'c1', kind: 'exception', text: 'Yazılı kabul', required_status: 'not_met' }] }],
    applications: [{ id: 'a1', rule_id: 'r1', premise_ids: ['p1', 'p2'], rationale: 'Kabulün kapsamı ayrıca incelenmeli.', assessments: [{ condition_id: 'c1', status: 'unknown', premise_ids: [] }] }],
    alternatives: [{ id: 'alt1', kind: 'search_gap', text: 'Karşı otorite araştırması eksik.', evidence_ids: [] }],
    conclusion: { text: 'Avukatın koşullu sonuç metni', requested_disposition: 'supported_candidate', application_ids: ['a1'], alternative_ids: ['alt1'], uncertainty: ['Kabul belirsiz.'], next_step: 'Özgün belgeleri inceleyin.' },
    evidence: [{ evidence_id: 'e1', start: 2, end: 60, full_passage_length: 400, text: 'Ödeme yapılmaz. <img src="private">', name: 'SYNTHETIC.png', document_id: 'd1', document_revision: 1, document_sha256: 'a'.repeat(64), locator: 'SYNTHETIC §1', quote_sha256: 'b'.repeat(64), passage_sha256: 'c'.repeat(64) }],
    fact_snapshots: [{ id: 'fact1', revision: 2, text: 'Taraf teslim yapıldığını iddia ediyor.', status: 'alleged', evidence_id: 'e1' }],
    checks: { recipe: 'private-rationale-checks-v1', scope: 'declared_structure_only', legal_approval: 'not_granted', effective_disposition: 'withheld', critical_count: 1, dependency_nodes: ['p1', 'r1', 'a1', 'alt1'], defects: [{ id: 'defect1', code: 'unqualified_legal_norm', target_id: 'r1', severity: 'critical', message: 'Hüküm sürümü ve zaman incelemesi gerekli.' }] },
    status: 'needs_review', authorship: 'user', legal_authority: false,
    revision_comparison: { previous_version_id: 'v1', changed_sections: ['applications'], changed_dependency_groups: ['fact_snapshots'], checks_no_longer_triggered: ['old-defect'], new_check_ids: ['defect1'], scope: 'structural_changes_only' },
  };
}

describe('private rationale review', () => {
  it('shows roles, steps, original source ranges and withheld evaluation', () => {
    const html = renderToStaticMarkup(<AnalysisContentView content={fixture()} onSource={() => {}} />);
    for (const text of ['Sonuç bekletiliyor', 'Hukuki onay verilmedi', 'Öncül → kural → uygulama', 'p1 · Beyan', 'Varsayım', 'otorite doğrulanmadı', 'Karşı otorite araştırması eksik', '[2, 60)', 'Özgün pasajı aç', 'çıkarımın doğruluğu', 'hukuki kusurun düzeltildiğini']) expect(html).toContain(text);
    expect(html).not.toContain('<details open');
  });
  it('renders all source and lawyer text as escaped text', () => {
    const html = renderToStaticMarkup(<AnalysisContentView content={fixture()} onSource={() => {}} />);
    expect(html).not.toContain('<script>private');
    expect(html).not.toContain('<img src');
    expect(html).toContain('&lt;script&gt;private');
    expect(html).toContain('&lt;img');
  });
  it('withholds a previously conditional assessment when its evidence is stale', () => {
    const content = fixture(); content.checks.effective_disposition = 'conditional'; content.checks.critical_count = 0;
    const html = renderToStaticMarkup(<AnalysisCheckPanel checks={content.checks} freshness={{ status: 'stale', reasons: ['Bağlı olgu değişti.'], scope: 'selected_private_dependencies_only' }} />);
    expect(html).toContain('Sonuç bekletiliyor');
    expect(html).toContain('Önceki metin korunuyor');
    expect(html).not.toContain('Koşullu taslak');
  });
  it('projects only editable input fields when revising a saved draft', () => {
    const form = analysisForm(fixture());
    expect(Object.keys(form.evidence[0]).sort()).toEqual(['document_revision', 'end', 'evidence_id', 'passage_sha256', 'start']);
    expect(form).not.toHaveProperty('checks');
    expect(form).not.toHaveProperty('fact_snapshots');
    expect(form).not.toHaveProperty('legal_authority');
    expect(form.conclusion.requested_disposition).toBe('supported_candidate');
    expect(form.premises[0].text).toBe('');
  });
  it('opens a missing condition assessment as unknown so a lawyer can repair it', () => {
    const content = fixture(); content.applications[0].assessments = [];
    expect(analysisForm(content).applications[0].assessments).toEqual([{ condition_id: 'c1', status: 'unknown', premise_ids: [] }]);
    expect(content.applications[0].assessments).toEqual([]);
  });
  it('binds a new draft to the visible fact revision without rewriting saved evidence or checks', () => {
    const content = fixture();
    const form = analysisForm(content, [{ id: 'fact1', revision: 3, text: 'Güncel beyan', status: 'disputed', updated_at: '' }]);
    expect(form.premises[0].fact_revision).toBe(3);
    expect(content.premises[0].fact_revision).toBe(2);
    expect(content.fact_snapshots[0].status).toBe('alleged');
    expect(form.evidence[0].passage_sha256).toBe('c'.repeat(64));
    expect(form.evidence[0].document_revision).toBe(1);
    expect(content.checks.effective_disposition).toBe('withheld');
  });
  it('starts an empty editor without inventing facts, rules or a conclusion', () => {
    const form = analysisForm();
    expect(form.premises).toEqual([]); expect(form.rules).toEqual([]); expect(form.conclusion.text).toBe('');
    const matter: Matter = { id: 'm1', title: 'SYNTHETIC', domain: 'contracts', objective: '', represented_party: '', stage: 'Hazırlık', status: 'draft', document_count: 0, created_at: '', facts: [], documents: [] };
    const html = renderToStaticMarkup(<AnalysisEditor matter={matter} onCancel={() => {}} onSave={async () => {}} />);
    for (const text of ['Yapıyı kontrol et', 'Analiz taslağını kaydet', 'Öncüller (0/20)', 'Kural veya sözleşme maddesi adayları (0/12)']) expect(html).toContain(text);
    expect(html).not.toContain('value="Teslim');
  });
});
