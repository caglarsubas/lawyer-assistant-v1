# Immutable-reference execution hook and staged signed route

F00-06 stays partial. This slice implements an unregistered ASGI handler and a
concrete, single-attempt Ollama HTTP hook in a separately built provider package.
It does not install or activate a route, use real issuer keys, call the running
provider/Ollama, load a model, or regenerate private analysis. Owner analysis v3
review and independent public-fingerprint confirmation remain pending.

## Frozen qualification

Freeze sixteen fresh invented H2401–H2416 outcomes and twelve contract methods
before first grading. The mock backend receives invented bytes; its small GGUF
sentinel is explicitly not a model. Cover digest dispatch, current auth/policy,
exact request bytes, remote/corrupt artifacts, redirects, 502, wrong models,
clipping, usage, bounds, expiry, revocation and nonce replay. Additional contracts
cover file/link protection, cancellation, concurrency and standalone packaging.
Retain the first candidate and complete first report, including any failures.
Reproduce in read-only network-disabled Linux with public source and scratch only.

## Artifact and execution boundary

`ManifestSnapshot` reads only an explicit owner-only staging directory. It checks
the full manifest digest, config and every referenced blob hash/size with bounded
streaming, no symlinks/hardlinks, and regular owner-only files. It permits one
local GGUF text model with a restricted layer inventory; manifest lists, remote
configurations, adapters and projectors are rejected. It does not copy or inspect
the live model store. A model-layer digest and a manifest digest are distinct.
The registered pin here identifies the full manifest and its referenced content.

The hook owns the immutable reference and native payload. It sends exactly one
POST to `http://127.0.0.1:11434/api/chat`, addressing `sha256:<manifest digest>`;
it never resolves a logical model alias, forwards caller credentials, accepts a
caller execution reference, uses environment proxies, follows redirects, retries,
reprompts, substitutes a model or invokes cloud fallback. Actual loaded provider
auth/policy/pin checks are retained from the earlier adapter. Native context and
completion limits are explicit, with conservative pre-admission and a 30-second
whole-operation ceiling within the signed expectation's shorter lifetime.

The response must be bounded uncompressed JSON, name the exact reference, finish
with `stop`, contain a single plain assistant message, and supply complete integer
usage within limits. Original request bytes remain bound even when whitespace
differs; the hook's native translation is explicit. Artifact checks repeat after
dispatch and current provider identity is rechecked before finalization/signing.
Errors, private text and credentials never enter response diagnostics or logs.

The [inspected upstream source](https://github.com/ollama/ollama/blob/675150d6ad2747df1e218ef59de9194bc4a7e538/server/routes.go)
has a separate digest-reference resolution branch. The source snapshot and hashes
are recorded in `deploy/fixtures/immutable_ollama_source.json`. They do not identify
the installed Ollama binary or prove it accepts this wire reference. Unsupported
references fail closed without trying a tag. Native compatibility remains open.

Hash checks plus a digest request are not hardware attestation or proof of which
weights executed. They rely on an independently qualified honest backend. Same-OS
owner compromise or a dishonest server cannot be excluded by HTTP signatures.
Production requires an isolated read-only artifact store, qualified backend build,
local/cloud configuration, tokenizer/truncation checks, artifact-verification work
budgets and a fresh approved native trial. Repeated streaming hashes here have not
been qualified at real model volume or concurrent load.

## Staged signed route

Only POST `/staged/v2/identity` and `/staged/v2/completions` exist. Exact paths,
no query string/root rewrite, one authorization header, explicit JSON, bounded
body size/fragments/time and strict JSON are required. Admin routes, arbitrary
URLs, caller receipt handles, attempt counts and execution references are rejected.
No entry point starts a server, registers a live router or loads credentials.

Identity uses the retained v2 issuer/consumer protocol. Completion first verifies
the exact identity, request hash, independent runtime pin, expectation and lifetime.
It durably reserves the response nonce before dispatch. Invalid/interrupted work
cannot silently dispatch again under that nonce. A valid response is finalized
once, reauthenticated, consumed durably and signed against exact returned bytes.
Cancellation propagates, releases capacity and never retries. Only one staged
completion is admitted at a time; busy work fails promptly. This is not five-job
capacity qualification or rollback-resistant campaign admission.

The handler returns fixed sanitized errors and `Cache-Control: no-store`. It has
no public inverse links, private-matter writes, analysis updates or review actions.
The retained encrypted issuer and separate unconfirmed public candidate are not
opened by this slice. Existing trust, originals, evidence versions, encrypted data,
credentials, sessions, confidential review history and earlier frozen artifacts
remain exact. The eight live services and their configuration stay unchanged.

## Next gates

Independently confirm the staged public fingerprint and registered runtime pin;
qualify the installed/backend artifact identity and actual immutable-reference
support in an isolated staged build. Then qualify scoped relay forwarding, trust
expiry/revocation/restore, cancellation, full-size artifact work and fresh durable
campaign admission before any native trial. Do not change shared live provider
settings, activate consumer trust, reuse old inference allowances or treat synthetic
signatures as native/legal qualification. Historical 502 cause, live execution
identity, sustained five-job capacity, corpus/legal quality and production rollout
remain open. Keep all nine CI jobs, workers, caps, coverage and five timing reserves.
