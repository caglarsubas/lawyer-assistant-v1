# Disposable sealed model-volume transfer and signed metadata handoff

This staged candidate extends the opt-in VM-local ext4 profile from
[windowed verification](WINDOWED_STORE_CANDIDATE.md). It has no application,
provider route, inference dispatch or automatic startup registration. The original
stream reader and immutable execution hook retain their existing behavior.
These model-only bundles never include matter documents, databases, reviews,
credentials, private keys, trust stores, control journals or sessions.

## Storage and approval boundary

An operator supplies an approved canonical index SHA-256 independently of the
package. The strict index contains only a manifest digest, unique content-addressed
artifact digests and sizes, total size and content identity. Unknown fields,
relative paths, duplicate artifacts, links, extra files and unexpected package
roots reject. At most eighteen artifacts, an 8 GiB model and 9 GiB total apply.

An external controller must bind each operation to its actual volume and authorized
root, ensure distinct newly created destinations, and enforce writer exit followed
by a genuine kernel read-only mount. A path string, signed message, file mode or
package-declared volume identifier alone does not establish that boundary. The
candidate retains descriptors and checks file/namespace identities, ownership and
permissions throughout the copy. It cannot defend against a hostile privileged
host that can replace mounts, keys, code or the control journal.

`sealed_volume.export_bundle` verifies an existing read-only store, hashes every
copied byte, fsyncs bounded chunks and publishes the index last in a fresh package.
`import_bundle` accepts only a read-only package, creates an exclusive destination
reservation and a fresh generation, verifies and copies into a private staging
directory, then atomically renames the snapshot. It produces **Prepared**, never
automatic activation. Cancellation after preparation revokes the operation.

The separate live SQLite journal has FULL synchronization, exclusive creation,
read-only inspection and explicit transitions:

`Copying → Prepared → Sealed → Revoked`

Earlier states may also be revoked. A later read-only reader freshly verifies the
complete destination before sealing. A copy crash leaves partial staging
quarantined. A rename crash leaves a complete orphan quarantined in Copying;
discovery does not promote it. Recovery inspection does not repair, reset, replay
or advance state. The trusted controller is responsible for retaining this live
journal independently of data backups; rollback of the journal by a privileged
operator is outside this qualification.

Restore means a fresh destination, operation and generation, retaining the sealed
parent and exact approved content identity. It never overwrites a model volume,
restores nonce state, copies a journal from a package or accepts a revoked parent.
Old signatures cannot admit the new generation or destination. The parent is
checked when the restore is created; this slice does not qualify cascading
revocation or rollback recovery of the control plane. Those are explicit gates
before any runtime integration.

## Signed relay boundary

`sealed_relay_handoff` uses a distinct `sealed-store-handoff` message kind under
the existing Ed25519 contract. It binds the exact provider identity certificate,
tenant/model/route/context pin, approved index, content, destination, operation,
generation, receipt and complete verification proof. The provider-identity issuer
and storage-handoff issuer have independently supplied trusted public keys.
Expected identifiers, nonces, keys and runtime pin come from trusted caller
context, never from the package or received message.

The existing opaque proof-envelope codec forwards exact signed bytes. The receiver
verifies strict fields, signatures, current identity and lifetime, durably reserves
a single-use challenge, freshly re-verifies the read-only store, then checks
identity, key availability, expiry and control state again. A crash after nonce
reservation burns the nonce across process restart. Replays, revoked operations
or keys, changed identities, wrong destinations and cross-kind certificates reject.

The result explicitly authorizes **metadata handoff only**. Neither this result nor
a retained report is a native-execution grant. This slice does not run an HTTP
relay server or send provider requests. Actual staged route/hook integration,
independent real issuer-fingerprint/runtime-pin confirmation, trust activation,
installed/executed weights and native inference remain separate gates. Disposable
test signing keys exist only in memory; retained evidence contains public keys.

## Qualification and reproducibility

Freeze `deploy/fixtures/sealed_handoff_policy.json`, candidate source and controller
before execution. The disposable worker is `scripts/sealed_handoff_native.py`;
its caller must enforce the documented mount, environment and ownership boundary.
Fresh deterministic GGUF-shaped padding contains zero tensors and no real weights.
Transfer has a separate 90-second/9-GiB budget; each complete verification retains
the 20-second/9-GiB hard limit. This is not a 20-second end-to-end import SLA.

Run only owned new volumes and pinned local dependency images, with no network,
ports, runtime mounts or inherited process environment; use two CPUs, 768 MiB and
96 PIDs. Only preparation adds CHOWN. Remove the writer before each read-only
reader. Preserve failures, interrupted copies and negative receipts. Never retry a
measured case or raise a target after seeing its result. Remove only test-owned
containers and volumes, with ownership checks.

CI uses small fixtures and signed-report replay, not large model I/O. Unit adapters
that emulate read-only checks are explicitly separate from native mount evidence.
No tests or existing workflow jobs, workers, coverage or deadlines are removed.
Private originals, exact evidence versions and review history stay outside this
campaign. Owner focused-analysis v3 review remains pending.
