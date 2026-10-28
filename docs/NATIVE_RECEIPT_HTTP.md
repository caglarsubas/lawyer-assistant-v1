# Native authenticated receipt handoff and restart

This opt-in qualification uses fresh Linux Docker/ext4 volumes, invented
identities and synthetic controller metadata. It exercises the existing
unregistered receipt adapter over actual loopback HTTP, with the real local
session, account, origin, CSRF and firm-role checks. It opens only an empty
disposable SQLite identity store; no matter, document or operational identity
store is accepted or mounted.

Two frozen protocols cover retirement and rollback. Each uses two controller
processes and a receipt process, then cleanly exits and restarts the receipt
process with the same encrypted record, key, source bytes, profile and independent
pins. The two receipt workers verify the read-only nine-module package before
loading trusted host authentication. The original fourteen-module controller
package and all earlier source-pinned qualification remain unchanged.

Each protocol checks fifteen exact HTTP outcomes: readiness; create-only
retention; fresh re-observation; bad cookie, origin, missing CSRF and unrelated
role; query/body-pin rejection; wrong ciphertext pin; restart and unchanged
re-observation; separately authorized destination and window repairs; source
expiry or withdrawal; and preparer-session revocation. Negative requests must
perform zero controller reads and disclose no retained metadata. Successful
read operations must perform their exact fresh controller reads.

Every receipt request checks exact source bytes, the original encrypted record
and all four retained histories. Deliberate fixture repairs and revocations are
separate from the read-only observations; the campaign does not claim that
those intended transitions leave every anchor unchanged. Process accounting
travels over a private parent/child pipe, without a new debug endpoint. All
workers must exit cleanly and all generated volumes must be removed.

## Reproduce

```sh
backend/.venv/bin/python scripts/qualify_receipt_http.py \
  --base-image lawyer-assistant-api:long-page-quotes-v1 \
  --output /absolute/owner-only/new-native-http-report.json
```

Use a preloaded public dependency image; no pull or live `.env` is used. The
derived image includes current tracked public scripts, application source and
fixture configuration, with exact hashes. New public probe files are included
explicitly. No checkout-wide copy or ignored file is admitted. Actual container
posture is checked before execution: network `none`, no published ports or host
mounts, read-only root/package volume, nonroot runtime, no capabilities, private
IPC/PID namespaces, two CPUs, 1 GiB RAM and 64 processes. The four named volumes
are fresh, distinct, labelled and owned by this campaign. Only preparation uses
three explicit filesystem capabilities to initialize those empty volumes.

The output path must be new. Incomplete runs remain incomplete and exit nonzero.
Only aggregate statuses, counts, public source/image hashes and posture flags
enter the report; no cookie, password, key, private receipt or source payload is
published. See the [source-bound first report](evidence/native-receipt-http-2026-10-28.json).

## Scope and remaining gates

Thirty native receipt HTTP cases qualify these two disposable workflows. This
does not qualify in-flight revocation, process crashes or power loss, operational
key custody, genuine operator appointments, real inference, production
installation, legal review or owner acceptance. The next engineering slice is
bounded in-flight authorization loss and interrupted-publication/restart
qualification with disposable identities. Owner review remains pending.

Docker qualification stays opt-in. Lightweight report and wiring tests use the
existing candidate CI group. Preserve all 1,018 deployment methods, ten jobs,
worker ceilings, deadlines and fixed reserve floors. Exact-head checks, merge,
independent main checks and runtime/acceptance remain distinct evidence states.
