# Read-only backend identity and immutable-reference inspection

F00-06 stays partial and owner analysis v3 review stays pending. This slice observes
the local Ollama listener/process/executable and metadata reference lookup. It does
not activate the staged hook/route/trust, use a signer, change provider settings,
load/unload a model, send a prompt or run inference. Prior encrypted issuer material,
the independently unconfirmed public candidate and existing runtime secrets stay exact.

## Frozen qualification before live inspection

Freeze twelve fresh invented I2401–I2412 outcomes and ten contracts before first
grading or live collection. Cover resolved/rejected references, metadata mismatch,
process/tag/loaded-inventory drift, invalid/compressed metadata, timeout, duplicate
model records, unsupported formats and server errors. Additional contracts cover
the endpoint allowlist, one direct connection, bounded reads/time, fixed sanitized
errors, timestamp exclusions, read-only hashing and process-field restrictions.
Retain the first candidate/report and reproduce the tests/report in read-only
network-disabled Linux with public code and scratch only. Fixtures never contact a
backend or execute a binary. Failures stay recorded rather than silently retuned.

## Collection contract

The only destination is `127.0.0.1:11434`. The fixed sequence is GET `/api/version`,
GET `/api/tags`, GET `/api/ps`, POST `/api/show` for the selected model, POST
`/api/show` for `sha256:<full manifest digest>`, then GET `/api/tags` and GET
`/api/ps` again. `POST /api/show` is the documented model-details lookup, not a
generation endpoint. Its exact body contains only a validated model reference and
`verbose: false`. There are at most seven requests, no prompts, credentials,
environment proxies, redirects, retries, downloads or administration operations.
Each request uses one explicit loopback connection, a four-second absolute budget,
strict bounded uncompressed JSON and no reconnect after a partial request.

The selected name comes from the application's existing nonsecret model setting,
processed only in the protected operator context. Ambiguous tags, malformed full
digests or nonlocal/non-GGUF records fail closed. Raw metadata, model names, model
templates, local paths and process records remain in owner-only gitignored receipts.
The public projection contains statuses, hashes, counts, a validated reported version
and explicit unknown/unqualified fields. Backend errors never become diagnostic text.

On macOS, the process observer reads listener PID/address plus only process UID,
start time and command name, never arguments or environment. It hashes the resolved
regular Ollama executable in bounded chunks without executing it, checking file
identity/size/time and process start consistency. Before/after observations must
match. Unsupported/missing/ambiguous process evidence remains unknown. A disk binary
hash is not proof of loaded code, process integrity, trusted build provenance or
remote signed identity. The HTTP version remains a separate unsigned self-report.

Named versus digest lookup compares every returned model-detail field except
`modified_at`, because named manifests and blob representations can have different
filesystem timestamps. Running-inventory comparison excludes only `expires_at`.
These exclusions are declared before live observations. Full wire hashes and raw
responses are retained; templates, parameters, model info and all other fields are
not normalized away. Mismatch, tag/process/loaded-inventory drift, explicit lookup
rejection and unmeasured/error states remain distinct. A rejection of the metadata
lookup is not a generation experiment or a universal claim about all versions.

## What the result can establish

`lookup_resolved` records matching metadata lookup within a stable observation
window; it does not attest generation compatibility or executed weights. A 400/404
digest lookup with a valid named lookup is `lookup_rejected`. Other failures remain
unmeasured. No result creates a runtime pin, signing trust, native admission,
deployment permission, five-job capacity qualification or legal approval. Existing
provider/relay routes, policies, model dispatch and all other tenants stay unchanged.

The eight application services, originals, encrypted bytes, exact evidence versions,
credentials, sessions, 31 earlier edits and private review history are compared before
and after collection. The private case is not an input. Independent fingerprint
confirmation and the owner's focused-analysis v3 review remain pending.

Next work follows the observed result: qualify or repair immutable-reference support
in a separate isolated backend build, preserve the current live binary/configuration,
independently confirm public trust/runtime pin, then qualify read-only artifact stores,
full-size verification, scoped relay/trust/restore and fresh bounded native admission.
Historical 502 cause, native execution, sustained five-job capacity and legal quality
remain open. Keep existing CI jobs, workers, caps, coverage and five timing reserves.

Primary references: [Ollama model details](https://docs.ollama.com/api-reference/show-model-details),
[running models](https://docs.ollama.com/api/ps), and the retained commit-pinned
upstream source record in `deploy/fixtures/immutable_ollama_source.json`.
