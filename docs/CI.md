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

The command above is the standalone complete-suite check. In GitHub Actions, the
five ontology preflight files are declared once in `CI_ONTOLOGY_PREFLIGHT_TESTS`.
Three expensive signed-publication integration files are declared once in the
workflow-wide `CI_PUBLICATION_TESTS` list. Preflight runs first; the main two-worker
step excludes both lists. The publication files run with two workers after the
serial database tests in the existing PostgreSQL job, without inheriting its
database URL. Together these three mandatory phases run the complete suite once;
a failed phase fails its required job. No case is waived or newly skipped.

This retains the complete suite and its real SHACL, cryptographic, authorization
and publication checks. There are no selective test skips, mocked validation
shortcuts, extra matrix runners or automatic worker-crash retries. Fixtures use
separate temporary directories, and network-server fixtures allocate ephemeral
ports. A test failure stops scheduling further tests (`--maxfail=1`); the required
check stays failed. Successful runs still execute the entire suite. All test
fixtures are function-scoped; splitting files does not share mutable fixtures
between workers. PostgreSQL concurrency tests remain in their separate serial job
with an explicit disposable database; they skip in the normal backend job. Research
publication/cancellation and coordinator-loss races join that existing serial job;
no additional hosted job, matrix runner, retry or higher time cap is introduced.

