# Bounded frontend CI capacity

The complete100 handoff passed PR159, but its frontend job took270/300 seconds,
leaving exactly the30-second minimum and no reserve for another return slice.
The growing isolated history suite is the measured bottleneck; shorter runtime
on a local machine does not establish hosted capacity.

Before adding any destination-return cases, split the existing suite using the
locked Vitest version's built-in hash sharding. `frontend` retains the complete
TypeScript/Vite build and runs shard1/2; `frontend-history` runs shard2/2. Both
retain x86 runners, isolation, two workers and five-minute caps. The default
`npm test` still runs the entire suite. No test file or application code changes.

This deliberately supersedes the previous eight-job allocation with nine jobs.
It adds a second frontend setup, while executing each frontend test once; it
does not raise any existing deadline or promise lower billing on every run.
Both frontend jobs must pass and leave at least30 seconds of headroom. All
seven backend/PostgreSQL/graph jobs, selections, caps and assertions remain.

`scripts/verify_frontend_shards.mjs` proves complete disjoint file discovery
using Vitest's exported sequencer. Each CI lane also verifies its actual JSON
report against the expected file set and requires every discovered case to pass.
Local qualification compares the full baseline's case identities with the
multiset union of both executed shards, including all9,632 original cases in
132 byte-identical files. A missing, extra, duplicated or failing report fails.
No verdict cache, test exclusion, skipped failure or unchanged-code timing
retry is introduced. All100 observations, confidentiality, versions, filters,
review history and permission behavior remain unchanged.

Hosted qualification, independently green base-main, exact submitted-head
checks, one ordinary matching-head squash and complete tested/merged tree
equality remain separate gates. A cancelled main run is not a green baseline.
Only its two cancelled jobs are resumed through the connected GitHub app;
successful jobs are not repeated. This is cancellation recovery, not a retry
to improve a timing observation.

The complete100 destination-return implementation remains unstarted until
this capacity prerequisite passes. Legal/corpus/rights/customer qualification
and deployment remain outside this engineering capacity result.

Local observation:72.697 seconds full-suite;40.786/40.379 seconds for shards,
with5,086/4,546 cases in66 files each. Their complete case multiset equals the
full baseline. All395 frontend files stay byte-identical;45 deployment contracts
and Ruff pass. Four deliberately invalid reports fail closed. See
[evidence](evidence/ci-frontend-shards-2026-10-20.json). Hosted qualification is pending.
