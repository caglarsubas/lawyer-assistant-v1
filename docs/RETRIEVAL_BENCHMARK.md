# R04 development retrieval benchmark

This measurement framework compares three search profiles on one sealed v3 index
and one currently authorized graph snapshot. It supports the planned **360-query
benchmark, 120 per launch practice**, while preserving pending acquisition and
lawyer-adjudication gates. A generated example or completed run cannot substitute
for that dataset or the independent held-out release evaluation.

## Freeze the input

`retrieval-development-benchmark-v1` declares development purpose, real/synthetic
origin, adjudication status and an adjudication-evidence digest when adjudicated.
The snapshot pins the graph release, signed-serving digest, activation sequence,
concrete index, indexed-document digest, schema, normalization/Unicode profile,
citation profile and fusion recipe. It must be a release-bound v3 index.

Each query declares its text, exact `as_of` date or explicit unknown date, practice,
year-period bin, slices, source/proceeding/near-duplicate family digest and corpus
coverage. Fixed slices include temporal transitions, citations, adverse authorities,
OCR, concept confusion, passage roles and missing coverage. Query IDs and identical
text/date pairs cannot repeat. Shared families remain allowed and are grouped when
estimating uncertainty; assigning hashes does not discover duplicates or leakage.

Supply unique authority judgments with relevance grades **0–3** and a separate
adverse-authority flag. An adverse authority must have a positive relevance grade.
An optional exact target must also have a positive judgment. These are reviewer
judgments about the containing authority, not automatic interpretations of a
citation, decision treatment, passage role or legal effect. The framework checks
structure and digests; independent review must establish their meaning and truth.

The planned temporal fraction is at least 30%. Reports show observed inventory and
the planned targets separately; they never invent missing tasks, judgments, reviewer
approval or sample-size sufficiency. Input schemas and Python cross-record rules
both apply. The input cap is 1,000 queries and 100 judgments per query, subject to
the offline CLI's existing 2 MiB/JSON-node limits per file.

## Capture actual search results

`app.retrieval_benchmark.capture_run(benchmark, authorized_search, seconds=120)`
accepts a configured `PublicSearchService` bound to the authorized signed release.
Call it within the trusted local evaluation process after constructing that service
through the existing private authorization configuration. It performs no settings
or `.env` loading, index build, selection, graph mutation or provider request.
There is no new public API or agent permission for selecting evaluation profiles.

| Profile | Requested channels |
|---|---|
| `lexical` | Existing Turkish-analyzed original text/title baseline |
| `turkish` | Baseline plus original-token, normalized and folded channels |
| `all` | Default channel set, including literal citations when supported keys occur |

All profiles use the same date/rights/review filters, signed-source projection,
200-candidate cap and cooperative 12-second search budget. Their candidate budgets
are apportioned by the existing recipe, so this measures the deployed profile
configuration rather than holding each channel's candidate count constant. Vectors
are excluded from this comparison. Normal application/agent calls retain `all`.
Old v1/v2 readers remain compatible; this comparison specifically requires v3.

The capturer checks the graph pin and index receipt before execution, verifies each
search's receipt, and rechecks both before returning. Revocation, activation changes,
receipt mismatches or inability to verify the frozen snapshot discard the capture.
No graph read lock is held across the benchmark; writers remain eligible between
ordinary search operations. Guards still apply within those operations.

Execution is sequential with no retry. The first profile rotates between queries
to reduce a fixed warm-cache ordering bias. The total query-work budget defaults to
120 seconds and can be set from 1–7,200 seconds. It is cooperative, checked before
each search; source/guard/in-flight work and final receipt checks can extend elapsed
time. Every unexecuted query/profile cell is retained as `not_run`; no further search
traffic is sent for it. A complete 360-query dataset may need multiple explicitly
budgeted captures; this version requires all cells in one supplied run and does not
merge independently captured snapshots.

A captured run contains the input digest, snapshot and all three cells per query:
status, elapsed time, rejected-hit count, returned-passage count and ordered distinct
authority IDs. Duplicate passage/assertion links to one authority receive one rank,
in order of first appearance. There are at most 20 raw returned passage records;
extra records are not fetched to fill 20 authority ranks. Captures contain no query
text or source passages, but identifiers/digests can link confidential research.
Store benchmark files and captures within the authorized evaluation environment.

