import { describe, expect, it, vi } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { AssignedAccounts } from './AccessAssignments';
import { ReviewRecord } from './ReviewRecord';
import { DecisionResolutionView } from './DecisionResolutionView';
import { ResearchOutputPicker } from './matter/ResearchOutputPicker';
import type { Employee } from './FirmAdminPage';
import type { Product } from '../types';
import type { DecisionResolution } from './decisionMapping';

describe('populated records preserve identity and history', () => {
  it('distinguishes duplicate titles by version and retains selected identity, stale status and escaped text', () => {
    const products = [2, 3].map(version => ({ id: `output-${version}`, version, title: '<script>same title</script>', created_at: '2026-11-01T12:00:00Z', status: version === 2 ? 'stale' : 'needs_review' } as Product));
    const before = structuredClone(products); const html = renderToStaticMarkup(<ResearchOutputPicker products={products} selectedId="output-3" onSelect={vi.fn()} />);
    expect(html.match(/aria-pressed="true"/g)).toHaveLength(1); expect(html).toContain('Sürüm 2'); expect(html).toContain('Sürüm 3');
    expect(html).toContain('Yeniden inceleme gerekli'); expect(html).toContain('&lt;script&gt;'); expect(html).not.toContain('<script>'); expect(products).toEqual(before);
  });
  it('uses account identities for duplicate names and keeps inactive and non-lawyer duty controls disabled', () => {
    const employees = [{ id: 'a', username: 'first', active: true, professional_role: 'lawyer' }, { id: 'b', username: 'second', active: false, professional_role: 'lawyer' }, { id: 'c', username: 'third', active: true, professional_role: 'staff' }].map(p => ({ ...p, name: 'Aynı İsim' } as Employee));
    const html = renderToStaticMarkup(<AssignedAccounts items={employees.map(p => ({ user_id: p.id }))} employees={employees} kind="workspaces" busy={false} onChange={vi.fn()} />);
    expect(html).toContain('Aynı İsim (first)'); expect(html).toContain('Aynı İsim (second)'); expect(html).toContain('devre dışı');
    expect(html.match(/type="checkbox" disabled=""/g)).toHaveLength(4);
  });
  it('keeps saved rationale, reviewer, revision and evidence exact without executable markup', () => {
    const event = { id: 'e', revision: 9, reviewer: { id: 'r', name: '<img src=x>' }, created_at: '2026-11-01T12:00:00Z', rationale: '  İlk satır\nİkinci satır <script>x</script>', evidence_refs: [{ reference: 'source-v2', sha256: 'a'.repeat(64) }] };
    const before = structuredClone(event); const html = renderToStaticMarkup(<ReviewRecord event={event} label="Düzeltme gerekli" />);
    expect(html).toContain('Revizyon 9'); expect(html).toContain('  İlk satır\nİkinci satır &lt;script&gt;'); expect(html).toContain('source-v2'); expect(html).toContain('a'.repeat(64));
    expect(html).not.toContain('<img'); expect(html).not.toContain('<script>'); expect(html).not.toContain('<input'); expect(event).toEqual(before);
  });
  it('distinguishes unknown dates from zero offsets and retains exact underlying resolution values', () => {
    const resolution = { start: 0, end: 7, occurrence_role: 'cited_authority', proceeding_ref: null, decision_ref: '<b>exact-ref</b>', institution_ref: null, target_ref: null, target_version_ref: null, event_role: 'unknown', event_date: null, authority_treatment: 'distinguishes' } as DecisionResolution;
    const html = renderToStaticMarkup(<DecisionResolutionView resolution={resolution} />);
    expect(html).toContain('<dd>0</dd>'); expect(html).toContain('Atıf yapılan otorite'); expect(html).toContain('Ayırt ediyor'); expect(html).toContain('<dt>Tarih</dt><dd>Bilinmiyor</dd>');
    expect(html).toContain('cited_authority'); expect(html).toContain('distinguishes'); expect(html).toContain('&lt;b&gt;exact-ref&lt;/b&gt;'); expect(html).not.toContain('<b>exact-ref</b>');
  });
});
