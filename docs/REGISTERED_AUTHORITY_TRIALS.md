# Registered fixed-evidence human authority trials

This R05A engineering workflow registers a question **before revising** an existing
lawyer-authored draft, freezes its case inputs and selected public authorities, then
retains a before/after comparison, separate-account observations and declared active
work time. It does not run inference or compare single-pass versus correction models.
The original draft was prepared **before registration**; its effort is retrospective.
This is a reproducible human revision capture, not a preregistered model benchmark,
randomized/blinded experiment, legal approval or a held-out qualification protocol.

## Register, then revise

In **Work notebook → Structured analyses → Public-authority context → Lawyer source
review → retained review → Registered authority trial before revision**, explicitly
load registration inputs. The original draft, source context and authority review
must be current. Model-assisted drafts are outside this human-only workflow.

Supply a title, question, example-family label and explicit real/synthetic declaration.
The browser hashes the family label; only its SHA-256 enters the protocol. Identical
labels enable declared grouping, not near-duplicate detection. Select two active
authorized lawyer/admin accounts different from the operator, baseline draft author
and source reviewer. No reviewers, origin or attestations start selected. Synthetic
matters/environments cannot declare real origin. Real is a declaration, not consent,
source-rights verification, professional credentials or actual independence.

The encrypted immutable registration freezes the original authority review and
context, exact source/historical/serving identities, baseline private version, six
semantic dimensions, every source-finding dimension, recipes and input SHA-256.
The fixed case input contains issue, posture, event date, original evidence selections,
premises, fact/source snapshots and contradiction snapshots. The complete original
rationale is retained too. No free-form rubric or hidden model prompt is introduced.

Revise through the existing private draft workflow. Rules, conditions, application,
alternatives and conclusion can change. Changing any fixed case input requires a new
baseline/context/review and registration. The candidate version and comparison must
postdate registration, as established by server UTC timestamps. The existing preparation
product's exact `needs_review → stale` transition caused by saving a private analysis is
normalized for this binding; other product fields/transitions still invalidate it.

Record a comparison against the original authority findings. Both assigned accounts
then sign in separately and record their source-linked semantic/adverse observations
using [authority adjudication](AUTHORITY_ADJUDICATIONS.md). They cannot author the
candidate or its comparison. The interface is not blinded. Account separation does
not certify that two distinct qualified people independently inspected the sources.

## Freeze records and work time

Return to the registered trial, explicitly load comparisons and choose an eligible
retained comparison. Load the separate-reviewer history and select at most one latest
Current observation per assigned account. The server rejects foreign, pending,
superseded, unauthorized or incorrectly timed records. Lists are paginated; each page
contains metadata only. The operator explicitly previews the exact selected basis.

Only the registering operator may save a capture. Each save pins the complete
comparison and immutable observation assessments/coverage with their upstream basis
and record SHA-256 values. Their shared comparison/source basis appears once in the
packet; this is a documented structural projection, not silently truncated evidence.
Neither ordinary reviews, findings, draft blockers nor graph assertions are modified.

Declare original/revised preparation, verification/lawyer-review and correction seconds.
All values are nullable strict whole seconds, 0–28,800 per phase. Blank means unknown;
explicit zero means no active work in that phase. Waiting for inference is not work
time. Separate adjudicator evaluation seconds remain separate and are not summed into
workflow effort automatically. No automatic timer or estimated missing time is added.

Three separate confirmations cover consistent shared setup, all verification/correction
and non-overlapping active time. Partial captures with missing reviewers, unknown
times or unchecked confirmations are retained. `capture_complete` means two current
assigned-account records and fully declared positive-total effort for both arms with
all confirmations. Unassessed/unresolved judgments can still be present: completion
does not mean adequate assessment coverage, semantic correctness or repaired findings.
Differing reviewer declarations are inventoried without voting or consensus. Missing
paired observations leave disagreement unknown. There are no quality, adverse-recall,
time-saving, cost-saving, compute-time or Standard/Deep benefit calculations.

## Privacy, history and exports

Workspace row locks serialize writes. Exact basis/head/client nonce checks make an
identical retry idempotent and conflicting requests fail. At most 60 registrations
per authority review and 60 capture events per trial are retained; existing source and
review history bounds also apply. Input is at most 16 KiB; full confidential responses
are at most 12 MiB with a metadata reserve. Oversized appends roll back atomically,
including the combined protocol/capture packet. No prior evidence is silently dropped.

Inputs and active roles are rechecked after flush and immediately before commit.
Admissions are finalized only after a clean public-authorization guard exit. A late
committed failure returns a pending ID with HTTP 409 and no notes or quotations.
Identical retry never completes a pending admission; fresh inputs/nonce produce a
distinct record. Old captures remain immutable. A newer capture or dependency,
recipe, reviewer-access, draft or upstream observation change makes affected evidence
Stale and closes export. A valid new capture can replace a stale latest capture after
dependencies are resolved; older history is always inspectable under current access.

Source denial, changed public bytes/pins or unavailable ancestors make the trial
Withheld: `protocol: null`, `snapshot: null`. All potentially quoting free text is
hidden, including title/question. Authorized identity/time/seal metadata remains.
Known child denial removes cached source context and review views and unmounts editors.
Already downloaded copies cannot be retracted. Records use existing private encryption,
retention, holds, deletion and backup inventory; public graphs receive no inverse links.

A JSON evidence attachment is available for a latest Current capture, including
explicit partial captures. Authorization, membership, head and all dependencies are
rechecked after serialization and at guard exit. Failed revalidation discards attachment
bytes. Headers are authenticated same-origin, `no-store` and `nosniff`. The packet is
confidential evidence, not public data, a qualification-score row or an approved export
of legal conclusions. No provider call, network permission, migration or CI job is added.

## API

Prefix: `/api/v1/matters/{matter_id}/analyses/{analysis_id}/authority-contexts/{context_id}/reviews/{review_id}/trials`.

| Route | Contract |
|---|---|
| GET `/registration-context` | Exact pre-revision context and eligible account inventory |
| POST `/` | Typed immutable registration; current context digest and nonce |
| GET `/?limit=&offset=` | Confidential registration metadata, 10 default / 20 maximum |
| GET `/{id}?capture_id=` | Latest or exact historical Current/Stale/Withheld projection |
| GET `/{id}/captures?limit=&offset=` | Capture metadata history, 10 default / 20 maximum |
| POST `/{id}/capture-context` | Exact comparison and optional 0–2 observation IDs; basis/head preview |
| POST `/{id}/captures` | Operator-only immutable capture with explicit effort and basis/head/nonce |
| GET `/{id}/export` | Revalidated confidential JSON attachment for latest Current capture |

Representative lawful Turkish legal sources, historical/effect review, independent
qualified adjudicators and held-out evaluation remain required. R05A stays partial.
Next engineering packet: confidential within-workspace authority-trial cohort
reconciliation with exact profiles, declared family/source overlap and unknowns.
Model-driven public synthesis and measured Standard/Deep improvement remain separate
qualification work. See [roadmap](ROADMAP.md) and [evaluation](EVALUATION.md).
