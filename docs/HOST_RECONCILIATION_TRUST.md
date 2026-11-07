# Signed current-trust resolver

`scripts/host_reconciliation_trust.py` implements the constructor-owned resolver
for the [isolated host admission gate](HOST_RECONCILIATION_AUTHORITY.md).
It verifies signed authorization metadata and returns the existing frozen
`HostBinding`. It has no filesystem, database, network, signing, provisioning,
receipt-access or application-registration operation.

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

The fence includes the complete stable selected state, digests, key IDs and
statuses. Conflicting statements at the same version, or an authenticated
unsupported epoch change, retire the instance. A fresh independently reviewed
configuration is then required; retrying an older active statement cannot
clear the conflict.

This fence exists only in memory. It does not establish continuity after
process loss, joint authority/consumer rollback or clock rollback. A fresh
nonce proves response binding, not that the authority's latest-state claim
is true. The operational authority and its durable continuity controls still
need independent provisioning and qualification.

Lock admission is bounded to two seconds. The ten-second operation budget is
checked before and after callback/verification work. It cannot interrupt a
blocked callback; real callback transports need separately qualified deadlines
and cancellation. Failure diagnostics are withheld at the resolver boundary.

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
backend/.venv/bin/python -m pytest backend/tests/test_host_reconciliation_trust.py -q
```

The complete new file runs in the existing backend-review job. Original test
identities, thirteen jobs, two-worker limits, time caps and reserve floors
remain required. Hosted exact-head and independent-main results qualify the
engineering slice.

Genuine fingerprint confirmation, appointments, authoritative latest-head/root
revocation administration, durable continuity, clock assurance and operational
load/cancellation evidence remain separate gates. This verifier does not supply
receipt-level issuer/custodian permission, a legacy authority bridge, directory
restore/rebinding, production activation or legal review.
