# Metadata handoff and read-only recipient acceptance

The unregistered adapter packages exact reviewed metadata for one explicitly
pinned disposable recipient. It transports opaque identifiers, proof/proposal/
decision/provenance/reference/plan hashes and expiry limits. It includes no
original documents, source plaintext, ciphertext records, session credentials,
actor/session snapshots, signing keys or filesystem paths. The canonical JSON
package has a strict 4 KiB limit. It remains confidential metadata.

Trusted host wiring supplies a distinct owner-only transport directory and its
independent identity/context pins, an immutable specification registry, explicit
package hashes and server-held source authorization. The recipient must have a
separate disposable account database, profile and assigned principals. The source
review remains bound to its original signatures and exact evidence versions.
Requests contain identifiers and exact hashes; they cannot provision keys, paths,
pins, accounts, credentials or review decisions.

`package` authenticates the assigned source reviewer before lookup or private
inspection, revalidates the signed review and retained reference twice, and
returns canonical metadata bytes without writing them. Negative independent
reviews, revoked authority or unavailable evidence withhold the package. An
external operator/fixture writer may publish a new owner-only copy exclusively;
the service provides no publication, overwrite, retention or recovery route.

`accept` authenticates the assigned recipient reviewer before lookup, reading or
parsing. The host must already pin the exact package version. It checks the
closed schema, destination, specification and hashes before source decryption;
then freshly revalidates the source review and independently captures recipient
inputs, checking both twice. Changed source, session, roles, byte versions,
registries, directories or inputs withhold acceptance. Missing, linked, staged,
oversized or malformed files remain untouched. Ten-second checked operation and
two-second combined admission budgets fail closed.

Acceptance is a read-only observation returned to the caller. It creates no
persistent decision and changes neither source review history nor recipient
history. Expiry never exceeds the reviewed evidence, original handoff,
specification or current recipient session. A later replay cannot renew authority.
Different valid bytes or signatures cannot replace the pinned versions.

This qualifies only disposable metadata exchange readiness. The transport hash
is a comparison commitment, not a credential or independent enrollment proof.
Genuine key custody, issuer/channel authenticity, durable retention, cross-store
atomicity, rollback/recovery, production activation and legal approval remain
unqualified. All corresponding authority flags remain false. No route is installed.

The opt-in campaign freezes 24 outcomes, uses two source pairs plus two separate
recipients (six disposable account contexts), and binds all 781 predecessor
source pins within 785 pins. Only declared session deletions and test-owned
transport/proof faults are permitted; original inputs and review histories stay
exact. The campaign uses no real cases, provider/model requests or genuine keys.

```sh
backend/.venv/bin/python scripts/qualify_metadata_handoff.py --output /private/new-report.json
```

Use an existing owner-only directory and a fresh output filename. Reports have a
separate 1 MiB limit for the complete source-pin inventory; transport limits are
unchanged. Incomplete attempts remain evidence; outcomes are not retuned.

CI headroom is addressed before new feature coverage: complete temporal58 tests
move from backend to publication, package34 from frontend to the database job,
and cohort32 from graph to analysis/recovery. Nine new regressions use the freed graph
capacity. All original test identities, real PostgreSQL races, 13 jobs, two-worker
limits, 73-minute aggregate cap, deadlines, immutable manifests and reserve floors
are retained. Exact-head and independent-main execution, reserve and preservation
checks gate delivery; local timings do not qualify hosted CI.
