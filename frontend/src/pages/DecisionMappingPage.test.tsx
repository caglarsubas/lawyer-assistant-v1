import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import DecisionMappingPage, { DecisionHistory, OccurrenceList } from './DecisionMappingPage';
import { decisionPath, decisionReviewPayload, emptyResolution, fetchDecisionOccurrences, type DecisionOccurrences, type DecisionState } from './decisionMapping';
import { comparisonHash } from './sourceComparison';
import type { PublicSourceDetail, PublicSourcePassages, User } from '../types';
const sourceId = 'a'.repeat(64); const text = 'Karar Tarihi: 12/1/2021'; const full = `😀 ${text} <script>x</script>`;
const user = { id: 'reviewer', role: 'curator', name: 'Küratör', permissions: ['source.curate'] } as User;
async function fixture() {
  const passage = { id: 'p1', start: 10, end: 10 + Array.from(full).length, text: full, text_sha256: await comparisonHash(full), locator: 'Test passage' };
  const source = { source_id: sourceId, source_version_id: 'v1', text_sha256: 'b'.repeat(64), raw_sha256: 'c'.repeat(64), items: [passage], offset_unit: 'unicode_code_points', integrity_scope: 'all_artifacts_verified' } as PublicSourcePassages;
  const start = 12; const end = start + text.length;
  const item = { id: await comparisonHash(JSON.stringify([sourceId, 'v1', source.raw_sha256, source.text_sha256, 'p1', passage.text_sha256, 'tr-jurisprudence-occurrences-v1', 'decision_date_label', start, end])),
    kind: 'decision_date', rule: 'decision_date_label', start, end, passage_start: 2, passage_end: end - 10, text, sha256: await comparisonHash(text), value_start: 26, value_end: end, value_text: '12/1/2021', parsed_value: '2021-01-12', parse_status: 'calendar_valid_only', status: 'machine_proposed' as const, identity_status: 'unresolved' as const, event_role: 'unknown' as const, authority_treatment: 'unknown' as const };
  const data = { schema_version: 'jurisprudence-occurrences-v1', extraction_version: 'tr-jurisprudence-occurrences-v1', source_id: sourceId, source_version_id: 'v1', raw_sha256: source.raw_sha256, text_sha256: source.text_sha256, passage_id: 'p1', passage_sha256: passage.text_sha256, passage_start: passage.start, passage_end: passage.end, locator: passage.locator, offset_unit: 'unicode_code_points', scope: 'selected_passage_only', integrity_scope: 'all_artifacts_verified', items: [item], count: 1, truncated: false, legal_identity_resolved: false, dates_promoted: false, human_review_recorded: false, graph_updated: false, limitations: [] } as DecisionOccurrences;
  return { source, passage, data, item };
}
async function response(data: DecisionOccurrences) { const evidence_json = JSON.stringify(data); return new Response(JSON.stringify({ evidence_json, evidence_sha256: await comparisonHash(evidence_json) })); }
const state = { source: { id: sourceId } as PublicSourceDetail, revision: 4, source_review_revision: 5, source_review_ready: true, export_allowed: true, publication_eligible: false, items: [], history: [], history_truncated: false, limitations: [], handoff_ready: false, assigned_to: null } as DecisionState;
describe('accountable decision UI', () => {
  const fetchMock = vi.fn<typeof fetch>();
  beforeEach(() => { vi.stubGlobal('fetch', fetchMock); fetchMock.mockReset(); }); afterEach(() => vi.unstubAllGlobals());
  it('denies users before source retrieval', () => { expect(renderToStaticMarkup(<DecisionMappingPage sourceId={sourceId} user={{ ...user, role: 'lawyer' }} />)).toContain('İnceleme yetkisi gerekli'); expect(fetchMock).not.toHaveBeenCalled(); });
  it.each(['../auth', 'A'.repeat(64), sourceId + '?token=x'])('rejects unsafe identifiers %s', id => expect(() => decisionPath(id)).toThrow());
  it('validates exact Unicode candidate and receipt identity', async () => { const { source, passage, data } = await fixture(); fetchMock.mockResolvedValue(await response(data)); expect(await fetchDecisionOccurrences(source, passage)).toEqual(data); });
  it.each(['source', 'offset', 'text', 'promoted', 'id', 'role', 'hash'])('withholds tampered %s receipts', async change => {
    const { source, passage, data } = await fixture();
    if (change === 'source') data.source_id = 'e'.repeat(64); if (change === 'offset') data.items[0].start++; if (change === 'text') data.items[0].text += 'x'; if (change === 'promoted') Object.assign(data, { dates_promoted: true }); if (change === 'id') data.items[0].id = 'f'.repeat(64); if (change === 'role') Object.assign(data.items[0], { event_role: 'publication' });
    fetchMock.mockResolvedValue(change === 'hash' ? new Response(JSON.stringify({ evidence_json: JSON.stringify(data), evidence_sha256: 'd'.repeat(64) })) : await response(data)); await expect(fetchDecisionOccurrences(source, passage)).rejects.toThrow();
  });
  it('does not return cancelled evidence', async () => { const { source, passage, data } = await fixture(); fetchMock.mockResolvedValue(await response(data)); const controller = new AbortController(); controller.abort(); await expect(fetchDecisionOccurrences(source, passage, controller.signal)).rejects.toThrow(); });
  it('escapes candidate text and shows unknown roles', async () => { const { item } = await fixture(); const markup = renderToStaticMarkup(<OccurrenceList items={[{ ...item, text: '<script>x</script>' }]} selectedId={item.id} disabled onSelect={() => undefined} />); expect(markup).toContain('&lt;script&gt;'); expect(markup).not.toContain('<script>'); expect(markup).toContain('kimlik ve rol bilinmiyor'); expect(markup).toContain('aria-pressed="true"'); expect(markup).toContain('disabled=""'); });
  it('retains disagreeing historical interpretations as inert text', async () => {
    const { item } = await fixture(); const event = { id: 'e1', revision: 2, mapping_id: 'm1', event_type: 'review', reviewer: { id: user.id, name: '<img src=x>' }, created_at: '2026-10-11T12:00:00Z', rationale: '<script>historical</script>', decision: 'accepted' as const, evidence_refs: [], source_review_revision: 3, snapshot: { passage_id: 'p1', candidate: item, status: 'accepted' as const, resolution: { ...emptyResolution(item), decision_ref: '<a href="javascript:x">' }, reviewed_source_revision: 3 } };
    const markup = renderToStaticMarkup(<DecisionHistory state={{ ...state, items: [{ ...event.snapshot, id: 'm1', status: 'needs_changes', stale: false, resolution: null, last_event: event }], history: [event], history_truncated: true }} />); expect(markup).toContain('Düzeltme gerekli'); expect(markup).toContain('Önceki görüşler korunur'); expect(markup).toContain('Eski olaylar silinmedi'); expect(markup).not.toContain('<script>'); expect(markup).not.toContain('<img'); expect(markup).not.toContain('<a href="javascript');
  });
  it('requires evidence and source readiness; sends no accepted interpretation for rejection', async () => { const { item } = await fixture(); const value = emptyResolution(item); expect(() => decisionReviewPayload(state, 'accepted', 'Test rationale', value, '', '')).toThrow(); expect(() => decisionReviewPayload({ ...state, source_review_ready: false }, 'accepted', 'Test rationale', value, 'support', sourceId)).toThrow(); expect(decisionReviewPayload(state, 'rejected', 'Test rationale', value, '', '')).toMatchObject({ expected_revision: 4, expected_source_review_revision: 5, resolution: null, evidence_refs: [] }); expect(value.event_date).toBeNull(); });
});
