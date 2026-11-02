# Read-only interruption/restart reconciliation

The staged `CopyReconciler` observes a pinned materialization context after a
restart. It adds no application route or live backup operation. Only `inventory`
and `reconcile` are accepted. Bindings come from trusted local wiring; request
bodies cannot select paths, keys, accounts, namespaces or commands.

## What a result establishes

| Result | Meaning |
| --- | --- |
| `review_reference_not_supplied` | The plan is authenticated; any observed decision publication remains unauthenticated without its exact reference. |
| `intent_not_observed` | No intent publication was present in the bounded observation; this is no authorization to execute. |
| `intent_reference_not_supplied` | An intent publication was observed but its exact ciphertext reference was not supplied. |
| `consumed_intent_without_completion` | The supplied intent authenticates and matches the plan/decision; no completion publication was observed. The destination can be empty, partial or an exact ciphertext copy. |
| `completion_reference_not_supplied` | A completion publication was observed; exact destination bytes alone do not authenticate a completion. |
| `retained_completion_reconciled` | Exact plan, review, intent, completion and destination versions authenticate; the historical execution context remains current at the check. |
| `retained_completion_reconciled_review_stale` | The retained completion authenticates, but its execution review/source context is stale. It is not renewed. |

Observed ciphertext hashes can be supplied explicitly on a subsequent read.
Decrypting a bound intent can calculate its plaintext digest, but never recovers
an acknowledgement. Completion must be supplied separately and must match the
original completed destination inventory, including file identity/version.
The response contains metadata and exact references, not document contents.

## Confidentiality and freshness

Every read requires current application session, firm role, CSRF and origin
verification. Distinct preparer/reviewer, source, destination, manifest, profile,
key and namespace bindings remain in force. Restore reconciliation preserves
its original backup references and both histories. Missing or unverifiable
origin evidence cannot silently qualify a dependent restore.

Capture source, journal, target and control inventories before and after the
read, under one 20-second workflow budget; require the caller's exact snapshot
hash for reconciliation. Each physical store remains limited to 32 entries and
1 MiB with bounded scans. The observations are non-atomic. Any changed snapshot,
conflicting publication/link, wrong reference, revoked caller, timeout or malformed
record withholds all partial history and observations. Historical review expiry
is reported separately from current read authorization.

There is no write, resume, repair, cleanup, overwrite, adoption, authority renewal,
key enrollment or trust migration. Even a complete destination with a consumed
intent is insufficient without an authenticated completion. Fresh independent
review is required for a subsequent operation. Ciphertext equality does not
establish document authenticity, legal meaning, power-loss durability, production
activation or owner legal approval.

## Qualification

The additive offline suite exercises partial and exact destinations, missing and
wrong references, stale execution review, fresh caller revocation, racing changes,
malformed/link-conflicted publications and dependent restore history. Preserve
all existing frozen scripts, fixtures and evidence reports byte-exact.

```sh
backend/.venv/bin/python scripts/qualify_journal_copy_restart.py \
  --base-image <public-dependency-image> \
  --output /absolute/owner-only/fresh-copy-restart-report.json
```

The frozen native campaign declares **41 outcomes in 41 fresh Linux processes**,
including one real SIGKILL after the first destination record is published.
Reconciliation runs in subsequent processes with real disposable app sessions.
Four fresh owned ext4 volumes, no host mounts/ports/network, read-only packages
and root filesystem, nonroot execution, two CPUs, 1 GiB and 64 processes bound
this drill. Check exact source and history bytes before/after every read and
remove the generated containers/volumes. No private case or inference is used.
The [source-bound native report](evidence/native-journal-copy-restart-2026-11-02.json)
records the qualified 41 outcomes; 51 additive offline cases also pass.
Native qualification is recorded separately from PR/main CI and live operation.

Keep ten CI jobs, two-worker ceilings, all 1,018 deployment identities, all
139 frontend files/10,532 cases, original caps and reserve floors. Additive backend
checks must pass exact-head and independent-main execution/coverage gates before
closing the engineering task. Broader readiness and the owner's pending analysis
review remain separate.

Next: independently reviewed recovery disposition planning from exact retained
restart observations. Planning must not execute or repair a partial destination.
Genuine appointments/custody and production recovery stay explicit owner gates.
