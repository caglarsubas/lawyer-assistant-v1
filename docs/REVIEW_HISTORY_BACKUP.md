# Review-history backup/restore and cross-instance recovery

This unregistered disposable service extends the anchored operator-review path.
The existing app cookie/session/RBAC, origin/CSRF, assigned-subject and firm guards
remain mandatory. Request JSON supplies validated IDs and exact hashes; storage
paths, keys, authority scope and target configuration remain server-side.

Backups contain exact logical review rows, original handoff/decision bytes,
parent links and audit frames. They exclude account stores, credentials, client
documents, keys and independent anchors/intents. Fernet encrypts each bounded
snapshot. A separately retained manifest pins the encrypted and plaintext hashes,
journal/scope and exact current head. Keys and manifests remain outside the
encrypted backup retention root. No content or key is returned over HTTP.

`backup` requires a new request ID and explicitly observed current head. It holds
the independent journal lock while capturing a fully anchored consistent state,
rechecks the actor at commit/reply boundaries, and retains both bundle and manifest
exclusively. Duplicate or interrupted IDs cannot overwrite existing bytes.
An interrupted blob without its manifest stays retained and unusable; a fresh
authorized request uses a new ID. Backups are capped at 64, plaintext at 4 MiB
and ciphertext at 8 MiB. Original model verification and HTTP budgets remain.

`restore` requires the backup ID, exact manifest hash, current independent head
and a new attempt ID. It validates encryption, scope, full audit/lineage and the
independently retained intents against that head. An older backup cannot rewind
newer history. Source loss/corruption is handled without opening or overwriting
the source journal. Restoration creates a new private stage with fixed SQLite
schema and exact original record bytes, then revalidates it before retaining its
receipt. Anchors, intents and keys are never restored from the bundle. The source
and any earlier successful or interrupted attempts remain unchanged.

`restore_status` first observes intent/receipt hashes without mutation. A caller
must pin both before receiving a verified result. Another instance can reconcile
a lost acknowledgement. An interrupted attempt remains incomplete and retained;
a new explicit attempt may restore the same exact snapshot. No replay, automatic
resume, target activation or renewed review approval is inferred. Restored decisions
retain the original actors, timestamps, source versions and staleness. A fresh
re-review remains a separate authenticated action and decision.

All instances serialize journal writes, restoration and recovery through the
same independently retained file lock/anchor. Qualification uses separate OS
processes and shared disposable identity/journal stores, including duplicate
prepare/backup/restore races and recovery of a different worker's interrupted
commit. Current sessions/roles are rechecked. This does not qualify production
PostgreSQL/IdP revocation fencing, distributed admission or real operator appointments.

The external-storage profile uses four independently named/mounted ext4 volumes:
read-only model/package, working journals/restores, independent keys/manifests/
anchors, and encrypted backups. Distinct named volumes qualify retention separation
on this host, not separate physical media or off-host disaster recovery. Loss of
keys, independent controls or the identity store, privileged joint rollback and
production key-custody/rotation remain separate qualification gates. No real
enrollment, installation, inference, private case use or legal approval occurs.
The owner's focused-analysis v3 review remains pending.

Both frozen storage profiles complete the same 26 cases, each through 57 actual
worker servers and 155 HTTP requests with at least two distinct processes per
case. The separate-volume profile is the release evidence. Each profile runs once
on fresh volumes under two CPUs/768 MiB, a read-only root, cleared environment,
no external network/host ports/runtime mounts, and the original model budget.
All four owned containers and seven fresh volumes are removed; raw inputs/results
from both profiles remain retained. Case expectations and test method bodies are
unchanged. The 585-contract suite and affected storage/report checks pass, with
full lint and shell syntax validation. CI unit scratch now uses the existing
bounded 1 GiB tmpfs policy; the complete discovery runs once with the same nine
jobs, workers and deadlines. Native durability stays separately qualified on
ext4. See the [dated evidence](evidence/review-history-backup-2026-10-25.json).
