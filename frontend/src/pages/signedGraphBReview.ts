import type { User } from '../types';
import { equivalencePath, type EquivalenceState, type EvidenceSelection } from './decisionEquivalence';

export interface SignedGraphBState {
  schema_version: 'signed-graph-b-review-v1'; confidentiality: 'firm_confidential'; firm_id: string; context_id: string;
  revision: number; history_complete: true; stale: boolean; trust_configured: boolean; signed_review_current: boolean;
  history: { id: string; revision: number; created_at: string; actor: { id: string; name: string }; envelope: { algorithm: 'Ed25519'; signature: string;
    body: { firm_id: string; context_id: string; decision: 'approve' | 'reject' | 'needs_changes'; public_reviewer: string; reviewed_at: string; reviewer_id: string;
      equivalence_revision: number; expected_review_revision: number; ontology_sha256: string; qualifications: { decision_on: string | null; institution: { scope: 'historical_identity_only'; registered_name: string; register_record_id: string;
        identity_window: { valid_from: string; valid_until: string | null; checked_through: string | null } }; relations: { source_id: string; relation: string; end_status: 'unknown' | 'closed' | 'open_ended'; valid_from: string | null; valid_until: string | null; checked_through: string | null; rationale: string }[] }; appointment: { scope: string; valid_from: string; valid_until: string; statement: string } } } }[];
  current: SignedGraphBState['history'][number] | null;
  graph_updated: false; publication_eligible: false; legal_truth_verified: false; institutional_competence_verified: false; finality_verified: false;
}
export function signedReviewPath(source: string, selection: EvidenceSelection) {
  return equivalencePath(source, selection).replace('/decision-equivalence?', '/graph-b-review?');
}
export function validateSignedReview(value: SignedGraphBState, state: EquivalenceState, user: User) {
  if (value?.schema_version !== 'signed-graph-b-review-v1' || value.confidentiality !== 'firm_confidential' || value.firm_id !== user.firm_id || value.context_id !== state.context_id
    || !Number.isSafeInteger(value.revision) || value.revision < 0 || value.revision > 50 || !Array.isArray(value.history) || value.history.length !== value.revision
    || [value.stale, value.trust_configured, value.signed_review_current].some(item => typeof item !== 'boolean')
    || value.history_complete !== true || value.history.some((event, index) => event.revision !== value.revision - index || event.envelope?.algorithm !== 'Ed25519'
      || event.envelope.body.firm_id !== user.firm_id || event.envelope.body.context_id !== state.context_id || event.envelope.body.reviewer_id !== event.actor?.id
      || event.envelope.body.expected_review_revision !== event.revision - 1 || 'credential_data' in event || 'accepted_key' in event)
    || (value.revision === 0 ? value.current !== null : JSON.stringify(value.current) !== JSON.stringify(value.history[0]))
    || [value.graph_updated, value.publication_eligible, value.legal_truth_verified, value.institutional_competence_verified, value.finality_verified].some(item => item !== false)
    || (value.signed_review_current && (value.stale || !value.trust_configured || value.current?.envelope.body.decision !== 'approve'
      || value.current.envelope.body.equivalence_revision !== state.revision || typeof value.current.envelope.body.qualifications?.decision_on !== 'string'))) throw new Error('İmzalı inceleme seçili büro ve karar bağlamıyla eşleşmiyor. Yenileyin.');
  return value;
}
