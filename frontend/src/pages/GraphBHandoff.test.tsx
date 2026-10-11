import { afterEach, describe, expect, it, vi } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { HandoffSummary } from './DecisionIdentityReview';
import { fetchGraphBHandoff, type GraphBHandoff, type IdentityState } from './decisionIdentity';
import { comparisonHash } from './sourceComparison';
import type { User } from '../types';
const sourceId = 'a'.repeat(64); const user = { id: 'synthetic', firm_id: 'synthetic-firm' } as User;
const current = { id: 'synthetic-event', revision: 1 };
async function fixture() {
  const files: GraphBHandoff['files'] = {};
  for (const name of ['original/text.txt', 'candidate/locators.json', 'candidate/jurisprudence.nt']) {
    const text = 'Synthetic bytes for ' + name;
    files[name] = { sha256: await comparisonHash(text), bytes: text.length, encoding: 'base64', data: btoa(text) };
  }
  const artifacts = { 'text.txt': { sha256: files['original/text.txt'].sha256, bytes: files['original/text.txt'].bytes } };
  const state = { source: { id: sourceId, artifacts }, revision: 1, mapping_revision: 2, source_review_revision: 3, current } as unknown as IdentityState;
  const data = { schema_version: 'decision-graph-b-handoff-v1', compiler_version: 'decision-graph-b-handoff-v1', confidentiality: 'firm_confidential', firm_id: user.firm_id,
    source_binding: { source_id: sourceId, artifacts }, identity_revision: 1, mapping_revision: 2, source_review_revision: 3, ontology_sha256: 'b'.repeat(64),
    identity_history: [current], history_complete: true, mapping_history: [{ revision: 2 }, { revision: 1 }], source_review_history: [{ revision: 3 }, { revision: 2 }, { revision: 1 }],
    files, structural_validation: { conforms: true, assertion_count: 3, legal_truth_verified: false }, scope: 'own_decision_identity_candidates_only', omitted_mapping_ids: [],
    signed: false, graph_updated: false, global_registry_qualified: false, legal_effect_verified: false, publication_eligible: false, limitations: ['<script>inert source text</script>'] } as unknown as GraphBHandoff;
  // Independent protocol construction: canonicalize nested object keys before hashing.
  function ordered(value: unknown): unknown {
    if (Array.isArray(value)) return value.map(ordered);
    if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value).sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0).map(([key, item]) => [key, ordered(item)]));
    return value;
  }
  const core = { ...data, files: Object.fromEntries(Object.entries(files).map(([name, { sha256, bytes, encoding }]) => [name, { sha256, bytes, encoding }])) };
  data.packet_id = await comparisonHash(JSON.stringify(ordered(core)));
  return { state, data };
}
async function response(data: GraphBHandoff) { const evidence_json = JSON.stringify(data); return new Response(JSON.stringify({ evidence_json, evidence_sha256: await comparisonHash(evidence_json) })); }
afterEach(() => vi.unstubAllGlobals());
describe('private Graph B download', () => {
  it('validates physical bytes, complete histories, packet hash and all three pins', async () => {
    const { state, data } = await fixture(); const mock = vi.fn().mockResolvedValue(await response(data)); vi.stubGlobal('fetch', mock);
    expect((await fetchGraphBHandoff(state, user)).data).toEqual(data);
    expect(JSON.parse(mock.mock.calls[0][1].body)).toEqual({ expected_revision: 1, expected_mapping_revision: 2, expected_source_review_revision: 3 });
  });
  it.each(['firm', 'revision', 'history', 'physical', 'hash', 'file', 'publication', 'packet'])('withholds tampered %s packages', async change => {
    const { state, data } = await fixture();
    if (change === 'firm') data.firm_id = 'another'; if (change === 'revision') data.identity_revision++; if (change === 'history') data.mapping_history.pop();
    if (change === 'physical') data.files['original/text.txt'].data = btoa('forged'); if (change === 'hash') data.files['candidate/locators.json'].sha256 = 'c'.repeat(64);
    if (change === 'file') data.files['../private'] = data.files['original/text.txt']; if (change === 'publication') Object.assign(data, { publication_eligible: true }); if (change === 'packet') data.packet_id = 'f'.repeat(64);
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(await response(data))); await expect(fetchGraphBHandoff(state, user)).rejects.toThrow();
  });
  it('withholds cancelled downloads and renders only inert private candidate status', async () => {
    const { state, data } = await fixture(); vi.stubGlobal('fetch', vi.fn().mockResolvedValue(await response(data))); const controller = new AbortController(); controller.abort();
    await expect(fetchGraphBHandoff(state, user, controller.signal)).rejects.toThrow();
    const markup = renderToStaticMarkup(<HandoffSummary data={data} />); expect(markup).toContain('Büroya özel'); expect(markup).toContain('Yayımlanmadı'); expect(markup).toContain('Hukuki doğruluk doğrulanmadı'); expect(markup).not.toContain('<script>');
  });
});
