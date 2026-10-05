# Local deployment and recovery

This is a development and evaluation baseline, not a production-qualified release.
The application, provider authentication, source rights, legal accuracy, capacity,
availability and privacy controls require separate qualification. Do not admit live
client matters until those gates pass. No provider key or existing credential is
created, read, rotated or reset by these setup instructions.

## Two ways to run

**Synthetic demonstration:** install Python 3.12+, Node 22 and `uv`, then run:

```sh
(cd backend && uv sync --frozen --extra dev)
(cd frontend && npm ci)
./scripts/dev.sh
```

Open `http://127.0.0.1:5173`. The isolated demonstration uses SQLite in `.data/demo`,
loopback API port 8000, and `demo` / `demo-local-only`. These are visibly synthetic
demo credentials, never a deployment credential. It disables live provider,
OpenSearch, Fuseki and research-gateway connections. It does not replace an
existing account or change the root `.env`. Stop it with Ctrl-C. A current LLM
credential is not required for this demonstration.

**Container evaluation:** manually copy `.env.example` to the gitignored root
`.env`, supply unique bootstrap credentials, a random URL-safe PostgreSQL
password and one persistent Fernet encryption key. Protect `.env` with owner-only
permissions and store the encryption key separately in your organization's secret
store. Supply a distinct random `LA_EXTRACTION_TOKEN` with at least 32 characters
for the isolated parser. Never print `docker compose config` without `--quiet`: the resolved form
contains secrets. Docker administrators can inspect container environments; use
mounted secrets and a secret manager before production qualification.

`LA_BOOTSTRAP_PASSWORD` is validated only when the configured username does not
yet exist: new accounts require at least 16 characters. Subsequent starts preserve
the existing account's password, role, active state and sessions. Editing the
bootstrap value does not change the password used to sign in.

The default stack now has seven services and six unique images: API and extractor
share one image; web, Fuseki, PostgreSQL, OpenSearch and scanner use the others.
After building and before first startup, provision signed CVD databases using the
[scanner guide](../deploy/scanner/README.md). Set `LA_CLAMAV_HOST=scanner` and
`LA_SCANNER_DATABASE_DIR` to the admitted read-only database release. The scanner
never downloads signatures at runtime.

```sh
docker compose config --quiet
docker compose build
docker compose up -d
docker compose ps
```

The only published port is `127.0.0.1:${LA_HTTP_PORT}` (default 8080) for the
frontend and same-origin API proxy. The current local setup uses 8081 because
8080 was occupied. Update `LA_ALLOWED_ORIGINS` alongside a port change.
PostgreSQL 16, OpenSearch 2.19.3 and both Fuseki/TDB2 datasets remain private.
Docker Desktop requires a non-internal ingress network for port publishing.
The web startup wrapper installs a default-deny outbound firewall, permits only
the resolved API address on port 8000, established replies and its loopback health
check, then runs nginx as UID 101 with no effective capabilities. IPv6 and IP
forwarding are disabled. DNS is used only during startup to resolve the API;
the generated nginx configuration uses that fixed address. If the API is
recreated with a different address, restart web to refresh both configuration
and firewall rules. Firewall setup failure prevents nginx startup.
Compose intentionally requires explicit credentials even for configuration
validation. For a secret-free static check only, pass dummy values in the command
environment and `--env-file /dev/null`, as CI does.

If Docker Desktop build-network DNS cannot reach Alpine package repositories,
the local web image can be built with
`docker build --network=host -f deploy/frontend.Dockerfile -t lawyer-assistant-web:0.1.0 .`
before `docker compose up -d --no-build`. This affects image building only;
runtime network restrictions remain in Compose. Disconnected installations
must receive prebuilt, approved images.

The default PostgreSQL URL uses the supplied password in a URL; keep that password
URL-safe, or supply an explicitly percent-encoded `LA_DATABASE_URL`. Changing
`POSTGRES_PASSWORD` after a database already exists does not rotate its role's
password. No setup/recovery script attempts credential rotation.

