# Source-linked revised-draft comparisons — R05A engineering contract

A lawyer can compare a newer private draft with one exact retained public-authority
review. The comparison preserves the original source quotations, historical version
identities, six observations per source, and both private draft versions. New
judgments are attributed human declarations, not verified repairs or legal truth.

## Workflow

In **Work notebook → Structured analyses**, revise the private draft and save a
separate version. Open its original **Public-authority context → Lawyer source
review → retained review → Findings-linked draft comparison**. Inputs and history
load only after explicit interaction; details remain collapsed.

Inspect original findings, before/after target changes, and original private and
public quotations. Give an explicit disposition and nonblank explanation for every
original source/dimension observation. No outcome, target or evidence is preselected.

| Disposition | Required technical linkage; meaning remains the lawyer's declaration |
|---|---|
| Addressed | At least one actually changed/added target in the candidate and one candidate private quotation. Explicitly chosen targets can map a replaced original group; equivalence is not inferred. |
| Retained | All original linked targets still exist with identical values and are explicitly selected. It does not endorse the original observation. |
| Removed | All original linked targets are absent, with no selected candidate targets. Partial removal must remain explained under another disposition. |
| Unresolved | Explicitly keep the concern open; target/evidence links are optional but validated when supplied. |
| Not assessed | Explicitly record the absence of an assessment, with an explanation. |

Add an overall note. Optional whole-second active review time is a manual
observation; blank means unknown. It is not total preparation time or measured
benefit. Save and inspect the retained comparison. Latest Current records export
as authenticated private JSON, DOCX or PDF containing the original findings,
quotations, target changes, selected links, account attribution and seals.

The comparison never changes a draft, ordinary review decision, authority context,
original finding, blocker or qualification flag. No model is called and no public
text or human finding enters a proposal prompt. Addressed declarations can coexist
with unresolved legal-norm blockers; technical linkage cannot establish semantic
support, binding force, adverse completeness or applicability.

## Expected historical staleness and current bindings

The original context/review stays Stale after a new draft. Comparison inputs allow
that expected change while requiring a later immutable version of the same analysis,
current selected private dependencies for both versions, unchanged original private
review/dependency bindings, and current permission for the exact public source pin
and bytes. Inputs use the latest candidate; saved inspections retain their exact
candidate. A further version makes the comparison Stale.

Saving a draft also invalidates retained research. Its historical change is visible
in the comparison and does not refresh that research or imply complete discovery.
The comparison uses the original frozen nominations and verified original source
passages, not substitute candidates from a changed research record. It separately
pins the entire current retained research digest at capture; subsequent research
changes invalidate the comparison, including changes to an already-stale record.

Changed facts, documents, contradictions, private review heads, authority-review
heads, recipes/dimensions or reviewer access require re-review. Stale original
private evidence blocks new capture: acquire/review refreshed evidence and a new
context rather than silently replacing the old quotation. Added selections from
unchanged/current documents and explicit target replacement remain visible.

Every inspection/export reopens public publication authorization and verifies the
original context. Public permission, pin, source integrity or unavailable original
record failures produce **Withheld**, with `snapshot: null`, hiding all potentially
quoting free text and both private comparison contents. Authorized metadata remains.
Stale records retain their frozen payload while public access is permitted; exports
are blocked. Current means technical binding availability, not a positive verdict.
A known child comparison denial clears cached ancestor review/context views and
unmounts their comparison editors; source-context reinspection remains explicit. Permission
changes cannot retract previously downloaded historical local copies.

## Immutable saves and concurrency

A basis SHA-256 binds the frozen review, both exact contents, target/evidence
inventories, current dependencies, recipe and dimensions. A workspace `FOR UPDATE`
lock serializes saves and private revisions. Expected comparison head plus a
per-account nonce prevent silent competing judgments: identical retries return one
record; altered payloads or competing heads conflict. History preserves disagreement.

The encrypted immutable `authority_revision_comparison` record has a canonical
SHA-256 seal. A separate encrypted `authority_comparison_head` establishes sequence;
`authority_comparison_admission` records clean completion of the post-commit public
guard. Flush/expire/final checks precede commit. A late failure after commit returns
HTTP 409 `committed_needs_revalidation`, the saved ID and no payload. Pending records
remain withheld after recovery or retry; a new input capture/nonce creates a distinct
comparison. Rendering-time dependency or final guard failure discards attachment bytes.

Writes require an active lawyer/admin application role and current workspace
membership. These roles do not certify professional credentials or independence.
Authorized members can inspect private metadata/history. No public graph receives
private notes or inverse matter-use links. Generic erasure inventories, holds and
encrypted backups cover all three record kinds.

## API and bounds

Base: `/api/v1/matters/{matter_id}/analyses/{analysis_id}/authority-contexts/{context_id}/reviews/{review_id}/comparisons`.

| Method/path | Operation |
|---|---|
| GET `/context` | Capture original findings and latest candidate, basis/head and freshness |
| POST `/` | Save every finding disposition with exact candidate, basis/head and nonce |
| GET `/` | Paginated authenticated metadata |
| GET `/{comparison_id}` | Current/Stale/Withheld projection |
| GET `/{comparison_id}/export?format=json\|docx\|pdf` | Revalidated latest Current attachment |

Up to 8 original source occurrences × 6 dimensions = 48 distinct dispositions;
12 candidate targets and 20 private quotation references per disposition; notes
3–2,000 characters with at least three nonblank characters; strict optional integer
time 1–28,800 seconds. Canonical input is bounded to 128 KiB. Complete records and
responses are bounded to 4 MiB with a 2 KiB envelope reserve; oversize records are
rejected without partial saves. Up to 100 comparisons per retained review; default
10 items per page, maximum 20. No arbitrary queries, graph updates or external dispatch.

## Remaining qualification

Synthetic tests use invented law and simulated rights; real signed bytes prove
engineering bindings only. Actual R03–R05 rights, historical identity and legal-effect
reviews, representative independent semantic/adverse adjudication, held-out evaluation,
qualified public synthesis and measured Standard/Deep benefit remain open. The next
bounded packet is independent semantic/adverse adjudication of source-linked
comparisons with explicit review coverage, without manufacturing legal approvals or
qualification scores. See [findings](AUTHORITY_FINDINGS.md), [context](ANALYSIS_AUTHORITIES.md),
[roadmap](ROADMAP.md), [evaluation](EVALUATION.md) and [verification](VALIDATION.md).
