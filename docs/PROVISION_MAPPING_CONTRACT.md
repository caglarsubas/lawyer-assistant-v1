# Exact provision mapping — implementation contract

Staged human-review tooling, separate from public RDF publication and retrieval.
Source packages remain immutable. All mapping selections/reviews are encrypted,
firm-confidential, source-bound records with append-only events and optimistic
revisions. Admin/curator readers only. Source-review ownership is required for
every write. No legal review is performed automatically.

## Candidate adapter

`backend.app.provision_candidates.find_candidates(package, *, offset=0, limit=20)`
returns `{source_id, source_version_id, text_sha256, extraction_version,
items: Candidate[], total, next_offset, truncated, limitations}`. Detect at most
500 explicit line-start Turkish article headings; limit1–20, offset0–500. Do not
normalize source text or infer instrument IDs/dates. Repeated headings remain
separate, with warnings. Proposed content ends at the next heading (or source end),
capped at20,000 Unicode code points with explicit truncation. Its boundaries may
include editorial text and always require review. `candidate_for_id(package,id)`
returns the exact recomputed candidate or raises ValueError.

```typescript
type ProvisionKind = 'article' | 'temporary_article' | 'additional_article';
interface Span { start:number; end:number; text:string; sha256:string }
interface Candidate {
  id:string; kind:ProvisionKind; label:string; number:string;
  heading:Span; proposed_span:Span; passage_ids:string[];
  warnings:string[]; status:'machine_proposed'; identity_status:'unresolved';
  non_whitespace_covered:boolean;
}
```

Candidate IDs are deterministic SHA256 of source package ID, extraction version
and heading offsets. Passage IDs intersect the proposed span. The coverage flag
means every non-whitespace code point belongs to an admitted locator; whitespace
gaps are allowed. It never certifies reading order, legal boundaries or fidelity.

## API

Prefix `/api/v1/public-sources/{source_id}`. Package ID is64 lowercase hex.
Every route verifies source artifacts and rechecks authorization. No arbitrary
URLs, provider calls, public graph writes or source package writes.

- `GET /provision-candidates?offset=0&limit=20`: adapter output; no database writes.
- `GET /provision-span?start=..&end=..`: verified preview before proposing or
  reviewing a corrected span. Returns `{source_id,source_version_id,text_sha256,
  span:Span,passage_ids,non_whitespace_covered}`. Same20,000-code-point bound,
  no mutations. UI acceptance requires a preview matching current span inputs.
- `GET /provision-mappings`: `MappingState` below; virtual revision0 when absent.
- `POST /provision-mappings`: `{expected_revision, expected_source_review_revision,
  candidate_id:string|null, start, end, kind, label, rationale}`. Creates an exact
  span proposal, initially `machine_proposed`. Candidate IDs must recompute from
  this package; supplied kind/label must match and span must include its heading.
  Null candidate allows a manual span proposal; it is still unreviewed. The
  server derives text/hash/passage IDs from verified source text. Max200 mappings,
  max20,000 code points/span. Identical kind/label/start/end proposals conflict409.
- `POST /provision-mappings/{mapping_id}/review`: `{expected_revision,
  expected_source_review_revision, decision:'accepted'|'needs_changes'|'rejected',
  rationale, evidence_refs:[{reference,sha256}], resolution:Resolution|null}`.
  Accepted requires resolution,1–10 evidence refs, all four latest source
  assessments accepted, and rights permitting `local_processing` and
  `internal_display`. It requires complete non-whitespace locator coverage.
  Other decisions require resolution:null and permit empty evidence. The source
  owner must submit; no client reviewer/time fields. All rationales3–4000 chars.
- `GET /provision-mappings/export`: unsigned, firm-confidential attachment JSON
  with exact source/review revision bindings, current mapping snapshots and last50
  events, explicit truncation. Never publication eligible.

```typescript
interface Resolution {
  start:number; end:number; // exact corrected provision text span
  instrument_ref:string; provision_ref:string; provision_version_ref:string;
  // Explicit reviewer references, each3–300 chars. Not auto-resolved graph IDs.
  text_role:'operative_text'|'amendment_text'|'transitional_text'|'quoted_text'|'unknown';
  valid_from:string|null; valid_until:string|null; // canonical YYYY-MM-DD, unknown stays null
}
interface Mapping {
  id:string; candidate_id:string|null; kind:ProvisionKind; label:string;
  span:Span; passage_ids:string[]; non_whitespace_covered:boolean;
  status:'machine_proposed'|'accepted'|'needs_changes'|'rejected';
  resolution:Resolution|null;
  reviewed_source_revision:number|null; stale:boolean;
  last_event:MappingEvent;
}
interface MappingEvent {
  id:string; revision:number; mapping_id:string; event_type:'propose'|'review';
  reviewer:{id:string;name:string}; created_at:string; rationale:string;
  decision:'accepted'|'needs_changes'|'rejected'|null;
  evidence_refs:{reference:string;sha256:string}[];
  source_review_revision:number;
  // full nonrecursive mapping snapshot: candidate_id/kind/label/span/passage_ids/
  // non_whitespace_covered/status/resolution/reviewed_source_revision
  snapshot:Omit<Mapping,'id'|'stale'|'last_event'>;
}
interface MappingState {
  source:PublicSourceDetail; revision:number;
  source_review_revision:number;
  assigned_to:{id:string;name:string}|null;
  source_review_ready:boolean; // all four accepted + required local use scope
  items:Mapping[]; history:MappingEvent[]; history_truncated:boolean;
  handoff_ready:boolean; publication_eligible:false; limitations:string[];
}
```

An accepted mapping is stale after **any** source-review revision change. Reads
compute this without modifying history. Reaffirmation needs a new explicit review
at the current revision. Source-review and mapping revisions both match before
every write; conflicts409 preserve input and never retry automatically. Require
live account/session checks and consistent lock order: identity, source-review
head, mapping CAS. Reads/export must detect source-review changes before returning.
Events capped1,000; responses contain newest50 plus current mappings. Encrypted
payloads bind firm/head/source/revision/event IDs; served history must be contiguous
and every current mapping must resolve to its exact immutable last event, even
outside the history window. Bounded replay of all event headers rejects hidden
newer decisions, missing events and replayed older head projections. Source-review
history also reconstructs the latest assignment and assessment decisions. A
request-local candidate index avoids rescanning every heading for each snapshot;
it cannot mutate or cache source evidence across requests. No plaintext review
rationale/reviewer audit copies.

Accepted dates may remain unknown; known intervals must not reverse. Separate
instrument/provision/version references cannot silently alias to current law or
be treated as canonical resolved identities. Amendment/transition/quotation roles
remain explicit reviewed classifications, not inferred genealogy relationships.
No API signs or publishes these records. Actual rights/identity/legal review and
an independently signed publication bundle remain necessary for graph ingestion.

## UI

Route `#/sources/{source_id}/provisions`, linked from source review. Preserve three
panels and source-page assistant guidance. Show source review prerequisites,
candidate warnings and exact headings/text; proposal span fields permit corrections
or manual selection. Mapping review separates references, role and unknown dates;
selecting acceptance does not prefill legal identities. Show stale states, exact
quotes/locators, revision conflicts and collapsed history. Originals stay inert
attachments. Use existing authenticated APIs; original review page owns assignment.