The web container serves prebuilt Vite assets through nginx. API `/api/v1/health`
is a process/service check, not evidence that inference or legal research is
ready. Missing models, credentials, scan configuration or source data must remain
unavailable states. Compose starts a private ClamAV service on TCP 3310. It
requires officially signed CVD files imported through the approved offline
process. The daily signature database may be at most seven days old by default;
`LA_SCANNER_MAX_SIGNATURE_AGE_DAYS` permits 1–14 days. Signature admission, scanner
health and every upload enforce that policy. A missing, stale, unavailable or
invalid scanner blocks intake, not application login or reading existing
documents. A clean scan alone does not establish parser safety.

Use **Bağlantıları denetle** on the system page for an authenticated, timestamped
`GET /api/v1/readiness` report. Provider checks validate configuration,
authenticated model metadata and the selected local model's context limit; they
do not generate text or establish tenant binding, cloud-fallback isolation or
legal correctness. Intake checks validate scanner readiness and the extractor's
authenticated `/ready` response. The documents panel uses the provider-independent
`GET /api/v1/intake/readiness` endpoint and disables new uploads until ready.
**Yeniden denetle** retries after service recovery; every upload still performs
its mandatory scan. Diagnostic details remain collapsible.

Production extraction goes through `LA_EXTRACTION_URL=http://extractor:8002`;
there is no local-parser fallback outside the synthetic demo. The extractor is a
separate nonroot container with a read-only filesystem, a 256 MiB no-execute
temporary filesystem, 1.5 GiB memory/no swap, two CPU equivalents and 96 processes.
Only API and extractor share the internal `extraction` network. The extractor has
no published port, Internet route, database/provider/graph network, matter volume
or application encryption/provider key. Its only application secret is the
dedicated extraction token. API forwarding between its networks is disabled.

The API must scan before dispatch. It sends only raw document bytes and an
admitted suffix, never the client filename, matter ID or provider credentials.
The worker admits two jobs, bounds uploads to 20 MiB and 30 seconds, and starts a
fresh parser subprocess for each document with a clean environment and temporary
directory. Each parser has a 60-second execution budget and existing CPU/output
limits; its process group is killed and temporary files removed on completion or
failure. Both worker and API client validate text/locator/warning/count fields
and reject additional identity, path or executable fields. The client rejects
redirects, proxy inheritance, public destinations and compressed/oversized/late
responses. Worker `/health` indicates process availability only; its separate
token-protected `/ready` contract verifies the extraction service protocol and
configuration without parsing a document.

This is implemented isolation configuration, not a demonstrated hostile-parser
containment claim. Before confidential intake, test it on the deployment host:
attempt outbound connections and access to sibling services, inspect mounted
paths/secret visibility, test archive/image bombs and process exhaustion, and
confirm cleanup after timeout/crash/disconnection. The persistent worker and its
per-job subprocesses still share one kernel, UID and container. A native parser
compromise could inspect another concurrent temporary job or deliberately escape
ordinary process-group cleanup. This does not provide adversarial isolation
between parser jobs; qualify separate per-job sandboxes before relying on that
boundary. Schema validation also cannot prove that a compromised parser extracted
the original faithfully. Local clean-upload, original-download, EICAR rejection
and scanner-outage checks passed; see [current validation evidence](VALIDATION.md).
Those checks do not establish hostile-parser containment on a customer host.

## Network and data boundary

- API, PostgreSQL, OpenSearch and Fuseki use the internal Docker network
  `lawyer-assistant-v1-private`. They have no Internet route through Compose.
- Parser traffic uses the separate `lawyer-assistant-v1-extraction` internal
  network. Do not attach the extractor to the private data or research networks.
- Scanner traffic uses the separate internal `scanning` network, shared only
  with the API. The scanner has no published port, application credentials,
  matter volume or access to the extractor, provider and public gateway networks.
