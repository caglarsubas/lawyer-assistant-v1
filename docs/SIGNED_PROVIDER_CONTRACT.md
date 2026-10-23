# Signed provider identity and exact response binding, v2

## Frozen scope and acceptance plan

This is an offline prospective issuer / relay-codec / consumer implementation,
not a serving-engine deployment or native trial. F00-06 remains partial. The
owner's focused-analysis v3 review remains pending. Preserve every prior experiment
and v1 protocol unchanged. No private sample, runtime metadata request, completion
POST, provider restart, route change, timeout increase or key provisioning occurs.

Freeze fourteen invented P2301–P2314 outcomes before first grading: valid roundtrip,
foreign caller, unknown trust, wrong identity nonce, absent/mismatching/stale execution,
changed request/response wire bytes, expiry, duplicated challenge, fallback and
nonfinite JSON. Contracts separately exercise concurrency, expiry, signature domain,
strict parsing, current authentication, exact pins and complete token counters.
Reproduce the full report and contracts on read-only network-disabled Linux with
public sources and scratch only. Ephemeral synthetic signing keys stay in memory;
never serialize, print, commit or provision them. Deterministic reports include
only case outcomes and fixed counters/flags, never raw proofs or synthetic content.

## Protocol and trust boundary

Ed25519 signatures use the distinct `lawyer-provider-binding-v2` domain and canonical
strict finite JSON. v1 signatures cannot cross that boundary. Trusted public key,
issuer key ID and complete expected pin are independently supplied to the client;
response-published keys or configured identity labels cannot establish trust.

The identity proof binds a fresh 128-bit challenge, issuer, authenticated tenant,
organization and key ID, resolved local model/digest/backend/format, context limits,
trusted route, disabled cloud fallback, issue time and short expiry. Identity
challenges are one-shot, including failed attempts. A signer must resolve these
values through an authenticated server adapter; it must not copy client headers,
model-generated fields, metadata flags or configuration labels as evidence.

A response expectation binds a new challenge, identity-certificate hash, pin hash,
exact original request-byte hash and short expiry. Before signing, the issuer
re-authenticates the current caller and resolves the current runtime. A separate
trusted adapter must supply a completed execution receipt with the same pin,
request/response byte hashes, challenge, identity hash, execution start/end times,
local execution and no substitution. Absent, stale or inconsistent receipts fail
closed. The fixture provides invented receipts; it proves contract rejection
behavior, not the truth of an actual provider execution.

The signed response binds exact original response bytes (including whitespace),
carried as bounded base64. The consumer verifies signature, issuer, certificate,
pin, request, response bytes, freshness, local model, stop status, no unsupported
fields/tools, and complete nonnegative integer token accounting before returning
content. Request, response and envelope caps remain 256 KiB, 8 KiB and 24 KiB;
application context is at most 8192 and output at most 1000 declared tokens.
These counters do not qualify tokenizer accuracy, prompt fit or semantic/legal
correctness. Failed responses consume the expectation; no replay or automatic retry.

The pure relay codec accepts only one bounded Authorization header and one
identity-challenge header, rejecting duplicates and unknown controls. It preserves
signed envelope bytes unchanged; preservation is not signature verification.
Current serving relay filtering/handlers are untouched. This module has no socket,
HTTP client, key loader, serving handler or activation switch. Existing relay origin,
firewall, TLS, credentials, administration restrictions and campaign admission gates
stay mandatory. In-memory one-shot locks are not durable cross-process campaign
admission or a live trust/key-revocation registry.

## Gates before live use

1. Review the v2 wire and adapter contract. Implement provider-side authentication,
   resolved-model/execution receipt adapters in the provider repository; validate
   actual loaded weights and absence of fallback/substitution with its owner.
2. Provision a dedicated provider signing key and independently distribute its
   public trust anchor, key ID, validity/revocation policy and complete expected pin.
   Synthetic keys/receipts and matching unsigned metadata cannot satisfy this gate.
3. Integrate and qualify challenge forwarding and exact proof preservation in a
   separately staged provider/relay build, preserving current budgets and origin
   controls. No live installation is implied by merging this prototype.
4. Obtain a fresh bounded synthetic native trial declaration and durable campaign
   admission; verify identity and response binding end to end before capacity work.
   Do not reuse exposed cases or the old eleven-call allowance.

Historical 502 cause, packet gaps, signed live identity, sustained five-job native
capacity, reviewed corpus, legal quality and production activation remain open.
Originals, encrypted bytes, exact evidence versions, confidentiality, credentials,
sessions, configuration, review history, earlier edits and frozen artifacts stay
exact. All nine exact-head CI checks and five protected timing reserves precede merge.
