# Staged receipt adapter and operator provisioning readiness

F00-06 exports a separate, public-source-only `lawyer_receipt_stage` package.
The existing controller package, receipt implementation and historical source
pins remain unchanged. The nine-module stage binds eight source-file digests;
only imports are rewritten for portability. Repeated builds are deterministic.
Inspect the closed package against an independently supplied manifest digest
before importing it. Unexpected files, imports, modes, links or changed bytes
fail closed. Application and inference-engine code are not bundled or imported.

The stage's default policy requires a kernel-read-only package. Unit tests use
an explicit writable-stage override in trusted constructor wiring; HTTP callers
cannot set it. This release supplies in-process and isolated-import qualification,
not a new native mount/process qualification. All prior native evidence stays
separate. No package installation or production route registration occurs.

Readiness compares independently supplied context, scope, key fingerprint,
directory identity and disposable-profile pins. It reads no receipts, generates
no keys and changes no accounts, permissions, trust or data. Matching pins yield
`ready_for_disposable_validation`. Key custody and genuine operator appointments
remain `unassessed`; every enrollment, deployment, execution and legal flag stays
false. A matching fingerprint or marker is not independent custody approval.

Trusted host wiring supplies the current-session resolver, receipt store, at
most eight prepared sources and exact independent expectations. The resolver
must validate the actual cookie, origin, CSRF, current RBAC and empty disposable
identity database. The stage itself contains no application/database imports.
Each session resolution owns a short-lived admission guard, released on success,
denial, timeout or cancellation before nested controller calls. Controller
requests retain their own guards; final session checks precede response
generation. This is explicitly not a joint or atomic authorization snapshot.

An unregistered ASGI instance accepts only POST `readiness`, `retain` and
`reobserve` under `/api/v1/firm-admin/receipt-stage/`. It uses the existing firm
administration permission catalog without changing that catalog. Require
unambiguous cookie/origin/CSRF/JSON headers, reject bearer fallback, query strings
and unknown fields, and bound headers, request bytes and body frames. Responses
are always `no-store`. Errors reveal only bounded codes, never cached bodies,
paths, key material, credentials or tracebacks.

Capture accepts a prepared-source ID, exact source digest and record ID. Sources,
raw inventories, keys and filesystem paths cannot be uploaded or rebound through
this endpoint. Re-observation requires the independent ciphertext digest.
Existing per-operation authorization, two-read and receipt-integrity checks
remain. Recheck the package, profile and session before returning data. If
authorization disappears after publication, retain the encrypted record but
withhold its acknowledgement; completion remains unassessed and there is no
automatic retry, deletion or rollback.

Seventeen tests and twenty-six negative subtests cover deterministic export,
import-only equivalence, isolated imports, manifest/profile/key/store mismatch,
closed requests, ambiguous headers, immutable wiring, guard release, cancellation
and final-response denial. Authenticated ASGI cases include two retentions and
fifteen re-observations over retirement, rollback, expiry, withdrawal, unrelated
roles and session revocation. Twenty-six controller reads include four source
collection reads and four capture reads; the remaining eighteen re-observe.
Exact ciphertext, source references and all four controller histories remain.

The complete new test file uses measured graph-candidate job capacity, retaining
the same command, pair and deadline. Existing backend/review inventories remain
4,055/133, deployment contracts remain 1,018 and frontend inventory remains
139 files/10,532 cases. Exact-head and independent-main checks, actual receipts,
all-job/backend-test reserves and existing short-phase gates remain mandatory.

Next qualify native read-only packaging and process-boundary adapter behavior
using disposable identities. Independently reviewed live key custody, genuine
appointments, production activation and owner legal review remain pending.
