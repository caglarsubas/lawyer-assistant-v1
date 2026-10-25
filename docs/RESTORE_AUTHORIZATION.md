# Disposable restore authorization and target selection

This unregistered qualification service extends the staged [history vault](REVIEW_HISTORY_BACKUP.md).
It accepts only marked disposable identities, the existing app cookie/CSRF checks
and current managed roles. It does not connect to production accounts, activate a
restored service, provision real trust, install a model or change legal reviews.

The preparer selects an exact encrypted backup and independent manifest, current
review anchor, packet/observation versions and a new opaque operation identifier.
The server binds these to the configured restore directory's device/inode/owner,
the source journal identity and a separately pinned custody enrollment. HTTP
requests cannot supply filesystem paths, keys or arbitrary target configurations.

Custody enrollment pins the dummy backup key's fingerprint and file identity,
purpose, scope and validity interval. Both key and enrollment must remain protected
owner-only files. The approved enrollment digest is trusted configuration outside
HTTP. Key bytes, cookies, CSRF values and passwords never enter responses or review
records. This is file-based disposable custody qualification, not production HSM,
escrow, key rotation or a claim of resilience to privileged joint rollback.

An independently authenticated, assigned reviewer approves or denies the exact
prepared request. The 300-second maximum grant preserves both actor/role snapshots
and the exact backup/context. Revocation, expiry, changed roles/sessions, key bytes
or inode, enrollment, source head or destination identity fail closed. A denied
grant cannot execute. The inherited direct restore route is blocked.

Execution uses the original preparer's session and exact authorization hash. It
durably consumes the grant before materialization, holding the cross-process
control fence through the bounded new-stage-only restore. All paths take the
control lock before the review anchor. No source ledger, decision, backup,
independent anchor or commit intent is overwritten. Replay cannot execute again,
including after an uncertain reply. A new attempt requires a fresh operation and
fresh independent authorization.

The restore control journal retains canonical hash-chained events and independent
admission intents, capped at 256 events. Exactly one admitted unanchored event can
be observed and repaired by a current assigned operator using both observed pins.
This repair retains consumption; it never renews an expired/revoked grant, reruns
the restore or invents approval. Missing intents, deeper rollback and tampering
are rejected. Read-only reconciliation reports absent, incomplete or exact restored
history. It cannot resume interrupted materialization.

Selecting a restored target is a separate reviewer action bound to the exact
restore intent and receipt hashes. The server validates the entire restored
projection against the independent current review anchor. Only the latest explicit
selection in this control scope can serve bounded, exact-ID/hash historical reads.
Old selections, original decisions and expired/stale review status remain retained.
Selection grants no live route or runtime activation and does not renew the
historical review. No document or case content is returned by these metadata tools.

Qualification uses two distinct server processes per invented case, actual loopback
HTTP and actual app session/RBAC code. Readonly zero-tensor model/package storage,
working state, independent keys/manifests/anchors and encrypted backup bundles use
four separate ext4 mounts in a network-disabled container. Unit/ASGI tests remain
separate from this native storage/process evidence. All existing package modules,
CI jobs, worker budgets, test discovery and timeout caps remain unchanged.

Next: bounded restore-target retirement and key-enrollment renewal with explicit
supersession and fresh authorization; production IdP/PostgreSQL fencing, genuine
operator appointments and independent key custody, physical/off-host recovery and
privileged joint rollback still need separate qualification. The owner's focused
analysis v3 review remains pending.
