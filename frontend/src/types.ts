export type Domain = 'contracts' | 'commercial' | 'employment';
export type FactStatus = 'documented' | 'alleged' | 'disputed' | 'assumption' | 'inference';
export interface User { id: string; name: string; role: string; firm_id: string; permissions?: string[] }
export interface Session { user: User; csrf_token: string; demo_mode: boolean }
export interface Bootstrap { demo_mode: boolean; version: string }
export interface SystemStatus {
  demo_mode: boolean;
  provider: { configured: boolean; identity_verified: boolean; tenant_id: string; organization: string; key_id: string; mode: string; readiness?: { configuration_ready: boolean; verification_scope: string; issues: { code: string; message: string }[] } };
  graphs: { mode: string; ontology_version: string; legal_review_status: string };
  services: Record<string, unknown>;
  limitations: string[];
}
export interface ReadinessIssue { code: string; message: string }
export type ReadinessState = 'ready' | 'blocked' | 'unavailable';
export interface IntakeReadiness {
  status: ReadinessState;
  demo_mode?: boolean;
  issues: ReadinessIssue[];
  scanner: { status: string; version?: string; signature_date?: string };
  extractor: { status: string };
  checked_at?: string;
}
export interface RuntimeReadiness {
  checked_at: string;
  provider: {
    status: ReadinessState;
    issues: ReadinessIssue[];
    model?: string;
    checks: { configuration: boolean; connection: boolean; model: boolean };
    qualification: 'runtime-connectivity-only';
    transport?: { mode: 'approved_laptop_tunnel' | 'private_network'; uses_public_network: boolean };
  };
  intake: IntakeReadiness;
  limitations: string[];
}
export interface PublicSourceRecord {
  id: string; title: string; source_url: string; source_version_id: string; domain: string;
  acquired_at: string | null; rights_status: string; review_status: string; passage_count: number; publication_status: string;
}
export interface PublicSourceCatalog { items: PublicSourceRecord[]; limitations: string[] }
export interface PublicSourceDetail extends PublicSourceRecord {
  dates: { published_on: string | null; effective_from: string | null; effective_until: string | null };
  artifacts: Record<string, { sha256: string; bytes: number }>;
  integrity_scope: string; limitations: string[]; injection_risk_hints: string[];
  review_evidence: { rights_supplied: boolean; identity_supplied: boolean; trust: string };
}
export type SourceReviewCategory = 'rights' | 'source_identity' | 'extraction' | 'legal';
export type SourceReviewDecision = 'accepted' | 'needs_changes' | 'rejected';
export type SourcePermittedUse = 'storage' | 'local_processing' | 'internal_display' | 'indexing' | 'local_inference' | 'export';
export interface SourceReviewEvent {
  id: string; revision: number; event_type: 'claim' | 'release' | 'assessment';
  reviewer: { id: string; name: string }; created_at: string; rationale: string;
  category?: SourceReviewCategory; decision?: SourceReviewDecision;
  evidence_refs: { reference: string; sha256: string }[]; passage_ids: string[]; permitted_uses: SourcePermittedUse[];
}
export interface SourceReviewState {
  source: PublicSourceDetail; revision: number; assigned_to: { id: string; name: string } | null;
  assessments: SourceReviewEvent[]; history: SourceReviewEvent[]; history_truncated: boolean;
  handoff_ready: boolean; publication_eligible: false; limitations: string[];
}
export interface PublicSourcePassage { id: string; start: number; end: number; text_sha256: string; locator: string; text: string }
export interface PublicSourceOriginalText {
  source_id: string; source_version_id: string; passage_id: string;
  raw_sha256: string; text_sha256: string; decoded_original_sha256: string; window_sha256: string;
  encoding: string; offset_unit: 'unicode_code_points_excluding_initial_utf8_bom';
  range_start: number; range_end: number; start: number; end: number; next_offset: number | null;
  text: string; integrity_scope: 'all_artifacts_verified';
  locator_coordinate_status: 'consistent_not_fidelity_reviewed'; extraction_fidelity_verified: false;
}
export interface PublicSourcePassages {
  source_id: string; source_version_id: string; raw_sha256: string; text_sha256: string;
  offset_unit: 'unicode_code_points'; items: PublicSourcePassage[]; total: number; next_offset: number | null; integrity_scope: string;
}
export interface GraphServingRelease {
  status: 'unconfigured' | 'verified' | 'unavailable';
  release_id?: string; ontology_sha256?: string; legal_review_verified?: boolean; reason?: string;
}
export interface Passage { id: string; locator: string | Record<string, unknown>; text: string; text_sha256?: string }
export interface ContextSelection {
  passage_id: string; document_id: string; document_name: string | null;
  document_revision: number | null; document_sha256: string | null;
  original_text_sha256: string; excerpt_text_sha256: string;
  excerpt_start: number; excerpt_end: number; full_passage_length: number;
  boundary: 'full_passage' | 'punctuation_line_window' | 'token_fragment';
  utf8_bytes: number; matched_query_terms: number;
}
export interface EvidenceContextPack {
  recipe: string; scope: 'private_document_quotes'; offset_unit: 'unicode_code_points';
  provider_use: 'prepared_only' | 'validated_quote_response' | 'not_configured' | 'no_selected_evidence';
  inventory: {
    input_passages: number; examined_passages: number; unexamined_passages: number;
    selected_passages: number; omitted_passages: number; shortened_passages: number;
    selected_documents: number; examined_documents: number; scanned_code_points: number;
    evidence_utf8_bytes: number;
  };
  limits: Record<string, number | null>; prompt: Record<string, string | number>;
  selected: ContextSelection[];
  omitted: { passage_id: string; document_id: string; reason: string }[];
  omission_counts: Record<string, number>;
}
export interface DocumentRecord {
  id: string; name: string; status: string; media_type: string; page_count: number | null;
  extraction_warnings: string[]; created_at: string; passages?: Passage[]; synthetic?: boolean; sha256?: string;
  revision?: number;
}
export interface Fact {
  id: string; text: string; status: FactStatus; evidence_id?: string | null; revision: number; updated_at: string;
}
export interface Claim {
  id: string; text: string; kind: string; evidence_ids: string[]; review_status: string; review_note?: string;
}
export interface ValidityEvidence {
  id: string; artifact_id: string; locator: string; text: string; sha256: string;
  text_representation_id: string; text_sha256: string; locator_map_sha256: string;
  start_offset: number; end_offset: number; grounding_status: 'verified_release_quote';
}
export interface ValidityMetadata {
  validity_end_status?: 'closed' | 'open_ended'; validity_checked_through?: string | null;
  validity_evidence?: ValidityEvidence[];
}
export interface AuthorityCandidates {
  hits: {
    passage_id: string; title: string; text: string; locator: Passage['locator']; authority_id: string;
    source_version_id: string; source_sha256: string; source_url?: string | null; review_status: string;
    valid_from?: string | null; valid_to?: string | null;
    validity_end_status?: 'closed' | 'open_ended'; validity_checked_through?: string | null;
    validity_evidence?: ValidityEvidence[];
  }[];
  coverage: { status: string; channels?: unknown; [key: string]: unknown };
  snapshot: unknown;
  limitations: string[];
}
export interface Product {
  id: string; title: string; status: string; version: number; summary: string;
  claims: Claim[]; issues: { label: string; missing_facts: string[]; counterarguments: string[] }[];
  coverage: { searched: string[]; gaps: string[] }; snapshots: unknown; graph_paths?: unknown;
  authority_candidates?: AuthorityCandidates; created_at: string;
  evidence?: Passage[]; context_pack?: EvidenceContextPack;
}
export interface ResearchRun {
  deadline_at?: string; budget_seconds?: number; phase?: string; cancel_requested_at?: string; finished_at?: string;
  id: string; status: string; question: string; created_at: string; product_id?: string | null; error?: string;
}
export interface Matter {
  id: string; title: string; domain: Domain; objective: string; represented_party: string;
  stage: string; relevant_date?: string | null; status: string; document_count: number; created_at: string;
  documents?: DocumentRecord[]; facts?: Fact[]; products?: Product[]; research_runs?: ResearchRun[];
  customer_ids?: string[]; customers?: Customer[]; updated_at?: string; revision?: number;
}
export interface Customer { id: string; name: string; notes?: string; created_at?: string; workspace_count?: number }
export interface WorkspaceComment { id: string; text: string; author_name: string; created_at: string }
export interface PortfolioFilters { customer_ids: string[]; date_from: string; date_to: string; date_field: 'created_at' | 'updated_at' | 'relevant_date' }
export type AssistantMode = 'guide' | 'chat' | 'daily' | 'weekly' | 'monthly';
export interface AssistantResponse {
  answer: string; mode: AssistantMode; sources: { id: string; label: string; workspace_id?: string; href?: string }[];
  suggestions: { label: string; href: string }[]; period: { from: string; to: string } | null;
  provider_used: boolean; limitations: string[];
}
export interface GraphCatalog {
  version: string; review_status: string; domains: { id: string; label: string; label_en?: string }[];
  classes: { id: string; label: string; module: string }[];
  relations: { id: string; label: string; requires_legal_review: boolean }[];
  coverage: unknown;
}
export interface GraphNode { id: string; label: string; type: string; graph: string; review_status: string }
export interface GraphEdge extends ValidityMetadata { id: string; source: string; target: string; label: string; status: string; evidence_id?: string }
export interface GraphResult { nodes: GraphNode[]; edges: GraphEdge[]; limitations: string[]; snapshot: unknown }
export interface GatewayEvaluation {
  decision: string; reason_codes: string[]; policy_version: string; payload_digest: string; request_id: string;
}
export type PracticeKind = 'scenarios' | 'contradictions' | 'arguments' | 'drafts';
export interface AuthorityReference { product_id: string; passage_id: string }
export interface PracticeRecord {
  id: string; revision: number; version: number; latest_version_id: string; created_at: string; updated_at?: string;
  title?: string; text?: string; status?: string; notes?: string; assumptions?: string[]; fact_ids?: string[];
  reason?: string; issue?: string; position?: string; evidence_ids?: string[]; authority_refs?: AuthorityReference[];
  draft_kind?: string; review_note?: string; authored_by?: string; authorship?: string; legal_authority: boolean;
  domain?: Domain | 'general'; curation_status?: string; curation_note?: string; classification?: string;
  fact_snapshots?: { id: string; text: string; status: string; revision: number }[];
  evidence_snapshots?: { id: string; name: string; locator: Passage['locator'] }[];
  authority_snapshots?: { product_id: string; passage_id: string; authority_id: string; source_version_id: string; candidate_only: boolean }[];
  purpose?: string; playbook_id?: string; version_id?: string;
}
export interface PracticeVersion {
  id: string; version: number; created_at: string; authored_by: string; change_note: string;
  content: PracticeRecord; immutable: boolean;
}

