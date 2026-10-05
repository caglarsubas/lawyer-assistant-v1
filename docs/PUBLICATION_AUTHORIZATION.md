# Live publication authorization

This engineering path publishes an independently reviewed **single-source
provision snapshot**, with closed validity dates or an explicitly reviewed,
evidenced open-ended state bounded by its checked-through date. It does not
certify the national ontology, review a licence, resolve an unknown validity end
date, or populate a real corpus.
All legal decisions and signing keys remain outside the application.

## Two approvals and a current review

A public Ed25519 attestation approves the exact ontology and transformed graph
bytes. A second, private Ed25519 authorization approves deployment-wide sharing
of that exact prepared release and binds its source/mapping review revisions,
identity registry, physical proof files, all six permitted uses, expiry and local
publication epoch. The same operator-configured trusted public key verifies both
strict, distinct signing envelopes. Keys embedded in input files are never trusted.

Private authorization is valid for at most 90 days. The audience is explicitly
`deployment_shared`; a firm's source-use acceptance alone is insufficient. The
reviewer must establish that all conditions of this audience permission are met.
Conditional, restricted-audience or multi-source publication is not implemented.
Proof-file hashes establish byte identity, not the legal meaning of a licence.

The accepted private record lives under `/data/release-authorizations/<release_id>`.
It contains `authorization.json` and the original sealed preparation `packet/`.
Files are 0600 and directories 0700. Private identities, revisions, notes, packet
hashes, epoch and rights/identity proofs never enter the shared bundle, RDF,
serving marker, metadata graphs or successful CLI output. The public reviewer's
label is separately and intentionally chosen for publication.

## Operator sequence

Use existing accepted source/mapping reviews and a current packet prepared with
[the preparation CLI](RELEASE_PREPARATION.md). The following are templates for a
trusted operator shell configured for the existing deployment; paths are examples.
Do not use synthetic test reviews or keys in production.

1. Initialize the private policy once with
   `python scripts/review_publication.py init-policy`. It creates a random local
   epoch and a private authorization directory. It never replaces an existing epoch.
2. Create private signing inputs:

   ```sh
   python scripts/review_publication.py candidate /private/packet \
     --operator-id CURRENT_REVIEW_OWNER \
     --public-reviewer 'Intentional public reviewer label' \
     --reviewed-at REVIEW_TIMESTAMP_WITH_TIMEZONE \
     --output /private/signing-inputs
   ```

   Review the complete ontology, canonical identities, evidence and both graph
   inputs. The deterministic conversion removes only the preparation marker,
   changes approved assertions to `legally_reviewed`, and adds the public reviewer
   and review time. It replaces private workflow timestamps with this public review
   timestamp. Identities, relationships, validity dates, source bytes and passages
   are preserved. Open-ended check dates and their separate source passages are
   preserved too; public review cannot predate the checked horizon. Unknown ends
   without that explicit evidence and unsupported text roles remain blocked.
3. The independent reviewer signs the canonical bytes of
   `public-review-body.json` externally. Supply an envelope with exactly
   `algorithm: "Ed25519"`, `body`, and a base64 `signature`. The app has no signing
   operation. Build and prepare the approved public bundle:

   ```sh
   python scripts/validate_ontology.py create-bundle \
     --structure /private/signing-inputs/inputs/structure.ttl \
     --jurisprudence /private/signing-inputs/inputs/jurisprudence.ttl \
     --evidence-dir /private/signing-inputs/evidence \
     --review-attestation /private/public-review.json \
     --trusted-review-key /trusted/reviewer.pem --output /private/bundle
   python scripts/graph_releases.py prepare /private/bundle \
     --trusted-review-key /trusted/reviewer.pem --output /private/prepared
   ```
4. Request independent deployment permission. The audience evidence hash must
   identify a physical proof already included in the private packet:

   ```sh
   python scripts/review_publication.py request /private/prepared \
     --packet /private/packet --operator-id CURRENT_REVIEW_OWNER \
     --trusted-review-key /trusted/reviewer.pem --reviewer 'Private accountable reviewer' \
     --approved-at APPROVAL_TIMESTAMP_WITH_TIMEZONE \
     --expires-at EXPIRY_TIMESTAMP_WITH_TIMEZONE \
     --audience-evidence-sha256 SHA256_OF_AUDIENCE_PROOF \
     --output /private/authorization-request
   ```

   Independently review and externally sign the exact canonical private body in
   `authorization-body.json`, using the same envelope format. Include no unsigned
   amendments. This approval explicitly covers identities, use and audience.
