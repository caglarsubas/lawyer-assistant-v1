# Backend graph partition and deadline margin

PR100's first run at `b18efa319c09734fce19842736b22ed49a9bdeae`
[timed out](https://github.com/caglarsubas/lawyer-assistant-v1/actions/runs/38841989198)
in the unchanged eighteen-minute backend step. Timing reports recorded 3,900
completed cases out of 3,907 before cancellation. Frontend passed with 51 seconds
margin. The prior backend margin was insufficient; no assertion failure was
reported before timeout, and that run did not authorize merging.

The full workload is too close to one lane's deadline. An expensive-first
dispatch experiment was assessed locally and rejected under its constrained
working-set budget. Its scheduling plugin was not retained; all existing test
bodies, fixtures, assertions, workers and `worksteal` scheduling remain unchanged.

## Complete, disjoint selections

`graph-runtime-contracts` runs four complete files, totalling 91 cases:

- `test_declared_graph_assembly.py`
- `test_graph_b_component_grants.py`
- `test_release_set_authorization.py`
- `test_open_validity_publication.py`

One central `CI_GRAPH_RUNTIME_TESTS` list drives both their inclusion and their
exclusion from the main remainder. That remainder now has 3,816 cases. All
other selections are unchanged. Independent complete collection retains the
4,521-case identity hash
`b167d772d1b670bc19d2ecd002bb48d4f58a07075b38baef12dd41d9aabc1616`
with no missing, duplicate or extra IDs.

The seven existing jobs keep their names, architectures, step/job deadlines,
worker limits and PostgreSQL durability/race behavior. The additional native ARM
job has a six-minute hard limit and exactly two workers with no worker restart
or retry. The existing twenty-minute backend job and eighteen-minute test step
are not extended. PostgreSQL's full 95-case selection remains unchanged.

This adds a bounded setup lane, not duplicate test execution. It addresses a
saturated lane rather than moving the problem into existing three-minute jobs.
Aggregate hosted time and billing require fresh observation; no universal cost
reduction is claimed.

## Qualification and merge

Qualify both complete affected partitions in isolated offline Linux containers,
with current tests mounted read-only and application sources independently
matched to the test image. Use real assertions and unchanged fixture logic.
Independent deployment contracts reject overlapping explicit groups, a group
missing from the remainder's exclusions, and accidental job-cap escalation.

Require all eight checks on the exact submitted head. At least thirty seconds
observed margin must remain in frontend, main backend job, its full test step
and the new graph job before ordinary merge. Re-check the current base and
compare complete tested/merged trees. Never infer main CI, deployment, billing,
legal qualification or lawyer acceptance from a passing PR run.

The complete local main remainder passed with 3,719 passed and 97
environment-dependent skips (3,816 collected) in 628.08 pytest seconds;
container wall time was 629.67 seconds. All 91 graph cases passed in 290.14
pytest seconds (291.67 wall). Both used two CPU shares, two workers, 1,536 MiB
memory and read-only current tests. These observations are engineering evidence;
they do not prove hosted timing or a billing reduction. Fresh exact-head results
remain the merge gate. See [feature evidence](evidence/carried-destination-event-handoff-2026-10-16.json).

The destination-arrival frontend-headroom prerequisite subsequently adds the
complete 31-case Graph B publication file to this existing job. Graph runtime is
122 cases, frontend human review 76, and the main remainder stays 3,816. All eight
job configurations and deadlines remain unchanged. See the
[current allocation and qualification](CI_FRONTEND_HEADROOM.md).

The arrival-preserving handoff subsequently co-locates the complete 17-case Graph B
snapshot file with publication in this existing job. Graph runtime becomes 139
cases, frontend human review 59, and the main remainder stays 3,816. All eight job
configurations and limits remain; complete affected groups require fresh local
qualification and all exact-head hosted margin gates still apply.
