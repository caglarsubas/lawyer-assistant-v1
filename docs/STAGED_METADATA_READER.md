# Independently selected staged metadata reader

This unregistered qualification adapter selects a staged withdrawal-history journal for bounded metadata reads. It accepts only marked disposable SQLite identities. It does not register a production route, enroll trust, install a runtime, run inference, review a legal case or activate a provider.

The canonical source remains the writer and the withdrawal authority. Ordinary actions continue through the unchanged original service. A staged reader cannot clear a withdrawal, restore an old authority, update its source snapshot or choose a fallback automatically.

## Exact subject and independent decision

The assigned preparer submits an exact stage ID and the original intent/receipt hashes. The service checks the encrypted backup manifest, exact source journal/event bytes, current independent anchor and admission intents, physical staged-journal identity and current source context. The stage's preparer session must still be the same current session. Its subject records the stage, journal, snapshot, context, current withdrawal head and physical namespace hashes.

A separate current assigned reviewer must approve the exact proposal. Approval pins the reviewer session and role snapshot. The original preparer can then select it once. Proposal lifetime is at most 300 seconds, also bounded by the preparer session. Both sessions, role snapshots and the source subject remain current at decision, selection and every read. Actor authorization precedes inspection of reader-control storage.

Reader controls use a separate bounded, append-only log with an independent external anchor and admission intents. The scope pins the original withdrawal journal, staging catalog and reader-control namespaces. Prepared, approved/denied and selected events remain retained. Changed clocks, identities, evidence, role snapshots, namespaces or missing independent controls fail closed.

## Read and history behavior

Typed actions under the existing qualification-only operator prefix are:

| Action | Purpose |
|---|---|
| `reader_observe` | Observe current reader/source heads and context; no activation |
| `reader_prepare` | Propose an exact staged subject |
| `reader_decide` | Record an independent approve/deny decision |
| `reader_select` | Select an approved proposal once |
| `reader_inventory` | Read at most eight metadata rows against the current canonical fence |
| `reader_status` | Observe then pin exact retained decision/selection hashes |
| `reader_recover` | Observe an admitted unanchored tail, then explicitly repair its exact head/tip |

Inputs have closed field sets, validated IDs and hashes, exact expected heads/context and bounded pagination. No client supplies a filesystem path. Source locks and before/after checks prevent returning a page when its context changes during assembly. A read already returned cannot be recalled; subsequent reads must pass the fresh fence.

Pagination binds the source basis, selected binding, reader-log head and actor. Cursors cannot cross selections or reader-log changes. A newer independently approved selection supersedes the old one; old decisions remain observable as history. Status inspection neither changes a record nor renews its authority. Lost acknowledgements use observation and exact pins, without replay. A retained but unanchored selection remains unavailable until explicit pinned recovery; missing admission evidence cannot be manufactured by recovery.

Canonical withdrawal immediately stales the old staged reader. A fresh backup, new stage and new independent review can expose current withdrawal metadata. They cannot reactivate the ordinary withdrawn reader. Expiry or any other stale source context similarly requires a fresh workflow.

## Qualification and remaining boundaries

The frozen campaign passes 20 cases through 40 actual loopback server processes and 434 HTTP requests in 93.96 seconds, within the unchanged 180-second budget. It uses two CPUs, 768 MiB, a 96-PID limit, four separate fresh ext4 mounts, read-only model/package storage, cleared process environments and no external networking. The real app's cookie/session, RBAC, origin and CSRF checks are exercised using invented accounts. All newly owned containers and volumes are removed.

Cases cover self-review and denied selection, wrong pins, source/role changes, expiry, replay/races, lost replies, explicit anchor recovery, tampering, canonical withdrawal, superseded selections, cross-selection cursors, session revocation, unassigned/CSRF denial, missing admission evidence and fresh post-withdrawal review. A separate contract checks authorization before damaged storage inspection. Frozen report checks reject altered outcomes, counts, authority flags and resource profiles. No personal case or real account is used.

The private launcher's display-only summary incorrectly printed 26 cases; its frozen policy, actual assertions, retained report and grader all require and verify 20. That original receipt remains retained; no report or case was rewritten to fit the label.

The 22 new reader methods and 49 retained authenticated-review methods form a complete third manifest shard in the existing backend job, sequentially before pytest. The single production build uses the existing final-authorization job's measured reserve. The original two frontend lanes retain their one Vitest plus one contract worker. Nine jobs, current concurrent-worker budgets, all test membership and existing deadlines remain. A first CI profile passed its checks but left only 20 seconds of history-lane reserve and is rejected. Complete groups move between existing jobs using the measured timings; no cases or expectations change. Merge requires all exact-head checks, the five timing reserves, a pinned-head merge and independently fetched-main tree equality.

Production IdP/PostgreSQL fencing, actual appointments and key custody, privileged joint rollback/key loss, off-host recovery, native provider/context/five-job qualification and legal acceptance remain open. The next reader slice is explicit retirement and independently reviewed rollback/renewal; no automatic reactivation is authorized. Owner review of focused private analysis version 3 remains pending.
