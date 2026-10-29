# Planning-journal interruption and restart reconciliation

The staged reconciler reads encrypted recovery-plan and decision history after
an interrupted process. It has no registered product route, mutation operation,
repair executor, adoption capability or operational enrollment endpoint.

## Exact read-only context

Trusted wiring independently pins the journal root identity, key fingerprint,
context, scope, account profile, source-pin digest and assigned preparer/reviewer.
A restart must supply those same bindings. Observing a directory or possessing
a similarly named record cannot provision or renew trust.

Every inventory or reconciliation uses real current account/session, origin,
CSRF and firm-role checks against an empty disposable identity store. Bounded
double scans cover both the original source store and the planning journal.
Reconciliation requires the caller's exact source and journal snapshot hashes;
the complete observations must still agree before a response is released.
Changed files, membership, links, source versions or authorization withhold
cached inventory and decrypted metadata. Observations remain non-atomic.

Known plans require their independently retained ciphertext and plaintext hashes.
Original source receipts are never decrypted. A matching plan can locate its
deterministic decision identifier, and a fresh journal observation can identify
the decision's exact ciphertext. Purpose-bound decryption, closed schemas,
exact plan references and accountable reviewer identity must all validate.
The decision digest is explicitly labelled as observed in that snapshot; it is
not represented as a previously acknowledged or independently pinned digest.

## Interrupted outcomes

| Observation after restart | Reconciliation result |
|---|---|
| Target not observed; unclaimed staging may remain | Preserve all entries; staging remains unattributed |
| Target shares an interrupted hard link or has unverifiable topology | Withhold decrypted history; preserve both names |
| Single-link plan exists but prior exact references are unavailable | Preserve metadata; require fresh preparation |
| Known exact plan exists, decision not observed | Report retained plan history without assuming a decision |
| Known plan and authenticated matching single-link decision exist | Inspect retained decision metadata with fresh authorization |
| Source, session, roles or time window no longer match | Mark the retained decision stale; preserve original history |

Absence in an observation does not prove a record never existed. Matching bytes
do not establish publication completion, recovered acknowledgement or authority.
Reconciliation never restores a lost success acknowledgement, deletes an orphan,
unlinks a pair, rewrites a decision or automatically renews review. A fresh plan
and independent review remain required for subsequent recovery work. An explicit
new preparation/review uses new create-only identifiers and preserves older
ciphertext; a duplicate decision remains a conflict.

## Native qualification

```sh
backend/.venv/bin/python scripts/qualify_planning_journal.py \
  --base-image lawyer-assistant-api:long-page-quotes-v1 \
  --output /absolute/owner-only/new-journal-restart-report.json
```

Both retirement and rollback protocols stop real plan and decision publication
at actual syscall boundaries: before link, after link, and after directory fsync.
The parent verifies the boundary, kills the process with SIGKILL, requires exit
`-9` and EOF without a success acknowledgement, then opens the same bindings in
a fresh process. Each mode uses 25 distinct journal processes, six intentional
kills, nineteen verified clean exits and thirteen fresh read-only processes.
The frozen matrix covers 44 outcomes in total, 88 journal API attempts and 76
acknowledged responses. Twelve operations deliberately lose acknowledgement.

Further cases cover repeated reads, a stale journal snapshot, explicitly added
synthetic source/staging entries, session revocation, historical access, expiry,
fresh independent re-review and duplicate decision rejection. Every read checks
source and journal bytes/link counts and all four retained controller histories.
Intended synthetic additions and account/clock changes remain separate actions.
The original encrypted source and prior journal ciphertext remain exact.

See the [source-bound native report](evidence/native-planning-journal-restart-2026-10-29.json).
All earlier reports and immutable receipt/controller exports remain unchanged.
The campaign uses disposable identities and invented metadata only: four fresh
owned Linux/ext4 volumes, no host mounts or ports, network none, read-only root
and packages, nonroot runtime, no runtime capabilities, two CPUs, 1 GiB memory,
64 processes and the existing time budgets. Generated containers and owned
volumes are removed; no private runtime, case, provider or inference is used.

Focused tests use the existing review CI job's measured reserve, preserving the
candidate group, all 1,018 deployment identities, ten jobs, worker ceilings,
deadlines, verified bootstrap and fixed reserve floors. Exact-head checks,
guarded merge, independent main checks and preservation receipts remain separate.

The initial PR run passed its tests but failed timing-reserve qualification:
history retained 29 seconds and final-release retained 26, below their fixed
30-second floors. Frontend retained only 32 seconds. Cancel that run and retain
the [measured observation](evidence/planning-journal-ci-headroom-2026-10-29.json).
Move unchanged contract slices 4 and 9 before the backend remainder, human-review
tests into review capacity, and workspace tests after PostgreSQL races. Every
group still runs once, sequentially within the existing worker ceilings and
its original timeout. Preserve all 1,018 method identities, the complete x86
frontend suite, ten jobs, bootstrap verification and reserve floors. Updated
placement assertions reuse the same methods. Previous bootstrap evidence stays
bound to its historical workflow; fresh exact-head/main receipts must qualify
the current layout.

This qualifies process interruption on a running kernel. Power-loss durability,
operational key custody, genuine appointments, installation, native/provider
inference and legal qualification remain unassessed. Owner review is pending.
Next: independently reviewed journal backup/restore readiness and copied-namespace
qualification, preserving both histories without implicit trust migration.