## Score a captured run offline

```sh
backend/.venv/bin/python scripts/benchmark_retrieval.py --schemas
backend/.venv/bin/python scripts/benchmark_retrieval.py /path/to/benchmark.json \
  --run /path/to/run.json
```

The scorer accesses no settings, database, network, provider or credentials. It
rejects duplicate JSON keys, nonfinite numbers, oversized/deep/wide input, unsafe
final file types/links, changed files and missing/repeated/foreign query-profile
cells. It recaptures both files before output. This detects ordinary file changes;
it is not a signed evidence system or protection against a privileged host.
Invalid input exits 2 without a partial report or submitted text/path in diagnostics.
Exit 0 means the scoring operation completed. Every report states
`production_qualified: false` and `runtime_authorization: none`.

The aggregate report contains counts, metrics, input/snapshot digests and fixed
scope/group labels; it excludes query IDs/text, authority IDs, family IDs and paths.
Reports also require protected storage because their hashes can link records.

| Metric | Calculation and denominator |
|---|---|
| Recall@20 | Distinct positive judged authorities found / positive judged authorities |
| nDCG@10 | DCG with gain `2^grade - 1` and discount `log2(rank + 1)`, divided by ideal DCG |
| Adverse Recall@20 | Positive judged adverse authorities found / judged adverse authorities |
| Exact-target hit@20 | Whether the explicitly judged target appears in the returned authority ranking |

The exact-target metric concerns text-query discovery. It does not evaluate the
separate structured `authority_id` lookup or fulfill its ≥99% release target.
Empty positive/adverse sets and unknown/outside corpus coverage are **unmeasured**,
not perfect results. Unjudged returned authorities have zero relevance gain and their
counts remain visible; nDCG depends on the completeness of the judged pool.

All covered queries with positive gold remain in aggregate metric denominators.
Partial, unavailable and unexecuted cells retain the authorities actually returned,
or an empty ranking, so failures cannot improve aggregate recall by disappearing.
Reports break down status, coverage and metrics by practice, year period and slice.
Elapsed means are descriptive executed-query observations, including failed work;
this is not representative p95 latency or capacity qualification.

Two paired comparisons use the same query/input/snapshot: `lexical → turkish` and
`turkish → all`. Each metric reports candidate-minus-baseline mean, improved/regressed/
unchanged counts and excluded queries. Paired quality intervals use only queries
whose two cells were available and whose metric was measured. Partial/outage cases
remain visible in the full aggregate and excluded-pair counts.

The deterministic 95% percentile interval uses **500 paired block-bootstrap samples**
resampling declared families, keeping all queries in each selected family together.
The canonical benchmark digest seeds the draws. Fewer than two eligible families
produce no interval. This reports uncertainty conditional on the supplied sample,
judgments and family definitions; it does not establish independence, representativeness,
causality, adequate sample size or a universal improvement guarantee. Inspect per-slice
failures and regressions before changing models or retrieval configuration.

## Exercise without legal data

Choose a new output directory:

```sh
backend/.venv/bin/python scripts/build_retrieval_benchmark_fixture.py \
  .data/verification/retrieval-example
backend/.venv/bin/python scripts/benchmark_retrieval.py \
  .data/verification/retrieval-example/benchmark.json \
  --run .data/verification/retrieval-example/run.json
```

The generator writes three invented queries and nine **invented rankings**. It does
not execute retrieval; origin remains synthetic and adjudication remains pending.
Separately, the opt-in v5 OpenSearch drill captures nine actual profile searches
against invented citation passages and three profile searches through actual
signed-source projection/private PostgreSQL authorization. The former uses an
explicit fixture projection; neither establishes legal relevance or real-corpus
quality. The [validation record](VALIDATION.md) retains exact software fingerprints
and distinguishes these scopes.

R04 still needs the real development set, two-reviewer adjudication, passage-level
judgments, reviewed target/version identities, independent adverse search,
vector/graph/reranker ablations and representative resource measurements. R08's
held-out evaluation and lawyer pilot remain separate gates.
