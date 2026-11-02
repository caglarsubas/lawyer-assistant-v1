# Independently reviewed copy-recovery dispositions

This staged operator service records a disposition of an exact retained restart
observation. It does not execute recovery. It has no product HTTP endpoint,
private-data migration, inference request or production activation.

## Contract

`DispositionPlanner` accepts only `prepare`, `decide` and `inspect`. An actual,
current app session, CSRF token, approved origin, firm permission and assigned
operator identity are required on every request. The preparer and reviewer are
different identities. This qualification uses disposable appointments only.

- `prepare`: caller supplies an unused 32-character plan ID, all six exact copy
  references (including explicit nulls for unavailable acknowledgements), the
  fresh observation hash, and one closed disposition code. The service captures
  and compares the complete authenticated reconciliation twice before retaining
  the encrypted plan; it rechecks the same context after publication.
- `decide`: the assigned independent reviewer supplies the exact plan ID,
  ciphertext hash and plaintext hash, plus `accept`, `changes_required` or
  `reject` and its fixed reason code. The plan, original observation, sessions,
  assignments, bindings and five-minute planning window must still match before
  and after the create-only encrypted decision publication.
- `inspect`: an authorized operator supplies those same exact plan references
  and an explicit decision ciphertext hash or null. It reads the retained plan
  and, if supplied, decision without modifying any journal. It compares fresh
  source observations, rereads exact records and rechecks the caller before
  returning metadata. Expired or superseded planning context is visibly stale.
  A missing decision reference stays missing even if a matching file exists.

Every response says planning only, source read only, non-atomic snapshot,
fresh independent review required, and no production execution authority.
There are no arbitrary paths, identifiers resolved by similarity, free-text
instructions, controller reads or repair/execute/resume operations.

## Dispositions and their limits

`retain_for_independent_assessment` is available for a successfully reconciled
observation. `seek_fresh_independent_context` is available for consumed intents
without a completion or a completed copy with stale original execution review.
`retain_verified_history` additionally requires an independently supplied,
authenticated completion reference. Byte equality alone is insufficient.

Acceptance is a review of this metadata and proposed disposition. It cannot
renew the original copy authorization, adopt a record, reconstruct a lost
acknowledgement, resume an interrupted copy, repair or clean up a target, renew
key custody, or activate provider/trust access. Any later operation needs a
separately designed and freshly reviewed context.

## Preservation and failure handling

The plan embeds the exact authenticated restart result, its hash, exact source
references, all source/destination/manifest/origin dependencies, actor records,
reviewer assignment, timestamps and explicit false execution flags. All older
source, planning, copy-review, copy-control and destination histories remain
read only. Restore observations retain their original backup dependencies.

A separately keyed encrypted append-only journal has an independently pinned
identity. Its root must be disjoint from every protected source, target and
origin root. Plans and decisions use distinct authenticated-encryption record
types; their record identities are create only. An append retained before a
late revocation, race or lost response stays retained. No overwrite, deletion,
automatic retry or inferred acknowledgement occurs.

Unknown references, ciphertext changes, invalid bindings, malformed input,
budget exhaustion, unavailable observations, or late physical races withhold
all decrypted plan/review metadata. Historical records remain readable by a
fresh authorized operator when prior planning sessions/windows become stale.
This is bounded observation, not a filesystem transaction or a legal approval.

Limits are inherited from the source reconciliation: 20-second operation
budget, 32 entries/1 MiB per physical inventory and closed bounded decoding.
No raw exception, credential or source path is returned on failure.

## Qualification

`backend/tests/test_copy_recovery_disposition.py` exercises real disposable
sessions and encrypted records, including restore-origin preservation,
independent/negative review, stale history, malformed/changed references,
revocation, late races, tampering, lost acknowledgements and closed operations.
The opt-in `qualify_copy_disposition.py` campaign runs frozen expected outcomes
across fresh processes on four owned ext4 Docker volumes; one copy worker is
SIGKILLed after its first target publication. Runtime/private-case data is never
mounted. It verifies both histories, all exits, independent identities, exact
versions and read-only inspections before removing only its owned resources.

These engineering checks establish neither power-loss durability nor genuine
operator appointments, key custody, production readiness or the pending owner
legal review. CI and independent-main gates are recorded separately in the
living roadmap/tracker.
