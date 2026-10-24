# Isolated complete-server build and metadata HTTP qualification

F00-06 stays partial; owner focused-analysis v3 review and independent issuer-key
confirmation remain pending. This slice builds and starts a complete disposable
server from pinned public source. It does not install that binary into the live
provider, use client documents, call completion/generation endpoints, activate
trust or update any analysis or review decision.

## Complete production build

The public archive at commit `675150d6ad2747df1e218ef59de9194bc4a7e538` contains
1,513 files. Every original file is verified against its Git blob identity and a
SHA-256 inventory. There are no submodules or symlinks. The original archive,
license, source tree and earlier failed qualification remain intact.

Only `manifest/manifest.go` changes as production Go code, using the exact retained
four-replacement integrity patch. The full original `go.mod` and dependency versions
stay unchanged. An initial dependency acquisition stops before testing because its
checksum-service cache is unwritable and the upstream `go.sum` lacks required
checksums. That failed receipt is retained. A separate disposable acquisition
directory permits checksum-cache writes and obtains 31 additional checksum lines
through `sum.golang.org`, preserving every original checksum. The derived `go.sum`
is the second changed build-input path; no dependency version is substituted.

Acquisition uses public source/dependencies only, with no case data or credentials.
The subsequent `go mod verify` and complete production build run **without network**
using the verified cache, read-only source/module inputs and pinned Go 1.26.10
Linux/ARM64 image. CGO is enabled. The exact build command and original/derived
source inventories, checksum additions, image and binary hash are frozen in
`deploy/fixtures/server_http_build.json`; the derived lock is retained separately.
The result is the complete production CLI/server binary, not a reduced package
module, rewritten handler or mocked transport.
Native llama-server/MLX runner executables are separate components and are not
built or qualified here.

The build label `isolated-http-675150d-integrity1` is deliberately separate from
the installed server's reported version. Build identity and a reported HTTP version
do not establish trusted release provenance, hardware attestation or executed weights.

## Fresh frozen HTTP campaign

Twenty-six new S2601–S2626 cases, the build/fixture identity, controller and twelve
contract methods are frozen before the first server campaign. There is one actual
campaign, one request per case and no case retries, repairs or expectation changes.
Bounded startup readiness probes are recorded separately. All **26/26** cases pass
on first grading. The complete server starts and handles real loopback HTTP, then
terminates on SIGTERM with exit code zero and no forced kill.

The campaign exercises:

- Version/build-label response, named-model listing with its exact manifest digest,
  and empty running-model inventory before and after the metadata work.
- Named, colon, dash, bare, prefix and uppercase references to the same artifact.
  The server's actual digest normalization accepts these forms, even though raw
  `types/model.ParseName` treats a colon reference as an ordinary model/tag.
- Missing names/digests, a corrupt regular manifest and a direct blob symlink.
  The two integrity cases return the expected HTTP 500 JSON errors.
- A digest-looking named alias that must not become fallback for an absent blob.
  A legacy named manifest works by name, while its unmaterialized digest is 404.
- Malformed JSON, missing model input, wrong method, unknown route, invalid runner,
  cloud-disabled named requests and rejected cloud digest references.
- Invalid GGUF metadata and verbose metadata for the zero-tensor control.

The GGUF control has invented metadata, **zero tensors and no model weights**.
It is not runnable as a language model. No real model, prompt, corpus, tenant key
or provider credential is an input. Metadata parsing is distinct from loading a
runner or executing inference. Both `/api/ps` observations contain no models.

Reference equivalence compares only the predeclared metadata fields in the frozen
case catalog: model info, details, parameters, template, system, messages,
capabilities, renderer, parser, template source and thinking metadata. This is a
specific field-equivalence result, not whole-response byte equality. Every full
request and response keeps its original independent wire hash and exact bytes;
timestamps, modelfile presentation and manifest summaries are not silently erased
from evidence. No response-signature or completion-identity qualification is inferred.

## Isolation and retained evidence

The runtime container has no network connectivity, published ports, privileges,
capabilities, host devices, Docker socket or private/runtime mounts. It runs as nonroot,
with a read-only root, binary, controller and synthetic fixture store. Only bounded
scratch and an initially empty receipt directory are writable. Resource and mount
settings are inspected before startup. The child receives an explicit environment
with cloud and pruning disabled; it inherits no host/provider credentials.

Normal server startup can create its own disposable local key under its tmpfs HOME.
This is not an existing issuer/provider key, is not enrolled or trusted, and is
discarded with the container. Raw server logs remain protected and are never copied
into Git or roadmap data. Existing staging keys and the unconfirmed public candidate
remain unchanged. The owned test container is removed after its stopped state is
verified; unrelated containers and services are untouched.

The controller permits only the frozen metadata paths plus the explicit wrong-method
and unknown-route controls. It rejects generation/admin/external targets before
connection, uses one direct loopback connection per request, bounded uncompressed
responses, a two-second request budget, and no proxies, redirects or retries.
Startup and shutdown have separate bounds. Actual child executable hashes before
and after HTTP work match the produced binary; synthetic fixture directory/content/
link inventories remain identical on the read-only mount.

`qualify_report` rechecks all exact wire hashes, ordered case/request bindings,
status and metadata predicates, startup/version evidence, child shutdown and scope
flags. A thirteenth contract revalidates the retained actual invented campaign.
The original twelve methods and helpers remain exact. Partial, tampered, wrong-build,
wrong-request or scope-promoting reports cannot qualify. The synthetic wire/report
fixtures contain no private matter data. Raw logs and acquisition receipts remain
in protected operator storage.

## Reproduce and remaining gates

Acquire and verify the complete pinned public source; preserve it separately.
Apply only the retained manifest patch and the verified derived checksum lock in a
new build directory. `verify_build_inputs` checks the complete original/derived
trees and the two declared changed paths. Acquire dependencies in a separate public
build stage, then verify/build offline using the frozen command and compiler image.
No downloader or builder runs on import.

Prepare a new synthetic fixture directory with `prepare`, freeze its inventory and
the executable hash, and copy only the controller, strict JSON helper and frozen
case/build declarations to the runtime. `run_campaign` refuses ordinary host or
implicit execution. The inspected disposable container starts the fixed binary
at `127.0.0.1:11579` inside its own network namespace. Preserve the first report,
wire receipt and private log; call `qualify_report` without replaying requests.

All **426 deployment contracts** and lint pass. Nine CI jobs, workers, caps,
coverage and five timing reserves remain unchanged. All 919 retained source/
configuration files, 31 earlier tracked edits, eight live services, originals,
encrypted bytes, exact evidence versions, credentials, sessions and confidential
review history remain exact. The provider repository is unchanged.

This qualifies the complete disposable build and its tested metadata HTTP subset.
It does not qualify completion behavior, context/tokenizer/truncation handling,
executed weights, the installed backend, full-size/concurrent artifact verification,
complete config/layer integrity or legal/production acceptance. Next qualify the
read-only complete artifact-store boundary and verification work budgets, then
scoped relay/trust/restore and fresh durable native admission. Independent public
fingerprint/runtime-pin confirmation remains mandatory before trust or native trials.
Historical 502 cause, sustained five-job capacity and owner v3 review remain open.
See [dated evidence](evidence/server-http-2026-10-24.json).
