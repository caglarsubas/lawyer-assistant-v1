# Operator evidence packets and read-only reconciliation

F00-06 remains partial. This separately trusted operator layer wraps the unchanged
fourteen-module portable controller package. It does not install code, confirm
trust, load a signer, contact a provider, execute weights or decide a legal review.
Owner focused-analysis v3 review and independent real issuer/runtime-pin
confirmation remain pending. No live matter, document or runtime secret is an input.

## Unsigned expectation packet

`scripts/operator_enrollment_evidence.py` provides `packet`, `retain`, `read` and
`reconcile`. Supply independent expectations, never automatically copy observed
enrollment into approval. The closed packet contains:

- A version, opaque packet identifier and explicit creation/expiry times, at most
  900 seconds apart; future, expired and malformed packets are rejected.
- The externally approved portable-package manifest SHA-256.
- Exact journal/operation/record/volume binding and original serialized runtime-pin
  SHA-256. It contains no filesystem-path fields or full runtime-pin/principal record.
- Expected public issuer/fingerprint, exact candidate bytes, optional independently
  approved confirmation bytes, and separate opaque reviewer/provisioner identifiers.
- Read-only disposable scope, with all trust/installation/execution/production/legal
  authority flags false. Unknown fields, credentials and authority flags are rejected.

`packet(expectations, packet_id=..., now=...)` returns unsigned bytes. Its output
hash is a producer integrity receipt, **not** proof of independent approval or an
authenticated human decision. Reconciliation requires an approval hash from the
trusted operator workflow outside that packet. Reviewer/provisioner labels must
differ; labels alone do not authenticate either person. Do not insert case facts,
names, prompts, API keys, signer paths or private key material into packet fields.

The optional CLI reads a protected expectations file and creates a fresh packet:

```sh
python scripts/operator_enrollment_evidence.py /protected/expectations.json \
  /protected/operator-packet.json --packet-id <opaque-32-character-hex-id>
```

No secrets are passed as arguments. The input has exactly
`package_manifest_sha256`, `binding`, and `enrollment`, with their field definitions
in `validate_packet`. Standard output contains a digest and unsigned/no-trust flags.
Errors are masked. Existing files are never overwritten. This command creates
metadata only; it does not perform or substitute for independent approval.

## Reconciliation and retained observations

Use separately trusted operator code and an external manifest approval to inspect
the read-only package **before importing its API**. Then pass that trusted API,
clock, explicit local paths, V2 `Journal`/`Binding` and packet approval into
`reconcile`. These arguments are not exposed as request-controlled routing.
The API module namespace must match the inspected package. Import/in-process
integrity, operator authentication and protected mount mappings are trust roots;
this is not a Python sandbox or a native-execution authorization service.

Packet/public/previous-observation reads require canonical owner-only directories
(0700), regular single-link owner files (0600), no symlinks, bounded stable reads
and strict duplicate-free JSON. Files are bounded to 32 KiB; FIFO reads fail without
blocking. A closed public inventory is inspected before opening allowed records;
unexpected private material and any revocation marker fail closed. Original public
candidate/confirmation bytes are compared, including whitespace or representation
changes that preserve their semantic key identity.

The retained preflight verifies read-only package/model storage, pinned dependencies,
exact binding, sealed ancestry, current journal/anchor and bounded V3 model content.
The original 20-second verifier limit remains unchanged. Reconciliation rechecks
packet bytes, public records, prior observation, current binding/anchor, fresh time
and public confirmation expiry before returning. Intervening replacement, expiry,
revocation or clock rollback blocks the affected observation. A snapshot cannot
prevent a change after its last check; effect/release boundaries still require
current authorization and one-use controls. No cached observation is a future grant.

Results are `blocked`, `waiting`, or
`reconciled_for_disposable_mock_validation`, with bounded gate codes and metadata
hashes. Missing candidate/confirmation or absent independent confirmation approval
remains waiting. Merely finding a new confirmation never grants approval.
Successful results retain all authority flags false. Outputs omit paths, principal
labels, fingerprints, public source bytes, private material and raw exceptions.
Treat hashes and the selection of evidence as confidential operator metadata.

`reconcile` performs no writes. A caller may explicitly retain the returned bytes
under a fresh owner-only filename through `retain`; the packet and prior observations
remain immutable. A supplied previous observation needs its own exact approved hash
and the same packet identity. The comparison reports unchanged/changed/not-comparable
metadata, preserving original observations rather than rewriting history. A newly
observed, unapproved confirmation is recorded as a change while status stays waiting.
Cross-packet, tampered, wrongly permissioned, future or unapproved prior evidence
is rejected. Previous observations never authorize enrollment or execution.

## Qualification and next gates

The first frozen native campaign passes **39/39 cases** against the unchanged portable
package, with no application/engine imports. It covers packet/hash/schema/lifetime/
file attacks, exact candidate/confirmation versions, wrong bindings/unsealed state,
expiry/revocation/replacement during a check, historical comparisons, a new unapproved
confirmation, forbidden privileged/network helpers and actual writable-mount rejection.
Only invented public identities, ephemeral in-memory keys and the retained 65,561-byte
zero-tensor model fixture are used. Read-only calls preserve metadata; four cases
deliberately inject external writes and three inject time changes. Caller retention
is measured separately after reconciliation. Model/package inventory remains exact.

Two new owned containers and three ext4 volumes provide two CPUs/768 MiB, a read-only
root, cleared environment, no external network/runtime mounts/host ports and separate
anchor storage. Preparation exits before reader use; all owned resources are removed.
Routine CI runs small contracts and retained-report replay. The initial nine-check
run passed, but its 972-second backend suite plus 69-second deployment-contract tail
left only 14 seconds reserve; the 30-second merge gate rejected it. Move the complete
deployment discovery exactly once to the existing frontend-history job, previously
212 seconds below its cap, with locked Python dependencies. All nine jobs, original
tests, two-worker settings, deadlines, frontend shards and coverage remain; add one
discovery-placement regression without retries or larger caps. The 985 other earlier
implementation/configuration files and complete portable package/archive remain
exact. No live provider or acquired weights are exercised.

Next implement an authenticated operator-review handoff with disposable identities,
binding approvals to exact packet/observation hashes and retaining reviewer-role and
staleness evidence. Genuine independent issuer/runtime-pin confirmation, installation,
executed weights, completion/context/tokenizer/truncation, sustained five-job native
research load, retention/capacity, cold/host-bind profiles, historical 502 root cause
and legal/production acceptance remain separate open gates. See
[dated evidence](evidence/operator-enrollment-2026-10-25.json).
