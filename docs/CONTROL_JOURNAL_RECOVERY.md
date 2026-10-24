# Staged control-journal recovery and descendant revocation

This unregistered V2 candidate extends the model-only
[sealed-volume handoff](SEALED_VOLUME_HANDOFF.md). It does not replace the V1
default, migrate existing journals, install a provider route, provision real trust,
run inference or modify any private matter. Existing sealed-volume and signed
handoff code remains unchanged; the V2 journal can be supplied explicitly by a
trusted controller. No agent receives SQL, file, restore or schema access.

## Independently retained checkpoint

The journal commits exact operation records, proof versions, event history and
nonce state through a bounded hash chain. A separate append-only anchor records
the journal identity, sequence and chain head. The controller must place that
anchor outside journal/model backups on a separate protected volume. A path in
another directory alone does not establish independent retention.

Every ordinary read validates SQLite integrity, strict journal identity, bounded
records, proof/content identity, history, ancestry and chain/anchor agreement.
Reads use a single database snapshot and shared anchor lock; mutations use an
exclusive bounded lock, an immediate SQLite transaction and FULL synchronization.
Mutations commit the database before fsyncing the next anchor entry. Other guarded
readers cannot observe the intermediate window; after a crash they refuse a gap.
An expired lock wait fails without admitting work. No timers or opaque receipts
turn uncertainty into permission.

This is an operational rollback guard under a trusted controller, **not a hardware
monotonic counter or protection against a privileged rollback of both journal and
anchor**. It does not prove executed model weights or authenticate an issuer.
The real issuer fingerprint/runtime pin still requires independent confirmation.

## Recovery without replay

`Journal.reconcile` is an explicit operator action, separate from read-only history
inspection. SQLite may roll back an interrupted uncommitted transaction. A valid
already aligned journal remains unchanged. If exactly one validated committed
transaction extends the current anchor, recovery retains that transaction and
advances only the anchor. It never replays semantic mutations, nonce reservations,
handoffs, model imports, inference or review decisions.

A database behind its anchor, a foreign journal, a corrupt database, an invalid
history, a malformed/torn anchor or a larger unexplained gap rejects. No missing
file is silently recreated, no damaged tail is truncated, and no orphan is
promoted. A crash after durable nonce reservation preserves the reservation; the
challenge cannot be retried after recovery.

`Journal.backup` creates an exclusive new SQLite snapshot and returns its exact
SHA-256 and checkpoint. It contains no anchor. Restore requires an independently
approved backup hash, expected journal identity, a kernel-read-only source and a
fresh destination. The restored database must match the current external anchor,
including nonce and revocation history. Older backups, wrong hashes/identities and
occupied destinations reject. A refused candidate remains quarantined. Restore
never rewinds or copies the anchor, resets nonces or activates a model. Two copies
using one anchor cannot both advance: the first commit fences out the stale copy.
Control-journal identity is preserved on exact recovery; model-volume restores
still require their own fresh generation as specified by the V1 transfer contract.

## Descendant revocation

Ancestry is acyclic, content-consistent and bounded to 32 nodes. Restore creation,
preparation, sealing, nonce reservation and nonce consumption check ancestors
inside the same guarded transaction. Parents must remain sealed. Revoking a node
marks its entire retained descendant set revoked in one transaction, including
Copying, Prepared and Sealed children. Proofs, generations, evidence identities,
events and used/reserved nonces are preserved. Sibling branches outside the
selected subtree remain unchanged. Repeating revocation is an idempotent no-op.

Revocation racing with descendant creation either blocks creation or includes the
new child. Revocation during local verification prevents sealing; revocation after
nonce reservation prevents the existing signed receiver from completing the
handoff. A completed metadata receipt never grants indefinite future execution.
Future runtime callers must use this guarded API and recheck at their effect
boundary; direct SQL reads and old retained reports are not authorization.

Work bounds are 512 operations and 8,192 events, nonces and commits; SQLite size
is capped at 16 MiB and the anchor at 8 MiB. Exceeding a bound rejects without
truncating history. These finite qualification limits require explicit retention
and capacity policy before a long-lived production deployment.

## Qualification scope

The policy and first candidate were frozen before grading. Thirty-two fresh
synthetic cases cover recovery, hot SQLite rollback journals, partial commits,
old/foreign backups, nonce preservation, cascade/branch isolation, corruption,
ancestry/work bounds and concurrency. Real process exits occur before commit,
after commit before anchoring, and after durable anchoring. A fault-only one-page
SQLite cache forces the hot-journal condition; normal journal settings are unchanged.

The native run uses four new ext4 Docker volumes, two CPUs/768 MiB, no network,
no ports or runtime mounts, a read-only root and cleared process environment.
Only the preparer adds CHOWN and exits before testing. Backup writers exit before
the restore reader mounts their volume read-only. Inputs are invented control
metadata and a 65,561-byte zero-tensor model fixture; this is not another 8 GiB,
five-job, cold-storage or real-inference performance campaign. The existing
20-second verifier budget and all earlier performance evidence remain unchanged.
All owned containers and volumes are removed with ownership checks.

CI receives small contracts and retained-report validation. Runtime integration,
actual issuer/trust confirmation, installed/executed weights, context behavior,
sustained research jobs and legal/production acceptance remain separate gates.
Original documents, exact evidence versions and private review history stay
outside this campaign. Owner focused-analysis v3 review remains pending.
