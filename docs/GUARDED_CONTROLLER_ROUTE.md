# Staged V2 controller and signed-route integration

The explicit `guarded_controller_route.build` factory composes the retained signed
ASGI route and immutable execution hook with the
[V2 control journal](CONTROL_JOURNAL_RECOVERY.md). It is unregistered and requires
an explicit `httpx.MockTransport` backend. There is no native socket-backend
default, live provider installation, key loader, trust activation or V1 migration.
Original source/defaults remain unchanged. This is protocol/control integration,
not evidence of executed weights, model accuracy or legal acceptance.

## Trusted binding and request isolation

The operator supplies an expected journal identity, operation, exact record hash,
volume binding, runtime pin and actual read-only root. Requests cannot supply or
override these objects. The controller checks sealed ancestry and the separately
retained anchor on each guarded operation. The snapshot adapter verifies actual
kernel-read-only model bytes with the original bounded V3 verifier before use and
through the retained hook's pre/post checks. Prepared or revoked work cannot be
silently promoted. The operator remains responsible for binding the correct volume
and root; a request field, path string or signed checksum cannot establish a mount.

Each ASGI request has its own context. Authentication is resolved through the
independently supplied loaded-auth/runtime adapter, then rechecked at admission,
completion, consumption and release. Credentials stay in RAM with repr disabled;
they never enter control/receipt tables, native request headers or diagnostic
output. Journal metadata stores hashes, versions, ancestry and one-use state,
without original prompts or responses. Direct hook calls outside an admitted
request context reject; user JSON has no arbitrary SQL, file or schema capability.

## One-use dispatch and guarded release

The controller reserves the exact response challenge in V2 before the original
receipt store begins. Its hash binds runtime pin, exact original request bytes and
response expectation. The guarded transport checks the exact method, loopback
destination and immutable-digest request bytes. It checks current authentication
and sealed ancestry, then consumes the nonce durably in the same guarded
transaction. That transaction is the admission boundary for one attempt.

Failure or interruption before/after admission burns the challenge. Restoring or
rolling back the older receipt database does not permit another attempt; V2 state
remains authoritative. A commit/anchor gap blocks ordinary reads and requires
explicit recovery; recovery preserves the reservation without replaying work.
There is no backend retry, tag fallback, redirect, environment proxy or cloud path.

The original hook owns response/context/usage validation. The guarded receipt
adapter checks current state before finalization and one-use consumption. The
outer ASGI wrapper buffers the signed result and performs a final eligibility
check before releasing success. A failed release returns only a generic no-store
error, with no buffered signature or native error text. Cancellation clears request
context, releases route capacity and preserves the used challenge.

Revocation before admission prevents an attempt; revocation during an admitted
attempt prevents a successful result from being released. Work already admitted
or bytes whose release has begun cannot be recalled. Future effect callers must
preserve these linearization boundaries. Retained V2 signatures do not grant
future execution or perform an offline revocation lookup. The response contract
is unchanged; public report replay never enrolls a real issuer or authorizes work.

## First qualification

The policy, eight initial contracts and candidate were frozen before grading.
All 29 fresh native cases pass first grading using 24 actual Uvicorn loopback
servers and 53 HTTP requests in a disposable Linux container. Five cases reject
at factory construction and one probes direct-hook rejection; the remaining
cases exercise actual HTTP. Model-backend calls use explicit mocks throughout.
Two exact signed responses are revalidated by the retained public consumer,
including original request whitespace. The model fixture has 65,561 bytes and
zero tensors; this is not another model-performance campaign.

Cases cover revocation at admission/completion/consumption/release, changed auth or
runtime pins, record/journal substitution, unsealed/writable stores, context and
expiry bounds, HTTP 502, clipped output, receipt rollback, lost admission,
commit/anchor recovery, replay and bounded concurrent capacity. An added contract
checks the exact masked failure body after signing; the eight original methods
and frozen native sources remain retained. Report contracts reject altered wire,
nonce history, scope, model inventory and profile evidence.

The native profile uses three new ext4 volumes, two CPUs/768 MiB, no external
network, no host ports or runtime mounts, a read-only root and a cleared process
environment. Only preparation adds CHOWN and exits before the read-only model
mount is used. The independently retained anchor occupies its own volume. All
owned containers and volumes are removed. Current real staged issuer materials,
live provider/backend, private originals, exact evidence versions and review
history remain unchanged. Owner focused-analysis v3 review stays pending.

Next produce a versioned portable guarded-controller package and explicit binding/
enrollment readiness checks, using disposable identities first. Real issuer and
runtime-pin confirmation, long-lived retention/capacity, installed/executed
weights, real completion/context/tokenizer/truncation, sustained native jobs,
historical HTTP 502 diagnosis and legal/production acceptance remain open.
