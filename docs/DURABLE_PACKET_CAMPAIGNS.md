# Durable disposable packet campaigns

This isolated accounting candidate supplies persistent admission and reservation
primitives. It has no provider dispatch, inference CLI, application route or
production install. Its recipe is `disposable-durable-packet-campaign-v1`.
The old planner, selector and native declaration remain unchanged. Their legal,
relevance, abstention, capacity and availability limits remain open.

## Trust boundary and frozen rules

A trusted issuer must bind each exact grant UUID, evidence/plan/question hash,
allowance and permitted action to independently acquired immutable evidence and
current matter permissions. The injected action authorizer is not implemented
production access control, a signature or independent human review. A caller hash
is not authority. Fixture always-true authorizers are restricted to invented tests.
Admitting this grant is not native execution permission.

A store is explicitly created once in an owned 0700 nonsymlink directory with a
0600 regular, single-link database. Its identity must be pinned in separate trusted
configuration. Reopen uses SQLite `mode=rw`, never missing-store recreation; changed
identity, corruption, unsafe permissions or an unsupported journal mode fail
closed. SQLite DELETE journaling, FULL synchronous commits, bounded lock waits,
foreign keys and immediate transactions serialize admission, reservation,
revocation and terminal metadata. Parent-directory creation is explicit; the
committed database directory entry is fsynced. This assumes a local filesystem
honoring SQLite locking/fsync, a trusted OS and exclusive custody of the store.
Do not qualify network filesystems with these results.

Preparation rebuilds the existing whole-passage plan from a validated serialized
snapshot, including unused evidence. Grant metadata pins the exact old selector
context, packet wire hashes and costs. Per-request caps remain at most 8192
conservative units, eight passages and 4000 copied bytes; full-plan allowance
bounds remain eight attempts, 65536 units and 32000 bytes. Structural validation
and hashes cannot establish the truth or acquisition rights of a caller's data.

Admission consumes a grant UUID once. It cannot be reissued with the same or a
changed context after reopening. A reservation's costs come from the admitted
manifest and are committed **before** returning. All reserved packets count toward
aggregate cost regardless of outcome. A committed crash leaves an ambiguous,
consumed reservation; never resume, refund or replay it. A denied uncommitted
transaction rolls back before dispatch permission exists. Terminal outcomes are
one-time metadata; successful-result digests are caller assertions, not independent
proof of provider behavior. They cannot replay source text or generated answers.
Revocation survives restart, blocks new reservations and successful terminal
publication, while allowing an authorized failure record to retain consumed cost.

This does not resist malicious host/database administration or rollback to a valid
older store/backup. A different configured store cannot spend the old authority,
but deliberately recreating trusted configuration or issuing a new UUID remains
an issuer action outside this boundary. Before future native use, enforce issuer
one-use intent, external restore fencing/epoch policy, exact current model and
transport identity, and an end-to-end native admission boundary. Never recover a
failed allowance by making a new store, grant or selector session. No production
backup/restore policy or private data is changed in this qualification.

Freeze candidate, six fresh P1701–P1706 cases, evaluator, contracts and these rules
before first evaluation. Keep the first report and any failures. The mock-only
bridge recreates the old in-memory selector per packet, reserves durably first,
checks the exact selector context, then records only a result digest. Its select-all
mock uses nominated IDs, not legal labels. Require exact original copying, exact
aggregate totals after reopen, rejection of duplicate reservations and no source
text/credentials in the database. The bridge is a fixture, not a production or
native inference executor.

Contracts must test exclusive/private store creation, missing/changed/corrupt store,
strict current action authorization and rollback, stale unused evidence, every
aggregate dimension and forged wire/cost, one-use grant IDs, process crashes before
and after a synthetic effect, duplicate/distinct process races, consumed failures,
revocation, terminal metadata, bounded lock failure and unsupported journal mode.
Reproduce the full fixed report and process contracts in read-only Linux with
networking disabled and temporary scratch only. Keep CI topology, caps, workers,
coverage and five timing reserves unchanged. No real network, native model,
private case, production store or review mutation is permitted by this experiment.
The owner's focused-analysis v3 review remains pending.
