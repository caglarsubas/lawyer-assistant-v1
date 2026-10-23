# Staged provider adapters and independent trust provisioning

## Declared scope and frozen plan

F00-06 stays partial and owner analysis v3 review stays pending. This slice stages
provider-side adapters and a separate public-trust enrollment workflow; it does
not install code in the provider, activate consumer trust, run native inference,
change routes or regenerate a private analysis. Previous protocols and experiments
remain exact. Original documents, encrypted bytes, exact evidence versions, private
records, credentials, sessions, configuration and review history are preserved.

Freeze twelve fresh invented P2401–P2412 outcomes and fourteen contracts before
first grading. Cover current/expired/disabled/foreign authentication, explicit key
IDs, changed model digest, mutable dispatch tags, external endpoints, receipt
completion/expiry/retry and independent trust enrollment. Reproduce the full report
and contracts in network-disabled read-only Linux with public sources and scratch.
All synthetic credentials and temporary keys belong only to invented tests.

## Concrete provider interfaces and limits

The inspected provider commit and hashes of auth, manager, registry and adapter
sources are recorded in `deploy/fixtures/provider_engine_source.json`. The fixture
extracts its actual key-record validity logic; no provider configuration or key
registry is imported. The staged auth adapter reads the already-loaded server
snapshot and checks auth enabled, validity and explicit tenant/org/key IDs on each
call. It never uses cached Request identity, reloads credentials, or invokes the
provider's rejected-key logging path, which includes token fragments.

The runtime adapter uses only `manager.iter_loaded()` and the loaded descriptor/
adapter. It never resolves, refreshes, loads or executes a model. It requires the
registered principal/pin, local Ollama endpoint, exact backend/context/digest and
matching immutable execution references in descriptor and adapter. The inspected
current provider dispatches a mutable model tag and has retry paths. That state
fails closed with `immutable_reference_required`; a registry manifest digest is
not an executed-weight attestation. Positive fixtures use a hypothetical future
pinned backend and do not establish that installed Ollama accepts that reference.

A SQLite receipt ledger stores confidential metadata only: opaque handles, hashes,
nonce, identity/pin, token limit, execution times and state. Trusted provider hooks
alone can begin/finalize it. Duplicate nonces are rejected; invalid or interrupted
finalization stays non-consumable. Consumption commits before returning, survives
normal process restart and is one-use under concurrent reads. Completion requires
one attempt, matching pin/reference, bounded lifetime, stop status and complete
integer usage. The issuer still independently re-authenticates and validates the
receipt against exact request/response/identity. This ledger does not execute a
model, prove truthful hook inputs, provide cross-restoration rollback resistance,
or replace existing durable campaign admission. Future private use requires the
approved encrypted provider volume, access controls and retention policy.

## Separate issuer and consumer provisioning

`provider_trust_stage.py` creates a new owner-only directory with an encrypted
PKCS8 Ed25519 key, random password file and public export. Files are exclusive,
regular, owner-only and bounded; symlinks, hard links and broad permissions fail.
Partial creation never publishes a usable manifest; nothing overwrites existing
material. Secret bytes never appear in arguments, stdout, logs or Git. The password
and key are both within the protected issuer staging directory; this is staging
protection, not an HSM or protection against compromise of the owning OS account.

Only the public export enters a separate consumer candidate directory. Importing
it does not trust it. Confirmation requires an explicit fingerprint independently
checked by the accountable operator, reviewer identity and time. It creates an
immutable confirmation record with a 24-hour staged validity window. Revocation
adds a separate record; any marker (including damaged/dangling) fails closed.
Missing/expired confirmation cannot supply a trusted key. A new key gets a new
issuer ID and directory; confirmations and revocations are never overwritten.
There is no automatic fingerprint approval or public-key discovery from responses.
Key confirmation alone cannot establish a runtime pin or native execution authority.

This milestone may create dedicated encrypted issuer material and a pending public
candidate in protected, gitignored local staging. It must not self-confirm the
candidate, copy keys into the live provider/app, alter `.env`, rotate existing keys
or attach a mounted secret. Public fingerprint confirmation remains an independent
operator step. No production trust registry or provider key-revocation integration
is implied by local staged records.

## Portable stage and next gates

`build_provider_stage.py` copies an explicit public-code inventory to the isolated
`lawyer_provider_stage` package. Only imports change in the frozen v2 contract;
reviewed JSON/pin validators are extracted without application dependencies. A
hash manifest excludes key material. The bundle is tested independently of the
application package, with producer-to-original-consumer interoperability. It is
not a provider installation or a serving handler. Dependencies need a separately
pinned and approved provider build; do not install into the running environment.

Next implement and qualify an actual immutable backend execution hook, bounded
single-attempt dispatch and protected receipt emission in a staged provider build.
Independently verify the public fingerprint and registered runtime pin, then qualify
relay challenge/proof forwarding, trust lifecycle/restore behavior and fresh bounded
native admission. Preserve the previous eleven-call allowance as historical only.
Live signed identity, historical 502 cause, sustained five-job capacity, reviewed
corpus, semantic/legal correctness and production activation remain open. Keep all
nine exact-head CI checks, existing workers/caps/coverage and five timing reserves.
