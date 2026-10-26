# Guarded journal recovery and finish reconciliation

This unregistered service extends destination maintenance with explicit repair of
an already-retained, independently admitted record. It uses disposable identities
and synthetic inputs; it does not migrate private cases or activate a provider.

## Exact retained evidence

`recovery_observe` returns a bounded metadata view of the maintenance and
destination heads/tips, namespace and legacy heads, current canonical withdrawal
context, retained-history digests, physical scope, current actor and exact change.
The view distinguishes a finish record pending its anchor from anchored finish.

`recovery_apply` requires that exact view hash and an explicit `window` or
`destination` target. The caller must be currently assigned to the same profile
and be one of the reviewed window's people. Authorization precedes storage access;
physical namespace identities and all history/admission chains are revalidated.
Observation is bound to the actor/session and cannot be borrowed by another one.

The service locks maintenance, namespace, legacy, destination and canonical
controls in a consistent order. An admitted tail may be at most one record ahead
of its external anchor. Repair appends only its existing exact frame to that
anchor. It never rewrites a record, recreates admission, refreshes a stage, repeats
a mutation, or creates another review/selection/transition. Unknown targets,
extra fields, stale views, changed physical namespaces and a current clock behind
any retained history fail before repair. Two simultaneously pending journals are
reported but cannot be repaired implicitly as a joint operation.

All four histories, metadata and admission evidence remain byte-for-byte intact.
Only the selected external anchor gains one frame. A fully anchored target is a
read-only no-op. A lost repair reply reconciles from the next exact observation;
reusing the pre-repair view cannot append a second frame.

## Authority and finish status

Recovery is metadata repair, not authorization renewal. Expired grants, revoked
reviewers and a subsequent canonical withdrawal remain effective. A historical
withdrawal head must still belong to the verified canonical ancestry. The current
source context is pinned separately and a mismatch remains visible. Existing
inventory checks still require current source, actors, review and exact versions.

An unanchored opening continues to fence inventory until it is explicitly
repaired; finishing the reviewed workflow is still required afterward. A child
selection repair cannot bypass fresh transition review or explicit finish. An
unanchored finish blocks ordinary reads until its admitted frame is repaired.
Anchored finish with a lost reply is observed without calling finish again.

`finish_observe` takes the exact view and finish-record pins and reports metadata
without mutation. It never declares access authorized; `authority_renewed` and
all activation flags stay false. The original writer and legacy-read fence stay
unchanged, including the old cursor and historical-review boundaries.

## Qualification and remaining work

The accepted native campaign passes **16 scenarios, 32 loopback servers and
889 HTTP requests in 90.03 seconds**. The frozen campaign covers opening/selection/finish repair, lost finish and
repair replies, missing admission, stale/borrowed views, expiry, withdrawal,
revocation, copied roots, wrong changes, competing repairs, joint-pending refusal,
clock rollback, read-only finish and old cursors. Native workers share only
disposable identity and control stores, with actual session/RBAC/origin/CSRF
checks on loopback HTTP. Resources remain two CPUs, 768 MiB, 96 PIDs, four fresh
ext4 volumes and no external network, within the existing 180-second cap.

All prior destination-maintenance source pins are retained. Source/report gates
bind the new runtime, adapters, fixtures, policy and tests to the exact native
campaign. Complete deployment discovery remains disjoint across the same seven
assignments and nine CI jobs. New cases share existing backend and graph-runtime
reserves; no frontend case, worker peak or deadline changes. Merge requires nine
exact-head checks, five reserves of at least 30 seconds, a pinned-head merge and
independently fetched-main tree equality.

Joint recovery, off-host/rollback-resistant custody, production PostgreSQL/IdP,
genuine operator appointments, live provider qualification and legal acceptance
remain separate gates. Owner review of the private analysis stays pending.
