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

### Research job lifecycle

Run **one API process/worker per database**, as in the supplied Compose image. Five
research threads share ten admission slots (running, queued and reserved combined).
Authorization precedes admission; capacity exhaustion returns HTTP 429 without
creating a job or audit record. Closed admission returns 503. Requests accepted just
before shutdown have an explicit interrupted outcome rather than an orphaned queue
entry. A cancelled running call keeps its slot until the worker actually exits.

`LA_RESEARCH_BUDGET_SECONDS` defaults to **300**, accepts 10–1800 seconds, and is
captured with `deadline_at` for each submission, including queue time. Checkpoints
before graph/search/inference work, after inference, and during publication check
access, stop intent and the deadline. An expired queued job performs no retrieval
when dequeued. There is no timer promising immediate expiry while a dependency is
still running; this is a cooperative budget, not a hard CPU/network kill deadline.

- `queued` → `running` → `completed`, or `failed`/`timed_out`.
- A user stop or archive writes `cancelling`; queued work is removed and acknowledged
  immediately, while running work reaches `cancelled` after it unwinds. The UI keeps
  polling and explains that an in-flight operation must finish first.
- Cancellation and product creation lock the same research record. If cancellation
  commits first, no product is saved. If publication commits first, cancellation
  returns the completed record and preserves its product. The publication transaction
  locks the matter before the run, matching archival order. Existing final public
  authorization checks and stale-product markers still apply.
- Shutdown stops admission, persists stop intent, removes queued work and joins
  workers before releasing database resources. It records `interrupted` for stopped
  unfinished work. Compose allows **240 seconds** before forcibly terminating the
  API; this grace period does not prove that an upstream model call was cancelled.
- On startup, only unfinished `queued`/`running`/`cancelling` records become
  `interrupted`; completed products remain intact. Recovery never auto-retries an
  inference or external request. Start a fresh research job explicitly.

The PostgreSQL coordinator holds a database-scoped advisory lock on a dedicated
connection; SQLite demonstrations use an adjacent OS lock file. Another API startup
fails before recovery. Ownership is rechecked during admission and worker stages;
a lost PostgreSQL connection/lease latches a failure and must not silently reconnect
as owner. Stop the old API and restart it after database maintenance. This mechanism
is not a distributed HA scheduler or a rolling-upgrade/failover qualification.
A database error persisting a terminal outcome disables admission; restore database
access and restart so recovery can classify unfinished records. `/health` remains a
process check, not proof that the research coordinator is admitting work.

All queue entries contain record IDs only. Questions, job phases, deadlines and stop
metadata remain encrypted, matter-authorized records. No private provider response or
exception text is retained in failure messages. Stop intent may be visible before
acknowledgement; never report it as proof that compute has already stopped.

### Inspect a research context

New preparation products retain an encrypted, matter-confidential selection record.
In the research panel, expand **Belge bağlamını ve seçim sınırlarını incele** to
compare exact prepared excerpts with full original passages. Counts distinguish
selected, shortened, omitted and unexamined passages; no model call is implied by
preparation alone. DOCX/PDF exports retain the limitations, ranges and digests.
See [private context packing](CONTEXT_PACKING.md) for fixed limits and prompt accounting.
Keep these records out of ordinary logs and public research requests. Public source
candidates remain separate. Older products are not assigned a new packing record.

### Private analysis drafts and stale work

In **Çalışma notları**, open **Yapılandırılmış analiz taslakları** to author and
check one issue. Source ranges, rule conditions, application and alternatives must
be linked explicitly. Missing critical structure withholds the dependent conclusion;
a clean structural check still grants no legal approval. Preview performs no write
or model call. See [workbench contract and API](ANALYSIS_WORKBENCH.md).

For a saved current version, **Yerel modelden düzenleme önerisi** starts a separate
private suggestion job only on explicit request. One pass is bounded to 120 seconds;
structural repair allows one additional pass, 240 seconds total, and 1,000 output
tokens per call. Configured research limits may be lower. The existing shared queue,
provider checks and exact tunnel exception apply; no cloud fallback is enabled.
Inspect changes, notes and original passages before adopting with a reason. This
appends a Needs review version with model attribution and retains the earlier draft.
Changed inputs/policy, cancellation, timeout or interruption block adoption; partial
output is labelled. Stop intent does not prove immediate upstream compute cessation.
Request-ID retries recover the same job; after reloading, inspect proposal history
before starting an intentional rerun. See [proposal bounds and API](ANALYSIS_SUGGESTIONS.md).