The isolated Docker recovery, five-job load, signed-graph lifecycle and public-search
index drills are explicit operator
commands, outside routine CI. Only their fast boundary/measurement tests join the
existing deployment-contract step. See the [load profile](OPERATIONS.md#five-job-application-baseline)
and [recovery drill](OPERATIONS.md#disposable-synthetic-recovery-drill), plus the
[graph lifecycle drill](OPERATIONS.md#disposable-signed-graph-lifecycle-drill) and
[OpenSearch qualification](OPERATIONS.md#isolated-opensearch-qualification). The latter
uses the pinned development dependencies in a separate test image; it is skipped in
routine backend runs unless the explicit isolated-drill marker is set. Its v2
workload uses disposable PostgreSQL and OpenSearch. Two new PostgreSQL cases reuse
one fixture per authorization schema to check five simultaneous read guards,
every protected row, exclusive publication actions and queued revocation. They
run in the existing serial PostgreSQL job without changing its five-minute cap.

The backend test step has a **18-minute hard limit**, inside a **20-minute job
limit**; frontend and PostgreSQL jobs each have a **five-minute limit**. Exceeding
a limit fails/cancels the check rather than marking partial work successful. Lint, backend tests and deployment tests are
separate steps. The test log prints the 30 slowest setup/call/teardown durations
to guide future optimization. Required job names are unchanged.

## Fresh matter authorization cost — 10 October 2026

PR #39's exact-head run `38050597031` passed, but its backend job took 19m14s
inside the existing 20-minute limit. A four-case isolated authority-workflow
profile found 47,319 calls to `require_matter` and 213,202 SQL statements. Each
call separately refreshed the account, checked case grants and refreshed action
permissions. The client-scope query was also constructed repeatedly.

`require_matter` now executes one prepared, parameterized statement covering
current account state, same-firm matter identity, direct/client scope and all
current role rows. Only query construction is reused. Every invocation still
executes SQL; no grant, permission, source verdict or trial-currentness result is
cached. Outer joins preserve unmanaged versus empty-managed roles and dangling,
foreign or malformed role denial. Account failure remains 401, absent/foreign/
out-of-scope matters remain indistinguishable 404s, and missing action permission
after valid scope remains 403. The expected firm is pinned before refreshing a
caller that shares ORM identity; a changed firm cannot overwrite that pin.

The same four cases in matching restricted Linux containers measured 112,927 SQL
statements after the change (**47.0% fewer**). Revalidation calls were slightly
higher (47,383 matter checks and 587 trial-currentness calls, versus 47,319 and
586 before), owing to asynchronous workflow polling. First-pair elapsed time was
30.30s before / 25.57s after; it is a diagnostic sample, not a stable hosted speedup
or invoice comparison. Both arms use invented cases and isolated databases.

Twenty-seven new regression cases require exactly one fresh SELECT per matter
check and verify current direct/client revocation, role changes, tenant changes,
archive/deletion, shared ORM identity and denial precedence. Existing full backend
and PostgreSQL race checks remain mandatory. CI events, job counts, execution
groups, workers, retries and deadlines are unchanged; collection verifies all
cases remain covered exactly once. Final checks and measurement fingerprints are
recorded in [verification](VALIDATION.md). Source/legal qualification and deployment
remain separate gates.

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
The later PR #27 correction also retains immutable SHACL parser syntax between
validations, while recreating translated programs independently as described below.

Each invocation owns its memory graph and bounded cache: at most 128 programs,
64 Ki characters per query/base/namespace mapping, 128 namespace entries and
1 Mi characters across retained keys. Overflow, unsupported options and custom
processors use native execution. Data and shapes are cloned before pySHACL's
in-place inference; caller-owned graphs stay unchanged. RDF, SHACL and catalog
files remain byte-identical, preserving ontology fingerprints and existing signed
packet compatibility. All live integrity and authorization checks remain active.

CI runs the query, membership, ontology-syntax, SHACL-syntax and RDFS-identifier checks before the expensive full suite. Their work
budget is deterministic rather than a fragile timing threshold: query parsing
must scale with distinct programs while the number of query executions remains
unchanged. It also tests the real release entry point, equal valid/invalid reports,
changed evidence/bindings, namespaces/base, cache limits and parallel isolation.
A regression fails this short step instead of consuming a full expensive run.
The tests remain mandatory in preflight; the subsequent CI step excludes the same
five files to avoid executing them twice. Dependency updates must pass them.
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

## PR #25 post-merge timeout: fresh inference membership work

The PR #25 checks passed, but exact post-merge main
[run 37733750369](https://github.com/caglarsubas/lawyer-assistant-v1/actions/runs/37733750369)
reached 99% and hit the unchanged 18-minute backend-step cap. The preceding PR run
passed 2,870 tests in 717.59s. This variation leaves insufficient margin; a passing
PR does not establish passing post-merge CI.

Profiling the real signed open-validity publication/search test found 93 full
SHACL validations and repeated exact-triple probes in RDFS inference. The scratch
graph now uses a **per-invocation, bounded exact-membership index** in its own
RDFLib Memory store. This changes lookup work, not inference rules or validation
policy. Native store writes maintain the index, including bulk/direct additions;
any removal, quoted/different context or more than 16,384 triples disables it for
that invocation. Wildcards and unsupported contexts retain native lookup. No
index, inferred fact or verdict survives into another validation.

Both profiles retained **93 validations and 1,023 query preparations**. Native
Memory pattern-iterator calls fell from **8,191,380 to 3,822,076**. Profiled elapsed
time was 101.04s before / 45.08s after; profiler overhead and local machine variation
make this diagnostic only. Eight alternating warm, unprofiled pairs on the full
2,374-triple schema and synthetic fixture measured medians **0.14304s before /
0.12206s after (14.7% lower)**. These are validator measurements, not hosted speedup
or invoiced savings.

The existing short preflight now also runs `test_validation_membership.py`;
**51 preflight cases passed**. They retain native inference/report equivalence,
current data after direct writes/removals, wildcard behavior, bounded fallback and
parallel isolation. The complete existing two-worker command passed **2,915 tests
in 331.56s locally**, with 39 documented PostgreSQL/drill skips and 28 warnings.
PostgreSQL races remain in the mandatory separate job. No jobs, workers, retries,
dependency changes, removed tests or increased limits were introduced. Fresh
source hashes, signatures, SHACL executions and live authorization remain intact.
New-branch hosted results and post-merge recovery require separate observation;
see [verification](VALIDATION.md).

## PR #27 timeout: repeated SHACL program parsing between validations

PR #26 and its exact post-merge main run passed, but PR #27
[run 37762645204](https://github.com/caglarsubas/lawyer-assistant-v1/actions/runs/37762645204)
hit the unchanged 18-minute Test backend cap after reporting **2,957 passed,
42 skipped and 28 warnings in 1,082.79s**. There was no assertion failure; the job
still failed and downstream contracts did not run. The failed result is retained.

Profiling the real signed-publication/search case reproduced **93 full validations**,
each translating its own 11 SHACL query programs. Their mutable program caches
were already local to each graph, but repeated validations parsed those same
programs again: **1,024 parser calls**, including one ordinary graph query.

Only `validate_graph` now opts into a synchronized LRU of **immutable parser
syntax**, keyed by exact SHACL query text. Each invocation reconstructs fresh
parser nodes and blank nodes, then translates with its current namespaces/base.
Each scratch graph owns its mutable programs, expressions, bindings and query
results. A cached expression is never executed or shared with another graph.
Direct/custom graph queries retain the ordinary preparation path. Changed shape
text parses anew; changed schema/data still run complete inference and validation.
No data graph, validation verdict, inferred fact, signature or permission is reused.

Retention is capped at **64 programs, 1 MiB of query-text bytes and 32,768 parser
nodes**, with at most 4,096 nodes per program and the existing 64 Ki-character
query bound. Eviction adjusts all counters. Unknown parser types/attributes,
named results with potentially aliased nodes and oversized trees retain freshly
parsed native behavior. Malformed queries fail and are not retained. The existing
per-invocation program/namespace/base/text limits remain active.

The representative profile retains **93 validations and 1,024 translations**;
parser calls fall **1,024 → 12** (11 cold SHACL programs plus the ordinary query).
Its after profile overlapped the complete suite, so profiled elapsed times are
diagnostic only. Eight alternating unprofiled warm pairs on the 2,374-triple schema
measure **0.12383s before / 0.09694s after median (21.7% lower)**. The final local
two-worker suite passes **2,979 tests in 323.79s**, with 42 documented skips and
28 warnings; this is not a controlled hosted-runner or invoice comparison.

The short preflight now includes **73 checks**, including all 22 new cache cases:
fresh evidence/shape verdicts, complete native reports and query work counts,
namespace/base resolution, rich query syntax, mutation/blank-node/concurrent
isolation, LRU and aggregate limits, malformed input and native fallback. All
checks remain in the complete suite. No jobs, workers, dependencies, retries,
test omissions or time-limit increases were introduced. RDF/SHACL/catalog bytes
and signed formats remain unchanged. New-head CI and post-merge CI are separate
observations; see [verification](VALIDATION.md).

## PR #30 timeout: repeated immutable identifier resolution

Initial [run 37874784913](https://github.com/caglarsubas/lawyer-assistant-v1/actions/runs/37874784913)
on `b4d024160662665cee0bb736b3f2a0e14f897f06` passed frontend and PostgreSQL but
backend reached 91% and exceeded its unchanged 18-minute step limit. Dependency
installation took three seconds. Removing repeated preflight execution was useful
but insufficient. There was no reported assertion failure before cancellation.

The signed-source authorization profile showed millions of repeated RDFLib
`DefinedNamespace` attribute resolutions in the native RDFS rule loop. RDF/RDFS
identifiers are constants; resolving their names on every rule invocation adds
work without changing their values. `ontology/rdfs_identifiers.py` binds those
identifiers to immutable tuples of the exact same URIRef objects.

The function's **native code object is reused**, including every entailment rule,
closure cycle and inference write. The pySHACL entry point also uses its native
code object with a private validator class. Only the application's exact scratch
graph and RDFS mode opt in. Third-party package globals are untouched. Different
dependency versions, unrecognized programs and other graph adapters retain native
execution. The engineering-tested versions are pySHACL 0.40.1, OWL-RL 7.6.2 and
RDFLib 7.6.0. No dependency or lockfile changes were needed.

There are twelve fixed identifier bindings and no matter data, source assertions,
query results, inferred graphs, source permissions or validation verdicts retained
by this adapter. Each call still constructs a new inference engine and performs
the full RDFS/SHACL validation against freshly read, integrity-checked inputs.
RDF, SHACL and catalog definition bytes and signed release formats are unchanged.

The deterministic regression budget retains **11,888 rule executions and 186
SHACL queries**, reducing namespace resolutions inside those rules from
**151,647 to zero** on the representative synthetic fixture. Native and optimized
inferred triples and valid/invalid reports match. Tests also cover cyclic
class/property relationships, domain/range, literals, container/datatype types,
unchanged caller inputs, immutable identifiers, unsupported-program/dependency
fallback and parallel graph isolation. They run in mandatory preflight before
the expensive suite. Collection proves **3,150 = 89 + 3,061** distinct node IDs,
with zero overlap, omitted cases or extras across the two CI steps.

Eight alternating warm, unprofiled comparisons measured native/identifier-bound
validation medians of **0.09503s / 0.05951s (37.4% lower)** using the final production
adapter with identical scratch graphs, shapes, options and syntax caches, without
patching dependency globals. This is a local validator
measurement, not a hosted runner or currency claim. Two pattern-index experiments
did not establish worthwhile improvement and were discarded. The correction adds
no runner, worker, retry or time-limit increase. Final-source full-suite, PostgreSQL,
offline Linux and hosted results are reported in [verification](VALIDATION.md).

## Offline evaluation scoring

The versioned analysis/privacy scorer is covered by fast synthetic Python tests in
the existing backend suite, including provider separation and CLI refusal cases.
It performs no provider requests or Docker workload. No job, matrix, dependency,
retry, worker or timeout is added for this milestone.

The R04 Turkish retrieval fields add fast normalization, recipe-compatibility and
channel-boundary tests to the existing backend suite. Real OpenSearch Turkish
matching remains in the opt-in isolated index drill, outside GitHub Actions.
No CI job, dependency, worker, retry or timeout was added.

The R04 literal-citation slice adds bounded parser, source-recheck and v1/v2
compatibility cases to the same backend suite. Its real OpenSearch keyword,
collision and tampering cases run only in the opt-in v4 drill. Exceeding the query
citation budget preserves other channels; source overflow blocks preparation
before index writes. The CI topology and deadlines remain unchanged.

The R04 development benchmark adds fast ranking, complete-cell, snapshot,
revocation, file-integrity and grouped-bootstrap cases to that suite. Real profile
capture is exercised only by the opt-in v5 OpenSearch drill. No hosted Docker
benchmark, matrix, dependency, job, worker, retry or time-limit increase is added.

## PR #30 follow-up: balance existing runner capacity

The identifier correction was active in the application: an actual runtime profile
retained 58 validations and 663,180 native rule executions, while namespace
resolutions fell from 8,500,101 to 41,605. Nevertheless, [run 37882649274](https://github.com/caglarsubas/lawyer-assistant-v1/actions/runs/37882649274)
on `1629195943490100ce712ab39a4350733d13dc4d` finished all remaining backend cases
(**3,010 passed, 51 documented skips**) in **1,090.47s**, just beyond the unchanged
18-minute step deadline. The check failed and downstream contracts did not run.
There was no assertion failure. Its PostgreSQL job finished in 1m48s and frontend
in 23s; all workload in one backend job still exceeded available time.

The three measured expensive signed-publication files now use spare capacity in
the existing PostgreSQL job. Its 48 database cases remain serial and its URL remains
scoped exclusively to that step; the ten publication cases then run with two
workers. These cases keep real validation, publication and revocation checks.
Both jobs consume one shared publication file list, preventing omissions or
duplicate execution when that list changes. Full-suite collection verifies
**3,150 = 89 preflight + 3,051 remaining + 10 publication** distinct node IDs, with
zero missing, extra or overlapping cases. The 51 database/drill skips in the
standalone suite are unchanged; database cases still execute in the serial step.

This balances the existing three jobs, without additional runners, workers,
retries, raised time limits or selective skips. It prevents the deadline from
discarding completed backend verification; actual hosted results must still be
observed at the new head. Future suite growth must be profiled against both job
budgets. Runner elapsed time is not an invoice or a production-performance claim.
