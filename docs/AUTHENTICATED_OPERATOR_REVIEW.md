# Authenticated operator-review handoff — disposable stage

F00-06 remains partial. This unregistered ASGI service records preparation and
independent review of exact operator packet/observation versions. Qualification
uses disposable accounts and the retained application's actual session/RBAC code.
The user's focused-analysis v3 review and genuine independent issuer/runtime-pin
confirmation remain pending. No live account, session, original document or matter
record is an input; no production route is registered or installed.

## Identity and role evidence

`scripts/operator_review_auth.py` wraps the unchanged `app.auth.authenticate`,
session records and current managed-role permission checks. Cookies, active accounts,
session expiry, origin, CSRF and the existing firm authorization guard are enforced.
The guard remains held through the complete response. Rechecks retain current
session identity, firm, employee revision, role IDs/revisions/permissions and a
digest of that evidence. Permission and principal results are never cached.

The adapter accepts only an owner-only marked disposable SQLite profile at an
explicit fixed filename. It pins the database inode/namespace, rejects production
PostgreSQL/arbitrary stores and refuses a database containing even one application
`Record`. The five retained app source files used in qualification are `__init__`,
`auth`, `db`, `firm_rbac` and `content_scope`; app startup, configuration, provider
and inference-engine modules are not loaded. The fixture creates no live accounts
and starts no application services.

A trusted immutable subject-to-role policy fixes the preparer/reviewer bindings and
firm outside HTTP JSON. Preparers need current `firm.manage`; reviewers need that
permission plus `source.curate`. Both require actual managed employee/role records.
Reviewer and preparer must be distinct authenticated subjects and match the exact
packet assignments. Neither a client reviewer label nor an admin label bypasses
those checks. Separate subjects do not establish that two independent humans have
been appointed; personhood, identity assurance and real appointments remain gates.

## Version-bound handoff and decision history

`authenticated_operator_review.Target` fixes protected packet/observation paths,
independently approved hashes, the inspected portable package, exact V2 binding,
read-only model and public trust records. Requests cannot select paths, firms,
roles, identities, model operations or source versions. A complete current
reconciliation is required before preparation and before a decision. Cheap fresh
checks revalidate packet/observation bytes, public evidence, sealed ancestry/current
anchor, read-only mappings, expiry and both actors' role/session evidence at commit
and response boundaries. The retained 20-second V3 verifier limit is unchanged.

The unregistered POST paths below use the existing firm-admin permission namespace
in a separate staging application:

| Action | Exact body fields | Result |
|---|---|---|
| `prepare` | request ID, packet SHA, observation SHA | Immutable pending handoff and its exact digest |
| `decide` | handoff ID/SHA, decision, reason code | One immutable authenticated decision |
| `inspect` | handoff ID/SHA, optional decision SHA | Metadata observation, pinned decision or retained stale history |

The prefix is `/api/v1/firm-admin/operator-review/`. This is not mounted in the
live application. Session headers must be unambiguous; duplicate session cookies,
missing headers, wrong origin/CSRF, bearer credentials, query overrides and unknown
body fields are rejected. Body/header/time budgets are bounded. Every response is
no-store, including masked errors; no raw exception or source content is returned.

Handoffs expire after at most 300 seconds, bounded further by packet, observation
and preparer-session expiry. Decisions distinguish `accept`, `changes_required`
and `reject`, with matching controlled reason codes. They record exact source
hashes, authenticated actors, role/session evidence and the separate review time.
All trust, installation, native-execution, production and legal authority flags
remain false. Acceptance is scoped to disposable metadata handoff only.

The private ledger uses owner-only exclusive files with original handoff and
decision digests. A replay, duplicate request or competing decision cannot replace
a record; capacity is bounded to 128 files. Current records are rechecked before
reply. A lost response or cancellation can leave an already committed metadata
record; the operation is never replayed. Cancellation waits for admitted worker
completion before releasing the real firm guard. The retained digest can be
observed and pinned explicitly, preserving history after an uncertain reply.

An authenticated assigned actor can inspect historical evidence after packet or
handoff expiry. Historical decoding validates original versions at their recorded
time, and **only** inspection uses it. Expiry, revoked sessions, changed role
revisions or changed source context make an existing decision stale. The old
decision remains intact; inspection never silently reapproves it or changes its
authenticated actors. Currently ineligible/foreign/unassigned actors cannot inspect
it. An observed decision digest alone does not adopt its contents as current.

## Qualification, boundaries and next work

The first frozen native campaign passes **44/44 cases**, through **44 actual Uvicorn
loopback servers and 92 HTTP requests**, with actual session/RBAC checks and invented
accounts. Cases include bad cookies/CSRF/origins, self-review, unassigned/foreign
actors, session/account/role revocation, exact version/hash changes, expired
handoffs, retained expired-packet/role history, duplicate/concurrent decisions,
lost replies, forbidden fields and refusal of non-disposable/data-bearing profiles.
No runtime signer or provider helper is invoked. Only the retained 65,561-byte
zero-tensor model fixture is used; model/package inventory remains exact.

The profile uses two CPUs/768 MiB, cleared environment, read-only root, no external
network/runtime mounts/host ports, separate anchor storage and three new owned ext4
volumes. Preparation exits before model/package read-only use. Both containers and
all volumes are removed. Credentials never appear in responses/review records.
Test-only password hashes are seeded once per process; each account subject,
profile and session is fresh, and every fixture login still verifies its password.

Two first-unit status-mapping failures are retained; invalid packet bytes and stale
operation errors were normalized without changing checks or frozen expectations.
All six unit methods then pass. The native outer wrapper had an incorrect estimate
of more than 100 requests; the frozen case paths require exactly 92, verified
individually without a rerun or expectation change. Original raw results and the
failed wrapper check remain retained. A later driver whitespace fix is separately
proved AST-equivalent; all other frozen native sources remain byte-exact.

This qualifies one-process disposable SQLite authentication and immutable metadata
handoff, with retained-report replay in CI. Production PostgreSQL/multiprocess
admission, authenticated IdP provisioning, real operator identity/appointments,
durable authenticated journal recovery, joint rollback resistance, signed external
review attestations and legal/production acceptance remain unqualified. Owner-only
files/digests are not a substitute for those trust roots. A snapshot cannot recall
bytes already released; native execution retains its separate effect/release gates.

Next add anchored authenticated decision persistence/recovery and explicit fresh
re-review using disposable identities, preserving original decisions and exact
source/auth evidence. Genuine issuer/runtime-pin confirmation, installation/executed
weights, completion/context/tokenizer/truncation, sustained five-job native research,
retention/capacity, cold/host-bind profiles and historical HTTP 502 cause remain open.
See [dated evidence](evidence/authenticated-operator-2026-10-25.json).
