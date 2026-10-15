# Final authorization CI budget recovery

PR94's first run, 38740368706, passed all 21 final-authorization cases in
348.91 seconds, but its job was cancelled after exceeding the six-minute cap.
Runner/service setup and cleanup consume that same job budget. A passing test
step therefore was not a passing check and did not authorize merging.

The retained mixed-assembly case alone took 173.91 seconds and appeared late in
the work-stealing queue. A controlled two-worker Linux/PostgreSQL comparison
measured 152.91 seconds for the original complete group and 146.32 seconds with
that long case first. Reordering alone provided insufficient margin.

The activation/rollback case, measured at 67.12 seconds plus setup in the hosted
run, now lives in `test_final_release_transitions.py` and runs first in the
existing graph-candidate job. Its test body and every assertion are unchanged.
Fixtures still perform the actual signed preparation, installation, activation,
rollback and revoked-target checks; no validation verdict is cached or skipped.

The final job retains its other 20 cases, starting retained assembly first. The
candidate job runs its existing 14 cases plus the moved transition case. The
complete backend selection remains 4,521 cases with no overlaps or omissions;
only that case's module-qualified ID changes. A comparison with the prior
collection and an exact test-body hash establish the mapping.

Seven jobs, two workers, original six-/three-minute job caps, all step deadlines,
worker restart limits and no-retry behavior remain unchanged. No cases are added
to the constrained PostgreSQL or final jobs. There is no new dependency, runner,
service, production-code change, disabled guard or automatic retry.

Qualification uses the unchanged application image with current tests mounted
read-only, two CPU shares, two pytest workers and an owned isolated PostgreSQL
network/database. Both affected complete groups must pass, with all cases and no
skips, before publication. Local timing is engineering evidence; it does not
establish hosted runner time, billing savings or universal timing guarantees.
The corrected commit requires all seven fresh exact-head checks before merge.

The initial run is retained as cancelled, not reclassified as successful. A CLI
cancellation request was denied with HTTP 403; that credential restriction was
not bypassed. Existing workflow concurrency can supersede obsolete runs on a new
commit. No automatic retry was introduced.

See [engineering evidence](evidence/arrival-event-handoff-2026-10-15.json).
