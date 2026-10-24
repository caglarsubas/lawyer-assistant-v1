# Windowed verification candidate

The original PR #212 reader missed the frozen 20-second pre/post target. Its
source, reports, failed initial unit candidate and negative result stay retained.
This candidate changes how the model bytes reach SHA-256, keeping the same full
digest and snapshot checks. It is an opt-in library strategy, not a runtime rollout.

## Implementation boundary

`strategy="stream"` remains the default and retains v1 proof compatibility.
`strategy="windowed"` maps the model using `ACCESS_READ` in fixed 16 MiB windows.
SHA-256 consumes each mapping directly, avoiding an extra Python bytes buffer.
Every mapping closes before the next one opens, including consumer exceptions.
It does not map the entire 8 GiB file, cache a previous digest, merge concurrent
requests, skip unchanged regions, or reuse a different job's verification.

The first mapped candidate passes 25 fresh boundary cases and its single pre/post
job in 9.38 seconds, but all five concurrent jobs reject with `changed`. Only two
of twelve requested observations produce proof. The original reader completes all
twelve on that same fresh corpus, with concurrent jobs reaching 24.00 seconds.
Fast rejected jobs are not successful verification or target attainment.

A separate fresh 2 GiB diagnostic stops all five workers on their first rejection.
It localizes the failure to the final manifest entry check: the guest inode differs
from the earlier observation while other recorded identity fields match. No field
is ignored or rounded. The source had closed blob descriptors between initial
hashing and final namespace checks, leaving inode identity dependent on reopening.
The diagnostic localizes that lifecycle gap; it is not a universal filesystem-cause
or hostile-host qualification.

`strategy="windowed-pinned"` retains each validated original blob descriptor through
the final checks, using a temporary duplicate for hashing. At most eighteen blob
descriptors plus four directories remain open. Final checks compare both the live
descriptor and current namespace entry with the saved identity, retaining every
field and read-only check. Success, rejection and duplication failure close the
descriptors. Actual namespace replacement still rejects. V3 proofs bind the pinned
strategy and exact retained/rechecked descriptor count; older v1/v2 observations
cannot satisfy a pinned request. The default remains the original stream strategy.

Only model content is mapped. Manifest/config collection and text-layer streaming
keep their existing limits, including the 1 MiB text cap. The larger mapping
window does not enlarge accepted metadata or layer sizes. Checks run before each
read/map and before hashing. The parent still bounds worker startup, waiting and
final proof acceptance. A mapping error rejects the operation without stream
fallback. Cancellation, incomplete results and worker exits cannot become proof.
Kernel-blocked I/O and privileged host mutation remain outside an absolute
userspace cleanup guarantee.

All existing kernel read-only, owner/mode/link, descriptor-relative access,
closed-inventory, manifest/config/layer digest, byte-budget, before/after identity,
directory and final entry checks remain. Remote/list/adapter/projector stores and
aliases remain prohibited. These are observations of a trusted sealed snapshot;
they do not establish an indefinitely immutable or hostile-host-safe store.
The GGUF header check still does not establish tensors, model usability or weights.

The opt-in worker returns v2 proofs binding `windowed-v1`, model digest, mapped-byte
count and exact window count. The supervisor requires a proof matching the requested
strategy. Existing v1 reports remain verifiable; a v1 proof cannot satisfy a mapped
request. Each 8 GiB observation must hash all artifacts and map all 512 model windows.

## Fresh frozen evaluation

Before native grading, freeze candidate source, a separately retained copy of the
original PR #212 source, controller, policy and initial contract methods. Twenty-five
new cases use a different fixture layout and content: multiple text layers, exact/
short/partial mapping windows, tail/middle corruption, missing text, remote model,
short descriptor/size, oversized text, inert injection text, links/aliases, writable
root, cancellation after startup, expired/aggregate budgets, reordered rootfs,
duplicate config keys, boolean schema and invalid strategy.

