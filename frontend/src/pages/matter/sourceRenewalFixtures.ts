import { createHash } from 'node:crypto';
import { canonicalJson } from './sourceReviewTypes';
import { manifest as original } from './sourceReviewFixtures';
import type { Renewal, RenewalComparison, RenewalMetadata } from './sourceRenewalTypes';
export const parentId = 'sac-' + '1'.repeat(20) + '-' + '2'.repeat(32);
const quote = original.sources[0].evidence;
const identity = { passage_id: quote.passage_id, source_version_id: quote.source_version_id, document_id: quote.document_id,
  quote_sha256: quote.quote_sha256, source_sha256: quote.source_sha256, text_sha256: quote.text_sha256, locator_map_sha256: quote.locator_map_sha256,
  start_offset: quote.start_offset, end_offset: quote.end_offset, offset_unit: quote.offset_unit };
const targets = { 'rule:r1': '3'.repeat(64) };
export const metadata: RenewalMetadata = { id: parentId, matter_id: 'matter1', analysis_id: 'analysis1', manifest_sha256: '4'.repeat(64), review_id: null,
  admission_completed: true, can_record: true, version_id: 'old-v1', product_id: 'old-p1', graph_release_pin: original.graph_release_pin, recorded_by: 'old-selector',
  sources: [{ identity, targets }], old_quotes_and_notes: 'withheld_use_original_guarded_context', review_inheritance: 'none', legal_equivalence: 'not_assessed' };
export const renewal: Renewal = { parent_context_id: parentId, expected_parent_manifest_sha256: metadata.manifest_sha256, expected_parent_review_id: null,
  reason: 'TEST ONLY explicit replacement reason', mappings: [{ parent_passage_id: quote.passage_id, new_passage_ids: [quote.passage_id], disposition: 'retained', note: 'TEST ONLY exact version mapping' }], added_passage_ids: [] };
export const comparison: RenewalComparison = { recipe: 'private-source-context-renewal-v1', depth: 1, parent_context_id: parentId, parent_manifest_sha256: metadata.manifest_sha256,
  parent_packet_sha256: '5'.repeat(64), parent_review_id: null, parent_version_id: 'old-v1', parent_product_id: 'old-p1', parent_graph_release_pin: original.graph_release_pin,
  release_changed: false, analysis_changed: true, research_changed: true,
  entries: [{ parent_identity: identity, parent_targets: targets, disposition: 'retained', note: renewal.mappings[0].note,
    successors: [{ identity, targets: { 'rule:r1': '6'.repeat(64) }, exact_evidence_same: true, exact_targets_same: false }] }], added_passage_ids: [],
  old_quotes_and_notes: 'withheld_use_original_guarded_context', review_inheritance: 'none', original_dependencies: 'retained_in_immutable_parent_not_reauthorized', legal_equivalence: 'not_assessed' };
export const renewedManifest = { ...original, renewal, renewal_comparison: comparison,
  renewal_comparison_sha256: createHash('sha256').update(canonicalJson(comparison)).digest('hex') };
