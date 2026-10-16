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

## Destination-arrival prerequisite

[PR100's corrected run](https://github.com/caglarsubas/lawyer-assistant-v1/actions/runs/38846573245)
passed all eight checks. Frontend used 262/300 seconds: npm tests 54, build 16,
workspace 32 and human review 148. Its 38-second margin leaves only eight seconds
above the merge floor. Backend used 887/1,200, its test step 805/1,080 and the new
graph job 247/360. These are observations, not universal timing or billing claims.

Before implementing destination-arrival return, the complete 31-case
`test_graph_b_publication.py` file moves from the frontend's human-review group
to the existing native ARM graph group. The frontend retains x86 permission,
private human-review and Graph B snapshot coverage. The graph group already
exercises signed snapshots and publication through its component/assembly work.

Human review becomes 76 cases and graph runtime 122; all other allocations stay.
Independent full collection preserves all 4,521 node IDs and their original hash
without gaps or overlaps. All eight parsed job configurations, workers, caps,
architectures, triggers, permissions, concurrency and PostgreSQL settings remain
identical. No test body, fixture, assertion, scheduler or verdict cache changes.

Both complete affected groups pass the constrained local qualification: review 76
in 106.83 wall seconds and graph 122 in 212.03. These measurements precede feature
implementation and do not establish hosted headroom or billing savings. Require
all eight exact-head successes and at least thirty seconds observed margin in
frontend, main backend job/test step and graph job before merge. Carry measured
hosted results into the next feature's documentation, avoiding a separate run
solely to update timing text.


## Arrival-preserving handoff capacity

[PR101's exact-head run](https://github.com/caglarsubas/lawyer-assistant-v1/actions/runs/38850758358)
passed all eight checks: frontend 207/300 seconds (93 seconds margin), backend
939/1,200 (261), backend test step 850/1,080 (230), graph runtime 258/360 (102).
Merged-main run 38852168039 separately passed; frontend used 202 seconds, backend
835 and graph 262. These are measured observations, not universal timing guarantees.

The next handoff leaves the entire workflow and backend test partition unchanged.
Its initial 68-case local measurement exposed redundant ancestor validation and
repeated predecessor construction. New checks retain the unchanged complete
history validator, validate fresh identities once, and compare every one of the
14 retained observations. Exact stable preparation equality preserves all checked
fields while separate clocks remain guarded. No cross-call verdict cache is used.
New tests clone their baseline independently; existing tests/fixtures are unchanged.
The same 68 cases then passed in 23.64 rather than 101.97 seconds. Six additional
preparation-forgery cases are included in the full 1,527-case pass.

Require fresh all-eight-check success and the same >=30-second measured margin
for frontend, backend job/test step and graph runtime before ordinary exact-head
merge. Record actual hosted timing in the PR body and next feature documentation;
do not start another Actions run solely to amend timing prose.
