# Staged operator checksum handoff

`OperatorChecksumAdapter` is an unregistered ASGI adapter for disposable operator
validation. It exposes one POST path,
`/api/v1/firm-admin/disposition-receipt-stage/reobserve`. It is not installed in
the live application and supplies no login, provisioning, persistence, recovery,
enrollment, inference or production route.

## Preparing the exact handoff

Trusted host wiring calls `prepare_handoff` using a current authenticated
preparer session. The configured receipt service fixes the local binding,
disposable profile and different assigned reviewer. The host separately supplies:

- Exact retained receipt bytes and an independently retained receipt checksum.
- A provenance record and its separately retained checksum.
- An opaque source identifier that selects only this configured handoff.

The host factory never creates provenance from incoming receipt bytes. The
provenance record has a closed canonical schema: source ID, opaque reference ID,
receipt checksum, local binding, profile, recording time and the fixed basis
`separately_retained_operator_checksum_record`. Its sender-authentication and
external-channel-verification fields must both remain false. The record must
postdate or coincide with the receipt and cannot be future-dated.

A checksum establishes exact byte identity; it does not authenticate the sender
or prove that an operator obtained it independently. The operator must obtain
the expected pins through the intended independent process. Do not calculate
them from an incoming packet and describe that as independent provenance.

The immutable in-memory handoff binds both pins, source, profile, local binding,
current preparer session/role snapshot, assigned reviewer role snapshot and a
five-minute handoff window. Its checksum identifies that exact preparation.
It is not a persisted review decision or an execution approval.

## Reviewer request

The request contains exactly `source_id`, `expected_handoff_sha256` and
`independent_receipt_sha256`. The last field is the reviewer's independently
supplied checksum for the retained receipt. It is compared with the prebound
pin and never replaces it. A future interface must not populate this independent
entry from the receipt or the same incoming handoff packet.

The adapter requires the current assigned reviewer, whose bound account differs
from the preparer. Real disposable cookie, firm, permission, origin and CSRF
checks run before the body or private provenance is inspected. An unassigned
reviewer or the preparer cannot use the endpoint. The preparer's session and
both role snapshots must still be valid at return.

The adapter then validates the exact handoff and both pinned inputs, compares
the supplied checksum, and invokes the existing read-only receipt re-observer.
All exact references and explicit nulls survive; missing acknowledgements are
not recovered. Stale and negative decisions remain history. Final checks cover
binding, pins, both actors, clock rollback and any underlying review still
observed as current. The handoff window cannot extend a planning-review window.

## Private output and budgets

Only after successful final checks does the adapter return a metadata report:
source/handoff/provenance checksums, preparer and reviewer actor digests, the
explicit comparison basis, and the fresh re-observation. Full provenance bytes,
retained receipt bytes, actor identities, plans, reasoning, paths and credentials
are withheld. Every response, including failures, uses `Cache-Control: no-store`.
An error returns no partial report or report checksum.

JSON bodies are limited to 2 KiB, eight ASGI frames and the existing two-second
read budget. Duplicate JSON keys, queries, bearer authentication, encodings,
invalid content type, ambiguous lengths and caller-selected pins/paths are
rejected. The authorization/re-observation workflow retains the existing 20-second cooperative
budget and an 8-KiB response limit. Cancellation propagates. No response bytes
are sent before the full result and final authorization are ready.

This is a repeatable read with fresh authorization each time. It claims neither
one-use delivery nor a recovered publication acknowledgement. Handoffs and
observations are unsigned and not persisted. The authenticated account
separation establishes current software admission, not independent human
appointments, external-channel authenticity, key custody or legal qualification.
Those genuine operational gates remain separate.

## Qualification boundary

Tests use real disposable sessions and encrypted journals for independent
reviewer admission, positive/negative/stale results, exact dual pins, malformed
provenance, closed HTTP input, frame/byte/time budgets, late revocation and clock
or review expiry. They neither open nor provision the live matter store. Earlier
native qualification is retained unchanged and does not qualify this new adapter.
Fresh exact-head and independently fetched-main checks, complete actual test
identity coverage, fixed CI reserves and preservation audits remain required.

Originals, exact evidence versions, credentials, sessions, the private analysis-v3
draft and review histories remain untouched. Owner review and genuine operator,
custody, provider, production and legal readiness remain pending.
