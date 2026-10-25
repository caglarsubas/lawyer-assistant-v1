# Disposable restore-target retirement and enrollment renewal

This unregistered service wraps the [restore authorization path](RESTORE_AUTHORIZATION.md)
using marked disposable identities and actual app session/RBAC/origin/CSRF checks.
It provides metadata controls, not production activation, deletion or encryption-key
rotation. Original documents and private cases are never inputs to qualification.

All requests bind the current enrollment digest and lifecycle head. A bounded,
server-configured catalog supplies two to eight exact custody enrollments and their
separate restore-control journals; HTTP cannot provide filesystem paths, keys or
new catalog entries. Every instance reads the shared lifecycle fence before each
action. Lock order is lifecycle → restore controls → review anchor, including all
delegated restore actions. No instance can retain a stale in-memory enrollment.

Retirement first observes and pins the exact target generation, operation, current
restore-control head, protected target directory identity and original intent and
receipt hashes. Metadata is checked against the consumed restore request and
independent backup manifest. This does not endorse the target's legal content or
claim a fresh full-history validation. A current preparer proposes retirement;
the assigned independent reviewer approves or denies those exact versions.
Changed evidence, pins, actors or context reject the proposal. Retiring a target
after its restore grant or enrollment expires still requires a fresh current
review; an expired retirement proposal cannot be reused.

Approval creates a permanent metadata tombstone. The wrapper then rejects serving,
selection and restore-status actions for that target. No original or restored
bytes, backup, review decision, key or independent anchor are deleted or rewritten.
An exact-decision-bound metadata status remains readable, including after a later
enrollment renewal. Retirement follows the physical target namespace and operation
across every configured enrollment generation. A renewed enrollment cannot
reintroduce a retired target ID; a different new ID can still pass fresh restore
authorization and selection. Declined proposals leave valid selections available.

Renewal independently observes and pins a preconfigured successor enrollment. The
key ID, key fingerprint, file device/inode/owner, purpose and identity scope must
match; the successor must be current, extend expiry and have at most 24 hours of
enrollment validity. Its restore-control journal must be empty. Original enrollment
integrity may be checked historically when expired, but that never restores its
validity or permits old restore grants to execute. The source packet, current
review head and both restore-control versions are bound to the proposal.

Only a fresh independent decision can supersede the current enrollment. The new
context starts with an empty restore-control journal. Prior grants, decisions and
selections remain in their original journals and cannot be served under the old
context. A new restore needs a fresh preparer request, independent authorization,
one-time consumption and exact target selection. Existing encrypted backups remain
usable with their original key and manifest; renewal copies no approval and changes
no key bytes. Real key rotation, escrow, HSM custody and key-loss recovery remain
separate work.

Lifecycle proposals expire within 300 seconds. Canonical append-only events and
independent admission intents retain the original actors, versions and outcomes,
within the existing 256-event bound. Replay and concurrent decisions fail closed.
After a lost reply, another instance observes retained state without replaying the
action. One admitted unanchored event requires explicit observed head/tip pins to
repair. Until then, ordinary actions are blocked and observation reports the last
anchored enrollment. Repair does not renew approval or automatically restore a
target. Missing intents, stale context and tampering are rejected.

Native qualification uses two server processes per invented case, actual loopback
HTTP and four separately mounted ext4 volumes under two CPUs/768 MiB with external
network disabled. Model/package storage is readonly; independent keys/controls and
encrypted bundles are separated from working state. Unit/ASGI checks are separate
from this process/storage evidence. No real account, case, provider request, model
execution, trust enrollment or live activation is involved.

CI keeps nine jobs and the original deadlines. The single build runs on the ARM
history lane; x86 frontend test coverage remains. Each existing frontend lane now
uses one Vitest worker and one sequential deployment-test shard, within its prior
two-worker budget. A committed complete test-ID manifest must match discovery on
both architectures. Hash assignment partitions that manifest disjointly; the
runner verifies the exact executed IDs and count before passing. Missing, duplicate
or changed discovery cannot silently reduce coverage. All existing test methods,
frontend file isolation, failure propagation, process-group cleanup and bounded
unit scratch remain; native durability is qualified separately on ext4.

Next: read-only lifecycle inventory and explicit enrollment-revocation rehearsal
with disposable identities. Production operator appointments, IdP/PostgreSQL
fencing, independent physical/off-host custody/recovery, privileged joint rollback,
provider/native load qualification and the owner's focused-analysis v3 review
remain open.
