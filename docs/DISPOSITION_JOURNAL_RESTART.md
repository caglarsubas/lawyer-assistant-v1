# Read-only disposition-journal restart reconciliation

This staged service observes a separately keyed disposition journal after a
process restart. It has no product route, recovery executor, private-data
migration, inference request or production activation.

`DispositionReconciler` uses the already independently pinned
`DispositionPlanner`, its source copy reconciler and journal binding. The
source, target, manifests, origin dependencies, keys, namespace, profile and
distinct preparer/reviewer remain part of the binding. Caller input cannot
select a store, key, root, institution, provider or controller.

## Closed operations

- `inventory` takes no fields. It obtains current app-session authorization,
  observes the full copy/control dependencies and disposition journal, checks
  their common source snapshot and repeats the observations before returning
  physical metadata and a snapshot hash. Physical presence does not authenticate
  a record's content, recover an acknowledgement or authorize an action.
- `reconcile` requires that exact fresh snapshot hash, a plan ID, explicit
  plan ciphertext/plaintext hashes or paired nulls, and an explicit decision
  ciphertext hash or null. A supplied reference must identify the exact retained
  version. No reference is selected by similarity or recovered from a filename.

Every request needs a current authorized preparer/reviewer session, firm
permission, approved origin and CSRF token. Reconciliation authenticates an
exact supplied plan and, only when explicitly supplied, its exact review. It
compares all observations again, rereads the retained records and rechecks the
caller and immutable bindings before returning decrypted metadata.

## Distinct outcomes

| Situation | Outcome |
|---|---|
| No final plan publication, including retained temporary staging | `plan_not_observed` |
| Plan file present without independently retained plan references | `plan_references_unavailable` |
| Exact plan supplied; no final decision publication | `decision_not_observed` |
| Decision present but its reference not supplied | `decision_reference_not_supplied` |
| Exact plan and decision authenticated | `retained_disposition_reconciled` |
| Exact history authenticated but earlier planning context stale | `retained_disposition_reconciled_stale` |

Missing references stay missing. An observed ciphertext hash does not recreate a
lost response or plan plaintext hash. A missing decision reference withholds the
decision even when a matching final record exists. An accepted, rejected or
changes-required decision retains its exact original content and version.

Expiry or prior-reviewer/session changes can make history stale without
invalidating its existence. A fresh authorized reader may inspect that history;
its planning-review status is explicitly false. This neither renews the prior
copy authorization nor supplies independent review for a future operation.

Wrong versions, changed snapshots, conflicting links, symlinks, tampered
ciphertext, invalid bindings, a revoked caller, unavailable observations or
exhausted budgets withhold all decrypted history. Returned errors contain no
paths, credentials, raw exception text or partial plaintext. Observations are
bounded comparisons, never an atomic filesystem snapshot or a legal opinion.

## Preservation and limits

The service writes no journal, source, target or review. It never deletes a
temporary file, repairs a link, adopts a record, retries/resumes a copy, recovers
an acknowledgement, changes custody/enrollment or renews execution authority.
All original histories and ciphertext versions remain unchanged.

The existing 20-second workflow and 32-entry/1-MiB per-store physical inventory
limits remain. Every result says read only, planning only, non-atomic, fresh
independent review required and no production execution authorization. All
recovery/effect/acknowledgement flags remain false.

## Qualification

Offline cases exercise actual disposable sessions and encrypted records,
including lost responses, independent positive/negative reviews, missing/wrong
references, staging files, hardlinks/symlinks, ciphertext changes, source races,
late revocation, expiry and physical budgets. The additive opt-in
`qualify_disposition_journal.py` campaign freezes 52 outcomes across 52 fresh
processes on four owned ext4 Docker volumes. Four workers are actually SIGKILLed
before final publication or after durable plan/review publication but before
acknowledgement; an acknowledged-review control remains independently readable.
Read-only restarts preserve both published records and abandoned staging files.

Only tracked public source and invented identities are mounted. Native proof
does not establish power-loss durability, genuine operator appointments/key
custody, live/private restore, provider qualification, production activation or
the pending owner's legal review. Native, PR, independent-main, preservation
and product-readiness evidence remain separate.
