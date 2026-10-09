# Source-bound lawyer authority findings — R05A engineering contract

A lawyer can now record observations against one exact frozen public-authority
context and its private analysis version. Each selected assertion/passage/authority
occurrence retains its original quotation, historical metadata and complete set
of linked draft targets. Observations are private human declarations, not verified
legal truth, source approval, model judgments or qualification scores.

## Lawyer workflow

In **Work notebook → Structured analyses → Public-authority contexts**, inspect a
saved context and explicitly open **Lawyer source review**. Load current source
bindings for a new review or load the paginated review history. The module and
records load only after explicit interaction.

Inspect the original passage and draft targets. For **every selected source**, give
an outcome and nonblank explanation for each dimension:

| Dimension | Question for the lawyer |
|---|---|
| Applicability | How do the facts, parties and procedural posture affect this authority? |
| History | Which provision version, event date and transition conditions require review? |
| Conditions | What elements, exceptions and missing evidence remain? |
| Relationship | Does the cited relationship support application, distinction or any legal effect? |
| Adverse authorities | Which contrary interpretations and coverage gaps remain? |
| Certainty | How strong is the conclusion and what uncertainty must remain visible? |

Explicit outcomes are **Supported**, **Needs change**, **Unresolved** and **Not
assessed**. None is preselected. Support is attributed to the lawyer; it does not
establish entailment or binding force. Every dimension requires an explanation,
including unknowns. Observations cover the selected source's entire linked-target
set; the app does not infer separate per-target verdicts.

Add an overall note. Optionally declare active review time in whole seconds; leave
it blank when unmeasured. This is a manual observation, not complete preparation
time, GPU compute or demonstrated time savings. Save, then inspect the retained
record to recheck its current bindings. Current records can be downloaded as
private JSON, DOCX or PDF with the observations and original evidence.

## Immutable record and conflict handling

The server regenerates the source context; clients cannot substitute quotations,
source versions or draft targets. A basis digest binds the exact context, packet,
recipe and six dimension definitions. A workspace row lock serializes saves; the
request must name the expected latest review. Final dependency/access checks run
after flush and before commit. Identical user/nonce retries return the same saved
record; changed payloads or competing review heads conflict.

Each encrypted immutable review includes the entire original context, account
identity/name, recording time, source observations, dimension labels, prior review
ID, sequence, request digest and SHA-256 seal. A separate encrypted mutable head
points to the newest sealed review. New observations preserve earlier disagreement;
they never overwrite history or alter the original private analysis, ordinary
analysis-review decision or public-authority context.

Writes require an active **lawyer/admin application role** and current workspace
membership. These checks do not certify professional credentials or independence.
Authorized workspace members can inspect retained records. No public graph gains
private notes, inverse links or matter-usage metadata. Generic retention inventories,
legal holds and encrypted backups include all three new record kinds.

Commit initially retains a pending admission receipt. Only a clean final publication
guard exit permits a separate completion transaction. A late failure returns **409
`committed_needs_revalidation`** with the saved ID and no source/observation bytes.
Pending records remain withheld after transient recovery or identical retry; a
fresh input capture and new nonce create a distinct review. This receipt records
the save's guard completion, not continuing permission or legal approval.

## Inspection and export states

| Projection | What remains visible | Export |
|---|---|---|
| Current | Frozen observations and original evidence; exact current technical bindings pass | JSON/DOCX/PDF, revalidated after rendering |
| Stale | Original frozen record while public access is permitted; changed dependencies, reviewer access, recipe or newer review identified | Blocked |
| Withheld | Authorized identity/sequence/seal metadata; `snapshot: null` | Blocked |

Every inspection/export reopens publication authorization, verifies the exact
retained context/source pin, and checks private dependencies. Public-source
permission or integrity failure withholds **free-text observations as well as
quotations**, because notes may repeat public text. Pending admission also withholds
the snapshot. Rendering-time dependency changes or final guard failure discard
attachment bytes. Export failure clears the UI's cached review view. Later revocation
cannot retract an already downloaded historical local copy.

Current is technical availability. Even six Supported outcomes leave existing
legal-norm blockers, applicability-unknown fields and qualification flags unchanged.
No model is called, no findings are automatically resolved, and no draft is revised
or promoted by recording observations.

## API and bounds

Base: `/api/v1/matters/{matter_id}/analyses/{analysis_id}/authority-contexts/{context_id}/reviews`.

| Method/path | Operation |
|---|---|
| `GET /context` | Regenerate Current inputs, basis digest, dimensions and expected review head |
| `POST /` | Save exact source assessments, basis/head and per-user nonce |
| `GET /` | Paginated private review metadata |
| `GET /{review_id}` | Current/Stale/Withheld projection |
| `GET /{review_id}/export?format=json\|docx\|pdf` | Revalidated latest Current attachment |

Up to **8 source occurrences**, **12 distinct targets per occurrence**, exactly
**6 dimensions per source**, **100 reviews per context**, **10 items per default
page / 20 maximum**. Notes are 3–2,000 characters with at least three nonblank
characters. Optional strict integer time is 1–28,800 seconds. Canonical assessment
input is limited to 128 KiB; records/responses to 2 MiB with a 2 KiB saved-envelope
reserve. Oversize, incomplete and ambiguous input is rejected, never partially
recorded. There is no arbitrary graph query, graph mutation or external dispatch.

## Remaining qualification

Tests and browser rehearsals use invented law text, test-only signing keys and
simulated rights. They establish engineering boundaries, not Turkish legal
accuracy, professional review, historical completeness or adverse recall. Actual
R03–R05 source, identity, history and legal-effect reviews remain prerequisites.

Source-linked comparison of a newer private draft against these exact findings is
implemented in the [comparison contract](AUTHORITY_COMPARISONS.md). Original findings
remain immutable; explicit human dispositions do not close them automatically.
Independent semantic/adverse adjudication, held-out evaluation, qualified public
synthesis and measured Standard/Deep benefit remain open. See the
[context contract](ANALYSIS_AUTHORITIES.md), [roadmap](ROADMAP.md),
[evaluation](EVALUATION.md) and [verification](VALIDATION.md).

## Optional selected-finding proposal follow-up

A separate, explicitly requested local-model job can use eligible findings from the
latest Current review. It never changes this immutable human review or its
`model_use: none` attribution. See [proposal contract](AUTHORITY_PROPOSALS.md).
