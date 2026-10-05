# Immutable graph serving releases

Runtime graph storage is a **read-only release volume**, containing two canonical
N-Quads payloads and their independently signed source bundle. A release ID is the
full SHA-256 of the source bundle manifest. There is no graph-write HTTP endpoint.

`ontology/serving.py` verifies the external Ed25519 review signature, source
artifacts, exact quotation spans, SHACL, and both graph partitions. It regenerates
the payloads and the deterministic `serving.json` marker before accepting them.
An unsigned staging bundle cannot be installed or activated. A signed bundle also
requires the [private live publication authorization](../../docs/PUBLICATION_AUTHORIZATION.md)
at installation, activation, rollback and application retrieval. Static signatures
alone are insufficient, including through `--root` and direct serving calls.
No command generates a review key or supplies an attestation on behalf of a lawyer.

Each family graph contains the signed ontology schema, shared non-assertion
resource/evidence context from both graph inputs, and that family's assertions.
Nothing infers binding force or legal applicability. The metadata named graph is
only a runtime consistency check; the independently verified bundle establishes
integrity. The API also checks returned relationships against its pinned bundle.

## Runtime and locking

At startup, Fuseki independently verifies the active bundle against the mounted
trusted public key, then uses Jena's transactional `tdb2.tdbloader --loader=basic`
to build **disposable TDB2 indexes in `/tmp`**. It checks both graph inventories
before exposing either dataset. The loader reads private payload copies whose
hashes match the regenerated signed receipt, closing the validation/reopen gap.
All startup subprocesses finish before the JVM
opens the databases. No other process opens those live indexes.

This design intentionally prioritizes integrity over startup speed. The canonical
source release is persistent and backed up; TDB2 indexes are rebuilt after restart.
Qualification for larger corpora must measure startup time and size the bounded
`/tmp` storage accordingly. Current startup limits are 600 seconds per family
import and 60 seconds per verification query. A size/timeout failure stops startup.

The runtime holds a shared `flock` on `/fuseki/publication.lock` across JVM exec.
Activation/rollback require an exclusive lock, plus the CLI verifies that both
Compose `api` and `fuseki` containers are stopped. A pointer update uses atomic
replacement and compare-and-swap of **both current ID and monotonic sequence**.
Rollback revalidates the previous release and increments the sequence. Installing
a new immutable directory does not change the active pointer and may run while
the old release is being served.

The runtime mounts `/fuseki:ro`; the API mounts the same volume read-only. Both
receive an independently supplied public key through `/graph-trust:ro` and the
`LA_GRAPH_TRUSTED_REVIEW_KEY` path. Never copy a fixture public key into that trust
directory. With no active release, the runtime serves two empty in-memory datasets
and ignores legacy `/fuseki/databases` content. With an invalid active release it
fails closed, without falling back to a previous release or the ontology catalog.

## Operator workflow

Run from the repository root using the backend environment. Supply an existing
signed bundle produced by `scripts/validate_ontology.py create-bundle` and the
independently provisioned review public key. Paths and IDs below are placeholders;
no corpus or legal review is shipped as production-ready data.

First complete the separate private authorization workflow linked above. Compose
transitions use the restricted `publication` profile publisher to hold live private
review locks; Fuseki receives no database credentials or private review records.
The `status` command checks public signature integrity only, not current permission.

```sh
backend/.venv/bin/python scripts/graph_releases.py prepare /secure/reviewed-bundle \
  --trusted-review-key /secure/reviewer.pem --output /secure/prepared-release

backend/.venv/bin/python scripts/graph_releases.py install /secure/prepared-release \
  --trusted-review-key /secure/reviewer.pem

backend/.venv/bin/python scripts/graph_releases.py status \
  --trusted-review-key /secure/reviewer.pem

docker compose stop api fuseki
backend/.venv/bin/python scripts/graph_releases.py activate FULL_RELEASE_SHA256 \
  --expected-current none --expected-sequence 0 --trusted-review-key /secure/reviewer.pem
docker compose up -d --no-build --wait fuseki api web
```

For subsequent activation use the actual current ID and sequence returned by
`status`. Activation never starts services or changes trust configuration. Check
application graph readiness after restart. `status` without a key reports the
pointer as **trust_not_checked**, never as verified.

```sh
docker compose stop api fuseki
backend/.venv/bin/python scripts/graph_releases.py rollback \
  --expected-current CURRENT_SHA256 --expected-sequence CURRENT_SEQUENCE \
  --trusted-review-key /secure/reviewer.pem
docker compose up -d --no-build --wait fuseki api web
```

Fresh Docker named volumes receive `publication.lock` from the image. For an
existing pre-release volume, initialize it once using the **newly built image**
before mounting it read-only (the default CLI uses the existing container's image
ID, so the old image cannot run the new helper):

```sh
docker run --rm --network none --read-only --user 10002:10002 --cap-drop ALL \
  --security-opt no-new-privileges:true \
  --mount type=volume,src=ACTUAL_GRAPH_VOLUME,dst=/fuseki \
  --entrypoint python3 lawyer-assistant-fuseki:5.3.0 \
  /opt/scripts/graph_releases.py --root /fuseki initialize
```

No source is deleted by initialization. `--root /offline/directory` targets an
explicit offline filesystem instead of Compose; the file lock still applies.
Interrupted preparation/import leaves the active pointer unchanged. Incomplete
`.preparing-*` or `.installing-*` directories are never selected; a process crash
may leave one for operator inspection. An ambiguous activation outcome is resolved
with `status`, not by blindly replaying a stale CAS command.

## Evidence and limits

Unit tests cover signature/trust rejection, deterministic payloads, tampering,
path/symlink protection, atomic staging, CAS, rollback, and active-reader locks.
An isolated Docker rehearsal additionally tested actual Jena compilation, both
named graph inventories, query-only HTTP routes, and JVM-held lock exclusion.
Its empty test inputs and ephemeral test key certify no legal facts or legal
review; they never enter the live volume or trust directory.

Jena references: [TDB2 command-line loaders](https://jena.apache.org/documentation/tdb2/tdb2_cmds.html)
and [read-only Fuseki configuration](https://jena.apache.org/documentation/fuseki2/fuseki-configuration.html).
Schema validation, signatures and exact byte/quote checks do not establish OCR
fidelity, reviewer qualifications, rights sufficiency, legal correctness or
applicability to a particular matter.