- The provider must be reachable through an operator-approved private route,
  normally by placing its container on this internal network. The initial
  provider adapter accepts vetted RFC1918/ULA/loopback IP literals only, not DNS
  names; this prevents a DNS check and the actual connection resolving to
  different destinations. Link-local, unspecified, multicast and other reserved
  addresses are rejected. HTTPS must validate a certificate containing that IP
  address. Explicit `LLM_PROVIDER_ALLOW_PLAIN_HTTP=true` permits HTTP only to an
  admitted private/loopback address on a reviewed private route; never use it to
  bypass an external provider restriction. Hostname/SNI/private-CA integration
  needs separately qualified transport support for direct providers. A public
  provider URL will not become reachable merely by supplying credentials. The
  explicitly approved laptop-tunnel option below still uses a private API route.
- The optional `native-provider` profile starts a narrow relay on the internal
  provider network and brings the default stack to eight services/seven images.
  Its firewall allows only the resolved private native host on TCP 8080, or one
  explicitly approved tunnel's pinned public IP on TCP 443; the API
  keeps its internal networks. Only authenticated model discovery and bounded
  completions for one pinned local model are forwarded. Follow the
  [native-provider activation checks](../deploy/provider/README.md) before
  `docker compose --profile native-provider up -d`. The profile does not enable
  identity or cloud-fallback attestations, nor does a relay health check prove
  inference readiness. Those attestations remain disabled until independently
  verified. Do not change a shared native engine's global fallback behavior as a
  consumer-setup shortcut.
- The optional laptop-tunnel exception requires `LLM_PROVIDER_TUNNEL_URL`,
  `LLM_PROVIDER_TUNNEL_APPROVED=true` and an exactly matching
  `LLM_PROVIDER_TUNNEL_APPROVED_HOST`. Leave the API base on the fixed private
  relay URL. Follow the [exact-host contract](../deploy/provider/README.md), verify
  the native tunnel mapping and its inspection/retention settings, then recreate
  API and relay. Recreate web after API replacement so its firewall pins the
  current API address. This mode uses internet transport; do not include it in an
  air-gap qualification. Default blank/false settings retain the private route.
- Optional public research requires `LA_GATEWAY_ENABLED=true`, a distinct strong
  `LA_GATEWAY_TOKEN`, a reviewed `LA_GATEWAY_ALLOWLIST`, and
  `docker compose --profile research up -d`. The gateway alone joins the external
  network. It receives no database, document volume, encryption key, bootstrap
  password or LLM provider credential.
- Docker's research network permits outbound traffic. Destination enforcement
  inside the worker is an application control, not an OS firewall. Production
  requires an egress proxy/firewall allowlist, DNS/redirect/SSRF tests and evidence
  that unapproved query/body/header/metadata never leaves the boundary.
- The default gateway accepts public legal queries; matter-specific requests need
  exact-request lawyer approval and may still be denied. Do not expand allowlists
  to bypass a blocked request. Failure to fetch must not appear as successful
  research.
- BYOK deep search is a [planned separate capability](LEGAL_ANALYSIS_AND_DEEP_RESEARCH.md),
  not an option supported by the current `research` or `native-provider` profiles.
  Do not put OpenAI/Anthropic/Gemini keys into the local-provider settings or mount
  them in the current public-source gateway. Its future connected broker/vault needs
  its own privacy, legal-fidelity, provider, retention and spend qualification.
  Fully disconnected installations keep that lane absent/disabled; offline analysis
  remains independent. No deployment or credential changes accompany this plan.
- Original uploads use application encryption. PostgreSQL, extracted passages,
  OpenSearch and graph storage are not all encrypted by `LA_ENCRYPTION_KEY`.
  Require host/volume encryption, access controls and protected swap/backups.
