# Independently reviewed journal backup/restore readiness

This staged, unregistered service prepares and independently reviews **metadata
readiness for a disposable copy qualification**. It does not execute a backup,
restore, repair, key transfer, trust enrollment, activation or acknowledgement
recovery. The encrypted planning journal and the original source store remain
read-only. Actual operational backup/restore remains a separate gate.

Trusted wiring independently supplies four disjoint namespaces: original receipt
source, planning journal, candidate destination and readiness review journal.
Pin every root identity, context, scope, key fingerprint, disposable account
profile and assigned preparer/reviewer. The candidate's key must already match
the independently pinned planning-journal key; no key is copied or provisioned
by the service. Keep the readiness review key separate from both original
receipt and planning-journal keys. Named paths, matching
ciphertext and possession of a key confer no destination trust.

## Observe, prepare, review, inspect

1. Authenticate the current real disposable app session, origin, CSRF and firm
   permissions. Only the specifically assigned preparer and independent reviewer
   can access the staged service; accounts containing private application records
   remain prohibited by the unchanged authentication adapter.
2. Perform bounded double physical scans of the original source, planning journal
   and candidate. Compare complete versioned observations again before responding.
   Preserve exact names, ciphertext hashes, byte counts, link topology and unknown
   conditions. No source or candidate record is decrypted. Envelope shape and
   matching hashes leave content authenticity and legal meaning unassessed.
3. Classify an empty destination or exact complete ciphertext copy separately.
   A nonempty partial/mismatched copy, interrupted staging, cross-directory hard
   links, unexpected entries or an empty source cannot prepare a readiness plan.
   All entries remain intact; nothing is silently excluded or normalized.
4. Require the caller's exact observation hash. Freeze the complete inventories,
   source/destination bindings, manifest, accountable actors and 300-second window
   in a create-only encrypted readiness plan under the separate review key.
5. Require the assigned independent reviewer's fresh session, exact plan ciphertext
   and plaintext hashes, closed decision and reason codes. Reobserve the source
   and candidate and recheck both actors before and after publication. Acceptance
   means only `reviewed_for_disposable_copy_qualification`; all execution, trust,
   custody, adoption and acknowledgement flags remain false.
6. Inspect history only with exact caller-retained plan/decision references and
   fresh current authorization. Missing review references are explicitly unknown,
   never assumed to mean no review exists. Changed inventory, actor/session,
   permissions or expiry makes a retained review stale. Historical ciphertext and
   original decisions are preserved. A withheld publication acknowledgement never
   becomes success through inspection.

A newly selected namespace requires independently supplied new pins and a new
plan with fresh independent review. The old namespace and its history remain
available under their original binding. Old review hashes cannot approve the
new plan or candidate. This service has no destination-selection authority.

Observations remain non-atomic. Failure responses withhold inventories, plans,
reviews, exception text, paths and credentials. No raw query, filesystem path,
key, actor identity or trust pin can be supplied through an operation body.

## Qualification and limits

```sh
backend/.venv/bin/python scripts/qualify_journal_backup_readiness.py \
  --base-image lawyer-assistant-api:long-page-quotes-v1 \
  --output /absolute/owner-only/new-copy-readiness-report.json
```

The opt-in Linux/ext4 campaign starts with both an empty target and a preexisting
exact copy. Its frozen matrix covers **38 outcomes in 38 fresh worker processes**:
actual disposable authentication, independent review, fresh read-only inspection,
changed staging, stale snapshots, explicitly repinned new candidates, rejected
old review reuse, expiry, fresh re-review and revoked sessions. Each worker
checks both read-only immutable packages before loading host authentication,
performs one bounded operation and verifies clean exit. Original source and
planning ciphertext and every earlier readiness record remain exact. Synthetic
candidate copies and changes are explicit fixture actions outside the service.

Use four fresh owned volumes, network none, no host mounts or ports, a read-only
root and package mount, nonroot execution without runtime capabilities, two CPUs,
1 GiB memory and 64 processes. Remove generated containers and volumes. No private
case, live provider, inference, production runtime or genuine key custody is used.
This does not repeat or extend the previous controller/mode or SIGKILL campaign.
The source-bound report is [retained here](evidence/native-journal-backup-readiness-2026-10-30.json).

Focused regressions use measured review-job capacity. Restore backend headroom
first by removing unchanged deployment slices 4/9 from the backend. The measured
frontend placement passed tests but retained only 11 seconds; keep slice 4 after
frontend workers, move slice 9 after review workers and return the single build
to recovered backend capacity. Every one of the 1,018 deployment identities still runs once. Preserve all
ten jobs, original deadlines, worker ceilings, complete frontend discovery,
checksum-verified bootstrap, zero automatic retries and fixed reserve floors.
Qualify exact-head CI and independent main CI separately before completion.

Next: separately reviewed bounded backup materialization and read-only restored
copy verification, with independently retained manifest and destination pins.
Readiness acceptance cannot authorize that action. Operational custody,
appointments, disaster/power-loss recovery, deployment, provider/native inference
and the owner's pending legal review remain separate outstanding gates.
