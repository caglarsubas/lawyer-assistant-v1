# Source-bound local authority proposals — R05A engineering contract

Lawyers can request a bounded local-model revision using selected findings from an
exact public-authority review. The original review, source context and draft stay
immutable. A proposal is untrusted text; a lawyer explicitly adopts it into a new
**Needs review** version. This does not establish legal accuracy or resolve findings.

## Workflow

In **Work notebook → Structured analyses → Public-authority contexts**, open a
retained context, then **Lawyer source review → Review history**. Inspect the latest
Current review and open **Local revision proposal from authority findings**.

Select 1–5 distinct source/dimension findings. Nothing is preselected. Eligible
outcomes are Needs change, Unresolved and Not assessed; Supported is excluded.
The server selects the original quotations and linked editable targets. The client
cannot supply replacement evidence or review prose. Starting requires an active
lawyer/admin application role and workspace membership; roles do not certify
professional credentials.

Choose one pass (120 seconds) or a structural repair budget (at most two passes,
240 seconds total). Opening tools or history never invokes inference. Inspect the
selected findings, original public passages, temporal unknowns, private passages,
candidate edits and per-pass responses. Cancel active work or explicitly adopt the
completed candidate with its exact hash, expected draft revision and change reason.
The parent analysis reloads after adoption. Earlier versions and findings remain.

## Fixed inputs and permitted model work

The recipe is `source-bound-authority-proposals-v1`, layered on the existing local
proposal protocol. Private-feedback/comparison protocols cannot be mixed into the
same request. Only selected findings and their exact source evidence enter the
measured prompt; reviewer identities, matter IDs and unselected review prose are
omitted. Source texts and observations are untrusted data, never instructions.

Issue, facts, roles, premises, rules, conditions, relationships, evidence, dates and
conclusion dependencies remain fixed. The model may propose linked application
rationale/condition assessments, conclusion text, next steps and additional
uncertainties. Each selected finding needs exactly one typed response:

- `proposed_change`, linked to permitted targets actually changed in that pass;
- `requires_manual_work`, with no claimed edits;
- `unresolved`, with no claimed edits.

Public authority IDs have a separate namespace from private evidence IDs. Each
response must cite its selected occurrence; invented references and unaccounted
edits fail validation. The deterministic critic checks declared structure only.
A pass introducing a new critical defect is rejected. Accepted candidate responses
retain their originating pass even when a later repair is rejected. The system
does not request or publish hidden model reasoning.

The existing shared queue, bounded cancellation/checkpoints, nonce receipts,
provider identity/model/context/transport checks and disabled cloud fallback apply.
No extra inference route, tool call or retry is added. The complete prompt is
budgeted without truncation; selected feedback is limited to 128 KiB, a typed patch
to 32 KiB, transport output to 64 KiB and completion to 1,000 tokens. The approved
laptop-tunnel transport remains explicitly disclosed as connected operation.

## Continuing permissions and immutable adoption

Dependencies pin the source context/review seals, recipe, original public nomination
and graph release. Adopting a private draft stales its research wrapper; that wrapper
status is separate from the unchanged frozen public nomination. It never substitutes
today's provision or bypasses current publication/evidence checks.

Source guards cover generation, publication and adoption. Committed proposal bytes
stay pending until a clean guard exit; a job cannot appear Completed before that
publication finishes. Adopted and subsequent manual/model versions receive separate
admission proofs and retain all public dependencies and original source/model
contributions (maximum eight; none is dropped). Later private proposals keep earlier
quotations and original model/job attribution visible in the draft and exports.
Late guard failure leaves committed bytes pending and withheld after transient
recovery. Identical request retries do not dispatch duplicate work. Competing
PostgreSQL adoptions serialize and cannot create two versions from one proposal.

Every proposal read, including the generic research-status/cancel routes, checks
permissions. Permission or source-integrity failure returns metadata only, with no
candidate, source feedback, notes or iterations. Derived draft reads/history, review,
follow-up inference and exports use the same retained dependencies. Missing service,
proof or mandatory lineage fails closed. UI failures clear cached affected views.
Revocation cannot retract an already downloaded historical local copy.

Changed review heads, recipes or reviewer access project Stale; source-dependent
exports close. DOCX/PDF retain original quotations, seals, historical limits and
response provenance and recheck dependencies after rendering. There is no automatic rebinding. The [explicit reviewed renewal workflow](AUTHORITY_REVALIDATIONS.md) adds an exact human assessment for retained unchanged sources, preserving prior evidence and model contributions. Revoked/changed evidence and incompatible contracts remain blocked.

## API and remaining gates

Reuse `/api/v1/matters/{matter_id}/analyses/{analysis_id}/suggestions` and its existing
history/detail/cancel/adopt endpoints. `POST` adds an optional `authority_feedback`
selection with `context_id`, `review_id`, `review_sha256` and `{source_index, dimension}`
findings. Responses include frozen feedback, typed responses and accepted-pass ID.
Legacy private request receipts remain compatible when this field is omitted.

Verification uses invented authorities and mocked inference, plus real PostgreSQL
locking and isolated offline Linux tests. It establishes engineering bindings only.
Source/legal approval, representative Turkish semantic/adverse evaluation, real
model performance, measured benefit, public synthesis and Standard/Deep
qualification remain open. See [roadmap](ROADMAP.md) and [validation](VALIDATION.md).
