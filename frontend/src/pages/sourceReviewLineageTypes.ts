import { canonicalJson } from './matter/sourceReviewTypes';
import { navigationReviewId, verifyNavigation, type NavigationMetadata, type SourceTarget } from './sourceContextNavigationTypes';
export type ReviewMetadata = { id: string; state: 'unknown' | 'changes_requested' | 'reviewed_conditional'; sequence: number | null;
  recorded_at: string | null; packet_sha256: string | null; manifest_sha256: string | null; previous_review_id: string | null;
  admission: 'complete' | 'pending' | 'unavailable'; integrity: 'verified' | 'unavailable' };
export type ReviewLineage = { recipe: 'private-source-review-lineage-v1'; matter_id: string; analysis_id: string; context_id: string; review_id: string;
  observed_at: string; context_navigation: NavigationMetadata; selected_review: ReviewMetadata; current_head: ReviewMetadata | null;
  head_relationship: 'current_head' | 'different_from_head' | 'unestablished';
  lineage: { scope: 'selected_predecessors_only'; status: 'complete_to_first_event' | 'truncated' | 'unavailable'; window: number;
    items: ReviewMetadata[]; next_review_id: string | null; total_count: null; head_reachability: 'not_checked' };
  tools_available: boolean; source_verification: 'not_checked'; legal_readiness: 'not_established'; qualification_granted: false };
const keys = (value: object, expected: string[]) => canonicalJson(Object.keys(value).sort()) === canonicalJson(expected.sort());
const sha = (value: unknown): value is string => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value);
const stamp = (value: unknown) => typeof value === 'string' && value.length <= 40 && Number.isFinite(Date.parse(value));
export function verifyReviewLineage(value: ReviewLineage, target: SourceTarget) {
  const fail = () => { throw new Error('Seçilen tarihsel kararın tam kimliği veya sınırlı bağlantıları doğrulanamadı.'); };
  if (!value || !target.review_id || !keys(value, ['recipe', 'matter_id', 'analysis_id', 'context_id', 'review_id', 'observed_at', 'context_navigation', 'selected_review', 'current_head', 'head_relationship', 'lineage', 'tools_available', 'source_verification', 'legal_readiness', 'qualification_granted'])
    || value.recipe !== 'private-source-review-lineage-v1' || value.matter_id !== target.matter_id || value.analysis_id !== target.analysis_id || value.context_id !== target.context_id || value.review_id !== target.review_id
    || !stamp(value.observed_at) || value.source_verification !== 'not_checked' || value.legal_readiness !== 'not_established' || value.qualification_granted !== false) fail();
  verifyNavigation(value.context_navigation, target);
  const check = (row: ReviewMetadata) => verifyReviewMetadata(row, value.context_navigation.context.manifest_sha256);
  check(value.selected_review); if (value.selected_review.id !== target.review_id) fail(); if (value.current_head) check(value.current_head);
  const head = value.current_head, selected = value.selected_review, lineage = value.lineage;
  if (head && head.id !== value.context_navigation.historical_review.id) fail();
  const relation = head?.integrity === 'verified' && selected.integrity === 'verified' ? (head.id === selected.id ? 'current_head' : 'different_from_head') : 'unestablished';
  if (value.head_relationship !== relation || value.observed_at !== value.context_navigation.observed_at
) fail();
  if (!lineage || !keys(lineage, ['scope', 'status', 'window', 'items', 'next_review_id', 'total_count', 'head_reachability'])
    || lineage.scope !== 'selected_predecessors_only' || !['complete_to_first_event', 'truncated', 'unavailable'].includes(lineage.status)
    || !Number.isInteger(lineage.window) || lineage.window < 1 || lineage.window > 10 || !Array.isArray(lineage.items) || lineage.items.length > lineage.window
    || lineage.total_count !== null || lineage.head_reachability !== 'not_checked') fail();
  if (value.tools_available !== (value.context_navigation.tools_available && selected.integrity === 'verified' && selected.admission === 'complete' && lineage.status !== 'unavailable')) fail();
  if (head?.integrity === 'verified' && (head.state !== value.context_navigation.historical_review.state || head.admission !== value.context_navigation.admission.review_state)) fail();
  if (head?.id === selected.id && canonicalJson(head) !== canonicalJson(selected)) fail();
  const seen = new Set<string>();
  lineage.items.forEach((row, index) => { check(row); if (row.integrity !== 'verified' || seen.has(row.id)) fail(); seen.add(row.id);
    if (index === 0 ? canonicalJson(row) !== canonicalJson(selected) : (lineage.items[index - 1].previous_review_id !== row.id || lineage.items[index - 1].sequence! - 1 !== row.sequence)) fail(); });
  const last = lineage.items.at(-1);
  if (lineage.status === 'complete_to_first_event' && (!last || last.sequence !== 1 || last.previous_review_id !== null || lineage.next_review_id !== null)) fail();
  if (lineage.status === 'truncated' && (lineage.items.length !== lineage.window || !last || !navigationReviewId(lineage.next_review_id) || lineage.next_review_id !== last.previous_review_id || seen.has(lineage.next_review_id))) fail();
  if (lineage.status === 'unavailable' && lineage.next_review_id !== null) fail();
}

export function verifyReviewMetadata(row: ReviewMetadata, manifest: string | null) {
  const fail = () => { throw new Error('Karar kaydının değiştirilemez kimliği doğrulanamadı.'); };
  if (!row || !keys(row, ['id', 'state', 'sequence', 'recorded_at', 'packet_sha256', 'manifest_sha256', 'previous_review_id', 'admission', 'integrity'])
    || !navigationReviewId(row.id) || !['unknown', 'changes_requested', 'reviewed_conditional'].includes(row.state)
    || !['complete', 'pending', 'unavailable'].includes(row.admission) || !['verified', 'unavailable'].includes(row.integrity)
    || (row.previous_review_id !== null && !navigationReviewId(row.previous_review_id))) fail();
  if (row.integrity === 'verified') {
    if (!Number.isInteger(row.sequence) || row.sequence! < 1 || row.sequence! > 100 || !stamp(row.recorded_at) || !sha(row.packet_sha256)
      || row.manifest_sha256 !== manifest || !sha(row.manifest_sha256)
      || row.state === 'unknown' || row.admission === 'unavailable' || ((row.sequence === 1) !== (row.previous_review_id === null))) fail();
  } else if (row.state !== 'unknown' || row.sequence !== null || row.recorded_at !== null || row.packet_sha256 !== null || row.manifest_sha256 !== null || row.previous_review_id !== null || row.admission !== 'unavailable') fail();
}
