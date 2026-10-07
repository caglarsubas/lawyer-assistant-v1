# Offline legal-analysis and BYOK qualification scoring

The separate [R04 development retrieval benchmark](RETRIEVAL_BENCHMARK.md) captures
fixed lexical profiles on one authorized snapshot and reports ranking metrics and
paired family uncertainty. Its development observations do not replace the held-out
legal-analysis/privacy qualification described here.

This command scores **supplied adjudications**. It does not run legal analysis,
inspect the underlying legal evidence, call a provider, certify reviewers, grant
source rights or enable dispatch. Reports always retain `production_qualified: false`
and `runtime_authorization: none`. Real evidence belongs in a confidential evaluation
workspace outside Git; committed/generated examples are synthetic.

The app's [source-linked revision adjudication](ANALYSIS_ADJUDICATION.md) records
authenticated private observations against exact before/after drafts and quotations.
It does not automatically produce scorer rows, independent annotators, held-out
families, adverse gold sets or full trial timings. Its optional declared review time
is one observation, not the scorer's complete preparation-time accounting. Real
comparison capture and independent adjudication still require a frozen protocol.

## Run a scoped evaluation

```sh
backend/.venv/bin/python scripts/evaluate_release.py --schemas
backend/.venv/bin/python scripts/evaluate_release.py /evaluation/tasks.jsonl \
  --snapshot /evaluation/snapshot.json --protocol /evaluation/protocol.json
```

Exit **0** means all implemented quantitative gates passed for the exact declared
scope. Exit **1** means valid input with unmet or unknown gates. Exit **2** means
invalid, mixed, changed or oversized input; no partial report is emitted. A passing
numeric result is never production qualification or an API capability token.

The legacy two-file invocation remains available for core metric inspection. Its
report now explicitly says `scope: core_metrics_only`, exposes
`core_quantitative_gates_pass`, and leaves `quantitative_gates_pass: false` with exit
1. A previously perfect core dataset cannot silently bypass the added analysis and
privacy requirements. Migrate qualification callers to `--protocol` and the extended
row schema; do not treat core-only success as complete evaluation.

## Freeze the protocol before measuring

The versioned protocol declares:

- **Scope:** `local`, with no provider/configuration; or `connected`, with exactly one
  of `openai`, `anthropic`, or `gemini` and its configuration digest. Evaluate each
  adapter/configuration separately. Local evaluation does not require a provider.
- **Snapshot and rubric:** exact SHA-256 values for the snapshot and the independently
  defined argument-quality/adjudication rubric. Snapshot JSON requires `ontology`,
  `graphs`, `corpus`, `model`, `policy`, `index` and `workflow` version identifiers.
- **Registration time:** a timezone-aware instant no later than any measured row.
  The scorer checks declared chronology, not that registration actually happened.
- **Samples:** at least 1,000 tasks and 3,000 claims, plus declared minima for each
  launch practice, slice, comparison, metric denominator and independent split family.
  Unknown minima must be `null`; they fail the corresponding gate. Do not replace
  the R01 dossier's pending minima with invented reviewer-approved sizes.
- **Split inventory:** development-family digests excluded from held-out observations.
  Families must represent the source/proceeding/near-duplicate grouping agreed by
  reviewers. Hashing files alone does not discover leakage or independent cases.

Reconcile these targets with the R01 evaluation plan and obtain accountable review
before freezing a real protocol. A protocol file cannot certify its own approval.
The canonical digest uses the validated model's JSON value, UTF-8, sorted keys,
compact separators, `ensure_ascii=False`, and no nonfinite numbers. The `digest`
helper in `backend/app/qualification_scoring.py` implements this convention. Protocol
list order remains significant. Ordinary input-file hashes are reported separately.

## Supply one adjudicated task per JSONL row

Each row binds the protocol, snapshot, rubric, exact task input, split family and
adjudication-evidence digests. It declares real/synthetic origin, measurement time,
mode/provider/configuration, distinct annotators and whether disagreements were
resolved. Duplicate task IDs or task-input digests, development-family overlap,
non-held-out tasks and mismatched scopes/pins are rejected. Synthetic rows remain
useful for exercising the scorer but cannot contribute to a passing real cohort.

The nested `score` retains the original citation, support, critical-error, retrieval,
abstention, usefulness, safe sensitive-task completion and preparation-time judgments.
Booleans/counts are strict: strings such as `"true"` and boolean counts are rejected.
Time savings still include verification and correction. Safe local completion can
satisfy legitimate sensitive-task passage; this is not an external-transmission quota.

