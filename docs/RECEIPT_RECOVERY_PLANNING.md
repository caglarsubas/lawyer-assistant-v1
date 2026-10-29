# Interrupted-publication inventory and reviewed recovery planning

The staged service inventories physical receipt metadata without decrypting
source receipts, reading controllers, repairing entries or changing any retained
history. It has no registered product route or production enrollment operation.
Source, journal, independent pins and assigned users are trusted wiring, never
request paths, keys or user-supplied role claims.

## Physical inventory

Each observation checks the independently pinned context, scope, root identity,
key fingerprint and disposable account profile. Two bounded scans must agree;
membership, inode, link count, ownership, mode, size, timestamps and exact
ciphertext digest participate in the snapshot. Names are represented by scoped
entry digests; published record identifiers remain metadata. Failed scans
release no partial inventory. Fresh account/session authorization is required
before, between and after scans.

| Observed condition | Interpretation and permitted planning action |
|---|---|
| Single-link record with envelope shape | Fresh authorized re-observation remains necessary |
| Unclaimed staging entry with envelope shape | Preserve staging for review |
| Record and staging name sharing one two-link inode | Preserve both names and investigate interrupted publication |
| Empty or incomplete staging bytes | Preserve the partial entry |
| Unexpected record envelope | Quarantine without mutation |
| Unaccounted links, unexpected topology or unverifiable linked envelopes | Preserve and escalate |

Matching bytes alone do not establish a hard-link relationship. Envelope shape
does not establish authenticity, completed publication, durability or authority.
Unknown names, unsafe permissions/ownership, symlinks and nonregular entries fail
closed. Each scan admits at most 32 entries and 1 MiB in aggregate, with a
two-second cooperative scan budget inside the existing 20-second action budget.
This is a repeated observation on a live filesystem, not an atomic snapshot or
a hard real-time storage-I/O guarantee.

## Independent review and encrypted history

A preparer selects one to eight entries from an exact snapshot. Selection must
include every observed name sharing a selected inode. The service derives a
closed set of nonexecuting actions and binds the complete observed inventory,
source/profile pins, actual preparer session, independently assigned reviewer,
and a 300-second validity window.

Plans and decisions are encrypted under a separate journal key in a disjoint
owner-only namespace. Purpose-specific authenticated encryption and exact
ciphertext/plaintext hashes prevent plan/decision substitution. Publication is
create-only; a deterministic decision identifier prevents overwriting a review.
Original source ciphertext is never decrypted. All earlier journal records
remain exact when new plans and decisions are appended.

The real local session, cookie, CSRF, origin, current account and firm-role checks
run against an empty disposable identity store. A different session of the
preparer cannot act as the independently assigned reviewer. GET, missing or
duplicate admission headers, unrelated users, changed roles, revoked sessions
and mismatched pins cannot grant access. Final authorization loss withholds the
response even if an encrypted record was committed; that record is preserved.
Expiry is checked again after publication and before acknowledgement: a newly
expired plan or review returns no successful acknowledgement, preserving the
committed ciphertext for later authorized reconciliation.

Decisions are **accept**, **changes required** or **reject**, each with a closed
reason code. Accept means **reviewed for metadata planning** only. It grants no
repair, deletion, orphan adoption, controller execution, enrollment or activation
authority. Changed membership, bytes, links, versions, actors or expiry require
a fresh plan and independent review. Authorized historical inspection marks
stale reviews explicitly and preserves their original encrypted versions.

## Qualification and limits

```sh
backend/.venv/bin/python scripts/qualify_receipt_recovery.py \
  --base-image lawyer-assistant-api:long-page-quotes-v1 \
  --output /absolute/owner-only/new-recovery-planning-report.json
```

The opt-in campaign repeats the previous 34 frozen HTTP outcomes, including six
actual SIGKILL exits, then runs 26 frozen planning outcomes and two additional
fresh inventory reads. Both retirement and rollback modes inventory eight actual
interruption leftovers: five single-link records, one unclaimed staging entry
and a two-name interrupted link pair. A separate synthetic addition makes nine
entries and must stale the prior accepted plan. Four encrypted journal records
per mode preserve preparation, review and fresh re-review history.

Real disposable identities supply independent review; no operational identity,
private case, provider or inference call is used. The campaign retains four
fresh owned Linux/ext4 volumes, network none, no host mounts or ports, read-only
packages/root, nonroot runtime, no runtime capabilities, two CPUs, 1 GiB memory,
64 processes and existing time budgets. Only generated resources are removed.
See the [source-bound native report](evidence/native-receipt-recovery-2026-10-29.json).

Routine CI adds focused tests to existing candidate capacity. All prior reports,
source pins, 1,018 deployment identities, ten jobs, worker ceilings, deadlines and
fixed timing-reserve floors remain. Exact-head CI, guarded merge and independent
main qualification remain separate from installation and runtime acceptance.

The next boundary is encrypted planning-journal interruption/restart and
read-only reconciliation, including uncertain decision acknowledgement. No
automatic repair or journal adoption is qualified here. Power-loss durability,
real operator appointments, independent operational key custody, provider/native
inference and production activation remain unassessed. Owner legal review is
still pending; engineering cannot supply it.
