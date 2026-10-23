# Read-only provider identity and prospective response binding

This candidate makes one bounded authenticated GET to the existing `/v1/models`
route. It never sends completion POSTs, retries, follows redirects, modifies
settings or runs inference. An optional separate observer makes one fixed-loopback
GET to `http://127.0.0.1:11434/api/tags`. No app route, native executor, production
install, new key or provider/relay change is introduced.

## Evidence boundaries

Model name/backend/context and verified relay transport are observations. Configured
tenant/org/key labels and operator flags are not server-authenticated identity.
A local Ollama manifest digest identifies that separately observed tag manifest;
it does not prove which engine endpoint or weights executed a request. Never
promote that independent digest to a qualified served-model pin.

The inspected engine schemas expose no immutable served-model/tenant attestation
on model listings or completions. The existing restricted relay also filters
model metadata and does not forward the new challenge header. Current unsigned
metadata therefore returns `qualified_pin=null`, explicit issues and no native
execution authority. The collector remains useful for safe capability diagnosis.
Do not infer identity from successful authentication, an alias, a request ID,
usage side-channel data or a matching public key supplied by the response.

## Prospective signed contract, not deployed provider capability

The versioned `lawyer-provider-binding-v1` contract requires an independently
provisioned trusted Ed25519 public key. No response may nominate its own trust key.
Future provider/relay support is required; this repository does not implement the
signer, identity endpoint or attested execution in the engine.

A read-only identity proof signs a fresh client challenge, the complete immutable
runtime pin and bounded issuance/expiry. The pin includes model ID and immutable
digest, local backend/format/context, tenant/org/key IDs, exact route and disabled
cloud fallback. It must match current model metadata, the expected caller/route
and any prior approved pin. Missing, malformed, stale, conflicting or untrusted
proofs cannot supply a qualified pin. The public observation excludes credentials,
URLs, model paths and arbitrary server fields; the metadata digest still remains
confidential research metadata for real matters.

A pending response revalidates the identity certificate and separately approved
pin using the independently pinned key. It binds exact request bytes, a fresh
nonce, identity/pin hashes and an expiry. The response's detached signature covers
that expectation and the canonical completion payload hash. A separate receipt
hashes the exact raw response bytes. Canonical payload binding is distinct from
HTTP byte formatting. The key is fixed at pending-request creation, and the
expectation is consumed once even on failure. Replays, swapped requests/nonces,
forged collection records, foreign signer, changed payload, unsigned legacy
response, fallback/substitution, incomplete output and over-budget usage fail.

These signatures establish claims made by a trusted signer, not honest physical
execution by themselves. A future signer must bind the resolved immutable model
and authenticated identity to the exact request during execution, preserve route
provenance and prevent substitution. Merely echoing client fields is insufficient.
The current consumer cannot manufacture that evidence. This in-memory one-shot
verifier also does not replace the durable issuer/restore/campaign budget boundary.
No legal conclusion, source review or private-case regeneration is authorized.

## Frozen qualification and live observation

Freeze candidate, eight fresh P1901–P1908 cases, mock signer/evaluator, contracts
and this declaration before first grading. Synthetic private keys are generated
only in memory and never serialized or provisioned. The invented prospective
signer exercises both valid and invalid proofs; it is not the deployed provider.
Expected outcomes are two bound synthetic responses, four rejected responses and
two unqualified identities, with eight mock GETs and no POSTs. Bound empty selection
does not qualify relevance or abstention. Retain the first report and failures.

Contracts cover independent trust, exact wire/nonce/pin/payload binding, certificate
revalidation, expiry/replay/concurrency, changed settings, strict JSON, HTTP and
size limits, local-only context metadata, manifest ambiguity, token limits and
compatibility with the frozen guard pin schema. Reproduce the whole report in
read-only network-disabled Linux with temporary scratch and public code only.
Keep CI topology, caps, workers, coverage and five timing reserves unchanged.

A separate live drill may read the existing app's effective settings in memory and
perform the single GET through its approved provider route, plus an independent
loopback manifest GET. Retain raw results only in protected local files and emit
allowlisted capability flags. No API key or private source is printed, persisted
in public evidence or passed as an argument. Do not install code or recreate
containers. If the route lacks signed binding, record the exact gap and keep native
admission blocked; do not substitute registry files or configuration assertions.
Originals, evidence versions and review history remain unchanged. The owner's
focused-analysis v3 review, fresh native acceptance and legal qualification stay open.