After a current change request, optionally expand **İnceleme bulgularını modele
ekle** and select up to five findings. No selection is automatic. Only selected
findings accompany the local proposal; its response must link actual permitted
edits or disclose manual/unresolved work. Inspect each response and original
passage. Adoption appends an unreviewed draft, retaining the source review and
response lineage without closing findings. A new review/head, source change or
recipe change invalidates the job. The v2 proposal recipe makes earlier v1 jobs
stale; existing draft history remains inspectable. See [feedback contract](ANALYSIS_FEEDBACK.md).

For manual review, open **Avukat inceleme kararı kaydet** and load the displayed
version's source and review bindings. Inspect original documents, then explicitly
evaluate sources, reasoning, fact roles, limits and model contribution. No criteria
are preselected. Record explained changes and linked findings, or accept only the
conditional private draft with all criteria addressed. This is a lawyer declaration,
not public-authority approval or automated legal verification. Critical/major findings
block acceptance; a change request withholds the displayed/exported assessment even
when structural checks pass. New text versions do not inherit the decision.
If review/revision pins conflict, refresh the exact version and history before
resubmitting; identical request-ID retries recover the same saved event. Review
changes invalidate older proposals and prepared work. See [review API and scope](ANALYSIS_REVIEWS.md).

Use **Güncelliği kontrol et** to reload matter inputs and draft freshness. A changed
fact/document/passage/contradiction/check or review recipe leaves previous text, decisions and versions
intact, projects Stale and requires review in a new version. Changed selections at
save return HTTP 409; refresh the facts and explicitly reselect changed passages.
When facts refresh during editing, bind their visible new revision explicitly.
Do not resolve a conflict by removing a condition merely to clear its warning.

Choose a specific immutable version for DOCX/PDF. Stale versions can be exported
as stale, withheld historical drafts; access or dependency changes during rendering
reject the response. Keep drafts, source selections and revision notes within their
authorized matter. This workflow adds no provider or external-access permissions.

### Build or rebuild a public search index

The trusted publisher can build a new **lexical-only** OpenSearch index from the
currently active, independently signed and privately authorized graph. Complete
source/rights/mapping review and graph activation first; see
[publication authorization](PUBLICATION_AUTHORIZATION.md). The builder does not
create a corpus or approvals. It reads no private matter data and never calls an
inference provider.

```sh
docker compose --profile publication run --rm --no-deps \
  --entrypoint python publisher /app/scripts/build_search_index.py \
  --expected-release FULL_ACTIVE_GRAPH_RELEASE_SHA256
```

The publisher uses its existing private database/review configuration and the
internal OpenSearch service. It holds the graph publication read lock before the
live source-review locks, keeping the source snapshot stable and the prior index intact.
Runtime read authorization takes PostgreSQL `FOR SHARE` locks on the operator,
source-review heads and mapping heads, in the existing deterministic order.
Verified readers can overlap, including searches against the prior index during a
rebuild. Preparation, installation, activation and rollback retain exclusive row
locks. Both modes retain full entry/exit validation and the existing database
lock/statement timeouts; permission decisions are not cached.

