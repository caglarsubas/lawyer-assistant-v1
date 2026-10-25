# Disposable lifecycle inventory and enrollment withdrawal

This unregistered wrapper extends [restore lifecycle controls](RESTORE_LIFECYCLE.md).
It accepts only the existing marked disposable profiles and actual local app
session/RBAC/origin/CSRF checks. Real accounts, keys, private cases, inference and
production activation remain outside this qualification.

Inventory exposes only opaque enrollment/version IDs, evidenced parent links,
enrollment validity/integrity status, control-head hashes and retained-record
counts. It returns no document text, evidence passages, key contents, cookies or
passwords. These metadata remain confidential to assigned operators. Responses
are `no-store`; this is not a public corpus endpoint or a legal approval.

The catalog stays server-configured and capped at eight enrollments. A page has
one to eight rows. Snapshot identity binds the catalog, lifecycle/control versions,
withdrawal state and enrollment integrity. Continuation tokens also bind the
authenticated session, role version, limit and offset. Each page reads current
state and rechecks it before replying. Changed state, actor or tokens reject the
continuation; callers explicitly observe a fresh snapshot. Cursors are pagination
state, never permissions or restore grants. Inventory performs no repair or write.

An exact observed subject precedes a preparer proposal and independent reviewer
decision to withdraw an enrollment. The subject binds the lifecycle head, control
and inventory basis, target enrollment and its evidenced descendants. Proposals
expire within 300 seconds; current actor/session/role evidence is checked before
and after retention. Wrong pins, self-approval, stale state, changed roles, replay
and competing decisions fail closed. Denial retains the proposal/decision while
leaving legitimate authority available.

An approved withdrawal blocks the target and its approved renewal descendants.
Every ordinary wrapped route checks this state before delegation, including
previously prepared renewal decisions. A withdrawn candidate cannot be activated;
a withdrawn current lineage cannot renew itself back into service. Unrelated
eligible enrollments retain their authority. There is no automatic fallback to
another enrollment and no reactivation route.

The outer withdrawal fence excludes withdrawal writers while admitted wrapped
actions finish; the inner lifecycle keeps its own exact-head checks and locking.
Management snapshots take locks in withdrawal → lifecycle → restore-control order.
The wrapper releases the inner snapshot lock before invoking the inner handler,
avoiding reentrant file-lock acquisition. All exposed instances use the wrapper;
there is no separate unfenced legacy listener. The withdrawal journal retains
independent admission intents and the existing 256-event bound.

Lost acknowledgements require fresh observation and exact decision pinning, never
replay. An admitted unanchored withdrawal blocks ordinary access until an assigned
operator explicitly observes and pins the head/tip for recovery. Observation reports
only the anchored withdrawal count. Recovery retains the original decision; it
does not refresh its timestamp or restore authority. An inner lifecycle rollback
that removes an approved withdrawal's evidenced head is rejected. Privileged joint
rollback of independent state remains a separate unqualified threat.

Read-only inventory and exact decision status remain available after withdrawal,
enrollment expiry or loss of key integrity, while the identity/assignment and
control evidence remain intact. Unknown key integrity is reported as unavailable,
not usable. Withdrawal may still be approved against that exact observation.
It destroys no key, decrypts no backup, rewrites no original review, and changes no
target or evidence bytes. The corrupted-key test is an explicit external fault;
the service never repairs or replaces the key. Source/identity/control corruption
can still block management and requires separately qualified recovery.

The frozen native campaign uses a three-enrollment catalog, two actual server
processes per case, real loopback HTTP and the retained app authentication code.
Four separate ext4 mounts isolate readonly model/package storage, work, independent
keys/controls and encrypted backups under two CPUs/768 MiB with external networking
disabled. Unit checks are separate from native durability/process evidence.

CI retains nine jobs, both existing test-worker budgets, x86 frontend coverage and
all deadlines. The new sequential inventory campaign is explicitly assigned to
the existing ARM contract lane, whose prior contract work was below its frontend
critical path. The committed complete test-ID manifest and executed-ID checks
prevent omission or duplication on either architecture. No new runner, retry,
longer timeout or reduced frontend isolation is introduced.

Next qualify withdrawal-journal backup/restore and revocation-fence reconciliation
with disposable identities. Genuine operator appointments, production IdP/PostgreSQL
fencing, physical/off-host custody and joint-rollback/key-loss recovery, real native
provider/context/five-job qualification and the owner's focused-analysis v3 review
remain pending.
