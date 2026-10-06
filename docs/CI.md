# CI runtime and cost controls

GitHub Actions runs the complete backend suite once per PR update and once for a
push to `main`. Feature-branch pushes do not start a second copy of the same PR
checks. Manual runs remain available. The existing concurrency group cancels an
older run for the same PR or branch; separate PRs retain separate checks.

Backend tests use **two pytest-xdist workers inside one runner** with work stealing
to balance individual tests as workers become free:

```sh
uv sync --project backend --frozen --extra dev
backend/.venv/bin/pytest backend/tests -n 2 --dist worksteal --max-worker-restart=0 --maxfail=1 --durations=30
```

This retains the complete suite and its real SHACL, cryptographic, authorization
and publication checks. There are no selective test skips, mocked validation
shortcuts, extra matrix runners or automatic worker-crash retries. Fixtures use
separate temporary directories, and network-server fixtures allocate ephemeral
ports. A test failure stops scheduling further tests (`--maxfail=1`); the required
check stays failed. Successful runs still execute the entire suite. All test
fixtures are function-scoped; splitting files does not share mutable fixtures
between workers. PostgreSQL concurrency tests remain in their separate serial job
with an explicit disposable database; they skip in the normal backend job.

The backend test step has a **18-minute hard limit**, inside a **20-minute job
limit**; frontend and PostgreSQL jobs each have a **five-minute limit**. Exceeding
a limit fails/cancels the check rather than marking partial work successful. Lint, backend tests and deployment tests are
separate steps. The test log prints the 30 slowest setup/call/teardown durations
to guide future optimization. Required job names are unchanged.

## Evidence and measurement boundary