The large model uses fresh deterministic bytes from seed 20261025. It is fully
written and fsynced, with a different digest from the earlier fixture, zero tensors
and arbitrary padding. It is not a runnable model. There is one actual campaign
per profile: candidate first, then the exact original reader, on the same fresh
snapshot. Each profile performs one pre/post job and five concurrent pre/post jobs:
twelve complete hashes of an 8 GiB model plus metadata/text. No performance case
is rerun or retuned after its first measurement.

Keep the prior 20-second per-job pre/post target, 60-second shared hard job limit,
75-second wave limit and 128 MiB per-worker RSS target. Both profiles use the same
two-CPU/768 MiB/96-PID Linux ARM64 container, no network/ports/capabilities/devices,
read-only fixture/controller/root mounts and bounded writable scratch. The order
is fixed and creation/prior reads heat caches; results are warm-cache observations,
not cold-storage or order-independent benchmarks. Large I/O stays local. CI runs
small contracts and revalidates the retained original actual reports.

The first unit campaign's mapping-boundary test assumed 4 KiB alignment, which is
invalid on this Mac. That failed run and original test stay retained. The correction
uses the host's allocation granularity; candidate/controller/policy and all expected
outcomes remain unchanged. It changes no production window size or target.

Any measured target miss stays visible. Even a pass qualifies only this synthetic
warm-cache verification subset. There is no app/provider install, live-store input,
private matter input, provider request, inference, key use or trust activation.
Independent runtime-pin/fingerprint confirmation, native-hook integration, sustained
research load, hostile mutable-store isolation and legal/production acceptance
remain separate gates. Owner focused-analysis v3 review remains pending.

## Descriptor-retaining and VM-local profiles

The descriptor-retaining candidate is frozen against a second corpus: thirteen new
native cases, eight initial contracts, source/controller and seed 20261027, with
unchanged 16 MiB windows, two CPUs, 768 MiB and time/RSS limits. All thirteen native
cases pass, including eighteen-blob retention and real worker descriptor exhaustion.
All twelve full-size observations now complete. The single job takes 10.12 seconds;
concurrent jobs reach 36.07 seconds. The paired original reader reaches 37.72 seconds.
The host-bind profile therefore still misses 20 seconds. Its negative result remains
retained; the successful single job does not qualify the concurrent target.

A separately frozen storage profile uses a newly owned ext4 volume inside the
Docker VM, fresh seed 20261028 and identical verifier source/workload/resources.
One preparer owns that empty disposable volume, exits and is removed before the
read-only verification container starts. It has only CHOWN added for final ownership;
the runtime has no added capability. No app/provider/data volume is mounted.
Preparation and measured profiles retain separate identities and receipts.

Pre-start capability/path normalization rejections are retained. A preparer OOM
at 768 MiB is also retained; no benchmark had started. Preparation is repaired by
fsync/eviction after every 64 MiB and renaming the staging model instead of copying
it, with no higher memory limit. A final complete stored-digest read precedes the
benchmark. Cache labels mean a prior read preceded measurement, without explicit
benchmark eviction; they do not claim that all 8 GiB remain resident. Exact requested
paths, Docker Desktop's exact `/host_mnt` rendering and a bidirectional nonsecret
nonce validate the controlled receipts mount. Unknown mappings fail closed.

The first actual VM-volume campaign completes twelve observations for each profile.
The candidate takes 8.30 seconds for one pre/post job and at most 18.94 seconds for
five concurrent jobs (18.95-second wave). Peak worker RSS is 45,412 KiB. All 6,144
model windows and 103,079,231,760 artifact bytes are verified in the candidate profile.
The paired original reader takes 8.88 seconds singly and reaches 24.07 seconds
concurrently. The candidate meets the frozen 20-second target **only for this tested
warm VM-local volume profile**. This is one campaign, not a hardware-wide latency SLA.
All owned containers/volumes are removed after receipts, source identities, read-only
proofs and nonce confirmation are retained. The code remains unregistered/inactive.

The host-bind misses, descriptor-lifecycle rejection and earlier PR #212 miss remain
visible. Cold-storage behavior, sustained use, native inference/research-job capacity,
sealed-volume import/restore, signed runtime/trust confirmation and legal acceptance
remain open. See [dated evidence](evidence/windowed-verification-2026-10-24.json).
