# Local deployment and recovery

Signed-in users change their own password through the top-bar shield icon or
`#/account/password`; see [password self-service](PASSWORD_CHANGE.md). The current
password is required, and success ends every session for that account. Deployment
bootstrap configuration does not reset an existing account and is not rewritten
by this feature. Encrypted documents and review history are preserved.

[Reference-case intake](REFERENCE_CASE_INTAKE.md) is an offline qualification tool,
not a deployment command or runtime permission. Keep real inventories, artifacts
and reports in confidential storage outside Git. Use new owner-only destinations
for invented fixtures. No source acquisition, provider call, database migration or
`.env` access is needed; current application/source authorization remains unchanged.

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
`.env`, set the bootstrap username and provision a new private secret directory
only for a new empty vault. Compose now uses scoped mounted files rather than
literal credentials in its environment. Protect `.env` and secret files with
owner-only permissions; keep an encrypted recovery copy separately. Follow the
[secret-isolation and rotation runbook](RUNTIME_SECRET_ROTATION.md). Never print
resolved configuration, raw inspection or secret files. Use `docker compose config
--quiet` and the allowlisted `scripts/runtime_diagnostics.py`. Docker/root access
still permits privileged secret access; production secret-manager qualification
remains open.

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

The mounted `database_url` includes a properly escaped PostgreSQL credential.
Changing `POSTGRES_PASSWORD_FILE` after a database already exists does not rotate
its role's password. Ordinary setup/recovery commands perform no rotation. The
separate offline migration requires stopped writers, authenticated backups and
exact preservation checks; never replace a vault key by editing a setting alone.

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
The runner selects one unused explicit IPv4 `/28` from the benchmark range using
the bounded Docker network inventory. All three fixture endpoints are pinned;
the network stays internal. Exhausted default Docker address pools do not require
pruning other projects. A conflicting address allocation fails instead of retrying
across networks. Only this generated project's resources are removed.

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

### Configured provider/context and five concurrent callers

`scripts/qualify_provider.py` is a separate opt-in experiment against the deployed
consumer adapter. Run it inside the existing API container, using the script from
the reviewed checkout via standard input. It reads server-side settings and mounted
secrets in memory; it never opens the matter store, original documents or review
records. `--help` does not load settings. It accepts no user prompt or document path.

```sh
umask 077
docker exec -i <api-container-id> python - \
  --expected-model ministral-3:8b --expected-context 8192 --execute-synthetic \
  < scripts/qualify_provider.py > .data/verification/provider-context-new.json
```

Use the exact owned API container ID and a new owner-only output file. No key is
passed on the command line. The model and application budget must match the declared
experiment; the qualifier does not change them. Verify the report's imported adapter,
envelope and validator hashes against the reviewed source. Bind the operator script
hash separately when it is streamed rather than installed. This command uses the
existing authorized transport; the approved laptop tunnel uses the public network
and does **not** constitute disconnected operation.

Authenticated model metadata is checked first. A synthetic context one unit above
the configured limit must reject before the readiness probe. One real completion
then uses exactly the application's conservative UTF-8/reserve boundary, followed
by one wave of five concurrent synthetic callers. Each actual call keeps the existing
120-second adapter budget and 1,000-token completion ceiling. There is no retry,
context increase, cloud fallback or shared-provider administration. The report keeps
all six outcomes independently and requires every call to pass; four successes
cannot qualify a five-caller wave. Five callers do not prove five parallel GPU
executions, and these prompts do not qualify end-to-end real-corpus research.

Outputs must have one bounded, complete source excerpt and the exact first evidence
identifier, with an empty summary. A valid source substring need not repeat the
fixture's label prefix. Paraphrases, unknown references, clipped sentences, extra
claims and incomplete completions fail. Response bodies and exception messages are
never exported. Reports contain only fixed failure codes, timings, synthetic prompt
digests and code/model/transport metadata. Conservative units are not measured
tokenizer counts. Tenant binding and absence of fallback remain separate operator
attestations; model metadata does not independently prove either condition.

The 22 October 2026 measurement passed the exact 8,192-unit boundary and over-budget
guard, but the real five-caller wave returned four valid responses and one adapter
rejection. Keep provider burst qualification open; do not replay until success or
silently raise relay/engine limits. The isolated controlled-provider application
drill passed separately. See [qualification evidence](evidence/provider-load-2026-10-22.json).

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

W02 adds an authenticated administration UI for explicit client/case scopes and
case responsibilities; see [the assignment contract](FIRM_RBAC_AND_SUPERVISION.md).
Upgrade API/schema and take a protected backup before enabling prospective grants.
The API's single coordinator performs the additive migration once per firm; older
writers must not run after enabling these grants. This offline command retains its
maintenance-window restriction and additional active-case access check. It considers
prospective scope for recovery checks, invalidates changed recipients' sessions and
advances the same case-team revision. Use the UI for client scopes and active/archived
case responsibility flags; the CLI changes independent direct memberships only.

W03 adds encrypted manual work/opinion records and the `work_participants` routing
table. Take a protected database/encryption-key backup before schema startup and
upgrade all writers together; mixed old/new writers are not qualified. Retain the
routing table, parent/recipient records and identifiers in backups, legal holds,
restoration and deletion design. Case archiving hides work, retaining histories;
physical erasure remains unavailable rather than pretending to delete routing only.

Creating a request requires an explicitly appointed case supervisor and recipients
who already have case scope and write permission. The queue at `#/work` and case
**İş takibi** are manual work tracking; dates are Europe/Istanbul, with no legal
period computation or external notifications. Each lawyer submits under their own
account; a different current supervisor records exact-submission feedback/acceptance.
Question/date/recipient changes mark earlier work Stale. Removed work recipients
lose sessions even if they retain case scope. Exclusive firm guards order removal
after admitted reads; W02 no-store/session monitoring clears open UI. Copies already
retained outside the browser are not recalled. Qualify target-host lock, disconnect,
restore and distinct-account workflows before rollout. See [human workflow/API](HUMAN_WORKFLOW.md).

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
is deactivated, because restoration requires both lifecycle action permission and current content scope. Restore
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
Before downtime, the helper captures only running state, Compose service labels
and network endpoint metadata. It checks explicit IPv4 and IPv6 requests on
**every attached network**, using network identities rather than display names.
Requested addresses must match the current endpoints. Every explicit reservation
precedes dynamic allocators on that network/address family. Relay → backing
services → API → web startup constraints remain; this also keeps web resolution
after API startup. A topological schedule satisfies both sets of constraints.