- OpenSearch security is disabled only for this unpublished, isolated evaluation
  node. This is not an authenticated or TLS-protected production search cluster.
  Add service authentication, TLS and dedicated service identities before a
  multi-host or multi-user production deployment. Docker network membership is
  not a substitute for matter authorization.
- HTTP with `LA_COOKIE_SECURE=false` is confined to loopback evaluation. Deploy
  behind an approved TLS ingress, configure exact allowed origins and enable
  secure cookies before remote access. The baseline must not be bound to
  `0.0.0.0` as a convenience shortcut.

The configured identity is tenant `lawyer-assistant-v1`, organization
`org-lawyer`, key ID `lawyer-assistant-v1-primary`. The user-managed root `.env`
key passed local registry binding and authenticated model-list checks on
4 October 2026. The deployed relay also passed a synthetic exact-evidence
completion using local `ministral-3:8b`. See [verification](VALIDATION.md) for
the measured scope; repeat binding/readiness checks after provider changes.
The key remains manually supplied through `.env`; live readiness and tenant
binding are separate checks. The provider
has no verified nonadmin whoami endpoint. Do not expose or call provider admin
routes through the application, and do not infer the identity binding from a
successful model-list response. Provider-operator attestation or a caller-only
identity contract is required. Keep OpenRouter fallback disabled and confidential
tool payloads out of provider telemetry. Do not modify a shared provider globally
as part of consumer setup.

## Offline user administration

`scripts/manage_users.py` provisions colleagues without changing existing
credentials. Run it only on the trusted deployment host against an existing
schema, during a maintenance window with API requests/research stopped. This
avoids racing the CLI's last-member checks with new matter creation. PostgreSQL
row locks serialize access changes made by this CLI; this is not a substitute
for a qualified live identity-administration service. The command does not call
an external identity service, bootstrap accounts, migrate schema or create keys.
`--help` is safe before configuration is loaded.

Supply your existing active administrator ID, obtainable from your authenticated
`/api/v1/auth/me` response before maintenance. Replace the uppercase identifiers
below with actual IDs. Commands list only user IDs, names, roles and active state
within that administrator's firm. They never print passwords or password hashes.

```sh
docker compose stop api
docker compose run --rm --no-deps api python /app/scripts/manage_users.py --operator ADMIN_ID list
docker compose run --rm --no-deps api python /app/scripts/manage_users.py --operator ADMIN_ID create --username NEW_USERNAME --name 'Lawyer Name' --role lawyer
docker compose run --rm --no-deps api python /app/scripts/manage_users.py --operator ADMIN_ID grant --user USER_ID --matter MATTER_ID
docker compose run --rm --no-deps api python /app/scripts/manage_users.py --operator ADMIN_ID revoke --user USER_ID --matter MATTER_ID
docker compose run --rm --no-deps api python /app/scripts/manage_users.py --operator ADMIN_ID deactivate --user USER_ID
docker compose up -d api
```

These are separate operator actions, not a script to execute in full. Account
creation requires an interactive terminal and a hidden, confirmed password of
16–200 characters. Never put passwords in command arguments, pipes or logs.
Existing usernames are rejected without a password reset. Available roles are
`lawyer`, `curator` and `admin`; new accounts receive no matter memberships.
Curators can use the separately authorized practice-playbook workflow but cannot
administer users. Account reactivation, password reset and role changes are not
part of this command.

Grant/revoke requires the operator to already belong to that active matter;
administrator status alone cannot bypass matter access. Cross-firm mutations
and grants to inactive users are denied. Revocation or deactivation cannot remove
the last active member of an active or archived matter. Archived matters also
retain at least one existing active administrator member when that administrator
is deactivated, because restoration requires both role and membership. Restore
an archived matter through its authorized workflow before changing memberships.
Self-deactivation is prohibited. Deactivation disables the account and deletes
all its login sessions; passwords and historical memberships remain intact.
Successful operations record actor/action/target/matter metadata in the audit
table without password or matter-content logging.

## Qualified public search

