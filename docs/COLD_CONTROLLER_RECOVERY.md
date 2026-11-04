# Cold controller recovery with original fixture bindings

The read-only loader reconstructs an operator preview controller from retained
invented fixture files. A separate seeding interpreter exits; the supervisor
retains only independently supplied pins and client test metadata. Every new
controller uses Python's spawn start method and reloads stores, keys, original
handoff and actor bindings from disk. No previous controller object survives.

Trusted wiring supplies the descriptor hash, original profile and database
identities, exact handoff and binding hashes, assigned actors, source identity,
origin and approved package manifest. The canonical descriptor cannot supply its
own approval. Required files have bounded reads, exact ownership and permissions,
single links and canonical paths. Keys, six store identities and exact ciphertext
inventories are checked before and after reconstruction. Missing or changed
inputs fail closed; nothing is adopted, repaired, rekeyed or generated on reload.

The account database is opened with SQLite `mode=ro`, using an existing `Store`
instance interface without invoking its schema-creating constructor. The original
key-maintenance marker guard, session and firm role checks still run. Both a live
maintenance marker and a dangling marker link prevent cold recovery. A native attempted schema write must
receive SQLITE_READONLY. Only explicit fixture session revocations in the test
supervisor change the invented account database. Recovery creates no sessions.

The original PreparedHandoff is reconstructed directly. Its original preparation
time, five-minute expiry, prepared actor, assigned reviewer, receipt and unsigned
provenance stay exact. Recovery never calls the preparation factory, extends
expiry, bootstraps credentials, enrolls trust or replays a request. Each explicit
request must pass current cookie, Origin, CSRF, role and actor checks again. A
fresh read-only comparison still requires an independent checksum entry.

Run `python scripts/qualify_native_cold_controller.py --base-image IMAGE
--output NEW_REPORT.json` against an already loaded public dependency image.
The additive campaign uses the unchanged mount/isolation controller: fresh
labelled Linux/ext4 volumes, read-only source/package/root filesystems, non-root
runtime, no added capabilities, no egress, no host mounts or published ports,
two CPUs, 1 GiB and 64 PIDs. It removes only its owned containers, volumes and
generated tags. CI verifies retained evidence offline and starts no native job.

The revised native candidate qualifies 30 outcomes across 12 distinct interpreter
processes, with three actual SIGKILL interruptions and 12 real HTTP requests.
Interruptions cover idle, admitted partial-body and completed-observation states.
Each listener closes; the interrupted request releases no response. Missing
independent pins, changed descriptor/handoff/profile/database identity, expired
handoff and revoked preparer prevent listener release. Revoked reviewer cookies
fail after a fresh cold load. Original keys and six stores stay byte/metadata
exact; the original 745-source restart evidence remains unchanged. The new
report binds 753 source files and the predecessor report hash.

This qualifies disposable controller-process loss with the same retained volume
identities. Host reboot, changed volume inodes, joint account-store rollback,
genuine operator appointment/key custody, external checksum-channel authenticity,
production deployment and legal acceptance remain unqualified. The owner's
focused-analysis-v3 review remains pending.
