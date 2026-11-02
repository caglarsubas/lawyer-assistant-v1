# Private read-only disposition reconciliation receipts

The staged `DispositionReceiptService` exposes only `receipt`. Trusted local
wiring supplies an independently pinned `DispositionReconciler`. There is no
product route, persistence, imported-receipt reader, recovery executor, provider
call, private-case mutation or production activation.

Each request selects one plan using exactly its ID, explicit plan ciphertext
and plaintext hashes or paired nulls, an explicit decision ciphertext hash or
null, and the expected observation snapshot. No store, path, key, reader or
controller can be selected through request fields.

The service performs two fresh complete reconciliations, requiring identical
results and current app-session, firm, origin and CSRF authorization. It then
returns an at-most-8-KiB canonical JSON receipt and SHA-256 checksum, after final
binding and session checks. The existing 20-second cooperative workflow budget,
physical-store limits and cancellation behavior remain in force. Late changes,
invalid versions, denied authorization or exhausted budgets withhold the entire
receipt and checksum. Existing files and histories remain byte-identical.

## Receipt contents

The receipt records the exact supplied reference set, including explicit nulls;
the combined, source, copy and journal snapshot hashes; the immutable binding
hash; an actor digest and issue time; the reconciliation outcome; and whether
the exact plan and decision were authenticated. A retained decision is identified
as accept, changes required or reject without exporting its reasoning, complete
plan, source observations, filenames, identities or credentials. These hashes,
references and the selection itself remain confidential metadata.

A physically present plan without retained references remains unresolved. A
physically present decision without a supplied exact reference stays withheld.
The receipt never recovers a missing acknowledgement. Stale authenticated
history remains stale; a plan without an authenticated decision is never marked
as having a current planning review. Independently reviewed negative decisions
remain negative.

Every receipt explicitly states read only, planning only, non-atomic, unsigned,
not persisted, fresh independent review required and no execution authorization.
All inherited recovery, adoption, custody, enrollment, inference and activation
effect flags remain false. A SHA-256 checksum identifies transport bytes; it
does not authenticate a sender, prove an earlier observation or acknowledge an
earlier plan/review publication. The service does not accept a receipt back as
authority, discover missing references, repair history or automatically save it.

## Qualification boundary

New offline tests use actual disposable sessions and encrypted journals for
exact positive/negative reviews, absent references, stale history, scope denial,
late revocation, changed windows, unavailable/error states, size limits and
cancellation. Earlier interruption/native evidence remains unchanged and is
not presented as execution of this new wrapper. Fresh PR and independent-main
checks, actual test identity coverage, fixed CI reserve floors and preservation
audits are separate release requirements.

The owner's private-case analysis-v3 review, genuine operator appointments,
independent key custody, native provider qualification and product readiness
remain pending. This receipt is engineering observation metadata, not a legal
assessment or recovery approval.
