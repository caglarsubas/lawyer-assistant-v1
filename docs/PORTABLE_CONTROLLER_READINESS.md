# Portable controller package and enrollment readiness

This is a **source-only, unregistered stage**, with explicit mock backend transport.
It neither installs a provider nor enrolls trust. F00-06 remains partial; the owner’s
focused-analysis v3 review remains pending. Existing live services, credentials,
encrypted originals, evidence versions and review history are outside this work.

## Build and independent inspection

`scripts/build_guarded_controller_stage.py` exposes `build(destination)` and
`archive(root, destination, approved_manifest_sha256)`. Use a fresh destination
inside an owner-only staging parent. The public output contains fourteen Python
modules and three manifests. The exclusive ZIP is deterministic, uncompressed,
fixed-timestamp, source-only, and outside the closed package directory. There is
no archive extractor, runtime installer, provider registry change or activation.

The prior eight route/package modules remain byte-exact. Six additional modules
carry the artifact verifier, sealed volume, V2 control journal, guarded controller,
manifest inspector and readiness API. Only their import statements are rewritten;
AST comparison checks the retained implementations. The source provenance manifest
records exact repository inputs. Import-only portability does not qualify native
weights, backend behavior, legal correctness or deployment equivalence.

Before importing **any** stage module, a separately trusted copy of
`controller_stage_manifest.inspect_stage` must check the stage against an
independently approved manifest SHA-256 and expected filesystem owner. Do not take
the approval hash or inspector from an untrusted archive. A self-consistent
manifest alone is not approval. Import checks are a portability inventory check,
not a Python sandbox. The operator must protect the approved mount/path against
replacement for the entire import and use interval.

Inspection requires the exact closed inventory, public directories 0755/files
0644, expected ownership, single links, no symlinks, stable bounded file reads,
matching metadata/module hashes and a limited static import inventory. Package
files are bounded to 1 MiB each/8 MiB total. At readiness/runtime inspection,
actual kernel read-only mounts are required; mode bits alone do not establish
read-only storage. Build-time inspection explicitly permits a writable staging
directory and confers no readiness. Do not import into a writable stage and allow
Python bytecode caches to mutate the inventory; the isolated driver uses `-I -B`.

Pinned compatible dependencies are `cryptography>=44,<47` and `httpx==0.28.1`.
The ZIP contains no interpreter, wheels, weights or dependency installer. An
offline dependency supply chain and deployment package remain separate work.

## Read-only binding and public enrollment preflight

The package’s `readiness.assess` takes an explicit external package approval,
model root, V2 `Journal`, immutable `Binding`, public consumer-trust directory and
independent expected issuer/fingerprint/reviewer/provisioner/confirmation hash.
All objects must belong to the same imported package namespace. No API key,
signer password or private signing key is a preflight input.

The result exposes bounded gate codes for package, dependencies, binding, model
and enrollment. It checks exact journal/operation/record/volume/pin identities,
sealed ancestry and current external-anchor agreement; the bounded V3 verifier
checks actual read-only content against the record. A second journal/anchor check
rejects revocation or context changes during the check. The original 20-second
model-verification limit remains unchanged.

Enrollment checks **existing public records only**. A missing candidate or an
absent/unapproved confirmation is `waiting`. Mismatched identity, unexpected
material, invalid/expired confirmation, self-review expectation or any revocation
marker is blocked. The confirmation bytes must match an independently supplied
hash, expected reviewer and candidate fingerprint/issuer. Reviewer and provisioner
labels must differ. Those caller-supplied labels do not themselves authenticate
a human or prove an independent review: an authenticated operator workflow must
supply the independent expectations. The existing confirmation expires after
24 hours. The preflight never invokes provisioning, confirmation, signer loading,
revocation, inference, network requests or control-journal mutation.

`ready_for_disposable_mock_validation` describes a consistent read-only snapshot,
**not** trust enrollment or execution authorization. Results always retain false
flags for real provider identity, executed-weight qualification, installation,
native execution, production and legal qualification. They do not carry bearer
secrets, paths, record identifiers, raw exceptions or private case content.
Current authorization, anchor, ancestry, nonce and release checks remain mandatory
at effect boundaries; cached readiness is never a future grant.

## Qualification and remaining gates

The frozen native campaign passes 29/29 cases with two Uvicorn loopback servers,
five actual HTTP requests, two explicit mock model sends and two signed responses
verified by the retained consumer. Tests cover altered/extra/missing code,
symlinks/hardlinks, an approved-but-forbidden import, wrong approval, writable
package, missing/mismatched/expired/revoked public enrollment, wrong binding,
unsealed/foreign journal, revocation during verification, forbidden privileged
helpers, signed byte preservation, old-receipt rollback and real-backend rejection.

Only invented public records, ephemeral in-memory signing keys and a 65,561-byte
zero-tensor model fixture are used. Read-only checks leave all metadata unchanged
except the case that deliberately injects an external revocation. The isolated
process imports no application or engine modules. Two CPU/768 MiB, no external
network, no host ports, cleared environment, a read-only root and three new owned
ext4 volumes bound the campaign. All disposable containers/volumes are removed.
Host bind ownership differed on macOS: the initial preparer rejected before any
acceptance case; its receipt is retained. The corrected preparer copies approved
public sources to ext4 with explicit ownership before read-only reader use.
An earlier unit fixture used a consumed synchronous mock response; only that
invented fixture changed to an async byte stream. Expectations and production
modules were not relaxed. First-attempt acceptance evidence and earlier failures
remain distinguishable.

Eleven added contract methods retain the 29-case policy (28 unit-adapted cases;
actual writable-mount rejection is native-only), deterministic archive checks,
import-only equivalence, standalone imports and negative report replay. CI uses
small fixtures and retained evidence; the live service and large-model benchmarks
are not repeated. Existing CI jobs, workers, caps and coverage remain unchanged.

Next prepare a bounded **operator evidence packet and read-only enrollment
reconciliation**, without generating or confirming real trust. Independent real
issuer/runtime-pin confirmation, authenticated review workflow, installation,
executed weights, completions/context/tokenizer/truncation, sustained five-job
native research load, long-lived capacity/retention, cold/host-bind profiles,
historical 502 root cause and legal/production acceptance remain open. See
[dated evidence](evidence/portable-controller-2026-10-25.json).