The baseline public corpus is empty. Leave `LA_SEARCH_RELEASE_ID` empty until an
approved publisher has loaded and qualified an immutable release in the sole
admitted index, `law-public-passages`. Merely setting a release identifier is not
qualification. The read-only adapter does not create indexes, import documents,
promote gateway downloads or put matter documents into public search. Missing
configuration returns `no_qualified_corpus`; source completeness remains unknown.

Each indexed passage needs exact `passage_id` (also the OpenSearch `_id`),
`document_id`, `source_version_id`, `authority_id`, lowercase `source_sha256`,
`release_id`, `text`, `title`, `source_url` and `locator`. Graph-linked entity IDs
may be bounded absolute RDF IRIs or local IDs; release identifiers use a separate
restricted grammar. `visibility=public`, `rights_status=permitted` and
`review_status=legally_reviewed` are mandatory filters, with exact release and
optional authority binding. The index publisher must map those identity and
status fields as exact keyword fields. These labels require a separately reviewed
publication process; the adapter cannot establish their truth from index content.
It independently rechecks returned metadata, projects only admitted fields and
rejects conflicting passage versions.

`valid_from` and optional exclusive `valid_to` are version intervals. An `as_of`
request requires a known interval containing that date; interval membership alone
does not establish which law applies to the matter. Text search uses a lexical
channel. Optional vectors from a qualified local embedding model use a separate
channel and reciprocal-rank fusion, with identical qualification filters inside
the kNN query. A supported Lucene/Faiss mapping, embedding model/version/dimension
compatibility and Turkish retrieval recall must be qualified before enabling
vectors; this baseline does not generate or pin embedding artifacts. Exact
authority resolution uses identifier filters rather than depending on text or
vector similarity. See OpenSearch's
[native filtered kNN requirements](https://docs.opensearch.org/latest/vector-search/filter-search-knn/efficient-knn-filtering/).

Queries, candidate counts, response bytes/nodes and request time are bounded.
Partial or unavailable retrieval remains explicit; matching candidates are not
released legal conclusions. The index must retain immutable physical-source
artifacts and a signed or otherwise authenticated publication manifest so an
operator can independently verify each claimed source version and hash.

## Graph and resource management

`LA_GRAPH_URL=http://fuseki:3030` is the server base. `/structural/query` and
`/jurisprudence/query` are separate persistent TDB2 datasets. The baseline exposes
query endpoints only; HTTP update, upload and admin paths are not available.
They start empty. No synthetic legal assertion is automatically imported into
either dataset. `ontology/fixtures` is test/demo material, not an authoritative
corpus. Validate ontology changes with `python scripts/validate_ontology.py`.

Versioned corpus publication needs an approved offline import job and source
manifest before real graph data is admitted. Do not open a TDB2 directory from a
second process while Fuseki is running. The schema-catalog explorer (synthetic
assertion fixtures are excluded) and a running Fuseki service are distinct states;
empty storage is not a source-coverage
claim. Configuration follows [Jena's TDB2 assembly guidance](https://jena.apache.org/documentation/tdb2/tdb2_fuseki.html)
and [Fuseki endpoint configuration](https://jena.apache.org/documentation/fuseki2/fuseki-configuration.html).

Start with at least 4 CPU cores, 8 GiB available Docker memory and sufficient disk
for copies, indexes and backups; this is a development allowance, not measured
pilot capacity. Configure Linux `vm.max_map_count` to at least 262144 for
OpenSearch. The baseline allocates 512 MiB JVM heap to OpenSearch and Fuseki.
Qualify actual OCR volume, index size, active concurrency and separate inference
GPU capacity. It is a single-node topology with no high-availability claim.

## Encrypted cold backup

The scripts require the stack's containers to exist and an operator-provided
`age` recipient file. Create and protect the corresponding age identity outside
the repository using your normal key-management procedure. The API image carries
`age`; the host scripts require Python 3.12 and Docker only.

```sh
./scripts/backup.sh /secure-backups/lawyer-2026-10-04.age \
  --recipients-file /secure-keys/backup-recipients.txt --stop-services
```

First stop any offline graph publisher or public-source importer; these one-off
processes are outside Compose's service lifecycle. Keep them stopped until backup
finishes. The command stops currently running stack services, including optional
provider/research services, and archives all five volumes at
one cold point, encrypts the compressed stream without writing a plaintext host
archive, and restarts only the containers that were running. It refuses to
overwrite existing archives. A failure removes only its newly created partial
file. If restarting fails, it reports failure and leaves manual recovery explicit.
The archive includes source image identities and a timestamp, not root `.env` or
backup identity files. Retain the application encryption key, database password,
image artifacts and deployment configuration separately; all are needed for a
usable recovery. Scanner signature releases are read-only bind mounts outside
the five backed-up volumes: preserve their signed CVD files and manifests
separately, and admit an unexpired release before restoring intake. The archive
does contain account/session database state: treat
it as confidential even when encrypted.

The v2 archive includes public-source staging and immutable graph bundles, receipts
and activation history. Preserve the independent graph-review public trust key
and trust-directory configuration separately; neither is restored from the archive.
Older four-volume v1 archives require their original matching restore tool/images;
the v2 tool deliberately rejects them instead of silently omitting source staging.

This is a downtime-based baseline, not an online backup, PITR system or proven
RPO/RTO. Custom PostgreSQL tablespaces/symlinks are not supported. The export
refuses links and special files rather than producing an incomplete backup.

## Restore into a new stack

Use the exact source images and original application/database secrets. Set a new
project name in the shell; do not overwrite an existing `.env` or reset credentials.
Ensure the original stack is not using the target port when you later start web.

```sh
export LA_STACK_NAME=lawyer-assistant-restore-drill
docker compose create api postgres opensearch fuseki
./scripts/restore.sh /secure-backups/lawyer-2026-10-04.age \
  --identity-file /secure-keys/backup-identity.txt --fresh-target
docker compose up -d
```

Restore requires stopped containers and five empty volumes. The graph volume may
contain only the fresh image's empty `releases/` directory and zero-byte
`publication.lock` / `.install.lock`; existing releases, pointers and databases are rejected. It checks
the full encrypted archive, source image match and archive paths before writing;
it rejects links, devices, traversal and missing volume data. Existing data is
never deleted. A write failure can leave partial data only in the fresh target;
preserve it for diagnosis and use another fresh project for a later attempt. The
restored services stay stopped until explicitly started. Validate login, document
decryption, evidence locators, relational counts and both graph datasets, then
exercise search rebuild/recovery before declaring a successful drill. Restrict
access until restored sessions and credentials have been reviewed by the owner.
Restore invalidates the historical publication epoch, including after extraction
failure. Reinitialize private policy and obtain fresh release authorization before
public-corpus retrieval can resume; see [publication authorization](PUBLICATION_AUTHORIZATION.md).

For independently reviewed graph preparation, activation, rollback and trust
mounts, follow [Fuseki publication](../deploy/fuseki/README.md). For isolated public
source acquisition and pending-review staging, see [registered sources](REGISTERED_SOURCES.md)
and [public-source intake](PUBLIC_SOURCES.md). Staged sources never become search
results or legal authority merely because an import succeeds.

### Source-review records

The API registers `source_review_heads` and `source_review_events` before startup
schema creation. Existing installations receive these additive tables without
rewriting matter records. They are included in the existing PostgreSQL cold-volume
backup. Assignment, notes, evidence references and reviewer projections use the
application encryption key; firm/source routing IDs, revisions and timestamps
remain database metadata. Protect the database and key together with their existing
retention and recovery controls.

The API keeps events append-only and rejects stale revisions through database
compare-and-swap and uniqueness constraints. This is not a tamper-proof external
audit log. A firm/source review is capped at1,000 events; the UI and dossier return
the latest50, explicitly marking truncation, while retaining the latest assessment
in each category. Preserve a protected database archive for full-history recovery;
do not delete older events to bypass the cap. Review exports are confidential and
unsigned; distribute them only within the approved publication-review process.

The source package remains read-only, including after all assessments are accepted.
Recovery must verify source bindings and decrypt review payloads as well as matter
records. Automated physical erasure, legal holds specific to source reviews,
production schema migration tooling and a complete restore drill remain later
qualification work; no source-review deletion endpoint is exposed.

Provision mapping adds `provision_mapping_heads` and `provision_mapping_events`
to the same encrypted relational store and existing PostgreSQL volume backup.
Each firm/source ledger is capped at 200 mappings and 1,000 events. Responses
retain current mapping snapshots and the latest 50 events; bounded replay of all
event headers proves that current mappings reflect the latest decisions, including
those outside that display window. Source reviews reconstruct current ownership
and assessment decisions from the full bounded ledger too. Every mapping
write checks the current source-review owner and both revision counters. On
PostgreSQL, identity then source-review row locks serialize review changes with
acceptance; mapping updates also use compare-and-swap. Accepted mapping records
become stale after source-review changes without rewriting the original decision.
No physical erasure endpoint is provided; retention, holds and full restore
qualification must include these tables. Candidate extraction remains read-only
and uses no model. No mapping automatically becomes a signed publication assertion.

## Disconnected artifact pack

For the offline, no-write mapping-to-graph review workflow, see
[release preparation](RELEASE_PREPARATION.md). Its confidential packets must stay
outside shared graph volumes. Validation needs the existing local PostgreSQL
store and encryption key; it never bootstraps a database. PostgreSQL row locks
require a normal transaction, so “read-only” here means application-enforced
SELECT/SHOW-only access and no ORM flush, not `SET TRANSACTION READ ONLY`.
Preparation-only RDF is rejected by the release validator regardless of signature.
The separately authorized conversion and live publication gates are described in
[publication authorization](PUBLICATION_AUTHORIZATION.md). Static status reports
signature integrity only; runtime readiness checks continuing permission.

The running baseline requires no npm, PyPI or image-registry access. Build and
review all artifacts on an approved connected build host first:

1. Pin application commit, `backend/uv.lock`, frontend lockfile, base-image
   digests, Fuseki release checksum and approved local model/OCR artifacts.
2. Build the API/extractor, web, Fuseki and scanner images, pull the pinned
   PostgreSQL/OpenSearch images, and record image IDs/digests, software bills of materials, licenses,
   vulnerability findings and review decisions. Published tags are not runtime
   qualification. If using `native-provider`, build and include its relay image
   too. Package security updates require new review and a restore test.
3. Save the six default runtime images with `docker image save` (seven with the
   native-provider relay), plus Compose, configurations, ontology artifacts,
   approved corpus manifests and the scanner's officially signed CVD database
   package with its admission manifest. Include the complete provider
   deployment/model pack separately. Never include `.env`,
   backup identities, client documents or provider credentials in the release pack.
4. Sign/hash the pack, transfer it through the approved import process, verify
   it, then `docker image load` on the target. Admit the CVD package locally using
   the scanner guide; signature freshness still applies at the disconnected site. Run
   `docker compose up -d --no-build --pull never`. No source build runs there.
   Include `--profile native-provider` only after that route's activation checks.
5. Keep the research profile disabled for a disconnected site. For a controlled
   gateway site, qualify the explicit egress path separately. Run a zero-egress
   check, restart/restore drill and actual inference/evidence tests at the target.

Local image builds, service health and bounded intake/readiness checks have been
exercised; [validation evidence](VALIDATION.md) records their scope. Disconnected
installation, customer-host isolation, volume encryption/recovery and legal
qualification remain separate gates. CI checks Python, ontology, frontend build
and Compose syntax; passing CI does not close those deployment gates.
