# Read-only verification-reference readiness

This unregistered host adapter previews a private retention plan and re-observes
one exact, independently registered encrypted verification record. It does not
publish a record or grant recovery, execution, trust renewal or legal approval.

`VerificationReferences.dispatch` accepts only `retention_preview` and
`reobserve`. Trusted host wiring supplies the verifier, distinct metadata store,
independent store/key pins, at most four exact references and at most four
acknowledgement pins. Incoming requests cannot supply credentials, select a new
store, register references or establish acknowledgement provenance.

The currently assigned destination reviewer is authenticated before reference,
namespace or retained-body inspection. Missing acknowledgement references or
independent host pins return no retained metadata and trigger no discovery or
decryption. A matching invented pin establishes only equality to the supplied
host registry; `genuine_acknowledgement_verified` remains false.

For admitted reads, use bounded directory admission and a ten-second checked
aggregate budget. Reject staging, links, broad permissions, excessive records and
oversized inputs without cleanup. Decrypt only the explicitly pinned record using
authenticated encryption bound to its record and destination/store context.
Recheck current source and destination authority, exact versions, original input
history, registry and namespace around two fresh verifier calls. Withhold all
plan/re-observation metadata on inconsistent observations or failed checks.

The returned plan pins exact source references, the original handoff and fresh
receiver verification. A retained record must equal that fresh plan. A different
receiver session or shorter validity requires fresh validation; neither reopening
a record nor previewing a new plan rewrites the original. Preserve the original
handoff expiry separately and never extend it.

`verification_reference_fixture.py` is an external test writer with invented
identities and acknowledgements. Its ability to retain fixture records is not an
application publication route or proof of production custody or durability.
The frozen opt-in campaign qualifies 20 outcomes across two source/receiver
pairs and four account contexts, with two fixture-retained verification records.
One declared fixture revocation and one namespace injection are retained.
Every service read preserves its before/after byte inventory; no service writes
are permitted. The report binds 777 source files, preserving all 773 predecessor
pins and the exact preceding report hash.

Run separately from routine CI:

```sh
backend/.venv/bin/python scripts/qualify_verification_references.py --output /private/new-report.json
```

The output must not already exist. Failure writes an incomplete report containing
only the error type. Reports contain aggregate outcomes and source hashes; no
private records, case contents, sessions, filesystem locations or keys.
Twelve ordinary regression cases use existing backend capacity. CI jobs, caps,
workers, placement manifests, reserve supervisor and fixed floors remain exact.

Genuine acknowledgement provenance/durability, independently reviewed retention
authorization and key custody, native mounts/listeners, production writes,
cross-store atomicity and joint rollback remain unqualified. The owner's focused
analysis review is still pending.