Relay-first ordering alone is insufficient: a dynamic backing service can take a
stopped PostgreSQL, API or web address. If the reservation order conflicts with
startup order, the helper **fails before stopping any container or invoking the
archive helper**. It also rejects missing, duplicate, inconsistent or unqualified
metadata, unsupported roles/manual link-local settings and exhausted inspection
bounds (128 running containers, 32 endpoints each, 512 KiB metadata). There is no
unsafe-order override. Keep one-off publishers/importers stopped as above.
The same verified schedule applies after an archive failure. No previously
stopped service is started, no container is recreated, and no retry or longer
shutdown timeout is added.

Check restart admission without keys, archive creation or downtime:

```sh
./scripts/backup.sh --preflight-only
```

Explicit `--project-name`, `--compose-file` and `--env-file` selections work in
this mode too. Do not combine it with archive, key, restore or downtime options.
Success reports only container/group counts and `backup_qualified: false`.
Preflight does not qualify storage, encryption, restore, health readiness or
legal correctness. It deliberately assumes the broadest dynamic allocation on a
shared network; independently excluded IP ranges are not treated as proof that
reordering is safe. Remediate a rejected topology through an independently tested
address/startup configuration, then run preflight again. Do not force a restart.
Exclude concurrent Docker start/connect/network changes throughout backup and
recovery: inspection is a point-in-time check, not an address lease or host lock.

The disposable [restart drill](../scripts/restart_preflight_drill.py) uses an
explicitly selected immutable cached Python image, bounded nonroot sleepers and
a newly created internal bridge, with no published ports, data mounts or secrets.
It calculates one unused `/28` in the benchmark range `198.19.0.0/16` from Docker
IPAM inventory; it never prunes networks or iterates creation attempts. Review
host/VPN routing before running it on another host. It observes dynamic-first
allocation, checks exact endpoint retention under the new schedule, verifies that
the read-only CLI blocks a cyclic topology, and verifies cleanup. Example:

```sh
python3 scripts/restart_preflight_drill.py --image "$LA_RESTART_DRILL_IMAGE_ID" \
  --report /secure-operator-receipts/restart-drill.json
```

Only inventoried Compose-labelled drill containers are operated on. The image
must be trusted and contain Python; set `LA_RESTART_DRILL_IMAGE_ID` to its full
local `sha256:` image ID. No image is downloaded. Receipts distinguish
an observed collision from an unobserved one. These sleeper tests do not qualify
PostgreSQL, OpenSearch or Fuseki recovery, provider behavior or a production
deployment. A mixed static/dynamic cycle requires separate address remediation;
the backup guard continues to prevent entering that unsafe downtime.
See [engineering evidence](evidence/backup-restart-preflight-2026-10-22.json).

#### Preserve existing addresses before cold recovery

The [address operator](../deploy/manage_addresses.py) prepares a read-only,
owner-only plan for the selected existing Compose project. It freezes each
endpoint at its **current** IPv4 address on its existing bridge. The plan binds
container and network identities, image/configuration/mount fingerprints, DNS
aliases, original endpoint requests and a complete dependency order. It does not
create networks, move data, recreate containers, change secrets or select new
subnets. Inspect the private plan separately before applying it; do not paste it
into logs, Git, shared reports or screenshots.

```sh
python3 deploy/manage_addresses.py plan --project-name lawyer-assistant-v1 \
  --plan /secure-operator-receipts/address-plan.json
python3 deploy/manage_addresses.py apply --project-name lawyer-assistant-v1 \
  --plan /secure-operator-receipts/address-plan.json \
  --expected-sha256 "$LA_REVIEWED_ADDRESS_PLAN_SHA256" --stop-services
```

Use the semantic plan hash printed by `plan`, after reviewing that exact plan.
Apply rejects snapshot drift before stopping consumers, then stops web, API,
backing services and relay in dependency order with their existing graceful
limits. With services stopped it disconnects/reconnects only unpinned endpoints,
requests their original addresses and preserves the DNS alias set. Existing
static endpoints need no reconnection. It starts relay, backing services, API and
web in order and waits for each group's existing health checks. Docker may
regenerate endpoint IDs and MAC addresses; these are not evidence identities.
Image, environment, capabilities, mounts, original documents and application
encryption keys are untouched.

Only unique, running, known service roles on exclusively owned IPv4 bridge
networks qualify. IPv6, custom endpoint options, nonzero gateway priorities,
legacy links, unknown roles, stopped service owners, foreign network consumers,
ambiguous identities and address conflicts require separate operator review.
Duplicate aliases preserve the same DNS set. No broad fallback is attempted.
Retain an authenticated recovery point and exclude all other Docker lifecycle,
publisher and import operations throughout the maintenance window. The plan lock
serializes invocations of that plan; it is not a daemon-wide Docker lock.

An interruption while pinning leaves the authorized services stopped. Retain
the plan and its `.journal.json` checkpoint. `resume` accepts the same plan hash
and downtime flags, verifies identities/configuration and only original, pinned
or disconnected endpoints, then finishes that exact plan. It also handles partial
startup by first quiescing the same authorized set. A complete checkpoint cannot
be replayed. Do not recreate containers or restore dynamic requests to guess a
rollback order. Unexpected ownership/configuration changes require inspection.

Successful CLI application verifies endpoint and configuration preservation;
its report still says `health_and_recovery_qualified: false` because a startup
check is not a recovery qualification. The generated `.compose-lock.json` is a
per-host **override**, containing only network names, static addresses and DNS
aliases. Retain it with the verified full deployment configuration and use it on
future recreation; never run it standalone or combine it with an older Compose
file. Validate only with `docker compose ... config --quiet`. Admission must
still pass `backup --preflight-only` against the matching deployment. The guard
remains mandatory after remediation and on later upgrades.

The native restart drill also tests interrupted pinning and exact-checkpoint
resume. The separate five-volume recovery drill now chooses distinct unused
explicit `/28` subnets for source/target, pins all fixture endpoints, verifies
address preservation through cold backup and retains hashes of its host
operator dependencies. It never prunes existing Docker networks or uses the
live `.env`, private documents or provider. Its small encrypted synthetic restore
qualifies only the documented fixture scope, not populated legal graphs,
production RPO/RTO, legal quality or five-job load.
See [address/recovery evidence](evidence/address-recovery-2026-10-22.json).

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

