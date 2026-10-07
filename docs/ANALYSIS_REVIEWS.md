# Version-bound lawyer review of private analysis

R05A now records immutable human decisions about an exact private draft. A recorded
lawyer declaration is separate from structural checks, model-proposal adoption,
public source/graph approval and legal-quality qualification. Its scope is always
`conditional_private_draft_only`; it cannot approve jurisdiction, historical law,
binding effect or a public authority. Manual review performs no inference or search.

## Workflow

In **Çalışma notları → Yapılandırılmış analiz taslakları**, open **Avukat inceleme
kararı kaydet**, then load the form for the displayed saved version. Inspect its
text, original documents, selected ranges, premise roles and uncertainties.

- **Değişiklik gerekli** records explained unresolved criteria or linked findings.
  Findings identify a declared step, severity, suggested correction and optional
  selected evidence. This decision withholds the displayed/exported conclusion
  even if structural checks pass; the original checks are preserved.
- **Koşullu özel taslak incelendi** requires explicit evaluation of all five criteria:
  original sources, reasoning/conditions, fact roles/contradictions, limits/alternatives
  and AI contribution. No criteria are selected automatically. Only AI contribution
  can be inapplicable, with an explanation and only when the version has no AI lineage.
  Stale private dependencies, critical structural checks, unresolved criteria and
  critical/major findings in that decision block acceptance.

An acceptance projects **Reviewed** for that exact conditional private draft.
It does not change stored Needs review text, machine checks or AI lineage. A later
human decision can supersede the current projection, with both declarations and
their expected predecessor retained. These are reviewer judgments; recording a
new judgment does not prove that earlier findings were resolved. Inspect the full
history when reconsidering a decision or writing a revised draft.

New text versions start unreviewed. Prior findings and reviews remain attached to
their original versions; they are not automatically resolved or transferred.
Changed private facts, documents, passages, contradictions, structural-check
recipe or review recipe project **Stale**, preserving earlier content and decisions.
A stale current version may receive a change request but cannot receive acceptance.
A review-recipe change alone allows explicit re-review of unchanged current text.

## Binding and confidentiality

The form binds the immutable version ID and canonical full-content SHA-256,
current analysis revision and expected latest review ID. The server supplies these
pins and the evidence inventory; callers cannot invent status, author, scope or
machine/public approval. Review records retain reviewer identity/name, time,
criteria, findings, source-selection digests, recipe and predecessor.

Review events are encrypted private `analysis_review` records. A separate encrypted
`analysis_review_head` selects the latest event per version. All reads, history,
joins, writes and export require existing firm/matter/session authorization; customer
tags do not confer access. Matter-row locking serializes review, draft and adoption
writes. Minimal audit metadata records the action without copying review prose.
No schema migration or new dependency is needed.

Each new decision invalidates existing preparation products, increments the matter
practice dependency and pins future quotation research to its review ID. A proposal
job pins the current review head; changes during execution, inspection or adoption
make older work ineligible. Completed candidates remain stored as stale, and
in-flight stale output cannot be adopted. Review text is not automatically added to
quotation or editing-model prompts. The separate [opt-in feedback workflow](ANALYSIS_FEEDBACK.md)
allows up to five findings from the latest current change request to inform bounded
local proposals. Typed responses do not resolve findings or inherit a review decision;
semantic repair qualification remains open. Human recording enables no provider or
external-access permission.

Exact-version DOCX/PDF includes the latest review projection, declaration, criteria,
findings, identity, time and content digest. Stale decisions or change requests
withhold the effective assessment while retaining original text and checks. Access,
source dependencies and the review head are rechecked after rendering; a change
during rendering rejects the export rather than delivering a mixed state.

## API and bounds

Relative to `/api/v1/matters/{matter_id}/analyses/{analysis_id}/reviews`:

| Method | Purpose |
|---|---|
| `GET /context?version_id=…` | Authorized immutable text digest, source ranges, typed targets, pins and acceptance gates |
| `GET ?version_id=…&limit=10&offset=0` | Immutable review history for the exact version; maximum 20 per page |
| `POST` | Append a version/head-bound decision and advance its review head atomically |

POST supplies `version_id`, `content_sha256`, `expected_revision`,
`expected_review_id` (null initially), a fresh 32-hex `request_id`, `decision`,
`note`, `criteria` and `findings`. A repeated identical request by its author returns
the original receipt, including after later revisions. A changed request with the
same ID, stale head or changed revision/content returns 409. Reload history after
a page reload; a missing response does not establish that no decision was saved.

Targets are `analysis`, `conclusion` or typed identifiers such as `premise:p1`,
`rule:r1`, `condition:c1`, `application:a1` and `alternative:alt1`. Types disambiguate
a node whose local ID resembles a reserved root. Findings cannot cite foreign steps
or sources. Inputs forbid extra fields and duplicate criteria/references. Limits are
five criteria, twenty findings, twenty evidence IDs per finding, 1,000 characters
per criterion note, 2,000 per decision/finding/correction and 100,000 serialized
UTF-8 bytes overall. Explanations require at least three nonblank characters.

## Qualification boundary

Synthetic checks cover immutable content, encryption, exact bindings, history,
supersession, source/recipe staleness, model-lineage criteria, membership isolation,
proposal invalidation and export races. Real PostgreSQL checks observe competing
decisions and identical retries waiting on the matter lock. Linux and browser
rehearsals use invented documents; none establishes that a lawyer actually read
a source, that an interpretation is correct or that a legal defect was resolved.

R05A remains partial. Reviewed public/historical synthesis, semantic/adverse
verification, broader model correction, calibrated Standard/Deep budgets and
lawyer-adjudicated accuracy/time benefit remain open. See [verification](VALIDATION.md),
[workbench](ANALYSIS_WORKBENCH.md), [proposals](ANALYSIS_SUGGESTIONS.md) and
[canonical roadmap](ROADMAP.md).