export type ProvisionKind = 'article' | 'temporary_article' | 'additional_article';
export interface ProvisionSpan { start: number; end: number; text: string; sha256: string }
export interface ProvisionCandidate {
  id: string; kind: ProvisionKind; label: string; number: string;
  heading: ProvisionSpan; proposed_span: ProvisionSpan; passage_ids: string[];
  warnings: string[]; status: 'machine_proposed'; identity_status: 'unresolved'; non_whitespace_covered: boolean;
}
export interface ProvisionCandidates {
  source_id: string; source_version_id: string; text_sha256: string; extraction_version: string;
  items: ProvisionCandidate[]; total: number; next_offset: number | null; truncated: boolean; limitations: string[];
}
export interface ProvisionSpanPreview {
  source_id: string; source_version_id: string; text_sha256: string; span: ProvisionSpan;
  passage_ids: string[]; non_whitespace_covered: boolean;
}
export interface ProvisionResolution {
  start: number; end: number; instrument_ref: string; provision_ref: string; provision_version_ref: string;
  text_role: 'operative_text' | 'amendment_text' | 'transitional_text' | 'quoted_text' | 'unknown';
  valid_from: string | null; valid_until: string | null;
  open_ended_validity?: { checked_through: string; evidence_start: number; evidence_end: number } | null;
}
export interface ProvisionMappingSnapshot {
  candidate_id: string | null; kind: ProvisionKind; label: string; span: ProvisionSpan;
  passage_ids: string[]; non_whitespace_covered: boolean;
  status: 'machine_proposed' | SourceReviewDecision; resolution: ProvisionResolution | null;
  reviewed_source_revision: number | null;
}
export interface ProvisionMappingEvent {
  id: string; revision: number; mapping_id: string; event_type: 'propose' | 'review';
  reviewer: { id: string; name: string }; created_at: string; rationale: string;
  decision: SourceReviewDecision | null; evidence_refs: { reference: string; sha256: string }[];
  source_review_revision: number; snapshot: ProvisionMappingSnapshot;
}
export interface ProvisionMapping extends ProvisionMappingSnapshot {
  id: string; stale: boolean; last_event: ProvisionMappingEvent;
}
export interface ProvisionMappingState {
  source: PublicSourceDetail; revision: number; source_review_revision: number;
  assigned_to: { id: string; name: string } | null; source_review_ready: boolean;
  items: ProvisionMapping[]; history: ProvisionMappingEvent[]; history_truncated: boolean;
  handoff_ready: boolean; publication_eligible: false; limitations: string[];
}