`analysis` records consequential applications and those independently judged to link
premises to exact authority/version evidence, critical inference/fact/omission/role
errors, and gold/retrieved adverse authorities. All consequential steps must be
judged grounded; answerable tasks cannot omit the analysis. Critical errors cannot
be offset by good claim-support averages. Known adverse Recall@20 must reach 95%;
empty gold sets are unmeasured and cannot satisfy the adverse slice.

Rows declare the applicable `slices` and individual `checks` from the exported
schema/Python catalog. Each selected slice must assess every required check. A
`false`, `null` or absent verdict fails that slice even when its other cases pass.
A single task may cover multiple slices, but it counts once in each. Actual privacy
or security experiments and their retained evidence must support these labels.

| Scope | Mandatory dimensions |
|---|---|
| Local and connected | Citation/time/institution, adverse authorities and fact comparison, allegation/finding and majority/dissent roles, correction, Standard/Deep, disconnected operations including cancellation/revocation, no external traffic, matter isolation, source rights, exports, retention and five-job contention |
| Connected, per provider | Direct Turkish/OCR/encoded identifiers and secrets; contextual and cumulative disclosure; facts/dates/thresholds/roles/uncertainty; keys, exact approvals, replay/retry, revocation, spend, tools and fallback; original citations, exact passages/versions, roles, injection and unavailable originals |

The connected operations slice includes testing the product with connected research
disabled; a connected installation must still support independent disconnected use.
A passed row is a reviewer-supplied observation, not an assertion made by this scorer
about the current deployment or a provider's current API/processing terms.

## Compare correction, depth and abstraction

Comparison slices require explicit pairs on the same task input and full snapshot:

| Kind | Baseline | Candidate |
|---|---|---|
| `correction` | `single_pass` | `bounded_correction` |
| `standard_deep` | `standard` | `deep` |
| `privacy_fidelity` (connected) | `original_private_local` | `sanitized_scenario_local` |

The last comparison is local: it never authorizes transmitting the private baseline.
Each trial records claim counts/support and claims with resolvable citations, gold adverse authorities found, argument
quality on the pinned rubric, critical errors, elapsed/compute time, reported USD
external cost, preparation time and lawyer review time. Total preparation time is
active preparation work including verification/correction; it is separate from
wall-clock execution time. Local trials must report zero external research cost.
These are supplied measurements, not provider billing reconciliation.

Every seeded correction defect must be recorded as repaired with evidence, explicitly
withheld or unresolved. Unresolved defects or introduced regressions fail the paired
gate. Missing time accounting also fails. Per-pair support, adverse recall or argument
quality regressions cannot be hidden by gains on other tasks; candidate critical
errors fail, and candidates retain 100% citation resolvability, 99.9% support and 95% adverse-recall floors.
Comparisons with unknown adverse denominators remain unqualified.

Reports show pair counts, introduced/unresolved defects, repairs/withholding,
per-pair improvement counts and median **candidate minus baseline** deltas. Time/cost
can increase without falsely implying better quality. `statistical_improvement_established`
remains false: this milestone does not compute paired confidence intervals or establish
causality. No gain is required merely to report a completed comparison; a passing
nonregression gate is not a claim that Deep mode improved the product.

## Exercise the contract without real data

Use a new output directory; the generator refuses an existing one:

```sh
mkdir -p .data/verification
backend/.venv/bin/python scripts/build_evaluation_fixture.py .data/verification/evaluation-example
backend/.venv/bin/python scripts/evaluate_release.py .data/verification/evaluation-example/tasks.jsonl \
  --snapshot .data/verification/evaluation-example/snapshot.json \
  --protocol .data/verification/evaluation-example/protocol.json
```

The last command should exit **1**: four invented rows, unknown minima and synthetic
origin do not qualify. Add `--provider openai`, `--provider anthropic` or
`--provider gemini` to the generator for a separate connected example. This changes
only fixture labels; it performs no provider access and accepts no API keys.

The scorer reads no `.env`, settings, database or credentials. It caps the task file
at 64 MiB/100,000 rows, each JSON value at 2 MiB, and snapshot/protocol files at 2 MiB.
It rejects duplicate JSON keys, nonfinite numbers, excessive nesting, symbolic or
hard-linked final files and nonregular files. It captures file identity/content and
recaptures before emitting a result; this is not protection against a privileged
host or an authenticated evidence-signing system. Extended reports contain hashes,
fixed scope labels and aggregates, not task IDs, annotator names, source passages,
scenario text or private paths. Protect reports too: stable hashes can link records.

Remaining gates include real sample acquisition and independent adjudication,
authentication/physical verification of referenced judgments, representative sample
approval, confidence intervals, temporal/relationship error slices, graph and retrieval
ablations, source freshness, actual provider/privacy/legal/operations qualification
and customer acceptance. This scoring milestone does not implement R05A analysis or
R05B adapters and does not complete R01 or R08.
