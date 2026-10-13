# Read-only retained dependency observation

Trusted local operators can inspect an installed whole release without altering
its publication state. Supply a closed `legal-retained-dependency-expectation-v1`
JSON object with its full `release_id` and `serving_sha256`; inferred `latest`
identifiers, extra options and partial hashes are rejected. Keep the configured
final review role and all five independently vetted public trust keys.

```bash
python scripts/inspect_retained_dependencies.py \
  --expectation /private/exact-dependency-expectation.json
```

The JSON receipt is firm confidential. Store or share it only through the
authorized operator workflow. It includes public component release identities,
the recorded immediate whole-base pointer, signed inventory/dependency hashes,
recorded approval/expiry times, the observed active pointer and two distinct
timestamps: current permission was checked inside the original-source guard;
the observation was returned after exit checks. It includes no source owner,
rights proof, credentials, private packet paths, source text or matter data.

`recorded_whole_signature: verified` means the original fifth-key signature
matches the exact sealed candidate and independent final-review packet. The
recorded inventory must also be present inside the freshly verified public Graph
A, with exact component membership and unchanged candidate/evidence bytes. This
is historical binding evidence, not a current permission verdict.

`current_permission: verified` is a separate point-in-time result from the full
existing whole-release guard. It reconstructs all original and retained Graph
A/B sources and grants under one ordered transaction. An expired or revoked
source, reviewer, identity, equivalence, register, key, epoch or parent dependency
produces `withheld_or_unavailable`. A valid original signature and installed
artifact can remain visible while their current use is withheld. The receipt
does not identify a particular failed dependency when verification is incomplete.

Only an installed target with the exact expected bytes can be observed. Inactive
installed targets are supported; observing one never makes it active or grants
runtime access. The inspector takes existing publication/installation shared
locks, opens no write transaction, initializes no state and records no audit/job
event. Closed packet inventories, every captured byte, original bindings, trust,
configuration and pointer are checked again before returning. Changing or corrupt
observation data produces a bounded safe error, not a repaired state or an
inferred complete inventory. Missing targets or grants likewise remain unknown.

Every receipt explicitly has false values for activation/runtime-read/retry
authorization, repair, publication and legal qualification. It is neither a
retained permission token nor proof that a particular command committed. Use the
[transition inspector](WHOLE_RELEASE_AUTHORIZATION.md#read-only-uncertain-transition-observation)
for exact uncertain before/after effects; neither inspector authorizes replay.

Engineering qualification uses invented corpora and TEST-ONLY signatures. It
covers valid retained inventory, installed inactive targets, current rights
withdrawal, corrupt and late-changing provenance, safe CLI errors, no state writes
and closed expectations. Actual source/legal review, national historical
population, production signing/activation and lawyer acceptance remain separate.
