# Disposable withdrawal-history backup and fence reconciliation

This unregistered archive wrapper uses the retained disposable session/RBAC,
origin/CSRF, marked SQLite profile and current operator assignments. No real
account, case document, provider request, production binding or native inference
is included. The existing serving wrapper and its default remain unchanged.

An assigned preparer can observe the exact current withdrawal/lifecycle/control
snapshot, encrypt its bounded journal metadata and original event bytes, and
retain an independently pinned manifest. The envelope binds the journal identity,
scope, current independent head, complete source context and ciphertext/plaintext
hashes. The original enrolled key's content and physical namespace are checked;
the archive neither generates nor replaces a key. Payloads are bounded to 4 MiB
plaintext/8 MiB ciphertext and 64 retained backups/stages. Keys, accounts, original
case documents, external anchors and admission intents never enter the bundle.

Restore is exclusively into a new staging directory. It validates the exact
manifest, current source bytes and external fence before writing original journal
files; the restored log is then scanned against the original independent anchor
and admission intents. Directory/file writes are synced. Existing attempts cannot
be overwritten or retried under the same ID. Incomplete attempts remain retained;
an interrupted backup requires a fresh ID. No restore grant, runtime binding,
selection, trust confirmation or activation is created by staging.

After staging, an assigned reviewer first observes the exact retained intent and
receipt pins, then requests a read-only comparison. The reviewer must be distinct
from the preparer, and both current identity/session/role evidence and source
context are rechecked. A successful comparison confirms byte-for-byte history and
the current fence; it is not a persisted legal decision, new restore authorization
or renewed approval. Missing receipts report incomplete stages. Lost replies can
be reconciled without replay, timestamps being refreshed or authority reopening.

Every operation holds the shared withdrawal fence, excluding withdrawal writers.
Snapshots additionally bind current lifecycle and restore-control heads; changes
make cached observations stale. Context is rechecked before/after retention, so
concurrent lifecycle changes can leave an incomplete or stale stage, never usable
authority. The original wrapper continues to block withdrawn lineages and pending
renewals. Missing/torn/advanced external controls, an old snapshot, changed source,
tampered staged files, replaced keys and clock rollback fail closed. Neither
staging nor reconciliation rewinds independent state or silently selects a reader.

Qualification uses frozen invented cases, two actual server processes per case,
real loopback HTTP and the unchanged application authentication code. Four separate
ext4 mounts isolate readonly model/package storage, work, external keys/controls
and encrypted backups. A fixture regression requires distinct per-case namespaces
when all cases use one backup mount. Unit scratch remains separate from native
process/durability evidence. The first failed native campaign remains retained;
its per-case archive namespace is corrected in a fresh candidate. That next
campaign passes 25/26 outcomes but exposes immediate ext4 inode recycling in the
replacement-fault setup. The next fixture holds the original inode open until the
replacement exists and asserts that the pinned namespace actually changed.
Policy, expected outcomes, service implementation and prior sources remain exact.
The local inode/hash custody profile does not attest filesystem inode generations
after privileged destruction/reuse or joint rollback; physical custody remains open.
Two further full profiles exceed the unchanged 180-second controller budget and
remain rejected. The controller retains partial output and per-case progress.
The next candidate starts the two independent workers together, within the same
two-process/two-CPU/768-MiB budget, rather than serializing their initialization.
No case, expected outcome, service guard or timeout is removed or extended.

The development tracker now always shows done/open/blocked-waiting/deferred
before/current counts, deltas and percentages. Pending heads retain the preceding
verified delivery as the baseline. Added/removed IDs and individual status
transitions remain visible even with zero net change. Open combines in-progress
and planned work; blocked/waiting is the existing waiting category. All 93 items,
including deferred items, stay in the denominator. These are item shares, not
effort-weighted progress or legal/release acceptance. See [tracker assets](tracker/README.md).

Next qualify explicit, independently authorized staged-reader binding and
withdrawal-fence cutover using disposable identities. Genuine operator/custody
appointments, production IdP/PostgreSQL revocation fencing, physical/off-host and
privileged joint-rollback/key-loss recovery, actual native provider/context/five-job
load and the owner's focused-analysis v3 legal review remain open.
