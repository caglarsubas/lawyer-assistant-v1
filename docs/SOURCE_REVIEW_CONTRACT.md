# Source review workspace contract

This is an authenticated human review record, not a graph-publication approval.
The source package remains immutable. All review notes, assignment and reviewer
identities are encrypted and restricted to the current firm. `admin` and `curator`
roles may access it; a lawyer role or another firm cannot read these records.
Acquisition packages remain shared public-only data, and are not mutated by review.

## API

Prefix `/api/v1/public-sources/{source_id}`; all source IDs are exact package SHA256.
All reads verify the package; mutations additionally require CSRF, live role/session
checks and optimistic `expected_revision`. No review signs a release or enables
retrieval. An absent review has revision0 and no owner; GET does not create it.

- `GET /passages?offset=0&limit=20`: exact paginated text, locator and Unicode spans,
  total, next_offset, source/raw/text digests and integrity scope. Plain text only.
- `GET /original`: integrity-checked opaque attachment (`application/octet-stream`),
  never browser-rendered HTML. Source fidelity review compares this with extracted text.
- `GET /review`: response shape below, last50 events, explicit history_truncated.
- `POST /review/assignment`: `{expected_revision, action:"claim"|"release", rationale}`.
  A reviewer claims an unassigned source; reviews require that ownership. Only the
  owner releases it, except an admin may release another owner's assignment with
  an explicit rationale. No automatic reassignment on another account's behalf.
- `POST /review/assessments`: `{expected_revision, category, decision, rationale,
  evidence_refs, passage_ids, permitted_uses}`. Accepted assessments require at
  least one evidence reference; accepted extraction also cites at least one
  actual passage ID. Rights acceptance specifies at least one permitted use.
  Other categories must not supply permitted uses. Rationale is3–4000 characters.
- `GET /review/export`: attachment JSON dossier containing current state and bounded
  history, preserving truncation when present. This is firm-confidential, unsigned
  and ineligible for graph publication by itself.

`category`: `rights`, `source_identity`, `extraction`, `legal`.
`decision`: `accepted`, `needs_changes`, `rejected`.
`permitted_uses`: zero or more of `storage`, `local_processing`, `internal_display`,
`indexing`, `local_inference`, `export` (rights acceptance requires at least one).
Evidence references: `{reference:string, sha256:64-lowercase-hex}`;1–10 on acceptance,
maximum10 otherwise. They bind an accountable review to supporting material; its
availability/authenticity still needs human verification. Passage IDs maximum100,
unique and members of the exact source package. Review never presumes current law.

## Response

```typescript
interface SourceReviewEvent {
  id: string;
  revision: number;
  event_type: 'claim' | 'release' | 'assessment';
  reviewer: { id: string; name: string };
  created_at: string;
  rationale: string;
  category?: 'rights' | 'source_identity' | 'extraction' | 'legal';
  decision?: 'accepted' | 'needs_changes' | 'rejected';
  evidence_refs: { reference: string; sha256: string }[];
  passage_ids: string[];
  permitted_uses: string[];
}
interface SourceReviewState {
  source: PublicSourceDetail;
  revision: number;
  assigned_to: { id: string; name: string } | null;
  assessments: SourceReviewEvent[]; // latest event in each category
  history: SourceReviewEvent[]; // newest first, capped50
  history_truncated: boolean;
  handoff_ready: boolean; // all four latest assessments accepted; NOT use permission
  publication_eligible: false;
  limitations: string[];
}
```

A `handoff_ready` dossier is ready for the independent publication reviewers to
inspect. Its permitted-use scope must be checked against the proposed processing;
it does not certify sufficiency for every use. Rejected/needs-changes decisions
replace only the current projection; earlier events remain in immutable history.
Repeated/conflicting requests return409 with no duplicate history or lost updates.
No API accepts a reviewer identity, timestamp, source digest override or signature.
An already-assigned source cannot be claimed again, including by its current
owner (409, no revision change). Each firm/source review is capped at 1,000 events;
the latest 50 are returned and truncation is explicit. A rejected or needs-changes
extraction assessment may report failure without selecting an extractable passage.
