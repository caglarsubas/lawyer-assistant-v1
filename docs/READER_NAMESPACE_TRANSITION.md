# Reviewed transition between reader namespaces

This unregistered qualification broker connects the existing staged-reader
namespace to a separately reviewed lifecycle-reader namespace. It uses invented
SQLite identities. It does not install a production route, migrate private cases,
enroll provider trust, change original documents or establish legal acceptance.

## Preserve each history and record a separate transition

The old and new reader logs retain their own schemas, identities, roots, external
anchors, admission evidence, proposals, decisions, selections and retirement
records. A third append-only journal records the transition. It references exact
namespace identities, physical namespaces, history heads/digests, selected events,
canonical withdrawal head, source context and snapshot. No reader events are
copied, converted, removed, renumbered or rewritten during transition.

The destination requires its own fresh stage and independent selection review.
Both selected readers must still be current, and their exact canonical snapshot
must agree. A retired destination is rejected. A fresh independently reviewed
renewal can be selected while retaining its earlier retirement records. Old
approvals are not imported as new authority.

Transition preparation, independent approve/deny decision and one-time commit are
separate authenticated actions. The current assigned preparer must commit its
exact approved proposal. The separate reviewer, both child reader grants, roles,
sessions, canonical fence and physical namespaces are rechecked. Lifetime is at
most 300 seconds and never exceeds either child grant or the preparer session.
Changes to either reader history invalidate pending review and current use.

## Routing and observation

Typed transition actions are `transition_observe`, `transition_prepare`,
`transition_decide`, `transition_commit`, `transition_status`,
`transition_recover` and `transition_inventory`.

Before commit, explicitly named `legacy_reader_*` and `destination_reader_*`
actions delegate only to their corresponding closed reader tools. They support
preparing the two exact reviewed selections. Destination inventory cannot bypass
transition review. The transition journal serializes delegation against commit.

After any committed transition, direct reader delegation is blocked. Selected
metadata reads use the exact approved destination through `transition_inventory`.
Legacy reading does not resume when a grant expires, a namespace changes or a
source is withdrawn. There is no fallback or automatic source/context refresh.
The original canonical service remains the writer and withdrawal authority.
Post-transition destination mutations need a subsequent guarded workflow.

Each page is limited to eight metadata rows. Both reader locks and the canonical
withdrawal lock remain held across page assembly and final child checks. Cursors
bind transition, control head, exact subject, source snapshot and actor; a legacy
cursor cannot be reused in the destination. Authorization precedes inspection of
reader or transition storage. No request supplies a filesystem path or query.

Status uses observation followed by exact decision/commit pins. It exposes only
retained metadata, including both history references and current usability. It
never refreshes a grant. Lost replies reconcile without replay. A retained,
admitted unanchored transition blocks ordinary access until explicit exact
head/tip recovery; missing admission evidence cannot be manufactured by recovery.
Recovery changes only the transition anchor, never either reader history.

## Qualification and remaining gates

The frozen synthetic matrix covers independent and denied review, changed
namespace heads, withdrawal, damaged histories, lost replies, unanchored commits,
missing admission, races, expiry, revoked review, cursor/bypass prevention, exact
subject pins, read-only lineage and preserved retirement history. Every transition
request verifies that old/new reader files and anchors remain byte-for-byte
unchanged by that request. Fault injection remains separate from this assertion.

Native qualification passes 20 scenarios through 40 actual loopback workers
and 675 HTTP requests in 96.31 seconds. It uses real app session, RBAC,
origin and CSRF checks, four separate fresh ext4 volumes, two CPUs, 768 MiB,
96 PIDs, cleared process environment and no external network. The campaign limit
remains 180 seconds. All prior lifecycle/native source pins remain unchanged.

The first CI profile passed all frontend and namespace tests but exceeded the
frontend job cap. Its retained per-case times now guide a closed, source-bound
namespace assignment profile. Every namespace method is assigned once within
explicit incremental work budgets. Missing, duplicate, stale or over-budget
assignments fail before execution. New cases share existing workers; a small
sequential slice uses reserve in the existing PostgreSQL job. No third concurrent
worker is added. All source-manifest deployment methods
must execute once across seven disjoint assignments within the same nine jobs.
Existing deadlines and frontend coverage remain unchanged. Merge requires nine
exact-head checks and five timing reserves of at least 30 seconds, then a
pinned-head merge and independently fetched-main tree equality.

Real route cutover must remove or isolate separately exposed legacy endpoints;
this disposable broker is not proof of production cutover. Production namespace
transition, PostgreSQL/IdP fencing, genuine appointments/key custody, off-host
recovery, signed live provider/context/five-job qualification and legal acceptance
remain separate gates. Owner review of focused private analysis v3 stays pending.

See the [dated evidence](evidence/reader-namespace-transition-2026-10-26.json).

The work profile is planning evidence, not a runtime guarantee. Actual exact-head
CI results and timing reserves remain mandatory. All native source pins, scenarios
and outcomes remain unchanged by this CI correction.