Offline restore also retains set-group-ID directory modes, which control group
inheritance in shared publication storage. Its fresh-target helper includes
`FSETID` with `CHOWN`, `FOWNER` and `DAC_OVERRIDE`; without it Linux can silently
strip the group-inheritance bit when restoring a numeric group outside the
helper's supplementary groups. This capability is confined to the networkless
restore helper and synthetic fixture setup. Backup readers and all application
containers retain their existing capability sets. The recovery drill includes
non-member-group `2775` directories and compares all volume bytes, ownership and
permission modes; matching content alone does not qualify recovery.
The [Linux capabilities manual](https://man7.org/linux/man-pages/man7/capabilities.7.html)
documents this distinction between ownership and set-group-ID permission.
See [permission-restoration evidence](evidence/restore-setgid-2026-10-22.json).

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


## R05A retained-source binding renewal

Use the [reviewed renewal contract](AUTHORITY_REVALIDATIONS.md) for inherited source
bindings. `authority_lineage_revalidation` and `authority_lineage_admission` are
encrypted case records; ordinary matter retention, holds and deletion apply. No
new service, provider call, graph mutation or database migration is required.

A new renewal creates an immutable draft version with a separate pending admission.
A `committed_needs_revalidation` HTTP 409 means the bytes were committed but the
last guard or permission checks did not complete. Preserve the receipt/history and
diagnose the incident; do not flip admission bits, strip retained source references
or retry to force acceptance. Missing proofs fail closed. There is no administrator
override/automatic pending-record repair in this packet. Restore and target-host
acceptance remain independent qualification work.

## R05A registered model-authority trials

[Registered model-authority trials](REGISTERED_AUTHORITY_MODEL_TRIALS.md) use existing
local research workers and encrypted `authority_model_trial`,
`authority_model_observation`, `authority_model_effort` and `authority_model_admission`
case records. Existing retention, holds and deletion apply. No schema/service
migration or new provider credentials are required. Use existing explicitly assigned
authorized accounts; protocol registration itself grants no access or reviewer status.

Each pair has permanent job receipts and at most three model calls. A failed or
stopped arm requires a new protocol; Run cannot replay it. Partial reservation is
visible. Check Current/Stale/Withheld state, exact original/renewal input seals, source
permissions and provider settings before diagnosing absent candidates or export.
Do not infer provider/GPU work from a missing response or treat recorded effort as
automatic timing, qualification or benefit.

`committed_needs_revalidation` means committed encrypted bytes remain pending.
Preserve the receipt, event/protocol and admission record. Diagnose final source and
participant authorization; do not flip completion bits, reseal inputs, strip renewal
references or retry to force admission. There is no override or automatic repair.
Source/admission failures clear protocol text, candidates, observations and effort
history. The metadata list contains opaque IDs/dates/seals only. JSON exports are
confidential case evidence and remain subject to firm handling after download.


## R05A confidential model-authority trial groups

[Model-authority groups](REGISTERED_AUTHORITY_MODEL_COHORTS.md) use encrypted
`authority_model_cohort` and `authority_model_cohort_admission` case records. No
schema migration, new service or provider credentials are needed. Existing case
retention, holds, erasure inventory and deletion cover both records.

Selections and public-authority usage remain confidential. Metadata lists are not
source permission checks: inspect full Current/Stale/Withheld state before export.
A changed run, observation, effort, draft, source, participant access or provider pin
requires a separate exact preview/freeze; original snapshots are never resealed.
Inventories reject limits rather than dropping evidence. A stale history is not a
current trial result, and complete capture is not legal or model qualification.

HTTP 409 `committed_needs_revalidation` retains the opaque committed group ID and
pending admission. Keep the receipt and diagnose source/private authorization; do
not flip bits, strip evidence or retry to force completion. Export remains closed.
There is no override or automatic repair. Confidential JSON handling after download
remains the firm's responsibility. Deployment/restore/offline acceptance and real
legal/model/source qualification remain separate gates.


### Provider burst repair and real five-job qualification — 22 October 2026

The relay admits twelve connection lifetimes for five caller workflows plus health
headroom, while limiting upstream generation to two leases and metadata to two
separate leases. Only overlapping metadata probes with the same credential, route
and model share a result; the entry is removed before publication wakes waiters.
Later probes authenticate afresh. Generation requests authenticate independently.
Queue, connect, TLS and response reads share a shrinking deadline within existing
caller timeouts. Failures expose fixed categories, never upstream text, credentials
or document bodies. There are no automatic inference retries or cloud fallback.

The private quotation recipe `private-quotes-v3-extractive` offers source-span IDs
and copies the selected original text on the server. Unknown, duplicate or augmented
selectors fail. Legacy prose still faces the unchanged exact-reference/quotation
guards; it is not approximately repaired. Full selected passages remain in the
measured prompt, and long unbroken text is not silently clipped. Existing stored
products, original documents and focused-analysis review versions are not rewritten.

For an explicitly authorized, real local-provider workload, build the current API
image and invoke `scripts/qualify_provider_jobs.py --execute-real-provider` using the
backend virtual environment. Supply `--api-image`, `--provider-profile` (an owner-only
JSON file containing exactly the twelve nonsecret fields in `PROFILE_FIELDS`),
`--provider-key-file` (the existing protected key file), `--provider-network`,
`--relay-container`, and a fresh protected `--output` path. Never pass a key value as
an argument. The runner rejects an image whose code fingerprint differs from the
checkout, an unexpected relay or provider network, or an occupied fixture address.
It uses the fixed relay-only internal provider subnet and temporary endpoint .14;
qualify a different network design separately rather than relaxing that assertion.

Only the disposable API joins that provider network and mounts the two inputs
read-only. Its fresh database/document volumes contain invented TXT sources; the
driver and PostgreSQL have no provider network or key mount, and nothing publishes
a host port. Both explicit fixture markers are required, and production startup
does not expose fixture counters. Three declared waves of five research jobs must
all complete, retain exact source revisions, ground every returned claim, and stay
Needs review. A failed wave stops qualification and remains a failed receipt.
Cleanup must remove only owned resources and restore the original network members.
No legal review or private-case inference is performed.

The measured 15/15 result qualifies this synthetic, short-TXT, fixed-model/context
profile and five overlapping application calls. Upstream generation is deliberately
bounded to two; five application jobs do not imply five GPU generations. Kernel
memory/PID peaks and sampled CPU/memory are reported separately; native-engine
resource use, sustained throughput, real-corpus quality and offline operation remain
unqualified. Retain failed diagnostic profiles as well as the passing profile.

Both frontend CI lanes now limit locked dependency installation to one minute with
bounded registry requests. All nine jobs, two test workers, disjoint shard coverage,
lockfiles, existing job caps and five merge timing reserves remain. A dependency
network failure fails early instead of consuming the whole test job. It does not
retry inference or hide failing tests.


### Mixed-format real-provider qualification

Use the existing opt-in `scripts/qualify_provider_jobs.py` procedure with
`--workload mixed-formats-v1`. The default `short-txt-v1` profile remains available
and explicitly identified in receipts. The mixed profile creates five disposable
workspaces, each containing TXT, DOCX, XLSX and text PDF fixtures. Each format has
64 invented records; TXT adds a long Turkish Unicode paragraph. These are synthetic
application/parser exercises, not representative legal judgments or client cases.

Three declared waves of five real-model research jobs must all pass. Before and
after research, authenticated original downloads must match the uploaded SHA256,
and document revisions and extracted passage hashes must remain exact. Each
product must remain Needs review, retain every source revision, and use actual
local-provider output. The verifier checks selected evidence against frozen original
passage offsets and hashes, recomputes the transmitted prompt/budget, verifies
coverage counts and requires nonempty, exactly supported quotations. The mixed
profile additionally requires all four documents represented, explicit omitted
passages and at least one shortened passage. It does not infer that all material
was read, or that quotations establish legal applicability.

A technically completed job with an empty selection fails this answerable fixture's
usefulness gate. `product_claim_grounding_failed` covers both absent and unsupported
claims; inspect the fixed `empty_quote_selection` counter to distinguish absence.
A model may properly abstain on other tasks; never force acceptance by fabricating
quotes, reducing the source inventory, treating empty output as success or rerunning
a failed wave until it passes. Preserve each declared profile and failed result.

The explicitly guarded disposable factory can observe failed relay responses with
Content-Length at most 512 bytes. It counts only fixed diagnostic enums and never
records request bodies, authorization, URLs, upstream messages or accepted response
text. Its provider-local HTTP client namespace adds observation only; production
startup and the global HTTPX module are unchanged. No retry or alternate transport
is installed. Unknown/oversized/compressed diagnostics are ignored while the
original HTTP failure still fails the job.

This fixture uses demo authentication and real parser subprocesses in fresh local
volumes. It does not exercise production malware scanning or the isolated extraction
service. OCR, rendered layout, footnote/text-box fidelity, actual legal corpus,
sustained load, native-engine resource limits and disconnected operation require
separate qualification. No private matter volume is mounted and no review is written.
A failed native qualification is retained even when engineering CI passes.

### Quote-selection evaluation and HTTP stage diagnostics

Use `scripts/qualify_provider_jobs.py --workload quote-selection-v1` with the same
explicit image, protected profile/key paths, owned relay/network, fresh output path
and `--execute-real-provider` acknowledgement described above. This chooses a
separate driver; the short-TXT and mixed-format load profiles retain their original
questions, sources and nonempty-answer gates. No private matter mounts or cloud
fallback are added. The default profile is still `short-txt-v1`.

`scripts/quote_selection_cases.py` freezes seven invented tasks and a suite digest
before inference. Five are answerable, including two contradictory amounts; two
require abstention. The fragment/natural pair shares four source documents, but the
selected context may differ. The driver verifies that all required oracle text is
available in the packed quotation catalog before any inference. It checks exact
versions, spans, original and passage hashes, context measurements, coverage and
pending review state separately from task relevance. An irrelevant exact quotation
fails; an empty positive answer fails; a negative answer must be empty. Expected
answers are not passed to the model. Never force a nonempty selection.

Each of the seven tasks runs once, with at most five concurrent application calls.
The driver records each outcome even if another case fails, drains admitted work,
and rechecks every original/version before the final gate. Completing a different
declared case is not a retry of a failed task. No failed result is replaced or
reclassified by later success. The eight offline contracts exercise parsing,
adversarial relevance, budget/version failures and the complete authenticated driver
with both passing and deliberately failing controlled answers. CI never uses a key.

The guarded disposable API exposes `/_provider_jobs/http` only with its control
token, on the isolated fixture network. Counters have fixed metadata/completion stage
names and finite HTTP status buckets. Success bodies are not inspected by this
observer. Failed responses retain only the existing exact relay-code allowlist,
bounded to 512 identity-encoded bytes; unknown diagnostic bodies are discarded.
Production startup installs no observer or diagnostic endpoint. Preserve the report
if a 502 occurs; a stage/status narrows localization, but does not prove the original
socket cause. Do not log upstream messages, hostnames, headers or credentials.

The 22 October native run passed all seven tasks without transport failure or retry.
Both expected abstentions were empty; five answerable cases returned exact relevant
quotations. Seven metadata and seven completion HTTP 200 responses were observed,
peak application overlap was five, and cleanup restored the original provider
network. This small exposed synthetic matrix is not a held-out legal acceptance
suite, representative-volume mixed-load qualification, sustained capacity, OCR/layout
or malware/extractor-isolation qualification. It does not clear the earlier failed
mixed workload or diagnose a nonrecurring 502. The production prompt/model/relay and
all private data, sessions, credentials and pending v3 review remain unchanged.
See [dated evidence](evidence/quote-selection-evaluation-2026-10-22.json).

### Representative-volume quote-selection evaluation

Select `--workload quote-volume-v1` using the existing guarded qualifier's explicit
image/profile/key/network/relay/output arguments and `--execute-real-provider`.
It creates five disposable workspaces and twenty deterministic synthetic files:
TXT/DOCX/XLSX/text-PDF, 64 records each, plus one long Unicode paragraph per TXT.
It retains corpus byte hashes, revisions, frozen-source seals, per-product prompt,
selection and source-snapshot seals. Original downloads and complete document views
are rechecked after all declared tasks, including a failed evaluation.

Fifteen distinct tasks are frozen up front: five payments, five conflicting pairs
and five missing court identities, in three waves of five. All required positive
facts must be visible before inference; later tasks do not replace earlier failures.
Positive empty output, irrelevant exact quotations, one-sided conflicts, changed
versions or incorrect budgets fail. Negative tasks require abstention. The existing
120-second provider budget, 60-second task wait, 240-second driver bound and all
context/source limits remain unchanged. No retries or alternative models are used.

The opt-in volume factory requires both real-provider and volume-candidate markers
before selecting `private-evidence-pack-v2-folded-anchors`. Only that disposable
process's research packing reference is changed. Production startup ignores the
fixture marker, API requests cannot select the candidate, and default packing stays
exactly v1. The candidate uses exact terms before folded Turkish/ASCII terms for
nomination; rarer matched terms anchor long excerpts. Source text/identities are never
normalized. A new recipe records the candidate profile and Unicode version. The
independent reference file preserves default-v1 and native-prototype-v2 manifests
for all fifteen cases. The post-trial isolation refactor is verified offline; the
failed native trial is not represented as execution of the final wrapper.

The token-protected fixture `/_provider_jobs/events` exposes at most 64 finite caller
intervals, without prompt, document, credential or URL data. Each wave's overlap is
computed independently; missing/invalid intervals fail qualification. These intervals
measure application provider calls including readiness/queueing, not GPU generations.
Existing finite HTTP stage/status and bounded failed-relay-code diagnostics apply.

The 22 October trial passed 12/15 tasks and remains **unqualified**. All three waves
peaked at five callers, but one positive abstained, one conflicting-pair answer failed
relevance, and one negative task failed completion HTTP 502. The relay classified
the latter as `provider_connection_closed` (`RemoteDisconnected`). This establishes
observed connection closure, not why it occurred or which upstream component caused
it. Keep all failures and do not silently retry, force quotations, increase deadlines
or promote technical completion to usefulness. No production image/configuration or
private matter was changed. The earlier profiles and owner v3 review remain intact.
Next use independent long-page relevance cases and bounded synthetic-only transport
correlation; production/representative-corpus/legal acceptance stays open.
See [dated evidence](evidence/quote-volume-evaluation-2026-10-22.json).

### Long-page quote selection and per-call diagnostics

Use `--workload long-page-quotes-v1` with the existing qualifier's protected
image/profile/key/network/relay/output arguments and `--execute-real-provider`.
It uses five invented, deterministic ASCII text PDFs with three pages of 48 lines
each, plus Turkish task questions. The tasks cover late facts, a contradictory pair,
absent information, document instructions and a negation with its adjacent condition.
Required evidence must be visible in the packed quotation catalog before any model
call. This profile alone opts into the disposable v2 packer; production stays v1.
It retains frozen source, prompt, manifest and product seals before outcome grading,
then rechecks all original bytes and document views after the full five-task wave.
One attempt per case, no retries, the same context budget and all existing provider,
task and driver deadlines apply. Exact-source matching cannot excuse irrelevant
quotes, omitted contradictory records or an omitted condition.

The token-protected fixture event endpoint now contains at most 64 caller records,
each with a synthetic question SHA-256, sequence, start/end, at most eight finite
HTTP stage/status/elapsed entries, fixed diagnostic codes and adapter outcome.
Correlation rejects duplicate/missing cases, unknown fields/codes, invalid statuses,
nonfinite intervals and out-of-interval observations. Thread-local accumulation keeps
concurrent calls separate; no prompt, document text, successful body, URL, header,
credential or arbitrary upstream message is retained. Question digests are research
metadata and must remain restricted to this synthetic fixture. These endpoints and
observers are absent from production startup. A returned adapter answer can still
fail the independent relevance or legal-review gate.

The native 22 October trial passed 3/5 and remains **unqualified**. A visible delivery
fact produced no quote; a second answer did not include both negation and condition.
The conflicting pair, missing-information abstention and hostile-instruction case
passed. All ten HTTP responses were 200, all five callers overlapped, original/version
checks passed and cleanup restored the original provider network. Controlled tests
exercise completion 502 plus `relay_provider_connection_closed` on one concurrent
call without leaking its arbitrary response text. This validates bounded caller-side
localization, not the historical socket cause, engine behavior or tunnel trace.

Retain all failed outcomes. Next investigate atomic quotation boundaries offline on
independent examples, preserving condition/negation context and exact source spans.
Do not force a nonempty answer, rerun these cases until passing, silently retry a
502, enable the candidate in production or change model/deadline settings. No private
matter, original, evidence version, review history, secret or live service is modified
by this tooling. Owner version-3 review and broader capacity/legal gates stay open.
See [dated evidence](evidence/long-page-quotes-2026-10-22.json).

### Offline quotation-boundary evaluation

Run the fixed synthetic suite with
`PYTHONPATH=backend:scripts backend/.venv/bin/python scripts/evaluate_quotation_boundaries.py --output <new-report.json>`.
The output path must be new. There is no private-input path, provider profile, key,
model, network request or application installation option. It compares the unchanged
production catalog against an offline neighboring-line prototype over the same
candidate-v2 packed excerpts. It never installs that packer or catalog in production.
The source cases, expected groups, suite hash, exact original and selected-span pins,
catalog/prompt seals, omissions and measured budgets remain in the dated evidence.

The prototype uses contiguous physical lines with at most one neighbor on each side.
It preserves CRLF/Unicode and code-point offsets exactly, never crossing a blank or
source/page boundary. Partially clipped physical lines, windows over 768 UTF-8 bytes
and candidates beyond the 64-quote cap are omitted with fixed reasons. There is no
smaller automatic fallback that could discard a condition. Measure the actual
serialized envelope, including quote metadata and existing framing/completion
reserves, against 8,192 conservative units. A fitting text excerpt does not imply a
fitting candidate catalog. Source grouping and geometric availability do not confer
legal association, relevance, authority or full context.

The frozen ten-case comparison reports 11/11 groups in coarse baseline quotes and
8/11 in candidate windows; two candidate prompts exceed budget. The late-PDF fact
gets a smaller 199-byte covering window but an inadmissible 8,464-unit prompt. The
overlong-line, blank-separated joint-context and dense count-cap cases remain open.
Six cases meet geometry-only checks, including the missing-information fixture;
neither model abstention nor document-instruction resistance has been measured.
The nine regression tests also run in a network-disabled, read-only Linux container
with public code only and no provider/private mounts, producing the exact host report.

The offline resolver revalidates the full plan against frozen evidence/originals,
then accepts only existing unique quote IDs (at most 20). A stale revision, edited
hash/span/plan or unknown reference fails. Resolution is a test utility, not an
execution or legal authorization. Preserve the original files and earlier native
failure receipts. Do not promote this exploratory suite to held-out legal acceptance,
raise limits, trim conditions or retry earlier model tasks to obtain a pass.
Next evaluate budget-aware nomination and explicitly retained companion context
offline, with a fresh declared native gate required before any production candidate.
Owner version-3 review, historical 502 diagnosis and broader legal/capacity gates stay
open. No live service, document, evidence version, secret or review record changes.
See [dated evidence](evidence/offline-quotation-boundaries-2026-10-22.json).

### Offline budgeted quotation bundles

Run `PYTHONPATH=backend:scripts backend/.venv/bin/python scripts/evaluate_budgeted_quotes.py --output <new-report.json>`.
Only fixed invented fixtures are accepted; there is no provider/key/private-input or
installation option. The twelve fresh cases retain source and plan seals, initial-pack
coverage, unused excerpts, exact budget measurements, fallbacks and explicit omissions.
No inference or HTTP call is made. The earlier reports and exposed native failures
remain immutable evidence with their original scopes.

The planner ranks anchors by folded query overlap and inverse line frequency over
the already packed excerpts. This is a lexical heuristic, not authority or relevance.
Each selected bundle contains the full anchor plus neighboring nonblank physical
lines within a maximum line distance of two. Blank-separated companions retain their
own spans and a boundary flag. No cross-source/page join is synthesized. If a required
part exceeds 768 UTF-8 bytes, a complete whole-excerpt fallback may preserve it within
the existing 1,800-byte limit. An incomplete physical line is omitted. The planner
never drops a companion to keep an anchor.

Serialize the actual question, selected evidence, bundle metadata and source-boundary
flags, adding the unchanged framing/completion reserves. Enforce the declared budget,
20 bundles and 64 parts. A bundle that does not fit is omitted whole with a fixed
reason. Only excerpts referenced by selected bundles enter this envelope; unused
initial evidence IDs and full initial-pack coverage stay in the plan. Their exclusion
can hide relevant or adverse facts, so the original inventory stays accessible and
this heuristic cannot establish corpus completeness. Question, policy, context limit,
complete source inventory (including unused versions), spans and prompt seals bind
the plan. Admission is `prepared_only`, never execution authorization.

The offline resolver rebuilds and canonically compares the plan against the current
frozen inputs. It accepts only unique selected bundle IDs and returns every part
with its original offsets, hash and role. It rejects stale versions, edited companions,
anchor-only IDs and insufficient envelopes. Parts are returned separately; proximity
does not create a legal relationship. A future native adapter must independently
qualify the distinct `bundle_ids` schema, parser and exact-source product checks.
Production startup and provider fixtures do not enable this prototype.

The fresh comparison has 9/12 group availability; eleven prompts fit and the explicit
1,536-unit envelope is blocked. Late-shipment and dense-anchor prompts cost 4,070 and
6,298 units within the default 8,192. Cross-page joint context and a clipped physical
line remain unresolved; one complete coarse fallback preserves an overlong line.
Missing-information nomination and hostile-source fixtures do not measure model
abstention or instruction resistance. These geometry/contract results are not a direct
accuracy comparison to the earlier single-quote study or a legal acceptance pass.

The nine new tests also pass in a read-only container with networking disabled and
only public code mounted, matching the complete host report. Private matter originals,
evidence versions, secrets, sessions and review history remain untouched. Next qualify
alternate wording/adverse-source coverage and a disposable native adapter before any
fresh native trial or production proposal. Owner version-3 review and historical 502
diagnosis remain open.
See [dated evidence](evidence/budgeted-quotation-bundles-2026-10-22.json).


### Disposable bundle adapter and alternate/adverse-source evaluation

`disposable_bundle_adapter.py` is an explicit opt-in Python adapter, with no app
factory, environment activation, production route or native-execution CLI. It
requires a `Provider`, `mode=MARKER`, an exact source inventory and its complete
sealed bundle plan. It reconstructs and hash-checks the existing offline message
envelope before calling the provider's guarded completion function. Source and
plan changes during transport discard the result. Outputs are separate exact
bundle parts with roles, boundary flags and fallback labels; they are not synthesized
claims or reviewed work products. Never join parts into an invented quotation.

Run only the fixed invented suites for this qualification:

```sh
PYTHONPATH=backend:scripts backend/.venv/bin/python scripts/evaluate_alternate_adverse_quotes.py --output /tmp/new-alternate-adverse-report.json
backend/.venv/bin/python -m unittest discover -s deploy -p test_disposable_bundle_adapter.py
```

The output path must not exist. The test fixture uses `httpx.MockTransport` and a
synthetic credential; it opens no sockets and reads no runtime configuration,
private matter, provider key or mounted secret. The fixed adapter evaluator selects
all nominated bundles under a controlled rule: nine mock metadata plus nine mock
completion requests across twelve cases. Regression tests make additional mock
requests. Neither count represents inference. Five barrier-synchronized mock
selections test source isolation only. A network-disabled, read-only Linux run
must reproduce both entire evaluator reports, not just their summary counts.

Retain the original suite/source hashes before grading. Expected source groups
belong to the evaluator only. Current results are 13/18 groups, 2/4 alternate-wording
cases and both sides in 4/7 adverse-source cases, with twelve fitting prompts. Keep
the missed paraphrases, missed unmatching adverse source, budget-excluded adverse
source and unlinked condition visible. Hostile source instructions remain data;
exact-copy/schema guards do not establish model instruction resistance or complete
adverse-authority discovery. Empty nomination is not model abstention.

Do not activate this contract in production or run native inference merely because
mock tests pass. A fresh native trial needs a separately frozen acceptance plan,
source and envelope identities, no expected-answer hints, explicit model/transport
scope and retained failure receipts. Do not replay earlier exposed failures until
passing. Preserve the private pilot and its pending owner review. Historical 502
cause, legal correctness and sustained native capacity remain open.


### Frozen source-diversity comparison

The separate `offline-diverse-source-bundles-v2` recipe has no provider or application
hook. The existing disposable adapter rejects its plans before transport; it cannot
silently adopt the new prompt or selection policy. See the
[declared policy](SOURCE_DIVERSITY_EVALUATION.md) before extending this experiment.

```sh
PYTHONPATH=backend:scripts backend/.venv/bin/python scripts/evaluate_source_diversity.py --output /tmp/new-source-diversity-report.json
backend/.venv/bin/python -m unittest discover -s deploy -p test_source_diversity.py
```

The output must not already exist. This evaluator accepts no external/private source
option and makes zero model/HTTP calls. Keep expected groups outside both planners.
Freeze fixtures, expected groups, code and evaluator before grading; retain the
first report. Later changes require a new declared experiment and must not erase
exposed failures. The current policy and sixteen fixtures were frozen before grading;
no fixture or planner changes followed the first report. A pre-grade physical-line
work cap bounds scanning without cutting a source into an apparently complete scan.

Current comparison: 21/31 source groups available in v1, 26/31 in v2; alternate
wording 0/3 versus 2/3; both sides in adverse-source cases 4/7 versus 6/7. Both have
fifteen fitting prompts and one blocked undersized envelope. Recipes differ in
nomination, envelope layout and admission, so this does not isolate a causal effect
of source rotation or establish model/legal accuracy. The later paraphrase, unlinked
condition, two over-cap sources and undersized envelope remain unavailable.

Unmatched-source fallback copies the first nonblank line and its bounded companions;
it does not imply relevance, factual absence or model abstention. The missing-
information case deliberately has a fallback candidate. Source proximity does not
establish a legal relationship. Preserve complete conditions, exact Unicode spans,
all source revisions, unrepresented-source lists and omission reasons. Rebuild the
complete plan before resolution, including unused sources. Reject ambiguous
revision/hash pairs, tampered plans and blocked envelopes.

Qualify new contracts in read-only, network-disabled Linux with public code only,
no provider or private-runtime mounts, and compare the complete report against the
retained first host result. All existing deployment and provider/context checks,
nine exact-head CI jobs and five timing reserves remain required. No test removal,
timeout increase, retry or production switch follows from improved offline counts.
A new disposable adapter and separately frozen native acceptance trial remain later
gates. Keep the private pilot and owner version-3 review pending.


### Disposable v2 wire adapter

`disposable_diverse_adapter.py` has no app hook, native CLI, environment activation
or production setting. Use its explicit v2 marker and call `prepare_diverse_selection`
to retain a complete wire manifest before selection. A prepared manifest is not
execution authorization. Keep the planner's original prompt digest alongside the
actual wire digest. Only the system's `B1` example becomes `D1`; source text and
other message bytes stay unchanged, as does the measured budget. Unknown `D…` and
legacy `B…` responses fail; there is no automatic ID translation.

Run only the fixed invented qualification suite for this experiment:

```sh
PYTHONPATH=backend:scripts backend/.venv/bin/python scripts/evaluate_diverse_adapter.py --output /tmp/new-diverse-adapter-report.json
backend/.venv/bin/python -m unittest discover -s deploy -p test_disposable_diverse_adapter.py
```

The output path must not exist. The evaluator accepts no private-source or provider
configuration option. Freeze code, fixtures, expected groups and evaluator before
grading. Retain the first report and every unavailable group; expected groups stay
outside planner and adapter. A read-only, network-disabled Linux run with public
code only must reproduce the entire report, not just its counts.

Current scope: 14 cases, 215 passages, 55 source versions, 13/20 required groups
available, both sides in 3/3 adverse-source cases. Seven groups remain unavailable
across separator, overlong-line, late-paraphrase, cap and budget cases. Four bundles
use unmatched-source fallback, including absent information. The controlled
select-all evaluator makes 11 mock metadata plus 11 mock completion requests;
regression tests make additional mock requests. There are zero network HTTP or
native/model calls in this experiment. Two no-candidate cases make no call; one
undersized envelope is blocked. Empty/subset selection and source proximity do
not establish relevance, abstention, legal effect or adverse-source completeness.

Validate the full manifest, original sources and budget before transport and
recheck caller sources, plan, wire and provider limit after transport. Discard
raced results. Keep all parts and conditions intact. Selected/omitted nominated
bundles and source-version aliases are confidential metadata and stay with the
exact manifest. Five concurrent mock selections test context isolation only.

Before any native trial, separately declare and freeze fresh sources, prompts,
wire/planner/model/transport identities, task and grading criteria, output/source
checks and failure handling. Do not pass expected-answer hints to the selector,
retry failures into success, activate production or alter the pending private review.
The prior native failures and historical HTTP 502 diagnosis remain unresolved.
## Fresh frozen native acceptance plan

`scripts/native_acceptance_plan.py` prepares the immutable synthetic-only
declaration in `docs/evidence/frozen-native-acceptance-plan-v1.json`. It does not
load runtime settings, keys or private matters and has no inference runner.
`scripts/native_acceptance_grading.py` validates that declaration against current
public code, original fixture bytes, complete inventory, exact wire messages and
separate expected groups before pure offline grading. Never treat a changed-code
rebuild as the same frozen plan. Use a new version and fresh acceptance set for
repairs; retain the original declaration and first preflight.

The fourteen-case declaration contains one serial smoke, two five-job batches and
three no-call controls. Its intended model is declared, but native model digest,
context and approved transport origin are not yet attested. Any later execution
needs a separate fresh authorization/binding receipt, isolated synthetic-only
inputs and the exact request/response/timing/identity evidence specified in
[the acceptance rules](NATIVE_ACCEPTANCE_PLAN.md). Do not mount production data or
configuration into an experiment or expose credentials in receipts. Only exact
case messages may enter the model; grading fields must remain outside its context.

The retained first preflight finds fourteen of twenty groups available across 113
passages/41 versions; all six missing groups stay in the denominator. The select-all
upper bound also fails the absent-information case. This is not native execution,
abstention accuracy or legal qualification, and the current gaps prevent full
acceptance. Transport-control success cannot erase quality misses. No native or
HTTP calls are made in this milestone. Never replay exposed cases until successful
or silently promote a controlled/fabricated selection into a native result.

Fourteen tests and identical host/Linux declaration/preflight results qualify
offline preparation and rule enforcement only. Linux runs read-only with network
disabled and public source only. Keep all nine exact-head CI jobs, existing caps,
workers and five timing reserves; verify merged-main separately and audit unchanged
originals, evidence versions, encrypted bytes and review history. Update the live
roadmap without marking F00-06 complete or changing the owner's pending v3 review.

The initial PR head misplaced the new declaration inside the closed five-file
R01 dossier. CI correctly rejected it; no merge was attempted. The declaration
was moved byte-for-byte to `docs/evidence/frozen-native-acceptance-plan-v1.json`.
Its seal, sources, planner, wire messages, criteria and first preflight are
unchanged. The original rule document is retained in
`evidence/native-acceptance-rules-before-location-repair-2026-10-22.md`; the current
rule document changes only that artifact path. The existing R01 validation step
now runs once before the full backend suite, with the same command, closed-file
guard, jobs, caps, workers and coverage. No whitelist expansion masks the error.

## Whole-passage packet evaluation

`scripts/whole_passage_packets.py` is a separate offline inventory candidate with
exact whole passages and bounded multi-packet preparation. It adds no application
route, live selector, inference or private-matter authorization. Every packet's
original spans, text hashes, source-version aliases, membership and wire messages
are sealed against the entire original inventory. Resolver inputs must match a
fresh full rebuild; cross-packet, unknown and legacy identifiers fail. Documents
may still be incomplete and separate passages have no automatic semantic link.

For the evaluated 8192-unit profile, each envelope retains at most 4000 copied
UTF-8 bytes and eight passages; up to eight envelopes increase total future cost.
Report per-packet measurements, aggregate units/bytes/call bounds and all omitted
sources. The later execution boundary must independently enforce the evaluated
profile, whole-job budget and trusted immutable matter context. A plan hash alone
is not permission, live-context verification or native acceptance.

Freeze the new P1501–P1516 fixtures, labels, implementation/evaluator and
[rules](WHOLE_PASSAGE_PACKET_EVALUATION.md) before the first offline grade. Run
`PYTHONPATH=backend:scripts backend/.venv/bin/python
scripts/evaluate_passage_packets.py --output <new-path>`; existing output files
are never overwritten. Keep prior suites and the frozen native trial unchanged.
Do not put evidence into the closed five-file `qualification` directory.

The retained first comparison finds 9/23 groups in unchanged v2, 13/23 with one
whole-passage packet and 18/23 with up to eight packets. First packets remain
byte-identical in the capacity ablation. The latter costs 32 versus 12 planned
envelopes and 144178 versus 42018 conservative units across the suite. Five groups
remain unavailable and all negative-case model outcomes are unmeasured. These
numbers describe availability, not accuracy, abstention, legal truth or native
capacity. A larger aggregate budget is not a free single-request improvement.

Fourteen new contracts and an identical network-disabled, read-only Linux report
qualify offline integrity only. All 215 deployment contracts and 206 relevant
context/provider/qualification cases pass locally. Keep all nine exact-head CI
jobs, existing caps/workers/coverage, the early R01 guard and five timing reserves.
Verify merged main and preserve originals, exact evidence, encrypted bytes,
credentials, sessions and review history. Keep owner v3 review and F00-06 pending.
A separately marked disposable selector, aggregate-budget/context boundary, fresh
native declaration and exact model/transport binding remain later gates.


## Disposable packet selection

The `disposable-whole-passage-selector-v1` candidate is not wired to the app or an
inference CLI. Run only its invented mock evaluation for this qualification:

```sh
PYTHONPATH=backend backend/.venv/bin/python scripts/evaluate_packet_selector.py
backend/.venv/bin/python -m unittest discover -s deploy -p 'test_disposable_packet_selector.py' -q
```

No `.env`, provider key, original document, matter identifier or production mount
is needed. The in-process mock serves the unchanged Provider; its synthetic model
never runs. The six-case select-all report tests protocol and exact copying only.
Keep source/review context private if evaluating any future authorized matter;
returned bundles contain text and must never be published in CI or roadmap data.

Native use is not authorized by this report. First supply a trusted acquisition
and permission boundary for immutable versions, durable one-use campaign admission,
current model/transport identity binding and a fresh declared acceptance trial.
Do not use an always-true fixture authorizer with private evidence. Plan hashes do
not prove source rights, matter authorization or blob integrity. The in-memory
session allowance cannot enforce aggregate campaign cost across crash/recreation.

Require the entire plan to fit all three explicit allowance dimensions. Fail closed
on a blocked per-request envelope, stale evidence/wire, revocation, changed provider
profile, unknown/cross-packet ID or exhausted allowance. Reservations are consumed
on failure; never retry or recreate a session to recover failed-attempt budget.
Metadata GETs are counted separately from completion attempts. Preserve originals,
prior plans and review decisions; a returned selection is never legal approval.
Retain the first test failure and its test-only serialization repair, frozen inputs,
full mock report and network-disabled Linux reproduction. Exact-head CI and five
existing timing reserves remain mandatory before merge. No deploy/restart follows
this protocol-only milestone. See [declaration](DISPOSABLE_PACKET_SELECTOR.md).


## Durable disposable campaigns

This accounting candidate has no inference CLI, provider dispatch, app route or
production installation. Exercise only the invented temporary-store qualification:

```sh
PYTHONPATH=backend backend/.venv/bin/python scripts/evaluate_durable_campaign.py
backend/.venv/bin/python -m unittest discover -s deploy -p 'test_durable_packet_campaign.py' -q
```

No `.env`, provider key, matter identifier, original file or production mount is
needed. The mock-only bridge recreates old selector sessions and reserves in a
separate temporary ledger before each fixed synthetic exchange. Its always-true
issuer is a fixture, never production permission. Report comparisons and process
crash tests establish accounting behavior, not native capacity or legal quality.

For any future approved integration, pin a single authority store identity in
trusted configuration, an exact issuer-approved grant and acquired evidence
context. A 0700 directory and 0600 file are mandatory. Never recreate a missing
store, refund a reserved packet, replay an ambiguous effect or issue a replacement
grant to recover failed budget. A denied transaction has not authorized dispatch;
a returned reservation has already consumed cost. Terminal digests contain no
source/answer and are caller assertions, not independent provider receipts.

Store copying/backup rollback, hostile host administration and reissuance of intent
are not solved by SQLite. Require external restore fencing and issuer one-use
intent enforcement, current model/transport binding and an end-to-end native
admission boundary before any native execution. The older eleven-call acceptance
plan cannot authorize these packets. Existing production backup/restore policy,
private data and owner v3 review remain unchanged. Preserve the first report,
pre-grade hashes and retained I001 formatting repair. Exact-head CI and the five
existing timing reserves are mandatory before merge; no deploy/restart follows.
See [declared trust boundary](DURABLE_PACKET_CAMPAIGNS.md).
