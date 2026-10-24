# Isolated backend reference, parser and manifest-store qualification

F00-06 remains partial. Owner focused-analysis v3 review and independent trust
confirmation remain pending. No live service, provider route, signing key, model
store, private document, analysis or review decision is an input to this work.

## What was built

`scripts/qualify_backend_store.py` prepares an inert Go test module from explicit
public source directories. `deploy/fixtures/backend_store_sources.json` pins two
upstream commits and every copied byte:

- Release tag `v0.32.14`: `d67ad83426633195089509347ffd4fe795120198`.
- Previously inspected staged snapshot: `675150d6ad2747df1e218ef59de9194bc4a7e538`.

The tag matches the previously observed HTTP version string. This does **not**
identify the installed executable's build provenance. The tag/commit observation
is an unsigned source acquisition, not a release-signature or binary attestation.

The unmodified `types/model`, `manifest` and `envconfig` package files are compiled
with a generated, stdlib-only module. Server route/image source and upstream module
requirements are hash-checked as context but are not compiled. This is package
qualification, **not a complete backend/server build or HTTP endpoint test**.
Source inventories, licenses, generated module/test hashes and compiler image ID
are retained. Extra Go files, changed source, linked/hardlinked inputs, oversized
files and existing/linked destinations are rejected before staging. The builder
does not download source, start subprocesses, run a server or import app settings.

The two builds use Go 1.26.10 in an explicitly pinned local compiler image, meeting
both upstream declared Go minimums. Containers have no network, published ports,
host networking, devices, Docker socket, capabilities, privileges, runtime mounts
or credentials. Source is read-only; only disposable scratch is writable. Execution
is nonroot, with two CPUs, 2 GiB memory, 128 PIDs and a 20-second test deadline;
the operator also bounds the complete compile/run step. Toolchain downloads,
module proxies, checksum service and CGO are disabled. All stores contain invented
JSON and an explicitly invalid-as-a-model GGUF sentinel; no model is loaded.

## Frozen outcomes and retained failure

Fifteen invented Q2401–Q2415 cases and nine contract methods are frozen before
grading. The first container launches encounter non-executable temporary mounts;
neither runs a test case. Their blocked logs stay retained. Only the disposable
executable scratch mount is corrected; source, cases and expectations stay exact.

Each profile then runs its first actual grading once. Release: **15/15 expected
outcomes**. Candidate: **14/15**, with **Q2412 failing**. The failed candidate,
expected rejection, first log and all original inputs remain unchanged. The
qualification reader rejects the complete failed candidate log. A tenth contract
keeps that actual invented failure from becoming an accepted qualification.
Passing engineering CI verifies this rejection; it does not qualify the backend.

| Observation | Release packages | Candidate packages |
|---|---|---|
| `sha256:<64 hex>` parsing | Ordinary model/tag | Ordinary model/tag |
| Colon reference with only a matching manifest blob | Not found | Not found |
| Colon reference with a different named alias | Other digest returned | Other digest returned |
| `sha256-<64 hex>` with only a legacy named manifest | Not found | Not found |
| Dash or bare full digest with a matching manifest blob | Not found | Matching digest |
| Unique 12-character prefix | Not found | Matching digest |
| Ambiguous prefix | Not found | Rejected |
| Tampered regular blob under a digest filename | Not found | **Other digest returned; expected rejection fails** |
| Named manifest with a missing model layer | Manifest parses | Manifest parses |

The newer resolver operates on the default-tag model-name expansion and looks for
the manifest itself in `blobs/sha256-<hex>`. A colon spelling becomes model `sha256`
plus a digest-valued tag, so it does not enter that resolver. The older source
performs ordinary named-manifest lookup. This provides a source-level explanation
consistent with the prior 404; it does not prove which code the live binary runs.

For the tampered regular blob, the newer package computes the actual content
digest but does not compare it to the digest filename on that path. The harness
detects a mismatch; the frozen expected rejection fails. No upstream implementation
or expectation is patched to hide this failure. A parsed manifest also does not
establish that referenced layers exist, are intact, or were executed. Every test
observes identical scratch-store directory/content inventories before/after lookup.

## Reproduce safely

Acquire the exact public files in the source lock into separate new directories;
preserve upstream licenses. Check the retained source hashes before staging. In a
protected operator context, import `qualify_backend_store.build`, supplying one
explicit source directory, a new destination and `release` or `candidate`.
The returned build receipt identifies every generated byte. It starts nothing.

Run only `go test -json -count=1 -timeout=20s ./qualifier` in the sandbox described
above, setting `QUALIFIER_PROFILE` to the matching profile and `OLLAMA_MODELS` only
through the harness's fresh scratch stores. Use the compiler image ID recorded in
the dated evidence. Retain stdout/stderr and the exact container intent; no automatic
retry or case adjustment is provided. `check_log` requires every unique case and
its successful event, the expected result, unchanged store and one successful
package termination. Failure, skipped/partial/duplicate/foreign results, wrong
profile, missing case inventory or malformed/oversized JSON cannot qualify.

The checked-in candidate log contains invented data only. Its required outcome is
rejection by the qualification reader. It is never a substitute for a new acceptance
suite after a future source or dispatch change.

## Remaining gates

The retained staged hook uses the colon spelling and stays inactive. Existing
frozen hook/route inputs are preserved; no alias is materialized in the live store
and no runtime dispatcher is changed. Neither source profile qualifies the current
immutable execution contract. Candidate lookup success with another spelling is
insufficient in the presence of the retained integrity failure.

Next prepare a separate source-level integrity fix and explicit full-digest wire
contract, with fresh frozen adversarial tests and complete server/HTTP qualification
in a disposable build. Qualify a read-only artifact store, linked-file boundaries,
manifest/config/layer verification and full-size work budgets. Independently confirm
issuer public fingerprint and runtime pin, then qualify scoped relay/trust/restore
and fresh durable native admission before any inference trial. No historical
inference allowance, synthetic signature or source-tag match supplies these gates.
Installed backend identity, executed weights, historical 502 cause, sustained
five-job capacity, legal correctness and production activation remain open.

All 402 deployment contracts and lint pass. CI jobs, workers, caps, coverage and
five required timing reserves remain unchanged. Originals, encrypted bytes, exact
evidence versions, credentials, sessions, private history, 31 earlier tracked edits,
staged issuer material and the unconfirmed public candidate remain exact. See the
[dated evidence](evidence/isolated-backend-store-2026-10-24.json).

Primary source: [release parser](https://github.com/ollama/ollama/blob/d67ad83426633195089509347ffd4fe795120198/types/model/name.go),
[release store](https://github.com/ollama/ollama/blob/d67ad83426633195089509347ffd4fe795120198/manifest/manifest.go),
[candidate resolver](https://github.com/ollama/ollama/blob/675150d6ad2747df1e218ef59de9194bc4a7e538/manifest/paths.go),
[candidate verification](https://github.com/ollama/ollama/blob/675150d6ad2747df1e218ef59de9194bc4a7e538/manifest/manifest.go).
