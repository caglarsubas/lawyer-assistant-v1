# Guarded post-transition destination lifecycle

This unregistered qualification service extends the reviewed namespace broker.
It uses disposable identities and local synthetic inputs. It does not cut over a
production route, enroll provider trust or migrate private matters.

## Separate authorization and immutable history

An independently reviewed maintenance window permits one exact destination
retirement, renewal or rollback. A fourth append-only journal retains its
proposal, independent decision, opening and verified finish. Its scope pins the
existing namespace journal, physical roots and external anchors. Each request
revalidates the original physical namespace bindings before maintenance access.

The legacy history stays byte-for-byte unchanged. Existing destination and
transition records, metadata and admission evidence remain unchanged; their
anchors and histories may only append. No old selection, review or transition is
rewritten or relabeled as a new approval. A rollback creates a fresh reviewed
selection referencing its historical target rather than reopening that target.

Window proposals bind exact starting heads and history digests, the active
transition, current canonical withdrawal context, one typed operation, one fresh
stage/receipt pair and fixed child-proposal and successor-transition identifiers.
The grant lasts at most 300 seconds and is bounded by the preparer's session.
Roles, sessions, review eligibility, source context and exact heads are checked
again when used. The preparer and reviewer must be distinct assigned people.

## Workflow and read fence

1. Prepare a fresh stage using the unchanged original canonical writer.
2. Observe exact metadata, propose the window and obtain independent approval.
3. Open the approved window. All namespace inventory reads are now blocked.
4. Execute the permitted child steps. Renewal/rollback require their own fresh
   independent reader decision and a new selection. Retirement targets only the
   exact current destination selection.
5. For renewal/rollback, prepare, independently review and commit a new namespace
   transition bound to the new destination. The original transition stays in the
   history and cannot authorize the new selection.
6. Explicitly finish against the exact destination head and transition commit.
   Only the newly reviewed namespace can then supply bounded metadata inventory.
   Retirement keeps reads blocked, with no fallback to the legacy namespace.

The old legacy selection is an evidenced historical identity after maintenance,
not a continuing permission. A fresh destination grant and fresh independent
transition decision establish new authority. This permits reviewed renewal after
legacy-grant expiry without extending or reactivating that expired grant.

Typed actions are `change_observe`, `change_prepare`, `change_decide`,
`change_open`, `change_step`, `change_status` and `change_finish`.
`change_step` accepts only the next permitted prepare/decide/select/retire step;
the server constructs the closed child request from the reviewed terms. It
accepts no filesystem path, arbitrary tool name or query. Original writer actions
remain unchanged. Direct legacy/destination delegation stays blocked after the
initial namespace commit.

The separate window lock serializes both the existing broker and new actions
across processes. Child journals retain their own locking, independent review
and exact expected-head checks. Competing openings or selections cannot commit
twice. Inventories retain the original eight-row bound and source checks.

## Observation, uncertainty and remaining gates

Status is metadata-only and never refreshes a grant. Pending, denied, expired or
finished windows do not report a current maintenance grant. Lost opening,
selection and transition replies reconcile from retained records; mutations are
never replayed automatically. Reads stay fenced until explicit verified finish.
Missing admission, damaged history, stale source or a replaced physical namespace
fails closed. This slice does not repair an unanchored maintenance/child journal.
Exact guarded recovery of those journals is the next qualification item.

The accepted native campaign passes **20 scenarios, 40 loopback servers and 975
HTTP requests in 112.84 seconds**. It uses the pinned local image, four fresh separate ext4
volumes, two CPUs, 768 MiB, 96 PIDs, a cleared process environment and no external
network. The frozen matrix covers renewal after expiry, retirement, rollback,
denial, self-review, unopened steps, old decisions, withdrawal, changed stages,
revocation, expiry, lost replies, read-only status, early finish, missing admission
and competing mutations. A copied-namespace regression checks physical identity
before change preparation. A source gate binds all current qualification files
to the native report while retaining all prior namespace-source pins.

Deployment contracts still execute exactly once across seven disjoint
assignments in the same nine jobs. New workflow cases use the existing backend
two-worker reserve. Frontend overlap, worker peaks, deadlines, locked dependencies
and all frontend tests stay unchanged. Merge still requires nine exact-head
checks, five reserves of at least 30 seconds, a pinned-head merge and independently
fetched-main full-tree equality.

Production namespace isolation, genuine operator appointments/key custody,
PostgreSQL/IdP fencing, off-host recovery, signed live provider/context/five-job
qualification and legal acceptance remain separate gates. Owner review of the
private focused analysis remains pending. See the [dated evidence](evidence/destination-change-2026-10-26.json).
