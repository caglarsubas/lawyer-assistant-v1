# Registered same-input local-model authority trials

This R05A workflow compares a single local-model pass with bounded structural
correction on one exact private draft and selected public-authority findings.
Register before either call. Candidates remain unadopted. Complete capture means
required records are present; it grants no legal approval, reviewer qualification
or demonstrated benefit. The held-out release protocol in [EVALUATION.md](EVALUATION.md)
remains separate.

## Choose and freeze the legal inputs

In **Çalışma notları → Yapılandırılmış analiz taslakları**, open a current public
review or the latest admitted [retained-source renewal](AUTHORITY_REVALIDATIONS.md).
Explicitly select one to five distinct source/dimension findings requiring change,
unresolved or unassessed. Nothing is selected automatically. Open the trial tools,
inspect the exact preview and register a question, rubric, declared example-family
digest, real/synthetic origin and two existing authorized lawyer/reviewer accounts.
Synthetic cases cannot be declared real; real origin remains a declaration.

Two input kinds remain distinct:

- `original_review`: current original context/review IDs, seal, complete assessment
  and source manifest. It cannot claim renewal provenance.
- `admitted_renewal`: exact latest admitted renewal ID/seal plus the original
  context/review dependency. Resolve by dependency digest and source identity,
  never list position. The new human assessment does not rewrite original model
  responses or make the former review current.

The sealed immutable protocol retains the full draft/version/revision/hash, private
evidence, source passages and temporal flags, complete human assessment, selected
findings, review heads, rubric/family/origin, account IDs, provider and recipe pins,
budgets, registration time and permanent request IDs for both arms. Operator,
baseline author and selected authority-assessment author are excluded as observers.
Only selected feedback enters inference; the full human basis, rubric and assigned
reviewer metadata are not added to the prompt. No credentials reach the browser.

Preview/registration disagreement, changed permission, source, version, model,
recipe or budget requires reopening the preview. Registration performs no inference.
The history panel is also available without selecting new findings.

## Run bounded candidates

Only the registering operator dispatches the pair through the existing suggestion
queue and local provider boundary. Single-pass allows one call/120 seconds; correction
allows at most two calls/240 seconds, each capped by the configured research budget.
A second correction pass occurs only for remaining critical structural checks, not
as an unconditional second attempt at legal reasoning. Maximum three provider calls
per pair; existing cancellation/checkpoints and accepted/rejected-pass provenance
remain. The approved local-laptop transport exception is unchanged.

Partial reservation remains visible. Repeating Run uses permanent receipts and can
start a missing arm; failed, canceled, timed-out or stopped arms cannot be restarted
under this protocol. There is no provider override, additional worker, cloud fallback,
arbitrary prompt or adoption route. Neither trial arm changes the draft or its review.

Inspect actual before/candidate changes, exact private/public passages and every
retained pass response. A rejected repair cannot replace the accepted pass's authority
responses. Job elapsed time includes queueing; provider round-trip timing is measured
for completed responses. GPU compute and interrupted/failed total work/cost stay
unknown. These timings do not establish savings or Standard/Deep qualification.

## Record human judgments and active effort

Each assigned account signs in separately. Both arms require the six semantic
dimensions and a disposition for all six dimensions of **every** source in the
frozen assessment, not just selected findings. Reuse exact source/target/private
passage links and the positive/adverse evidence rules in
[authority adjudication](AUTHORITY_ADJUDICATIONS.md). Positive or adverse declarations
need supporting links and explicit inspected selected-source scope. Unknown,
unresolved and unassessed observations stay explicit. Scope cannot imply an
exhaustive search for authorities absent from the selected corpus.

Two accounts do not establish expertise or actual independence. This workflow is
not blinded. Preserve differences per arm/dimension/source; no majority vote or
automatic correctness score. Until two current judgments exist, paired disagreement
is unknown. Judgment histories append using exact execution/comparison seals,
idempotency nonces and each account's own previous record.

The operator separately declares preparation, verification/review and correction
seconds for each arm. Blank is unknown; explicit zero is valid for an absent phase.
Complete accounting requires known phases, a positive total for each arm and three
explicit confirmations: shared setup included consistently, full verification and
correction included, active phases non-overlapping. Waiting for inference is not
active effort. Optional evaluator-review seconds remain separate. No timer infers
these measurements, and no benefit or quality threshold is computed from them.
The non-overlap confirmation resets when the trial, execution or prior effort
record changes; it cannot carry over to another capture.

`capture_complete` requires current authorized inputs, two completed measured
candidates, latest judgments from both assigned accounts and complete effort
accounting. Unresolved judgments can still produce a complete capture. Completeness
never means semantic support, measured improvement or release qualification.

## Confidentiality, freshness and admission

Encrypted case records use existing permissions, retention, holds and deletion.
Public graph datasets receive no private usage links or trial updates. Metadata
listing contains IDs, timestamps and seals only; even a free-text title could quote
a public passage and is withheld from this unguarded metadata view.

Source/graph/private evidence, draft or review-head changes, provider/recipe/budget
changes, and participant access loss invalidate completion and block export. A
source/admission failure withholds protocol, candidates, observation text and effort
history. Authorized private Stale history remains inspectable where source checks
still pass. Browser request failure clears captures and previews; it does not keep
displaying previously authorized quotations.

PostgreSQL case locks serialize append and export. Before-commit changes roll back.
Pending admission is completed only after clean source-guard exit and current
authorization checks. A late failure returns `committed_needs_revalidation`; retain
the receipt and diagnose the incident. Retry cannot complete pending admission.
There is no override, resealing or automatic repair endpoint. Guard failure after
serialization discards export bytes.

Limits: 60 protocols per analysis; 60 observation and 60 effort events per protocol;
16 KiB registration request; 128 KiB selected feedback; 2 MiB human basis;
128 KiB assessment per arm and the inherited 200 KiB paired observation request;
12 MiB canonical capture with a 4 KiB response reserve. Reject oversized additions;
never truncate evidence/history. List default 10, maximum 20. Active job polling is
2.5 seconds and stops on request failure until explicit refresh.

## API

Prefix: `/api/v1/matters/{matter_id}/analyses/{analysis_id}/authority-model-trials`.

| Route | Contract |
|---|---|
| `POST /registration-context` | Typed source selection; guarded current input preview and eligible accounts; no inference |
| `POST /` | Exact preview/version/revision, receipt nonce, selection, rubric/family/origin and two accounts |
| `GET /?limit=&offset=` | Bounded metadata only |
| `GET /{id}` | Current/Stale/Withheld capture, jobs, comparisons, histories and unknowns |
| `POST /{id}/run` | Registering operator, empty strict body, permanent two-arm receipts |
| `POST /{id}/observations` | Assigned account, exact execution/comparison seals, both complete arm assessments and own previous head |
| `POST /{id}/effort` | Operator, exact execution and previous effort head, declared active phases and confirmations |
| `GET /{id}/export` | Fresh guarded confidential canonical JSON; `no-store` and `nosniff` |

There is no new service/schema migration or credential/source/account activation.
Existing [private model comparisons](REGISTERED_ANALYSIS_COMPARISONS.md) and
[human revision authority trials](REGISTERED_AUTHORITY_TRIALS.md) retain separate
protocols. Next engineering: confidential model-authority trial cohort freeze and
reconciliation, retaining exact incompatible profiles, overlap, disagreement and
unknown measurements. Lawful corpus acquisition, protected independent legal review,
representative Turkish semantic/adverse evaluation, real-model benefit, deployment
and release qualification remain open.
