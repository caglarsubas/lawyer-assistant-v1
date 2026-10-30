# Reviewed journal materialization and restored-copy verification

The staged service copies **opaque encrypted planning-journal records** into an
independently pinned empty destination. It adds no product route, live backup
scheduler, production key enrollment, restore activation or authority renewal.
Original receipt sources and planning journals stay read-only. Genuine custody,
operator appointments and the owner's legal review remain separate gates.

## Separate execution authorization

A readiness decision is a prerequisite, not permission to execute. Prepare a new
purpose-specific operation (`backup` or `restore`) with the exact readiness plan
and review references, the complete ciphertext manifest and an independently
retained manifest hash. Trusted wiring pins destination identity, scope, key,
account profile and distinct preparer/reviewer. Request bodies cannot provide
paths, keys, identities, alternative namespaces or execution commands.

Record operation plans and decisions create-only under a fifth, separate control
key and namespace. The assigned independent reviewer must explicitly authorize
the disposable copy, using exact plan hashes and closed decision/reason codes.
Recheck the original readiness actors and window as well as the execution actors
and window. Execution cannot extend the prerequisite's remaining review window.
Revoked sessions, changed roles, changed source or candidate versions, mismatched
manifests and expired reviews block execution without changing retained history.

The destination must be empty. Interrupted staging, unknown files, unaccounted
links, partial copies and existing complete copies cannot be silently excluded,
overwritten or treated as a fresh destination.

## Create-only publication

1. Reobserve exact source and destination versions with fresh app authentication,
   CSRF, origin and firm-role checks against a disposable, empty identity store.
2. Publish an encrypted, deterministic **consumed intent before copying any data**.
   Another invocation cannot reuse the operation to resume or overwrite a copy.
3. Read each source record with its exact hash, ownership, mode, link and file
   version checks. Copy ciphertext unchanged using exclusive, fsynced publication.
   Check authorization, source freshness and the expected destination prefix
   before and after each copied record.
4. Verify the complete destination inventory and manifest, then publish an encrypted
   completion receipt with exact intent and destination-version references.
5. Recheck destination observations and all relevant actors/windows before a
   success acknowledgement. If acknowledgement is withheld, retain every committed
   intent, record and receipt. Never roll back, delete or automatically resume.

Observation is non-atomic. The inherited limits remain bounded: at most 32 source
entries and 1 MiB per observed store, bounded physical scans, a 20-second workflow
timeout and at most a 300-second review window. Interruptions may leave a partial
or complete destination without an acknowledged completion. That is a review
condition, never automatic permission to retry or infer durability.

## Restore origin and read-only verification

A restore binds the independently retained **backup operation, decision, intent
and completion references**, not merely a similar filename or matching content.
Its source must be that backup's pinned destination. A fresh destination, readiness
review and execution review are required. Preserve the backup's control history,
readiness history, source records and ciphertext while restoring to a new stage.
Neither namespace's history is imported into the other's authority controls.

Read-only verification requires exact caller-retained intent and completion
references and compares the full destination to the frozen manifest and exact
completed inventory version. Changed bytes, replacement inodes, modes, links,
extra entries or staging withhold decrypted history and fail verification.
Missing completion references remain unknown. Verification cannot reconstruct a
lost acknowledgement or authorize installation, trust migration or record adoption.

A historically exact backup may remain byte-verifiable after its old review or
source context becomes stale. Report that staleness separately; fresh restore
review does not renew the old decision. Current caller authorization is always
required. Ciphertext equality leaves content authenticity and legal meaning
unassessed; graph applicability and legal conclusions receive no approval here.

## Qualification

```sh
backend/.venv/bin/python scripts/qualify_journal_materialization.py \
  --base-image lawyer-assistant-api:long-page-quotes-v1 \
  --output /absolute/owner-only/new-materialization-report.json
```

The frozen native matrix covers 36 outcomes across 36 fresh Linux worker
processes: backup/restore round trip, distinct execution decisions, rejected
readiness/old-decision reuse, exact read-only verification, stale reviews and
revocation. One real SIGKILL occurs after the first target record is fsynced and
published on a running kernel; verify exit `-9` and EOF without acknowledgement.
Reopening the same bindings preserves the consumed intent and partial copy;
re-execution is refused and missing completion remains unknown.

Use four fresh owned ext4 volumes, read-only packages and root filesystem,
network none, no host mounts or ports, nonroot runtime without capabilities,
two CPUs, 1 GiB memory and 64 processes. Verify the immutable receipt/controller
exports before app authentication in every worker. Remove generated containers
and volumes. No private case, provider or inference is used. See the
[source-bound native report](evidence/native-journal-materialization-2026-10-30.json).
This qualifies the declared process interruption, not power-loss/disaster recovery.

Keep all existing test identities, ten CI jobs, worker ceilings, deadlines,
bootstrap guards and reserve floors. Move the unchanged lightweight 64-case
readiness-context group to spare frontend capacity, after its existing workers
exit. New materialization tests use ARM review capacity; no existing case is
omitted or duplicated. Require exact-head and independent-main qualification.

Next: bounded read-only interruption/restart inventory and reconciliation of
consumed intents and completion references, with independently retained pins.
Automatic repair/resume, genuine custody, live/private operational backup and
restore, activation and legal approval remain unqualified.
