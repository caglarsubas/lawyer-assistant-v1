# Isolated manifest-integrity fix and fresh frozen qualification

F00-06 stays partial. This fix changes one source file in a newly generated,
disposable Linux package build. It does not install a backend, change a live model
store, activate a signed route/trust, use a signer or regenerate private analysis.
The owner's focused-analysis v3 review and independent public-key confirmation
remain pending. Earlier failed qualification and all its inputs remain unchanged.

## Source fix

`deploy/fixtures/manifest_integrity_patch.json` records four exact replacements,
the upstream commit, path and complete before/after SHA-256 hashes. The source is
the retained `675150d6ad2747df1e218ef59de9194bc4a7e538` snapshot, with the earlier
source lock and original license preserved. No upstream repository or original
source snapshot is edited. Only the new build's `manifest/manifest.go` changes.

The defect was in the shared manifest opener: a direct regular manifest blob had
no expected digest. Both the byte-returning and rewound-file readers calculated
its content hash but could return bytes under a different digest filename.

The isolated patch identifies a direct blob by its path in the explicitly configured
blobs directory. It requires a regular file with a complete digest filename, binds
the reader's expected hash to that filename and uses the existing digest comparison
before returning bytes or a file. Direct symlinks are rejected before opening their
targets, including links to another valid blob or identical bytes outside the store.
Ordinary named regular manifests keep their computed identity; an ordinary tag that
resembles a digest filename is not accidentally pinned. Existing checked named
manifest symlinks retain their behavior in the tested Linux environment.

The correction is shared by `ParseNamedManifest`, `ReadManifestData` and the
internal verified-file path. It adds no alias, fallback, download, repair or write
to a lookup. The raw parser versus server-normalization distinction from PR #209
still applies: these tests do not execute the HTTP resolver or a complete server.

## Fresh frozen tests

Twenty newly defined U2501–U2520 cases, the patch, harness, stager and ten Python
contract methods are frozen before any grading. The patch is frozen before the
same fresh suite runs against either source variant. Neither source variant is
adjusted after exposure.

The untouched baseline matches **13/20** expected outcomes and fails **seven**.
The isolated patch matches **20/20** on its first grading. The same case IDs,
expectations, harness bytes and source dependencies are used in both builds.
Complete first logs and source/build/image hashes are retained. An eleventh Python
contract rechecks both actual invented logs and rejects the failed baseline as
acceptance evidence. The ten original methods remain exact. No case, failure or
expectation is rewritten to obtain the passing result.

The fresh suite covers:

- Correct dash, bare and uppercase digest references, plus the verified-file path.
- Appended whitespace, same-size edits, replacement content, truncation and a corrupt
  unique prefix through the actual parse, byte and file readers.
- Missing blobs, malformed JSON and a digest-looking named alias that must not
  become fallback for a missing direct blob.
- Ordinary named content, formatting changes, digest-looking tags and checked named
  symlinks, preserving their computed-identity behavior.
- Direct links to another digest and to identical bytes outside the store; directories
  at a blob path; and unchanged scratch directory/content/link inventories.
- A named manifest with an absent model layer still parses. This deliberate boundary
  demonstrates that manifest integrity is not full artifact-store verification.

All source and inputs are public/invented. The small GGUF sentinel is explicitly
not a model. No client documents, real model artifacts or historical inference
allowances are used. The earlier Q2412 failed source/log/expectation stay exact.
The new success does not relabel that historical candidate as passed.

## Staging and evidence contract

`scripts/manifest_integrity_stage.py` has no downloader, subprocess runner, server,
application configuration or secret loader. It verifies the pinned prior source
lock and every upstream byte, then applies the one exact preimage patch for the
`patched` variant. Unknown variants, modified source, extra package files, changed
patch/cases/harness, linked inputs, duplicate patch context and existing/linked
destinations fail closed. The upstream source directory stays unchanged. Generated
files are owner-only, and the build receipt records each hash and the sole modified
upstream path. No arbitrary patch execution or fuzzy matching is provided.

`observe_log` validates a complete twenty-case Go JSON log, exact variant/readers,
unchanged scratch stores, unique result and completion events, and consistent
case/root/package outcomes. It can preserve the baseline's negative diagnostic.
`qualify_log` admits only the passing patched log. Missing, duplicate, skipped,
foreign, malformed, inconsistent or wrong-variant work cannot qualify. Frozen case,
harness, patch and prior source-lock hashes are embedded in the stager.

Both builds run once in a pinned Go 1.26.10 Linux/ARM64 compiler image with two CPUs,
2 GiB memory, 128 PIDs, a twenty-second test timeout and a 150-second operator bound.
Containers are nonroot, have a read-only root and source mount, no network/ports,
devices, credentials, Docker socket or private/runtime mounts. Only disposable
scratch is writable; its execution setting is declared before the run. Toolchain
downloads, module proxies, checksum service and CGO stay disabled. Scratch stores
and outside-link targets exist only inside that disposable test arena.

Reproduction uses `stage(explicit_public_source, new_destination, variant)` for
`baseline` and `patched`, then the documented isolated container with only
`MANIFEST_VARIANT` selecting the corresponding variant. Run
`go test -json -count=1 -timeout=20s ./manifest`, retain both logs and receipts,
and apply `observe_log` or `qualify_log` as appropriate. Full source, cases,
harness and compiler identity are in the [dated evidence](evidence/manifest-integrity-2026-10-24.json).

## Remaining qualification

This clears the scoped fresh Linux manifest-content regression. It does not qualify
the installed binary, complete HTTP/server behavior, executed weights or production.
Mutable hostile-filesystem races, hardlink/store-root isolation, concurrent changes,
config/layer presence and integrity, manifest-list/remote-model restrictions,
full-size hashing work and Windows behavior remain outside this package result.
A separately qualified read-only artifact store remains mandatory.

Next qualify the full disposable server/HTTP path, including its real digest
normalization and exact request/response behavior, with fresh frozen tests and
an explicit backend/build identity. Then qualify store isolation, complete artifacts,
full-size work, scoped relay/trust/restore and fresh durable native admission.
Independent public-fingerprint/runtime-pin confirmation remains required before
trust or native trials. Historical 502 cause, sustained five-job capacity,
reviewed corpus, legal correctness and production activation remain open.

All 413 deployment contracts and lint pass. Keep nine CI jobs, workers, caps,
coverage and all five timing reserves. Originals, encrypted bytes, exact evidence
versions, credentials, sessions, private review history, 31 earlier tracked edits,
912 retained source/configuration files and existing staged issuer/public candidate
remain exact. The provider repository and eight live services remain unchanged.
