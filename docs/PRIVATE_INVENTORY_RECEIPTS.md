# Private receipt retention and fresh re-observation

This F00-06 adapter retains only the selected handoff metadata from the preceding
handoff contract. It never copies the original multi-context inventory, uploads
documents, changes source evidence or rewrites controller/review histories.

Trusted operator wiring constructs a `ReceiptStore` with an existing owner-only
directory, independently bound context/scope and a 256-bit encryption key. Keys,
paths and readers are not request fields. No default key, credential loading,
directory listing, route, installation or production enrollment is introduced.
The key is excluded from the store's representation and is never retained in a
receipt. Genuine key custody and deployment approval remain separate gates.

`retain` requires the exact source receipt digest and explicit selection. It
checks fresh authorization before calling the existing handoff, retains its
original/current selected observations and provenance digests unchanged, and
reauthorizes immediately before publication. The source inventory and original
documents remain in their original stores. The encrypted record holds only the
selected metadata, including its original source-byte digest; that digest does
not claim to reconstruct the omitted source entries.

Records use AES-256-GCM with a fresh nonce and authenticated context, scope and
record identity. Plaintext is bounded to 64 KiB. A prebound, stable 0700 directory
contains 0600 records. Publish through a private staging file, file fsync,
create-only hard-link publication and directory fsync; verify the published bytes
before acknowledging success. Existing records are never replaced. An uncertain
post-publication result preserves the record and requires independent inspection
and a fresh exact digest; no retry or historical cleanup follows automatically.

`reobserve` requires an independently supplied digest of the exact ciphertext.
Authorize before file access, validate file identity/mode/ownership/link count and
digest, decrypt and verify the closed historical metadata, then authorize fresh
controller reads. Recheck both the session and the exact retained file before
returning any historical/current body. Hashes are integrity/provenance pins, not
access credentials. Possession of a record ID, ciphertext, digest or old receipt
does not grant access. Changed source/context and changes between reads remain
explicit. Denial, conflict, malformed evidence, file changes or budget exhaustion
release no cached body. Re-observation never writes a record or controller.

Capture uses seven authorization boundaries; re-observation uses six. Each
operation permits at most two controller reads, with the existing two-second
per-operation and twenty-second cooperative total limits. File access is bounded
and local; these limits do not promise preemption of blocked filesystem calls.
Cancellation propagates. No atomic snapshot, current review validity, approval
renewal, legal qualification or execution authority is asserted. All historical
and fresh metadata remains private; there is no shared cache or public graph use.

Eighteen tests and thirty-six negative subtests include two disposable retained
records and fifteen authenticated ASGI re-observations over retirement/rollback,
expiry, withdrawal, unrelated actors and session revocation. Thirty-two read
requests include four creating the source inventories, four capturing the
handoffs and twenty-four re-observing. Original source pins, exact ciphertext and
all four controller histories remain unchanged around ordinary re-observation.
Actual filesystem, cryptographic, authorization-boundary, crash-acknowledgement,
mid-read tampering, timeout and cancellation cases are also covered.

This is in-process disposable qualification, not native/production acceptance.
The complete new test file uses the existing review job's measured capacity;
its existing two workers, deadlines and all previous cases stay. The backend
remainder stays at 4,055 passing cases, and all 1,018 deployment methods and
139 frontend files remain. Require exact-head and independent-main checks,
actual receipts and unchanged job/short-phase reserve gates before completion.

Next qualify staged adapter integration and operator provisioning readiness.
Independent key custody, genuine appointments, live deployment and owner legal
review remain pending; engineering results do not supply those approvals.
