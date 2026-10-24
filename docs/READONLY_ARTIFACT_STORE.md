# Read-only artifact-store observation

This unregistered verifier observes a **sealed, single-model snapshot**. It does
not open the installed store, modify the frozen execution hook, activate a route
or trust candidate, start a server, or perform inference. Its snapshot is a narrow
admission prerequisite, not complete provider or legal qualification.

## Boundary and evidence

The snapshot root contains exactly `blobs`, `manifests` and `manifests-v2`.
Both alias directories are empty. Every blob is referenced by the pinned manifest;
unreferenced content, named aliases and alternate fallback are rejected. A root
path must resolve without links. Directory descriptors use `O_NOFOLLOW`, and
child access is relative to open directory descriptors. Directories require the
current UID and mode 0700; files require that UID, mode 0600, regular-file type,
one link and the blob directory's device. Restrictive modes alone do not pass:
Linux `fstatvfs` must report a kernel read-only mount on every opened object.

The exact schema-2 manifest, config and every layer are streamed through SHA-256.
Descriptor types/sizes and the closed inventory must agree. Manifest/config JSON
is bounded to 64 KiB and rejects duplicate keys. There is one local GGUF model
layer, at most 8 GiB; optional template/system/params/license layers each have a
1 MiB bound. At most sixteen layers and eighteen blobs are accepted; aggregate
hashed bytes are at most 9 GiB. Duplicate/cyclic references, remote configs,
manifest lists, adapters/projectors and unknown config fields fail closed.
An optional config rootfs list must match the exact layer digests in order.

The model's first 24 bytes receive only GGUF magic/version sanity checks.
Tensor structure, numerical weights, tokenizer, context limits, model usability,
execution identity and inference output remain unqualified. The synthetic large
fixture has zero tensors and arbitrary padding; it is not a runnable model.

File identity includes device, inode, mode, owner, link count, size, modification
and change times. It is checked around streaming, against the current entry and
again after all artifacts. Directory identities and inventories are rechecked.
Proofs apply only to that observation window. A host with write access to a bind
source, privileged remount, compromised kernel or adversarial filesystem is
outside the seal's trust boundary. These checks do not prove an indefinitely
immutable store or close every possible mutable-store race. Production requires
an independently trusted snapshot/host boundary and guarded pre/post use.

## Verification budgets

One spawned worker streams 1 MiB at a time. It collects only bounded manifest and
config bytes. The caller owns the absolute deadline, including startup and final
result acceptance; a cancelled, late, malformed or partial response is rejected.
There is one attempt and no fallback. Cleanup terminates/kills and reaps the child;
ordinary userspace cancellation is tested. An uninterruptible kernel I/O task is
not an absolute wall-time guarantee. Reports expose fixed codes and hashes/counts,
without paths, model text, credentials or private matter data.

The frozen qualification uses 38 small cases, a fully written/fsynced 8 GiB
deterministic synthetic model blob, one pre/post verification job, then five
concurrent pre/post jobs. Each job shares a 60-second deadline, individual worker
limits never exceed 60 seconds, the wave limit is 75 seconds, and the separate
pre/post target is 20 seconds. Peak worker RSS target is 128 MiB. The 20-second
target reserves ten seconds of the older 30-second execution-hook envelope, but
passing it does not qualify that hook or leave a proven inference allowance.

The disposable Linux/ARM64 container has two CPUs, 768 MiB memory, 96 PIDs, no
network/ports/devices/capabilities, a read-only root and fixture/controller mounts,
and bounded writable scratch. No live/provider/private mounts enter it. Fixture
creation and the first read heat caches: measurements are **warm-cache**, with
no cache eviction or cold-disk claim. Hashing twelve snapshots is not five
simultaneous research or inference jobs. Local-only large work is not added to CI;
CI revalidates the retained actual reports and runs small contracts without Docker.

The original and corrected source/test candidates, failed first unit run, policy,
controller, first native case report and budget measurements are retained. Expected
outcomes and performance thresholds are fixed before grading. Used cases cannot
serve as fresh unseen acceptance for a later implementation.

Production integration, hostile mutable-store isolation, sustained native load,
signed relay/trust/restore and independent public-fingerprint confirmation remain
separate gates. Owner focused-analysis v3 review remains pending. Originals, exact
evidence versions and confidential review history are outside this campaign.
