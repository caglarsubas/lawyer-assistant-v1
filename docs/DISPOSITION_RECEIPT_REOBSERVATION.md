# Read-only receipt re-observation

The staged `DispositionReceiptReobserver` compares exact retained receipt bytes
with current, authorized observations. Trusted local wiring supplies the existing
`DispositionReceiptService` and an independently retained receipt SHA-256. The
only operation is `reobserve`; its only request field is `receipt_bytes`.
The caller cannot override the checksum, select stores or keys, or supply a
cached authorization or a recovered reference.

The checksum identifies bytes. It does not establish who created the receipt,
authenticate its historical claims, acknowledge a publication, or approve any
action. Do not calculate the expected checksum from an untrusted incoming
receipt and describe that as independent verification. Operator provisioning
and independent custody remain separate prerequisites for genuine use.

## Fresh reads and comparison

1. Validate the existing local binding and authenticate the current session,
   firm membership, permitted role, origin and CSRF protection before parsing
   retained private bytes.
2. Require at most 8 KiB of canonical JSON, the exact independently retained
   checksum, the closed v1 receipt schema, the same local binding, valid typed
   fields and a nonfuture issue time. Duplicate keys, extra fields, changed
   checksums and invalid effect flags fail closed.
3. Read the current authorized journal inventory. Carry the exact retained plan
   and decision references, including explicit nulls. Only the observation
   snapshot is taken from the fresh inventory; no missing acknowledgement is
   supplied from newly visible records.
4. Request two fresh complete receipts. Each receipt service independently
   repeats complete reconciliation and authorization. Require their metadata
   to match, allowing only their issue time to differ. Changed sources, review
   validity, bindings or sessions within this observation window withhold the
   comparison.
5. Compare snapshot hashes, publication visibility, reconciliation outcome,
   authentication state and current planning-review status. Reader identity and
   issue time are excluded from this metadata comparison, since every read has
   its own current authorized reader and time.
6. Recheck the binding, current reader and, for a review observed as current,
   its actors and validity window before returning any result.

The metadata report identifies the retained checksum and changed field names,
and includes the fresh receipt and its checksum. It omits retained raw bytes,
old actor metadata, complete plans, review reasoning, document text, paths and
credentials. The complete report is also limited to 8 KiB. Errors return neither
a partial report nor a checksum. The existing 20-second cooperative workflow
budget applies to the whole operation; cancellation propagates.

## Meaning and limits

An unchanged comparison means the retained unsigned metadata agrees with these
fresh authorized reads. It does not prove the earlier observation, establish
legal correctness or grant current execution authority. Changes before the new
observation window can be reported; instability during that window fails closed.
Snapshots remain explicitly non-atomic.

An expired or revoked review can be displayed as stale history after a fresh
authorized read. A negative decision stays negative. A missing plan or decision
reference stays absent even if its publication is now visible. Neither an
unchanged comparison nor a new receipt renews the underlying review or repairs
an acknowledgement. All recovery, adoption, enrollment, custody, inference,
activation and legal-qualification effect flags remain false.

There is no product HTTP route, receipt persistence, history update, import into
a matter, recovery executor or provider call. Inputs and reports are confidential
selection metadata and must stay within their authorized context. Live originals,
exact evidence versions, credentials, sessions and review history are untouched.

## Qualification

Offline qualification uses disposable identities and encrypted histories for
positive and negative decisions, absent references, changed and stale context,
fresh authorization, malformed bytes, budget/cancellation and late revocation.
It does not extend earlier native interruption evidence to this new wrapper.
Exact-head PR checks, independently fetched main, complete test identity
coverage, unchanged CI caps/reserve floors and preservation audits are required
separately. Owner analysis-v3 review, genuine operator/custody/provider work,
production activation and legal readiness remain pending.