On 5 October 2026, completed [run 37283288461](https://github.com/caglarsubas/lawyer-assistant-v1/actions/runs/37283288461)
reported **1,971 tests in 2,101.48 seconds (35m01s)**. Dependency installation
took only four seconds. Both `push` and `pull_request` independently executed
the suite for the same revision. Removing that duplication removes one complete
automatic workflow run per PR revision; it does not remove post-merge verification.

A local profile of two graph tests found repeated SHACL/RDFS/SPARQL work dominated
execution. Each validation reparsed identical SPARQL for every focus node, amplified
by the entry/exit checks that detect tampering and revoked approvals. File-level
timestamps in the old GitHub log are buffered and do not reliably measure individual
test files; use pytest's duration report instead. Dependency caching is not the
current bottleneck and no additional cache infrastructure was added.

Before the query optimization, the complete R02 backend collection passed locally
with two workers and file grouping: **2,058 passed, eight PostgreSQL cases skipped, 28 existing deprecation
warnings in 336.83 seconds (5m36s)**. The PostgreSQL cases remain mandatory in their
dedicated CI job. `actionlint`, project-wide Ruff, frozen offline dependency sync
and lockfile inspection passed; the only added packages are the development-only
`pytest-xdist` and `execnet`, with all existing versions retained. Local evidence
is in `.data/verification/ci-parallel-full.log` and `ci-old-run.{json,log}`.

The pre-optimization two-worker [run 37288487441](https://github.com/caglarsubas/lawyer-assistant-v1/actions/runs/37288487441)
finished its backend suite in **1,178.94 seconds (19m38s)**: 2,057 passed, eight
skipped and one failed. Its relay test observed an upstream connection before the
server thread completed cleanup. The test now waits for an explicit completion
event with a bounded deadline, preserving its closure assertion. It does not use
fixed sleeps or automatic retries.

Compare a completed optimized hosted run with these measurements before claiming
additional hosted speedup or currency savings. Local wall time is not a hosted
runner benchmark, and elapsed runner minutes are not an invoice. Existing runs
use the workflow with which they started; changing the file does not retroactively
change their worker count or timeout.

## Root-cause fix and regression prevention

`ontology/validation.py` uses RDFLib's prepared-query API to parse each distinct
query program once within a single validation. Every focus-node query still
executes against the current data and bindings. The key includes the query,
effective namespace mapping and base URI. There is no shared cache of results,
validation verdicts, inferred facts, authorization decisions or release contents.
The separate bounded Turtle syntax cache described below retains only parsed
ontology definitions; it never retains validation results.

Each invocation owns its memory graph and bounded cache: at most 128 programs,
64 Ki characters per query/base/namespace mapping, 128 namespace entries and
1 Mi characters across retained keys. Overflow, unsupported options and custom
processors use native execution. Data and shapes are cloned before pySHACL's
in-place inference; caller-owned graphs stay unchanged. RDF, SHACL and catalog
files remain byte-identical, preserving ontology fingerprints and existing signed
packet compatibility. All live integrity and authorization checks remain active.

CI runs `test_validation_queries.py` and `test_ontology_syntax.py` before the expensive full suite. Their work
budget is deterministic rather than a fragile timing threshold: query parsing
must scale with distinct programs while the number of query executions remains
unchanged. It also tests the real release entry point, equal valid/invalid reports,
changed evidence/bindings, namespaces/base, cache limits and parallel isolation.
A regression fails this short step instead of consuming a full expensive run.
The tests remain in the full suite as well. Dependency updates must pass them.
The final two-worker work-stealing command passed all 2,081 backend tests locally
in **241.73s (4m01s)**, with eight PostgreSQL skips and 28 existing warnings.
This is 28.2% less wall time than the earlier 336.83s local run despite adding
23 regression tests. It is not a controlled hosted-runner comparison.

The representative synthetic corpus performs **186 query executions** under both
implementations, with **186 parses reduced to 10**. Runtime measurements and
full-suite results are recorded in [the verification record](VALIDATION.md).
This improves the production validation path as well as CI; no validation is
mocked out to obtain the reduction.

References: [GitHub triggers and timeouts](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax),
[pytest-xdist worker distribution](https://pytest-xdist.readthedocs.io/en/stable/distribution.html).

[RDFLib prepared queries](https://rdflib.readthedocs.io/en/7.1.0/intro_to_sparql.html),
[pySHACL validation options](https://github.com/RDFLib/pySHACL).

## PR #6 timeout: repeated ontology parsing

[Run 37337320919](https://github.com/caglarsubas/lawyer-assistant-v1/actions/runs/37337320919)
hit the existing 18-minute backend-step limit at 99% completion. The log contains
no test assertion failure before timeout. The previous SPARQL optimization did
not eliminate repeated Turtle parsing: validation and serving reconstruction
each parsed the same ontology, including once for each serving graph family.
The application also re-imported the serving module on every guard call.

Serving code is now imported once per process. A four-entry LRU retains immutable
Turtle syntax keyed by **exact freshly read bytes and each file's base URI**.
Each entry is limited to 32 files, 512 KiB of source bytes plus URI text, and
10,000 triples. Larger inputs parse normally without retention. Each caller gets
a separate graph with fresh blank nodes; caller mutations and inference cannot
alter cached syntax. Access to the LRU is synchronized. Source assertions, matter
data, query results, signatures, permissions and validation verdicts are not cached.

Every invocation still reads source files. Serving reconstruction verifies their
hashes against the signed manifest before consulting cached syntax, then recreates
both payloads. Full RDFS/SHACL validation and entry/exit authorization checks still
run. Changes with identical file size and timestamps invalidate syntax by content;
missing, unreadable or malformed files still fail. Ontology definition bytes and
signed release formats are unchanged.

Regression checks enforce parsing-work counts, source-record reparsing, changed
schema and shape behavior, graph/blank-node isolation, base-URI handling, eviction,
oversize fallback, concurrent readers and warm-cache tampering rejection. They run
in the short preflight step and remain in the full backend suite. No jobs, workers,
dependencies, retries or time-limit increases were added. The verification record
contains local measurements and, separately, observed hosted results.
