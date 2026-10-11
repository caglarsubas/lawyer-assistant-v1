import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { DossierSummary } from './DecisionMappingPage';
import { fetchDecisionDossier, type DecisionDossier, type DecisionState } from './decisionMapping';
import { comparisonHash } from './sourceComparison';
import type { PublicSourceDetail } from '../types';
const id = 'a'.repeat(64); const user = { id: 'reviewer', name: 'Synthetic reviewer', firm_id: 'test-firm' };
const artifacts = { 'raw.bin': { sha256: 'b'.repeat(64), bytes: 20 }, 'text.txt': { sha256: 'c'.repeat(64), bytes: 12 } };
const state = { source: { id, title: 'Synthetic source', source_url: 'https://example.invalid/synthetic', source_version_id: 'v1', domain: 'employment', acquired_at: null, rights_status: 'pending', review_status: 'pending', passage_count: 1, publication_status: 'staged', artifacts, dates: { published_on: null, effective_from: null, effective_until: null }, integrity_scope: 'all_artifacts_verified', limitations: [], injection_risk_hints: [], review_evidence: { rights_supplied: false, identity_supplied: false, trust: 'synthetic' } } as PublicSourceDetail, revision: 2, source_review_revision: 3, export_allowed: true, publication_eligible: false, history_truncated: false, history: [{ revision: 2 }, { revision: 1 }] } as DecisionState;
async function fixture() {
  const text = '😀 Exact synthetic evidence';
  return { schema_version: 'decision-review-dossier-v1', confidentiality: 'firm_confidential', firm_id: user.firm_id, exported_by: user,
    exported_at: '2026-10-11T12:00:00Z', signed: false, publication_eligible: false, source_binding: { source_id: id, artifacts }, mappings: state, history_complete: true,
    source_review: { revision: 3, history_complete: true, history: [{ revision: 3 }, { revision: 2 }, { revision: 1 }] },
    supporting_passages: [{ id: 'p1', start: 2, end: 2 + Array.from(text).length, text, sha256: await comparisonHash(text), locator: 'Synthetic passage' }],
    handoff_checks: { independent_review_ready: false, canonical_identity_resolved: false, legal_effect_verified: false, publication_eligible: false, unresolved_mapping_ids: ['m1'], identity_conflicts: [] }, limitations: ['Synthetic review only'] } as DecisionDossier;
}
async function response(data: DecisionDossier) { const evidence_json = JSON.stringify(data); return new Response(JSON.stringify({ evidence_json, evidence_sha256: await comparisonHash(evidence_json) })); }
describe('confidential decision dossier', () => {
  const fetchMock = vi.fn<typeof fetch>(); beforeEach(() => { fetchMock.mockReset(); vi.stubGlobal('fetch', fetchMock); }); afterEach(() => vi.unstubAllGlobals());
  it('pins source and ledger versions and returns exact hashed bytes', async () => { const data = await fixture(); fetchMock.mockResolvedValue(await response(data)); const result = await fetchDecisionDossier(state, user); expect(result.data).toEqual(data); expect(JSON.parse(String(fetchMock.mock.calls[0][1]?.body))).toEqual({ expected_revision: 2, expected_source_review_revision: 3 }); });
  it.each(['firm', 'user', 'revision', 'source', 'history', 'source_history', 'publication', 'artifact', 'passage', 'hash'])('withholds mismatched %s evidence', async change => {
    const data = structuredClone(await fixture());
    if (change === 'firm') data.firm_id = 'another-firm'; if (change === 'user') data.exported_by.id = 'another-reviewer'; if (change === 'revision') data.mappings.revision++; if (change === 'source') data.source_binding.source_id = 'd'.repeat(64); if (change === 'history') data.mappings.history.pop(); if (change === 'source_history') data.source_review.history[0].revision--; if (change === 'publication') Object.assign(data, { publication_eligible: true }); if (change === 'artifact') data.source_binding.artifacts['raw.bin'].sha256 = 'e'.repeat(64); if (change === 'passage') data.supporting_passages[0].end++;
    fetchMock.mockResolvedValue(change === 'hash' ? new Response(JSON.stringify({ evidence_json: JSON.stringify(data), evidence_sha256: 'f'.repeat(64) })) : await response(data)); await expect(fetchDecisionDossier(state, user)).rejects.toThrow();
  });
  it('cancels before returning a downloadable file', async () => { fetchMock.mockResolvedValue(await response(await fixture())); const controller = new AbortController(); controller.abort(); await expect(fetchDecisionDossier(state, user, controller.signal)).rejects.toThrow(); });
  it('shows unresolved conflicts as escaped review evidence, never publication approval', async () => { const data = await fixture(); data.handoff_checks.identity_conflicts = [{ decision_ref: '<script>x</script>', field: 'decision_number', alternatives: [{ value: '<img src=x>', mapping_ids: ['m1'] }] }]; const markup = renderToStaticMarkup(<DossierSummary data={data} />); expect(markup).toContain('İmzasız'); expect(markup).toContain('Yayımlanmadı'); expect(markup).toContain('Eksikler veya uyuşmazlıklar var'); expect(markup).not.toContain('<script>'); expect(markup).not.toContain('<img'); });
});
