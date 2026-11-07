# Isolated host authorization for reconciliation

This is the first host-integration layer of the
[operating plan](RETENTION_RECONCILIATION_OPERATIONS.md). It qualifies admission
and repeat authorization against the application's existing session and firm
permission checks. It has no registered application route, receipt access,
retention operation, provisioning API or bridge into the disposable planners.

## Trusted wiring and request boundary

`scripts/host_reconciliation_authority.py` accepts a constructor-supplied host
application, selected-record resolver and clock. The request supplies only a
JSON `record_id`. The gate requires the exact POST path
`/api/v1/firm-admin/retention/reconcile`, no query, a permitted nonempty Origin,
one session cookie and one CSRF header. Headers are bounded to 64 entries and
16 KiB; the JSON body is bounded to 1 KiB. Duplicate JSON keys, extra fields and
invalid opaque identifiers are rejected.

The gate builds a fresh request from trusted application configuration. Caller
application, request state and caller-held authorization guards are excluded.
It authenticates the current session and requires both `firm.manage` and
`source.curate` before decoding the record identifier or consulting the resolver.
The locally acquired firm guard covers resolution and is released on exit.

## Exact authorization context

The constructor-owned resolver receives the authenticated record selection,
firm and principal. It must independently authorize that selected receipt scope
and establish current source, permission, enrollment and trust validity. It
returns a frozen `HostBinding` containing:

| Binding | Purpose |
|---|---|
| Schema, revision and fixed `reconcile` action | Identify this admission contract |
| Record, firm and principal identifiers | Prevent selection or identity substitution |
| Scope and source digests | Preserve exact evidence context |
| Permission and enrollment digests | Bind the current authorization and appointments |
| Trust-registry digest | Detect changes in the selected current trust context |
| Issue and expiry times | Define the resolver's applicable validity window |

Registry metadata alone does not prove independent fingerprint provenance or
key custody. The resolver must withhold a binding for absent, unauthorized,
revoked, expired or otherwise unverified context. The gate checks the supplied
binding's types, identifiers and validity; a genuine registry integration is
still a separate implementation and qualification requirement.

`authorize(scope, body)` returns a private, process-local snapshot. It binds the
exact resolver result to the current principal, firm, session digest/expiry,
session version and employee/role revisions. Authentication and resolution are
repeated before admission completes so a changed context is withheld.

`recheck(snapshot, scope)` requires the exact object issued by that gate and
freshly repeats authentication and trusted resolution. Copied, reconstructed
or foreign snapshots are rejected. Any changed evidence, permission,
appointment, trust revision, role or session requires a new admission. Recheck
preserves the selected snapshot and cannot renew its lifetime, which is at
most 60 seconds and bounded by session and binding expiry.

Snapshots have no public serialization API. They contain no raw session cookie,
CSRF value, secret key or signature. Keep them within authorized host wiring;
no application endpoint currently returns them.

## Qualification and remaining integration

`backend/tests/test_host_reconciliation_authority.py` uses invented SQLite host
identities and the real authentication/RBAC implementation. It checks successful
admission and recheck, cross-firm/principal denial, malformed requests,
authentication before lookup, current session/role changes, exact trusted
binding changes, expiry and guard release. Its complete file runs in the
existing backend-review CI job with two workers. Existing test identities,
job caps and reserve floors remain required.

This qualification establishes this isolated request boundary. It does not
establish an atomic cross-store snapshot, a hard cancellation deadline,
production operating limits or permission to access a retained receipt.
The original `SessionAuthority` disposable SQLite restrictions and predecessor
planner type checks remain intact.

The next integration must provide an independently administered current trust
resolver, authenticated role/principal enrollment and a reviewed connection to
the exact recipient observation. Human and AI preparation/review assignments
must be distinguished from configured host principals and custody controls.
Agent assessments do not provision those principals or hold production keys.

Directory restoration remains a separate protocol: changing a receipt store's
device/inode identity changes its permission and AEAD binding. A copied
ciphertext hash cannot establish authorized recovery. Preserve original
ciphertexts, permissions and review history; any successor binding or
re-encryption needs its own reviewed protocol and authorization.
