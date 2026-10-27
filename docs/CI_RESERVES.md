# CI reserve qualification

The preceding release passed all checks, but candidate and withdrawal jobs had
only 20 and 3 seconds of reserve in its PR run. Its main run was also successful.
Deployment work shared short job deadlines with expensive legal-graph tests.

Move the complete deployment assignments 5, 6 and 7 into the existing backend job
before pytest. Their one-minute step caps remain. Each runs sequentially using
the backend's existing two-worker upper bound. The candidate, withdrawal and
PostgreSQL jobs retain all their pytest files and original deadlines. No job,
retry, extra peak worker, test omission or fixture change is introduced.

The seven assignment counts remain **408 / 435 / 106 / 23 / 9 / 26 / 11**. Pairs
serve assignments 1, 3, 4, 5, 6 and 7; history assignment 2 keeps one contract
worker alongside one Vitest worker. Validate exact source-manifest receipts,
unique executed IDs, per-worker coverage and parent aggregation. A process exit
alone cannot attest complete work.

All ten exact-head checks and every job's 30-second reserve, including the
backend test-step reserve, are required before merge. Existing job and step
deadlines remain unchanged. Compare runner seconds and the critical job against
the preceding main run; this is a timing proxy, not measured invoiced cost.

Original documents, exact evidence versions, credentials, sessions, review
history and existing runtime configuration must remain exact. No runtime
service is restarted and no case or provider inference is requested. All 103
qualified native source pins and 96 prior dependencies remain unchanged.

## Next recovery qualification boundary

Prepare a bounded, read-only operator inventory over explicitly authorized
change IDs using the existing `joint_observe` and `joint_finish_observe` paths.
Do not enumerate directories, expose file paths or private content, call
`joint_apply`, enroll real identities or activate product routes. Bind returned
metadata to actor, context and exact history/plan/view identifiers. Preserve
partial, revoked, withdrawn and stale observations explicitly; multiple reads
must not be described as an atomic cross-context snapshot.

Fresh disposable tests must cover unrelated identities, missing contexts,
changed heads between reads, pending anchors, retired readers, rollback
successors, revoked review and source withdrawal. Compare all retained histories
and originals byte-for-byte before/after. This is the next planned engineering
slice; legal review and genuine operator/key-custody approval remain separate.
