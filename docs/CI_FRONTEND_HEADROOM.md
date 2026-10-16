# Frontend CI headroom

PR98's frontend job passed in 297 seconds under its unchanged 300-second cap.
The hosted timing record attributes 89 seconds to workspace contracts and 147
to human-review contracts, versus 17 seconds for the build and 18 for frontend
tests. The expensive model-cohort file alone used 105.99 aggregate worker
seconds across 19 cases. This is measured scheduling pressure; adding UI cases
without rebalancing would leave the job vulnerable to normal runner variation.

The complete `test_authority_model_cohorts.py` file now runs in the existing
main backend remainder instead of the frontend's workspace group. Existing
central selectors automatically remove it from the remainder's ignore list.
The frontend retains x86 permission, proposal, human-review and graph coverage;
model-cohort contracts use the already established native ARM backend executor.
No production code, test assertion, fixture logic, verdict cache or retry changes.

All seven job names, two-worker limits, architectures, step/job deadlines,
PostgreSQL storage/durability settings and complete 4,521-case identity inventory
remain. Only allocation changes: workspace 67 -> 48; main remainder 3,888 -> 3,907.
All other disjoint groups are unchanged. Independent full collection proves no
missing, overlapping or additional IDs; the complete inventory hash is unchanged.

A broader redistribution into three-minute jobs was rejected after local
measurements showed insufficient margin. The chosen receiver is qualified as its
complete exact workflow partition, not a reduced subset. The existing test image
was independently matched against every current backend application source file;
current test files are mounted read-only. Local timing establishes engineering
behavior only; hosted headroom and billing savings require separate evidence.

See the carried-destination engineering evidence for the complete local and
hosted results. Never respond to another margin loss by dropping cases, extending
caps, adding workers, accepting cached verdicts or blindly rerunning suites.
Re-measure the affected complete partitions before the next allocation change.

## Observed qualification of the allocation

[PR99's exact-head run](https://github.com/caglarsubas/lawyer-assistant-v1/actions/runs/38838401590)
passed all seven jobs at `7ca00e58dbe9dd61f9cc501dec8c8747aad30887`.
Frontend used 243/300 seconds (57 seconds margin), compared with PR98's 297.
Workspace contracts used 33 seconds and human-review contracts 151; frontend
tests used 26 and the build 17. The receiving backend used 1,090/1,200 seconds
(110 seconds margin); its full backend test step used 1,008/1,080 (72 seconds
margin). Tested and merged complete trees matched.

These are individual hosted observations, not universal timing or billing
guarantees. Subsequent feature PRs retain the allocation and require all seven
successful exact-head checks plus at least 30 seconds observed margin in the
frontend job, receiving backend job and its full backend test step. A successful
check with less margin requires investigation before merge; do not raise caps,
drop tests or rerun merely to obtain a better timing sample.

PR100's first run retained 51 seconds frontend margin but its full backend
remainder timed out. The [backend graph partition](CI_BACKEND_GRAPH_PARTITION.md)
supersedes the single-remainder capacity assumption: all seven existing jobs
remain, with one additional six-minute, two-worker job selecting 91 complete
graph cases exactly once. The main remainder becomes 3,816. All eight current
checks and fresh frontend/backend/graph margins are mandatory before merge.
The rejected local dispatch-order experiment is not part of the solution.
