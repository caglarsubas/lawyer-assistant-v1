# Anchored decision recovery and fresh re-review

This unregistered disposable service extends the authenticated operator handoff.
It accepts only the existing marked, empty SQLite identity profile. Current app
cookie/session, managed-role, origin/CSRF and firm guards remain mandatory.
It provides metadata review history, not trust enrollment, deployment, execution
or legal approval. Distinct subjects do not establish distinct human reviewers.

## Retention and recovery boundary

The bounded SQLite journal retains exact original handoff/decision bytes, their
source/context and authenticated actor evidence, and explicit parent links. Its
hash chain covers every record and link. Each frame also requires an exclusive,
durable commit-intent file outside journal backups, followed by an independently
retained anchor. These trusted locations are fixed by server configuration.
The portable fourteen-module provider package is unchanged.

Commit order is: validate current evidence/actors; retain independent intent;
commit journal with full durability; append/fsync anchor; project exact immutable
record bytes into the private ledger. Losing a response never authorizes replay.
Ordinary requests reject an unanchored suffix, missing projection, corruption or
rollback. A database-only forged suffix lacks its independently admitted intent.
At most one verified committed frame may await anchor reconciliation. Deeper
divergence, unknown files, changed existing records, wrong identity scope, unsafe
file posture or a database older than the retained anchor fail closed.

`POST .../operator-review/recover` accepts only `expected` and `repair`:

1. `expected: null, repair: false` observes hashes/counts without mutation.
2. Explicitly submit both observed `anchor_head_sha256` and
   `journal_tip_sha256`, with `repair: true`, using a current assigned session.
3. After fresh checks, the service may advance only the verified pending frame
   and recreate missing projections from the exact retained bytes. It never
   overwrites an existing projection or creates a review from an uncommitted
   intent. Interrupted repairs can be observed and pinned again.

Returned heads and missing counts describe the pinned pre-repair observation.
Read them again after recovery when a new current observation is needed. A
recovered decision retains its original timestamp, reason, actors, versions and
staleness. Inspecting it performs the normal current-context checks; recovery
never renews its approval. All authority flags stay false.

The journal is capped at 128 records, 16 parent links per path and 256 independent
intents. Existing body/header/time/model-verification limits remain unchanged.
No request may select a path, identity store, firm, actor or provider credential.
The actual firm guard remains held through response release and cancellation.

## Explicit fresh re-review

`POST .../operator-review/rereview` accepts the exact retained parent handoff ID,
handoff hash and decision hash, plus a new request ID and current packet and
observation hashes. A decided parent is required; parent hashes must resolve in
the same anchored identity scope. The current preparer, source reconciliation,
reviewer eligibility and bounded expiry are checked anew. A new handoff is
retained with its explicit parent link, returning `fresh_independent_review_required`.

The parent's decision is never copied. The assigned reviewer must submit a new
decision against the new exact handoff. Changed/expired parent sources, roles or
sessions do not erase history, but they cannot authorize the new review. New
packet/observation versions remain separate retained files. A changed assessment
can coexist with the original decision. Exact lineage is available on authenticated
pinned inspection; unrelated operators and replayed request IDs are refused.

## Remaining qualification

The independent anchor and intent store are a trusted controller boundary, not
an external attestation service. Joint privileged rollback or modification of the
journal, anchor/intents and identity store is outside this qualification. Durable
restoration of those independent controls, real operator appointments and IdP
provisioning, production PostgreSQL/multiprocess admission, actual enrollment,
installation, executed model weights and legal acceptance remain separate gates.
The owner's focused-analysis v3 review remains pending. No private case or live
account is used in these fixtures.

## Retained qualification — 2026-10-25

All 31 frozen cases pass through 31 actual loopback servers and 124 HTTP requests
on fresh ext4 volumes, with actual retained app authentication/RBAC. Models and
package are read-only; there are no private inputs, live accounts, host ports,
external network, provider requests or inference. The profile keeps two CPUs,
768 MiB, a cleared environment and read-only root. All four owned containers and
six new volumes across both candidates are removed.

The first unit candidate had an invalid SQLite initialization; it was corrected
without changing the 31 case expectations or three test method bodies. Importing
a helper TestCase initially duplicated discovery; it now uses a module reference.
The first native driver stopped before any HTTP request on a missing helper.
Its raw logs/cleanup and source freeze are retained. A new driver candidate,
fresh volumes and unchanged expectations complete each case once; no failed
case is retuned. All 575 deployment contracts (seven new), full lint and retained
report replay pass. The complete CI discovery moves once to the existing frontend
lane based on measured 169s reserve versus 43s in history; no jobs, workers, test
coverage or deadlines are increased. Exact-head CI and timing gates remain
mandatory before merge. See the [dated evidence](evidence/anchored-operator-2026-10-25.json).
