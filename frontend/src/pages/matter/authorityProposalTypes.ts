import type { LinkedAuthority } from './authorityTypes';
import type { FindingDimension, FindingOutcome } from './authorityFindingTypes';

export interface AuthorityResponse {
  finding_id: string; outcome: 'proposed_change' | 'requires_manual_work' | 'unresolved';
  edited_targets: string[]; text: string; authority_ids: string[];
}
export interface AuthorityFeedback {
  recipe: string; dependency: { context_id: string; review_id: string; review_sha256: string };
  findings: { finding_id: string; authority_id: string; dimension: FindingDimension; outcome: FindingOutcome;
    note: string; target_ids: string[]; editable_targets: string[] }[];
  sources: { id: string; selection: LinkedAuthority['selection']; evidence: LinkedAuthority['evidence'];
    temporal_alignment: LinkedAuthority['temporal_alignment'] }[];
}
