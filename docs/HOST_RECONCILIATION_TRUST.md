# Signed current-trust resolver

`scripts/host_reconciliation_trust.py` implements the constructor-owned resolver
for the [isolated host admission gate](HOST_RECONCILIATION_AUTHORITY.md).
It verifies signed authorization metadata and returns the existing frozen
`HostBinding`. Trusted host wiring can supply a private continuity store for
committed head observations and retirement.

## Independent inputs

Trusted host wiring supplies one `SelectedContext`: exact record, firm,
principal, recipient profile, authority context, scope, source and permission.
It also supplies three immutable `AuthorityPin` values, a `MinimumHead`, a clock
and the evidence/current-head callbacks. None of these are HTTP request fields.

The registry, enrollment and checkpoint authorities have distinct key IDs,
public keys, principals and profiles. Their principals and profiles differ
from the recipient's.
Each fingerprint must equal SHA-256 of the exact pinned public bytes. A proof
cannot supply or replace its own trusted key. Unsupported rotation requires
new independently reviewed wiring.

Public fingerprints and role labels do not establish independent key custody,
genuine appointments or truthful authority state. Those remain provisioning
and operating requirements outside this verifier.

## Proof protocol

Each envelope uses its own schema and Ed25519 signature domain. Inputs must be
canonical JSON bytes, at most 16 KiB each, with exact fields and strict types.
Duplicate keys, unknown fields, malformed signatures and noncanonical bytes
are withheld.

| Proof | What must match |
|---|---|
| Enrollment | Selected identity and evidence context, fixed `reconcile` action, active status, epoch/sequence and fixed validity window |
| Registry | The same selection and window, exact enrollment-envelope digest, signer identities/statuses and enrollment state |
| Current checkpoint | Fresh challenge, authoritative selected registry/enrollment digests, epoch/sequence, context and current statuses |

`evidence(selection)` returns bounded signed registry/enrollment bytes.
`current_head(challenge, selection)` must independently look up the latest
selected state, including current revocation. The expected version fields in
the selection are comparison constraints; the service must not simply sign
those values or an old caller-supplied head.

For each resolution, the verifier:

1. Checks the constructor-selected identity and admits one bounded operation.
2. Generates a fresh challenge and verifies a current checkpoint.
3. Verifies the signed registry and enrollment, their exact linkage, status,
   selection and independently pinned minimum head.
4. Obtains another checkpoint using a different challenge and requires the
   matching selected authority state in both checkpoints.
5. Rechecks validity and the checked budget before returning `HostBinding`.

Registry/enrollment digests are computed from their exact signed envelopes.
The registry digest is computed outside the registry payload, avoiding a
self-hash. Fresh challenges and checkpoint observation times stay outside
the stable binding. Its signed authorization window is fixed, at most 60
seconds and bounded by every pinned-root validity window. Both checkpoint
leases must cover that same expiry. Repeated resolution cannot extend it.

## Continuity and failures

A fresh, authenticated, well-formed head for the selected identity is retained
before later evidence or authorization denial. This includes revocation and
material context changes. Older heads cannot be restored by retrying after
such a failure. Unrelated identities cannot alter this instance's fence.

The fence hashes the complete stable selected state, including digests, key IDs
and statuses. Conflicting statements at the same version, or an authenticated
unsupported epoch change, retire the resolver. A configured continuity store
retains that retirement across restarts.

## Host-owned continuity store

The default resolver keeps observations in memory. For restart continuity,
trusted wiring supplies `TrustContinuityStore` as `continuity`. Host setup uses
the validated resolver's `continuity_binding_sha256` and a separately retained
store ID to initialize an exclusive record with `TrustContinuityStore.create`.
Subsequent processes open that same file with the configured ID and binding.
The digest binds the selected context, public authority pins and minimum head.

The store requires an owner-only directory and file. A directory lock
serializes cooperating processes. Each advancement or retirement replaces
one bounded record after synchronizing the new file, then synchronizes the
directory. The record contains the store ID, wiring digest, sequence, registry
digest, state digest and retirement status. Unavailable or invalid state
withholds resolution. A failed write retires the live resolver.

The restart guarantee covers committed observations on the same trusted local
filesystem. An interrupted commit or restored copy requires operational
reconciliation. Joint rollback, clock rollback and authoritative latest-state
administration still require independent controls. A fresh challenge binds the
checkpoint to the request. The host relies on the configured authority to
report current state.

Lock admission is bounded to two seconds per lock and the continuity lock also
respects the remaining operation budget. The ten-second operation budget is
checked around callback, verification and storage work. Callback transports
and filesystem operations need operating limits for stalled IO. Failure
diagnostics are withheld at the resolver boundary.

## Qualification and remaining gates

The complete `backend/tests/test_host_reconciliation_trust.py` file uses
invented authorities and ephemeral in-memory fixture keys. Its 125 cases cover
proof/key/context substitution, stale and revoked evidence, challenge replay,
expiry, observed-head continuity, same-version conflicts, unsupported epochs,
budget/admission failures and integration with real host authentication.

Run the repository's configured checks, including placement whenever the
workflow inventory changes:

```sh
backend/.venv/bin/ruff check --config backend/pyproject.toml backend/app backend/tests deploy scripts ontology
backend/.venv/bin/python -m unittest discover -s deploy -p test_deployment_ci_placement.py
backend/.venv/bin/python -m pytest backend/tests/test_host_reconciliation_trust.py backend/tests/test_host_trust_continuity.py -q
```

The backend-review job runs the complete resolver and continuity files. The
continuity cases exercise a separate process, competing resolvers, retirement,
unavailable state, an interrupted replacement and bounded lock contention.
Hosted PR and main results qualify the engineering slice with thirteen jobs,
two workers, the existing time caps and reserve floors.

Genuine fingerprint confirmation, appointments, authoritative latest-head/root
revocation administration, restore and clock assurance, operating limits and
receipt-level issuer/custodian integration remain production qualification
work. The owner's legal review remains pending.