Shared locks still exclude account, rights and mapping updates. A pending
revocation can wait for an in-flight build, and queued writers can delay later
readers; a timeout fails closed. This change does not promise immediate revocation
or lock-free reads. Callers must not upgrade shared locks or mutate rows within a
read guard. SQLite demo mode remains optimistic. See PostgreSQL's
[row-lock compatibility rules](https://www.postgresql.org/docs/16/explicit-locking.html#LOCKING-ROWS).
Representative lock-wait and production concurrency qualification remains open.
Every output row comes from a legally reviewed assertion and its exact
signed evidence passage, authority, historical interval and original source hash.
Unknown or unsupported intervals and invalid/oversized fields are never guessed or
truncated. URLs remain absent where the signed graph has no authoritative URL.

Each build uses a fresh name bound to the release and a random generation. Existing
indexes and aliases are untouched. The builder uses create-only bulk operations,
checks every item, blocks writes, refreshes, verifies the complete inventory by
count and exact document readback, then records ready metadata. A receipt is emitted
only after the private authorization exit check. It reports the index name, release,
recipe, candidate count and inventory digest; it contains no passage text or private
review metadata. See the OpenSearch [Bulk API](https://docs.opensearch.org/latest/api-reference/document-apis/bulk/)
for the per-item failure behavior checked here; the implementation is tested against
our pinned OpenSearch 2.19.3 image.

A successful build is **not selected automatically**. Set `LA_SEARCH_INDEX` to the
returned concrete index and `LA_SEARCH_RELEASE_ID` to its exact active graph release
in the deployment's private configuration, then recreate the API through the normal
operator deployment process. Verify readiness and representative searches before
using it for work. Roll back an index selection only to an intact index for the
same currently authorized graph release. A different graph release requires the
existing stopped-service activation/rollback workflow and renewed validation.
The legacy fixed `law-public-passages` configuration remains compatible; its name
alone does not establish qualification, and this builder never writes to it.

Managed-index readers reject building, writable, aliased, foreign-release or
incompatible indexes before search and recheck the receipt/write block afterward.
They continue to verify returned passages
against signed source evidence and current private permission. The ready marker
and write block are operational safeguards, not independent legal authority or
protection against a privileged OpenSearch administrator. Original text/identifiers
are preserved. The v3 recipe retains Turkish text analysis and v2's independent
original-token, normalized and folded fields, then adds typed literal-citation
keys. Keyword authority identities remain unchanged. Existing v1/v2 indexes retain
their previous reader paths. See
[Turkish retrieval and migration](TURKISH_RETRIEVAL.md) for pinned profiles, bounded
candidate fusion and exact source-span hints, and
[literal citation discovery](CITATION_RETRIEVAL.md) for supported labels, bounds and
explicitly unresolved targets. Embeddings/reranking and measured
Turkish/adverse recall remain unqualified.

The initial build budget is 2,000 candidate records, 32 MiB of original-plus-derived
JSON, batches of at most 50 records/1 MiB, bounded HTTP responses and a cooperative
60-second build budget. Source
validation/guard checks and in-flight calls can extend elapsed time; this is not a
hard process deadline or production capacity estimate. One passage can produce
multiple assertion/authority records, so the count is not a corpus-completeness
measure. Larger workloads fail visibly rather than silently truncating the index.

On error, retain the reported index for inspection. It may be partially written or
already sealed if acknowledgement or the final permission check failed. Never select
it based only on its name, blindly retry the same writes, or delete another index.
The builder performs no automatic rollback/deletion; a deliberate new invocation
creates a separate generation. Current source revocation disables retrieval even
from previously completed indexes. Retention and removal remain operator-managed.

#### Isolated OpenSearch qualification

```sh
docker build -f deploy/backend.Dockerfile -t lawyer-assistant-api:r02-search .
docker build -f deploy/search-index-test.Dockerfile -t lawyer-assistant-search-test:r02-search .
mkdir -p .data/verification
python3 scripts/qualify_search_index.py \
  --test-image lawyer-assistant-search-test:r02-search \
  --output .data/verification/search-index-drill.json
```

The second image contains pinned test dependencies and fixtures; never deploy it as
the API. The runner verifies both application and fixture fingerprints, uses a
fresh internal-only Docker network and named PostgreSQL/OpenSearch volumes, and
publishes no host ports or bind mounts. Both pinned database images must already
be loaded. PostgreSQL gets a new generated test-only password; the driver creates
and drops random child databases under the dedicated test database. The driver
keeps synthetic source files and test keys in tmpfs; no `.env`, existing database
or provider key is used. Each service is limited to two CPUs and 256 PIDs; memory
caps are 512 MiB for PostgreSQL, 1.5 GiB for OpenSearch and 1 GiB for the driver.

The v5 workload includes targeted synthetic Turkish case/Unicode/apostrophe/alias,
negation/number and original-offset matching, plus seven literal-citation cases
covering role separation, zeros, collisions and forged derived keys. Those matching
cases use a fixture projection. The development benchmark also captures nine profile
searches on invented citation passages and three through the actual signed-source/
private-authorization path. See [benchmark capture and scoring](RETRIEVAL_BENCHMARK.md)
for frozen inputs, complete outcome accounting and uncertainty limits.
The lifecycle workload exercises exact signed passage retrieval, historical filtering,
five concurrent searches during a guarded rebuild, write blocks, an actual
per-item bulk failure and second-source revocation. It observes the revocation
writer's real PostgreSQL lock wait, releases the build, then verifies that committed
revocation blocks every retained index and further builds before search traffic.
The report records those synthetic search timings and writer wait-plus-commit time;
they are not production latency targets. The same isolated run executes the
PostgreSQL snapshot, authorization and research-job race suites, including five
simultaneous guards, protection of every selected source/mapping row, exclusive
publication actions and denial after a waiting reader encounters revocation.
Cleanup must
be confirmed for a passing report. Host crashes/SIGKILL can leave resources; inspect
only the recorded generated project before cleanup. The workload stays outside
routine CI; its test is explicitly skipped unless the isolated drill marker is set.

### Disposable signed-graph lifecycle drill

This opt-in drill exercises the actual immutable publication functions and
Fuseki/TDB2 runtime with three invented, test-signed releases. It uses **no real
legal assertions or permissions**. An explicit synthetic authorization guard is
confined to the fixture process; private authorization, revocation, legal review
and production publication remain separate gates. Never admit the drill's test
key or artifacts to a real deployment.

```sh
docker build -f deploy/backend.Dockerfile -t lawyer-assistant-api:r02-graph .
docker build -f deploy/fuseki/Dockerfile -t lawyer-assistant-fuseki:r02-graph .
mkdir -p .data/verification
python3 scripts/qualify_graph.py \
  --api-image lawyer-assistant-api:r02-graph \
  --fuseki-image lawyer-assistant-fuseki:r02-graph \
  --output .data/verification/graph-drill.json
```

The runner claims a new output file before creating resources and verifies both
images against the checkout. It generates a fresh project, two empty named volumes
and an internal-only network, with no host ports, bind mounts, Docker socket or
`.env` access. The ephemeral private test key is never written. Runtime graph and
fixture mounts are read-only; only the isolated fixture writes them. The bootstrap
can change ownership only after both volumes are empty. Preload the images for
disconnected execution; the runner never builds or pulls them. Kernel resource
measurement requires cgroup v2 with `memory.peak` and `pids.peak`; missing metrics
fail the drill instead of producing estimated values.

Each release has 128 invented linked resources per family, plus the ontology
snapshot (the schema is not thereby legally approved). Both named-graph
inventories and release-specific sentinels must match. The sequence exercises:

1. Start A and repeatedly query both datasets while installing B. At least one
   complete query round must occur within the measured install interval. A remains
   active; activation while Fuseki holds its reader lock must fail.
2. Pause the C importer after the first staged file, kill that fixture container
   with SIGKILL, and prove no C release/pointer was published. Retry the same import;
   the partial stage remains visible for inspection until drill cleanup.
3. Recreate Fuseki with empty tmpfs and compare the regenerated TDB2 inventories
   to A. Stop it, activate B, recreate, and verify B without mixed-release graphs.
4. Stop it, corrupt B's canonical payload, and require startup to exit specifically
   for integrity failure without fallback. Roll back to A with sequence 3 and
   reconstruct/verify A. Refuse a stale sequence and the corrupted rollback target.

The report records source/image fingerprints, hardware/caps, query-round/install
and startup-to-health timings, runtime kernel memory/PID peaks after startup and import phases, and cleanup. Startup
measurements include Compose overhead; query rounds contain four sequential SPARQL
requests. These are small-fixture observations, not production latency or RTO.
TDB2 rebuilding occurs while service is unavailable; concurrent OpenSearch
reindexing, model research and representative corpus load are not exercised.

Ordinary success/failure and Ctrl-C paths clean up only the generated project,
including the deliberately killed container. A passing report requires confirmed
cleanup. A host crash or SIGKILL of the runner can leave disposable resources;
inspect the exact `lawyer-graph-*` project before removing it. Never prune unrelated
volumes. This drill is intentionally outside routine GitHub Actions.

### Five-job application baseline

The opt-in load drill exercises the actual HTTP API, coordinator, encryption,
bounded demo parser subprocesses and PostgreSQL under an explicitly synthetic
provider. It uses a separate driver container, no live `.env` or host data, no
published ports and a fresh internal network/two volumes. The production entrypoint
has no load-control routes; only the guarded test factory exposes them, with a
per-run token. The fixture ignores inherited provider settings and requires the
dedicated `lawyer_load_drill` database.

```sh
docker build -f deploy/backend.Dockerfile -t lawyer-assistant-api:load-check .
mkdir -p .data/verification
python3 scripts/qualify_load.py --api-image lawyer-assistant-api:load-check \
  --output .data/verification/five-job-report.json
```

Choose a new report filename. The pinned PostgreSQL image must already be loaded;
no pulls occur during the drill. The API image's copied source and dependency-input
fingerprint must match the checkout. Docker must expose cgroup v2 `memory.peak`,
`memory.max`, `pids.peak`, `pids.max` and CPU accounting. Missing/incomplete resource
measurements fail the drill. API and PostgreSQL each have two CPUs, 1 GiB memory
and 256 PIDs; the separate driver has one CPU, 768 MiB and 128 PIDs. Allow about
4 GiB free Docker memory plus image/data storage. These limits describe the fixture.

The fixed profile creates five workspaces and uploads 20 files: TXT, DOCX, XLSX
and text PDF, each containing 64 synthetic paragraphs/rows. Five research jobs
wait at a controlled provider gate while five more queue. An eleventh request must
return 429 without a new record/audit. Queued jobs cancel without execution; a
running cancellation waits behind an observed PostgreSQL row lock and retains
capacity until the provider returns. Five additional TXT uploads must finish while
the first five jobs remain active. The cancelled job publishes nothing; the other
four results must be stale. Three fresh five-job waves must finish with current
evidence dependencies and exact quoted passages, then all workers must drain.

The payload-free JSON report records the profile, uploaded byte hashes, image/source
identities, hardware, checks, request timings, 15 fresh-job timings, observed lock
wait and resource data. Nearest-rank p95 values describe only those small samples.
The lock is deliberately held for 250ms after PostgreSQL reports the wait: that
duration is injected contention, not an estimate of normal lock latency. Fresh-wave
throughput excludes the deliberate gate/lock phases and uses an immediate synthetic
quote response; it is **not LLM throughput**.

Docker samples report cache-adjusted memory and CPU; kernel high-water marks cover
short bursts and include startup plus small measurement-process overhead. The driver
is excluded from API/database measurements. CPU accounting includes throttling under
the configured cap. Passing means this bounded fixture completed with no observed
OOM/service failure; it does not establish a sustained stress ceiling or a latency
SLO. No malware scanner, production extractor service, OCR, Fuseki corpus, OpenSearch
retrieval or real inference is qualified by this drill.

The driver has a 240-second outer timeout, 30-second HTTP timeouts and a 60-second
provider gate/terminal-wait limit. Cleanup removes only the generated project and
its volumes/network; a cleanup failure reports the remaining project explicitly.
Keep this drill outside routine CI. Repeat representative tests on the intended
hardware with the reviewed corpus, production intake and evaluated local model
before qualifying five simultaneous production research jobs.

### Readiness checks

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
approved publisher has loaded and qualified an immutable release in the
legacy fixed index, `law-public-passages`, or a sealed release-bound managed index
from the builder above. Merely setting a release identifier is not
qualification. The read-only adapter does not create indexes, import documents,
promote gateway downloads or put matter documents into public search. Missing
configuration returns `no_qualified_corpus`; source completeness remains unknown.

Each indexed passage needs exact `passage_id`,
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
The fixed legacy route uses `passage_id` as OpenSearch `_id`; managed indexes add
`assertion_id` and hash the release/passage/assertion/authority tuple, preserving
distinct evidenced relationships for the same passage.

`valid_from` and optional exclusive `valid_to` are version intervals. An `as_of`
request requires a known interval containing that date; interval membership alone
does not establish which law applies to the matter. Text search uses a lexical
channel, with independent original/normalized/folded channels for v2/v3 managed
indexes and source-verified literal citation occurrences for v3. Citation-number
matching never resolves the target authority or its historical version. Optional
vectors from a qualified local embedding model use a separate
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

The helper selects exactly five distinct **named** volumes from the selected
containers, rather than inheriting every service mount. Read-only service mounts
(notably graphs and public sources) receive a direct writable mount only in the
offline restore helper. Host bind mounts are not accepted as archive roots; trust,
configuration and scanner mounts are excluded. Backup respects each container's
configured shutdown grace (240 seconds for the API) instead of overriding it with
a shorter stop timeout.

Both scripts accept `--project-name NAME`, repeated `--compose-file PATH` and
`--env-file PATH`. Pass the same explicit configuration used to create the target;
`--env-file /dev/null` prevents root `.env` loading for a fully specified drill
configuration. With these flags omitted, the repository Compose configuration and
its normal environment behavior are preserved.

The v2 archive includes public-source staging and immutable graph bundles, receipts
and activation history. Preserve the independent graph-review public trust key
and trust-directory configuration separately; neither is restored from the archive.
Older four-volume v1 archives require their original matching restore tool/images;
the v2 tool deliberately rejects them instead of silently omitting source staging.

This is a downtime-based baseline, not an online backup, PITR system or proven
RPO/RTO. Custom PostgreSQL tablespaces/symlinks are not supported. The export
refuses links and special files rather than producing an incomplete backup.

### Disposable synthetic recovery drill

Run this opt-in engineering drill after building/loading the images. It is not a
routine CI job. The pinned PostgreSQL/OpenSearch images must already be available;
the drill refuses pulls. Build the API from the current checkout: its copied source
and dependency-input fingerprint must match before any stack is created.

```sh
docker build -f deploy/backend.Dockerfile -t lawyer-assistant-api:recovery-check .
docker build -f deploy/fuseki/Dockerfile -t lawyer-assistant-fuseki:5.3.0 .
mkdir -p .data/verification
python3 scripts/qualify_recovery.py \
  --api-image lawyer-assistant-api:recovery-check \
  --output .data/verification/recovery-report.json
```

Choose a new report filename per run. The runner generates two fresh project names,
an internal network for each, five independent volumes per project and ephemeral
encryption/database/age keys. It loads no live `.env`, mounts no existing host data, publishes
no ports and makes no provider calls. API/Fuseki/PostgreSQL each have a 1 GiB cap;
OpenSearch has 1.5 GiB, with two CPUs and 256 PIDs per service. Allow roughly 10 GiB
of free Docker memory for both stacks and overhead. These are drill limits, not
production sizing guidance.

The drill uploads/extracts a synthetic text file through the authenticated API,
saves a fixture research product, stores an OpenSearch sentinel and seeds three
durable unfinished research states. After a cold backup it rejects a truncated
encrypted archive without writes, restores into a fresh target and compares all
five inventories (bytes, paths, owner/group and mode), except the publication epoch
that must be removed. It rejects another restore into that nonempty target, starts
the recovered services, checks login/document decryption/all encrypted records,
unchanged completed work, interruption without replay, search persistence and both
empty Fuseki endpoints. A second backup checks that three running source services
restart while a deliberately stopped Fuseki stays stopped.

The JSON report contains image IDs, source fingerprints, hardware/limits, timings,
counts and check outcomes, with no credentials or document payloads. Normal success
or failure removes disposable containers, volumes, networks, archives and keys;
cleanup failure is an explicit failed result listing remaining project names.
A host crash or forced termination can require cleanup of those `lawyer-recovery-*`
projects. The retained report cannot itself restore data; the ephemeral keys are
intentionally discarded.

This covers small synthetic cold recovery with an empty legal corpus. It does not
qualify signed populated-graph rollback, inference, malware/OCR qualification,
power-loss recovery, five-job throughput or production RPO/RTO. Seeded unfinished
records test startup recovery; they do not simulate killing a working provider.
Real deployment qualification must repeat the drill with its reviewed corpus,
actual retained keys and declared hardware under the operator's recovery procedure.

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
