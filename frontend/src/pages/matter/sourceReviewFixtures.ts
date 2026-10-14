import { createHash } from 'node:crypto';
import { DIMENSIONS, reviewPayload, sourceIdentity } from './sourceReviewTypes';
import type { ContextView, EditableAssessment, Manifest, Quote, ReviewInputs, Selection } from './sourceReviewTypes';

export const text = 'TEST ONLY 📄\r\n<img src="https://private.invalid/x"> Özgün alıntı.\r\n';
export const quote: Quote = { passage_id: 'urn:test:passage', source_version_id: 'urn:test:version', document_id: 'urn:test:raw', text, locator: 'TEST ONLY page 1',
  quote_sha256: createHash('sha256').update(text).digest('hex'), source_sha256: 'a'.repeat(64), text_sha256: 'b'.repeat(64), locator_map_sha256: 'c'.repeat(64),
  start_offset: 2, end_offset: 2 + Array.from(text).length, offset_unit: 'unicode_codepoint', release_id: 'd'.repeat(64),
  assertion_id: null, authority_id: null, authority_resolution: 'not_performed', matter_applicability: 'not_assessed', temporal_applicability: 'not_assessed', finality: 'unknown' };
export const selection: Selection = { ...sourceIdentity(quote), target_ids: ['rule:r1'], relationship: 'unresolved', note: 'TEST ONLY private nomination <script>private</script>' };
export const manifest: Manifest = { matter_id: 'matter1', analysis_id: 'analysis1', version_id: 'v1', product_id: 'p1', title: 'TEST ONLY source selection', purpose: 'TEST ONLY private review', selections: [selection],
  expected_release_id: quote.release_id, expected_serving_sha256: 'e'.repeat(64), graph_release_pin: { status: 'verified', release_id: quote.release_id, serving_sha256: 'e'.repeat(64), activation_sequence: 2 },
  sources: [{ selection, evidence: quote, target_snapshots: { 'rule:r1': { text: 'PRIVATE analysis step' } } }], analysis_author_id: 'version-author', analysis_owner_id: 'original-owner',
  analysis_content_sha256: 'f'.repeat(64), product_sha256: 'a'.repeat(64), event_date: '2024-03-01', research_snapshot: { recipe: 'test-only', release_id: quote.release_id, serving_sha256: 'e'.repeat(64), as_of: '1921-01-01' },
  coverage: { completeness: 'unknown', total_expected: null }, limitations: ['TEST ONLY partial corpus'], legal_approval: 'not_granted', matter_applicability: 'not_assessed', temporal_applicability: 'not_assessed', finality: 'unknown' };
export const inputs: ReviewInputs = { manifest, expected_manifest_sha256: 'b'.repeat(64), expected_review_id: null, dimensions: { quote_identity: 'Özgün alıntı', target_alignment: 'Analiz adımları', temporal_limits: 'Tarih sınırları' }, independent_reviewer_required: true, can_record: true };
export function assessments(): EditableAssessment[] { return [{ ...selection, relationship: 'adverse_candidate', note: 'TEST ONLY independent interpretation', observations: DIMENSIONS.map(dimension => ({ dimension, outcome: 'confirmed', note: 'TEST ONLY confirmed limitations, not legal approval' })) }]; }
export function view(): ContextView { return { id: 'sac-' + 'a'.repeat(20) + '-' + 'b'.repeat(32), recorded_by: 'selector', manifest_sha256: inputs.expected_manifest_sha256,
  manifest, public_source_access: true, freshness: { status: 'current', reasons: [] }, review: { effective_state: 'reviewed_conditional', id: 'sar-' + 'c'.repeat(20) + '-' + 'd'.repeat(32), latest_review_id: 'sar-' + 'c'.repeat(20) + '-' + 'd'.repeat(32), is_latest: true,
    snapshot: { recorded_by: 'reviewer', recorded_at: '2026-10-14T00:00:00Z', sequence: 1, previous_review_id: null, packet_sha256: 'e'.repeat(64), dimensions: inputs.dimensions, legal_approval: 'not_granted', input: reviewPayload(assessments(), 'TEST ONLY review note', 'reviewed_conditional', inputs)! } } }; }
