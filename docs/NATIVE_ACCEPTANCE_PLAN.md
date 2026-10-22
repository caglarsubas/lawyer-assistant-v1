# Fresh frozen native acceptance declaration

This milestone prepares a plan, not a native run. No provider settings, secrets,
private case records, model calls, legal review decisions or production hooks are
used. The owner's focused-analysis version 3 remains pending. Synthetic extracted
text does not qualify PDF, Word, OCR, page layout or real legal reasoning.

## Freeze and separation

Freeze P1401–P1414, original text/UTF-8 hashes, document revisions, questions,
expected groups, empty-selection expectations, planner code and full source
inventory before the first offline preflight. The declaration contains the exact
v2 plan, separately versioned D-ID wire messages, measured budget, omissions,
criteria digest, implementation/dependency hashes and fixed schedule for every
case. The entire declaration is sealed and rebuilt for validation. Earlier
fixtures, failures, prompts and production packing remain unchanged.

`docs/evidence/frozen-native-acceptance-plan-v1.json` is the canonical prepared
artifact. Expected groups stay in the separate fixture/grader: a later executor
must send only each case's exact `messages`, never the declaration or expected
groups. All fixture facts are invented. Their document hashes identify synthetic
text collections, not uploaded binary originals. Engineering-authored labels have
not received independent legal adjudication. The set is fresh to native model
execution, not a claim of developer-blind or independently held-out evaluation.

## Preconditions for any later execution

This declaration has no executable runner or execution authorization. A separate
execution step must retain an owner-authorized binding receipt before its first
completion, pinning the actual model digest, registry context and approved local
transport origin. The digest and origin are explicitly **not yet attested** here.
Keep that binding separate from this immutable plan; a model-name match or old
readiness report is insufficient. The later implementation must provide fresh
before/after identity checks and their approved metadata routes before execution.
Unverifiable identity, a changed digest, cloud routing or fallback blocks the run.

The intended model is `ministral-3:8b`, tenant `lawyer-assistant-v1`, organization
`org-lawyer`, key ID `lawyer-assistant-v1-primary`. Credentials remain server-side
and never enter this artifact or public logs. An approved HTTPS tunnel ending on
the owner's laptop remains an allowed transport; it is not literal air-gapped
operation. No BYOK or external inference is authorized by this plan.

Use the unchanged disposable adapter and Provider safeguards: 8192 conservative
UTF-8 accounting units, 1200 completion-reserve units, maximum 1000 completion
tokens, temperature zero, non-streaming JSON object, 8192 response bytes and 4096
selection-content bytes. These units are not measured tokenizer counts. The
Provider's total response budget is 120 seconds and HTTP socket timeout at most
90 seconds. Block an over-budget envelope before transport; never clip a condition,
translate a legacy ID, synthesize a quotation or repair an invalid response.

Use an isolated disposable process with invented sources only, no production
data/settings/secret mounts, no application persistence and only the approved
provider route. Inject the credential through a protected runtime-only channel.
Record fresh authorization and exact evidence identity at the boundary, not just
caller-supplied hashes. This declaration does not implement those runtime checks.

## Schedule, request bounds and stops

1. Verify the full plan/code/source/criteria/wire seal and all no-call controls
   P1412–P1414. A control can pass transport isolation while still exposing a
   positive quality failure; retain both outcomes.
2. Run P1401 once as a serial smoke test. A smoke failure stops subsequent waves.
3. Run exactly P1402–P1406 as one five-job batch, then P1407–P1411 as another.
   Keep fixed membership/order and one attempt per case. Do not select replacement
   cases after seeing results.

Maximum 11 completion requests, 11 adapter metadata requests and 24 separately
bound identity-metadata requests (before/after each native case and the trial):
35 metadata requests total. No retries, metadata caching or extra exploratory
completion is permitted. Each wave has a 150-second wall bound and the entire
trial a 450-second bound. Record queue time, start/end and monotonic elapsed time,
including every failure. Five-way start barriers and observed request-interval
overlap are necessary evidence of concurrency. One small two-wave trial cannot
establish sustained capacity or legal workload performance.

Missing authorization or identity, changed code/source/wire/criteria, a failed
no-call control or a private-input/egress/logging violation blocks all transport.
HTTP 502, metadata/transport failure, wrong identity, invalid/fabricated IDs,
evidence races, deadline/response-bound failure or cancellation stops new work.
Cancel queued work and drain already in-flight work to its deadline; do not claim
that cancellation undoes an HTTP request. Preserve completed, failed, in-flight,
cancelled and not-started rows. A semantic miss is scored once without a rewritten
prompt or same-case retry. Historical 502 failures remain unresolved.

## Grading and release interpretation

The independently held grading fields require all expected text fragments from
the right document revision to occur within one selected atomic bundle for each
group. A source occurrence or partial condition earns no complete-group credit.
Required supportive and adverse groups remain distinct. Expected-empty cases
require an empty selection: schema-valid irrelevant fallback selection fails.
An empty response to a positive case fails. A no-candidate positive control or a
blocked positive request never becomes a quality success.

Report candidate availability before model selection, selected/available and
selected/all-required groups, both sides per adverse case, per-kind outcomes,
explicit-empty performance, exact spans/revisions, omitted sources, fallbacks,
partial-source flags, no-call controls, transport failures and latency. Keep all
14 cases and all required groups in denominators, even when unavailable, blocked,
cancelled or unstarted. Full acceptance requires every positive case/group and
explicit-empty expectation to pass with no integrity/transport failure. The
smaller eligible/available subsets cannot supply the overall pass rate.

The offline preflight deliberately selects all nominated candidates to measure
an availability upper bound. It is not a model result; it may fail empty-selection
rules. Its pure grader always returns native verification false, even for a
perfect fabricated selection. Contract tests cannot create a native receipt.
Future native evidence needs actual request/response/identity/timing receipts and
independent reconciliation against the frozen declaration before any native
qualification. Even a successful synthetic trial supplies no legal, reviewed
corpus, production activation, negligible-error or sustained-capacity guarantee.

## Operator procedure

Prepare with `PYTHONPATH=backend:scripts backend/.venv/bin/python
scripts/native_acceptance_plan.py --output <new-path>`. The CLI creates a new
file exclusively and never overwrites an earlier declaration. Freeze its SHA-256
before invoking `native_acceptance_grading.preflight`. Keep the first report,
frozen hashes and all failures. Any repair needs a newly versioned recipe and
fresh native acceptance cases; never tune this exposed set until it passes.

Before merge, run offline contract tests, a public-code-only read-only Linux
container with networking disabled, full deployment contracts and relevant
provider/context regressions. Retain identical host/Linux declarations and
preflight reports. All nine exact-head CI jobs and the existing five 30-second
timing-reserve gates remain required, with unchanged jobs, caps and workers.
Verify merged-main tree separately. Audit unchanged originals, exact evidence,
encrypted bytes, runtime credentials, sessions and review history; update the
roadmap without completing the pending owner review or native qualification.
