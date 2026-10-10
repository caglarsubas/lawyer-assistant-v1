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
- `GET /original-text?passage_id=html_block_0001&offset=0&limit=12000`:
  an inert original HTML source-code window beside the selected extracted passage.
  The offset is relative to that passage's recorded original range; the limit is
  1–12,000 Unicode code points. No arbitrary original range or source URL is accepted.
  See the inspection boundaries below.
- `GET /review`: response shape below, last50 events, explicit history_truncated.
- `POST /review/assignment`: `{expected_revision, action:"claim"|"release", rationale}`.
  A reviewer claims an unassigned source; reviews require that ownership. Only the
  owner releases it, except an admin may release another owner's assignment with
  an explicit rationale. No automatic reassignment on another account's behalf.
- `POST /review/assessments`: `{expected_revision, category, decision, rationale,
  evidence_refs, passage_ids, permitted_uses, effort?}`. Accepted assessments require at
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

## Active review effort

An assessment may include `effort: {active_seconds: integer, basis:
"self_reported_timer" | "estimate"}`. Seconds are strict integers from 0 through
86,400. The record describes active work on **this assessment only**: exclude
breaks, waiting and time already declared for another assessment. The curator
enters their own timer result or an estimate; the platform does not measure or
independently verify human effort. The form defaults to an empty duration and an
estimate basis. Opening a source, claiming an assignment or saving a decision
does not automatically start a timer or infer duration from server timestamps.

Omitted/null effort, including every legacy record without the field, means
**unknown**. An explicit zero remains a recorded declaration with its selected
basis. Assignment events cannot include effort. No caller can supply a reviewer,
timestamp, verification status or custom measurement basis. Effort is encrypted
inside the same append-only assessment, bound to its authenticated reviewer,
revision, firm and exact source artifacts. No database migration or legacy
record rewrite is required. The existing owner, CSRF, revision, integrity and
fresh authorization checks apply.

`effort_summary` in GET, successful mutation responses and the unsigned JSON
export covers **all verified assessment events**, including superseded decisions.
The existing 50-event display/export window does not limit these totals:

- `total_assessments`, `timer_reported_assessments`, `estimated_assessments`,
  `unknown_assessments` describe their denominators. Unknown is never counted as
  zero-duration work. Assignment/release events are excluded.
- `timer_reported_active_seconds` and `estimated_active_seconds` remain separate.
- `scope: "all_assessment_events"`, `declaration_only: true` and
  `includes_superseded_assessments: true` identify the interpretation explicitly.

The entire bounded ledger is already checked against immutable events before
the summary is computed; a missing, corrupt or mismatched event fails closed
even outside the visible window. Reads do not create or backfill records. Old
API responses without a summary display “unavailable”; the UI never reconstructs
a total from its possibly truncated history.

These are unadjudicated effort declarations, not reviewer productivity, legal
approval, representative throughput or a benchmark. An erroneous declaration
remains in immutable history and needs explicit adjudication when preparing a
study; entering another assessment does not erase the earlier time. Time metadata
never changes rights, handoff readiness, publication eligibility or source use
permissions. An assessment update retains normal dependency revalidation.

## Original source-code inspection

For prepared HTML, choose **Özgün kaynak koduyla karşılaştır** on a passage.
The view preserves source whitespace, CRLF, markup and HTML entities as escaped
plain text. It does not render HTML, execute scripts, open links, load resources,
call a provider or interpret the document. Narrow work areas stack the comparison.
Large original ranges have separate paging; only one passage's original window is
open at a time. Opening a window never selects **İnceledim** or saves a decision.

Every window verifies the complete immutable source package, then checks the
recorded source-code range and its line/column against the decoded original.
UTF-8, Windows-1254 and ISO-8859-9 use the same strict decoder as disconnected
preparation. No fallback or replacement decoding is allowed. The preview admits
only `text/html` originals of at most 1 MiB and the preparation adapter's exact
source-code locator syntax. Other formats, unknown locators, conflicting encodings
and inconsistent coordinates return a fixed 422 response. The original attachment
remains the independent inspection path; integrity failures remain 409.

Responses bind source/package/version/passage identity, raw and extracted-text
digests, decoded-original and window digests, encoding, original range, returned
window and `next_offset`. Offsets exclude an initial UTF-8 BOM and count Unicode
code points, rather than UTF-8 bytes or JavaScript UTF-16 units. The browser checks
identity and window bounds before display. JSON responses use `no-store`, `nosniff`
and a restrictive CSP. Live curator authorization is checked again before return;
refresh, paging, source changes and access denial cancel or discard old windows.

`locator_coordinate_status: consistent_not_fidelity_reviewed` means coordinates
agree only. A self-consistent operator-supplied locator can still identify the wrong
content. `extraction_fidelity_verified` therefore remains false. Source identity,
visual reading order, omitted content, privacy, rights, historical applicability and
actual extraction fidelity still require accountable human review. Source-code
coordinates are neither rendered page locations nor legal provision identities.

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
  effort?: { active_seconds: number; basis: 'self_reported_timer' | 'estimate' } | null;
}
interface SourceReviewState {
  source: PublicSourceDetail;
  revision: number;
  assigned_to: { id: string; name: string } | null;
  assessments: SourceReviewEvent[]; // latest event in each category
  history: SourceReviewEvent[]; // newest first, capped50
  history_truncated: boolean;
  effort_summary: {
    scope: 'all_assessment_events'; declaration_only: true;
    includes_superseded_assessments: true; total_assessments: number;
    timer_reported_assessments: number; estimated_assessments: number;
    unknown_assessments: number; timer_reported_active_seconds: number;
    estimated_active_seconds: number;
  };
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