5. Accept the externally signed authorization:

   ```sh
   python scripts/review_publication.py accept /private/prepared \
     --packet /private/packet --operator-id CURRENT_REVIEW_OWNER \
     --trusted-review-key /trusted/reviewer.pem \
     --authorization /private/signed-authorization.json
   ```

   Acceptance reacquires current review locks, reconstructs the packet and exact
   transformed public graphs, verifies every signature and source byte, and writes
   the private record atomically without replacing an existing record. Signing
   offline itself cannot prove live freshness; freshness is checked when accepting
   the signature and again at each subsequent boundary.
6. Initialize graph-volume permissions with `python scripts/graph_releases.py
   initialize`, then install using the existing CLI. Stop API and Fuseki explicitly
   before activation/rollback. Every transition requires the private authorization:

   ```sh
   python scripts/graph_releases.py install /private/prepared --trusted-review-key /trusted/reviewer.pem
   python scripts/graph_releases.py activate RELEASE_ID --trusted-review-key /trusted/reviewer.pem \
     --expected-current none --expected-sequence 0
   ```

   Default commands use Compose's dedicated `publication` profile publisher. It
   uses the API image, UID 10001/GID 10002, no published ports, no provider secrets
   and only the internal private network. It holds the private database review
   locks itself through the filesystem transition. The graph volume uses a shared
   publisher group; ordinary API and Fuseki graph mounts remain read-only.
   `--root` requires the same private live checks and is not a bypass.

Inside Compose, run private preparation/review commands using the publisher image
with `--entrypoint python` and `/app/scripts/review_publication.py`, mounting only
needed operator input/output directories. The service already has the database,
source and private-data configuration. Its default private-data mount is read-only;
for `init-policy` and `accept` only, the trusted operator must explicitly override
the existing documents volume mount to `/data` as read-write. Keep transition
commands on the read-only default. Do not copy root `.env` into a packet.
The Fuseki-only image cannot perform private approval or publish a release.

## Transition, runtime and restore behavior

Installation holds its filesystem lock; activation/rollback first obtain the
exclusive publication lock, then private review locks. Row locks follow the existing
operator → source review → provision mapping order. PostgreSQL connection, statement
and row-lock waits are bounded. The target is checked again at operation exit.
Existing installed releases and rollback targets receive the same current checks.
An old signature or previous-pointer entry is never continuing authorization.

API startup, graph queries, lexical/vector search, final research saving, review and
export check current private authorization. Search must match the active graph
release. Index hits must match signed raw-source hashes, complete quoted passages,
locators and evidenced authority links; index-only titles, URLs and identifiers are
never returned. Current signed RDF lacks public URLs, so projected hits return no
URL rather than trusting index metadata. Missing records, unavailable review storage, changed source/rights/mapping
state, inactive or reassigned owners, changed trust/epoch and expired permission
fail closed. Retained products project a stale state; their stored text, review
history and cited snapshot are preserved. Request-time checking does not rewrite
previous work. Graph-dependent saves and reviews retain a pending authorization
marker through the final check. If a check fails after the database commit, the
response identifies the saved work as requiring revalidation, rather than claiming
it was rolled back. Export auditing records preparation, not delivery. There is no
permissive legacy signed-release fallback.

Fuseki verifies public bytes and holds the publication read lock. It receives no
private database credential or review record. Continuing authorization is enforced
by the application's retrieval broker; Fuseki remains an internal, query-only
service, not a user-accessible authorization boundary.

A failure after an atomic pointer replacement may have committed the transition.
The CLI reports this possibility: inspect the public pointer and installed inventory
before retrying. It never blindly reverses a pointer or deletes a foreign output.
The `status` command reports signature integrity only, explicitly not current
private authorization. The application readiness state performs the live check.

Encrypted restore now removes the restored publication epoch, including after a
failed extraction. Historical approvals therefore cannot revive automatically.
Initialize a fresh policy, re-review current source state and obtain a fresh signed
release/authorization before resuming research. Existing private authorization
records are retained for audit and never overwritten. Any manual database restore
outside this tool must invalidate the epoch before starting services.

Full reconstruction and signature/SHACL checks run at each gate in this initial
implementation. This prioritizes correctness for the small initial corpus; large
corpus latency, authorization renewal, multi-source locking and five simultaneous
research jobs still need qualification. A valid signature establishes the configured
signer's approval, not their professional qualification or universal legal truth.
