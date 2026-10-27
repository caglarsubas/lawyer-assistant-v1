# Explicit recovery of two pending journal anchors

This unregistered controller extension qualifies metadata recovery with invented
records and disposable identities. It does not install a provider, migrate a
private case, renew access or establish production rollback resistance.

## Exact plan and explicit progress

`joint_observe` verifies the existing maintenance, namespace, legacy, destination
and canonical withdrawal controls under a consistent lock order. Both journals
must have valid independent admissions. Their retained events must describe the
same independently reviewed child, transition and exact finished change. An
unfinished change, unrelated tail or changed physical namespace cannot qualify.

The returned plan binds the actor/session, exact change and finish, retained
history digests, tips, physical scope and current source context. Its progress
view additionally binds both current anchor positions. The plan stays stable as
anchors advance; every repair requires a freshly observed progress view.

`joint_apply` appends one already-admitted frame to one explicitly selected
anchor. A pending destination is repaired before the maintenance finish anchor.
An attempt to finish first, reuse an earlier view, borrow another actor's view,
or use another plan fails before writing. Competing instances cannot append the
same frame twice. All records, admissions and the other anchors remain exact.

After a lost reply, a separate process observes retained progress; it does not
repeat the selection, transition, finish or an already completed anchor write.
An anchored no-op writes nothing. `joint_finish_observe` checks the exact plan,
view and finish record and returns read-only completion metadata. It can describe
pending progress without claiming that inventory access is authorized.

Two external anchors are not an atomic transaction. Reads remain fenced while
either journal is pending. After repair, ordinary source, expiry, assignment,
review and revocation checks still apply. Historical approvals and old cursors
are never reactivated. Withdrawal or expiry between steps requires a fresh view;
metadata repair never turns the changed context into a grant.

## Qualification and limits

The frozen native campaign passes **16 scenarios, 34 actual loopback servers and
950 HTTP requests in 103.33 seconds**, within the retained 180-second cap. Two
scenarios stop the original worker and start a replacement after a lost reply;
the concurrent worker count stays at two. Actual local session, RBAC, origin and
CSRF checks use a shared disposable identity store. No real account is enrolled.

Four fresh distinct ext4 volumes, two CPUs, 768 MiB, 96 PIDs, a cleared process
environment and no external network remain required. All 96 current source pins
include the preceding 87 unchanged dependencies. Owned containers and volumes
are removed after qualification. No inference or live provider request occurs.

The frozen joint workflow uses renewal. Joint retirement and rollback campaigns
remain separate coverage gaps.

The mixed pending state models separately restored external anchors: an admitted
finish is retained before its anchor, and the invented destination anchor is one
admitted frame behind. This is a controlled recovery fixture, not evidence of
off-host custody or production rollback protection.

The complete deployment inventory is 992 methods, disjoint across seven existing
assignments in the same nine CI jobs. Fresh exact-head success, five reserves of
at least 30 seconds, a pinned merge and independently fetched-main tree equality
remain mandatory. Frontend coverage, worker peaks and deadlines are unchanged.

The first CI placement left 13 seconds of frontend reserve and 31 seconds of
graph-runtime reserve. Five measured contracts (26.517 seconds) leave frontend
for existing history/candidate reserves; two graph contracts (8.888 seconds)
join the existing two-worker backend assignment, whose contract step took
108 seconds under its unchanged 120-second cap. The qualified runtime and all
96 native source pins stay unchanged. Fresh exact-head timing gates are required.

Production PostgreSQL/IdP, genuine appointments and custody, off-host recovery,
signed live provider qualification and legal acceptance remain separate gates.
The owner's private analysis review remains pending.
