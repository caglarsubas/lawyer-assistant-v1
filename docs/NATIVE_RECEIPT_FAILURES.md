# Native receipt authorization loss and interrupted publication

This opt-in campaign qualifies failure handling using invented identities and
synthetic metadata. The original nine-module receipt export, fourteen-module
controller export and all earlier reports remain unchanged. Both packages are
verified on a kernel read-only mount before trusted host authentication loads.
No fault controls are exposed through HTTP or registered in the product.

Two frozen retirement/rollback protocols use actual loopback HTTP and the real
cookie, origin, CSRF and firm-role checks against empty disposable identity
stores. Each protocol starts fifteen distinct worker processes, including two
controllers, and makes seventeen receipt HTTP attempts. Ten receipt workers
exit cleanly; three are deliberately stopped with actual SIGKILL. Private,
one-shot parent/child pipe barriers have bounded waits and closed messages.

## Authorization boundaries

- Revoke the preparer's session after the first fresh controller read during
  re-observation. Reject the request without returning retained metadata.
- Revoke after the second read during retention. Reject before publication;
  no encrypted record or staging entry is created.
- Revoke after successful encrypted publication, before the final host check.
  Reject the response, preserve the committed ciphertext and require a new
  password-authenticated session before re-observation.

Each revocation changes the actual disposable session store. A new session is
created through the real password check; restoring or replaying the revoked
session is not allowed. Fresh reads retain their own actor identity and do not
convert historical observations into current authority.

## Process interruption boundaries

The qualification-only child observes the unchanged publication implementation
at actual filesystem calls. It pauses before the create-only hard link, after
that link but before staging unlink, and after directory fsync. The parent then
kills the worker and verifies exit `-9` and a lost HTTP acknowledgement.

| Boundary | State after restart | Explicit retry |
|---|---|---|
| Before link | No published record; preserve the orphan staging entry | Create the previously absent record without changing the orphan |
| After link | The two-link record is unverifiable; return no metadata | Conflict; preserve both linked names and exact bytes |
| After directory fsync | Independently pinned, single-link ciphertext can be re-observed with fresh authorization | Conflict; no overwrite |

Restart uses exactly the same root identity, key, source bytes, profile and
package pins. Read-only checks and rejected requests preserve every existing
entry, including link counts, permissions, ownership and ciphertext. Every
request preserves all four controller histories and the original source.
Intended session revocation and new-session creation remain separate from
those immutable histories. No automatic orphan deletion or repair is performed.

## Reproduce and evidence

```sh
backend/.venv/bin/python scripts/qualify_receipt_faults.py \
  --base-image lawyer-assistant-api:long-page-quotes-v1 \
  --output /absolute/owner-only/new-native-failure-report.json
```

Use a preloaded public dependency image. Only tracked public source and explicit
probe files are copied, with exact hashes; no `.env`, private host mount or
operational data is accepted. Four fresh labelled Linux/ext4 volumes, network
`none`, no host ports, a read-only root/package mount, nonroot runtime, no
capabilities, two CPUs, 1 GiB RAM and 64 processes retain the prior posture.
Preparation alone initializes empty volumes with three explicit capabilities.
Cleanup removes only this campaign's generated containers and owned volumes.
Output is an aggregate report; failed attempts remain incomplete.

See the [source-bound report](evidence/native-receipt-faults-2026-10-29.json).
The frozen matrix contains 34 HTTP attempts, six intended SIGKILL exits and
six in-flight session revocations across both modes. Controller read counts,
process identities, clean exits and filesystem states must match exactly.

This is process-crash qualification on a running kernel, not power-loss or
storage-hardware durability qualification. Real appointments, independent key
custody, production installation, provider inference and owner legal review
remain unassessed or pending. The next engineering slice is read-only
interrupted-publication inventory and explicit reviewed recovery planning,
preserving orphan evidence without automatically promoting an incomplete record.

Docker remains opt-in; lightweight report and wiring regressions use existing
candidate CI capacity. All 1,018 deployment methods, ten jobs, worker ceilings,
deadlines and fixed reserve floors remain. Exact-head qualification, merge,
independent main qualification and runtime acceptance remain separate gates.
