# Private inventory-receipt handoff

This F00-06 engineering slice passes one explicitly selected inventory entry to
an independently prebound destination reader. It adds a callable Python adapter,
not an application route, deployment, enrollment or execution permission.

`handoff(raw, expected_receipt_sha256, request, contexts, actor_sha256=...)`
requires an independently supplied digest of the exact source bytes. The closed
selection contains the opaque context ID, change ID and expected context digest.
Trusted wiring supplies the destination scope, session-authorizer and the two
permitted read callbacks. Receipts never supply credentials, URLs, paths, registry
entries or callbacks. Only the selected context is consulted; no enumeration,
retry, shared caching, public graph update or file import occurs.

Before any read, validate the receipt hash, its internal inventory digest, closed
schema, false authority flags, counts, unique entries, complete observations,
actor/scope bindings and exact plan/view hashes. Source bytes are bounded to
128 KiB and the existing eight-entry inventory limit. The selected source entry
must have two verified metadata observations and match the independent selection
and destination scope. Partial or failed source entries cannot be handed off as
verified metadata. Structural/hash consistency is not authenticity or authority;
the exact receipt pin and trusted destination wiring remain independent inputs.

Reauthorize at entry, before both fresh reads, after those reads and immediately
before releasing the comparison. Preserve real controller authentication and
no-store behavior in the adapter. At most two read requests run, with the existing
two-second per-operation and twenty-second cooperative total limits; adapters
must honor cancellation. Denial, conflict, malformed destination evidence,
unavailability or budget exhaustion releases no cached source/destination body.

On success retain the original selected entry and fresh destination entry
separately. Compare both observation pairs by named fields. Pending anchors,
changed context/source and changes between reads stay explicit; no automatic
repair, context rebinding, approval renewal or history rewrite follows. Private
selections and their aggregate metadata remain confidential. This is not an
atomic snapshot. Current authority and review validity remain unassessed, and
every legal, enrollment, installation and execution flag remains false.

Thirteen tests and eighteen negative-input subtests include thirteen handoffs over
fresh disposable retirement/rollback controllers: twenty handoff read requests,
plus four reads creating their source receipts. Four retained histories and the
exact source receipts remain unchanged around every handoff. Revocation,
unrelated sessions, expiry, withdrawal, explicit context changes, changed read
pairs, final authorization loss, malformed receipts and cancellation are covered.
This is in-process ASGI qualification, not new native or production acceptance.

All existing source pins, 1,018 deployment contracts, frontend cases, ten CI
jobs, step/job deadlines and worker limits remain exact. Require complete
exact-head checks with thirty seconds of job/backend-test reserve and the
existing short-phase gates, then independently verify merged main and actual
test receipts. Overall checklist/readiness and owner review remain separate.

Next qualify explicit handoff retention and later re-observation using disposable
identities, with independent exact receipt pins and fresh authorization on every
access. No retained receipt may become a bearer credential. Genuine operator
appointments, key custody, production activation and owner legal review remain
pending.
