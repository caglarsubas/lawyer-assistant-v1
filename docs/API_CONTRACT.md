# Initial application contract

All endpoints are `/api/v1`; JSON snake_case. Cookie sessions are HttpOnly. Login returns
`{user: {id, name, role, firm_id}, csrf_token, demo_mode}`; authenticated mutations send
`X-CSRF-Token`. `GET /auth/me` restores user/CSRF state. `POST /auth/login` accepts
`{username,password}`, `POST /auth/logout` signs out. Frontend uses same-origin `/api` proxy.

Public `GET /bootstrap`: `{demo_mode,version}`. All other endpoints below require authentication.
`GET /status`: `{demo_mode, provider:{configured,identity_verified,tenant_id,organization,key_id,mode},
graphs:{mode,ontology_version,legal_review_status,serving_release}, services, limitations:string[]}`.
`identity_verified` records operator attestation, not a consumer-side identity proof.

`GET /matters` -> array of `{id,title,domain,objective,represented_party,stage,relevant_date,status,
document_count,created_at}`. `POST /matters` accepts title, domain (contracts/commercial/employment),
objective, represented_party, stage and optional relevant_date (ISO date).
`GET /matters/{id}` additionally returns `documents`, `facts`, `products` and `research_runs`.
`POST /matters/{id}/documents` multipart `file` -> document with id,name,status,media_type,
page_count,extraction_warnings,created_at. `GET /matters/{id}/documents/{doc_id}` -> same plus
`passages:[{id,locator,text}]`. Source originals remain encrypted.
`GET /matters/{id}/documents/{doc_id}/original` integrity-checks/decrypts the original for authorized download.
Synthetic seed documents have no original binary. `page_count` is null when the format has no physical pages;
`passage_count` is separate. Extraction warnings and failed content must remain visible.

`POST /matters/{id}/facts` accepts `{text,status,evidence_id?}` status is documented/alleged/disputed/
assumption/inference. `PATCH /matters/{id}/facts/{fact_id}` same fields plus reason; invalidates
dependent work. Facts have id,text,status,evidence_id,revision,updated_at.

`POST /matters/{id}/research` accepts `{question,as_of?:ISO date}` -> research run with
`id,status,question,created_at,product_id?`. `GET /matters/{id}/research/{run_id}` refreshes result.
`POST /matters/{id}/research/{run_id}/cancel` cancels.
`POST /matters/{id}/authorities/search` accepts `{query,as_of?,authority_id?,limit:1..50}` for local public-corpus retrieval.
It performs membership checks before and after the query. No raw search DSL or private-index selector is accepted.
Product `{id,title,status,version,summary,claims:[{id,text,kind,evidence_ids:string[],review_status,
review_note?}],issues:[{label,missing_facts:string[],counterarguments:string[]}],
coverage:{searched:string[],gaps:string[]},snapshots,created_at}`.
Products additionally retain `evidence`, `graph_paths`, `authority_candidates`, `critical_gaps` and source hashes/revisions.
Unqualified legal corpus is a critical gap and prevents whole-product Reviewed status.
`GET /matters/{id}/products/{product_id}` -> product.
`POST /matters/{id}/products/{product_id}/review` accepts `{claim_id?,decision:approve|reject,note}`.
`GET /matters/{id}/products/{product_id}/export?format=docx|pdf` -> download, draft marked.

## Lawyer-authored practice records

`GET/POST /matters/{id}/practice/{kind}` lists or creates private preparation records. Lists accept
`limit` (1–100) and `offset`. These records are user-authored and never promoted to legal authority.

| Kind | Content |
|---|---|
| `scenarios` | `title`, `assumptions` (1–20 strings), `fact_ids`, `notes`, `status:active|retired` |
| `contradictions` | Two distinct same-matter `fact_ids`, `reason`, `status:open|resolved|dismissed` |
| `arguments` | `issue`, `position:supporting|adverse|alternative`, `text`, `evidence_ids`, `authority_refs:[{product_id,passage_id}]`, `status:working|ready_for_review|withdrawn` |
| `drafts` | `title`, `draft_kind:preparation|review_note`, `text`, `review_note`, `status:working|ready_for_review|withdrawn` |

Arguments require at least one valid local passage or a public passage already recorded in that authorized
matter's research. A public candidate reference does not establish applicability or binding effect.
Scenario assumptions never overwrite the fact ledger. `GET/POST .../{kind}/{record_id}/versions` reads history
or appends a version. Updates require `expected_revision` and a `change_note` of at least three characters;
historical version records are immutable through the API. Changes mark existing preparation products stale.

`GET /matters/{id}/practice/drafts/{record_id}/export?format=docx|pdf&version_id=...` exports a specific
immutable draft version (latest if omitted), visibly labeled as lawyer-authored and unverified. Version IDs
must belong to that exact draft and matter. Research snapshots retain practice version references without
converting hypotheses into source-backed facts.

`GET/POST /playbooks` lists or creates firm preferences; creation and version changes require admin/curator.
Content: `title`, `domain:contracts|commercial|employment|general`, `text`,
`curation_status:draft|curated|retired`, `curation_note` (required for curated status).
`GET/POST /playbooks/{id}/versions` provides immutable history and optimistic edits.
`GET/POST /matters/{id}/practice/playbooks` lists or explicitly adopts a curated version using
`{playbook_id,version_id,purpose}`. Adoption copies the selected version into the matter with
`classification:firm_preference` and `legal_authority:false`; later playbook edits never silently change it.

## Governance

See [governance contracts](GOVERNANCE.md) for legal holds, append-only retention policies, reversible archive,
dry-run erasure inventories and exact source/assertion/release dependency invalidation. Lifecycle mutations
require an active same-firm admin who already has matter membership. Physical erasure is not enabled.

## Graphs and public gateway

`GET /graphs/catalog` -> `{version,review_status,domains:[{id,label,label_en}],
classes:[{id,label,module}],relations:[{id,label,requires_legal_review}],coverage}`.
`GET /graphs/explore?query=&graph=structure|jurisprudence&as_of=&limit=30` ->
`{nodes:[{id,label,type,graph,review_status}],edges:[{id,source,target,label,status,evidence_id?}],
limitations:string[],snapshot}`. `POST /graphs/tools/{tool_name}` typed tool payload and result.
`GET /graphs/coverage` -> ontology/institutional/corpus/assertion coverage with explicit unknowns.

`serving_release.status` is `unconfigured`, `verified` or `unavailable`. A verified
release supplies the exact bundle and ontology hashes and the independently
verified review signature state. Query results retain the serving receipt hash;
research jobs also pin the activation sequence and refuse publication after a
release change. `release_verified` verifies source membership and exact evidence;
`legal_usable:false` and `matter_applicability:not_assessed` remain explicit.
An installed bundle does not guarantee a reachable or matching Fuseki process;
coverage reports unavailable when its runtime receipt cannot be checked.

`GET /public-sources?limit=50&after=SHA256` is restricted to active admin/curator
roles. It returns `items`, `next_cursor`, `integrity_scope:manifest_only` and
limitations. `GET /public-sources/{SHA256}` verifies all package artifacts and
exact Unicode spans before returning full metadata with
`integrity_scope:all_artifacts_verified`. Acquired/published/effective dates may
remain null. All imported packages stay `staged`, `rights_pending` and
`legal_review_pending`, including operator-supplied review evidence. No source
package mutation, graph publication or external acquisition API is provided.
Admin/curator passage and original download routes verify every artifact first;
originals are opaque `.bin` attachments with no-sniff and sandbox headers.
Firm-confidential review routes support assignment, four separate assessments,
optimistic revisions and an unsigned dossier export. Reviewer identity and time
are server-generated, and accepted assessments do not promote the source. See
[source-review contract](SOURCE_REVIEW_CONTRACT.md) and [offline source intake](PUBLIC_SOURCES.md).

`GET /public-sources/{SHA256}/provision-candidates` returns bounded heading
proposals; `GET .../provision-span?start=&end=` previews exact Unicode spans.
`GET/POST .../provision-mappings` reads the firm-local mapping ledger or proposes
a mapping; `POST .../provision-mappings/{id}/review` records an accountable
decision with exact references, dates and evidence. Writes require both mapping
and source-review revisions and current ownership. Accepted mappings require all
four source assessments and local-processing/display rights, becoming stale after
any source-review revision change. `GET .../provision-mappings/export` is an
unsigned dossier attachment. These endpoints never update RDF or search data.
Full shapes and limits: [provision mapping](PROVISION_MAPPING_CONTRACT.md).

`POST /matters/{id}/gateway/evaluate` accepts `{query,destination,query_type:public|matter}` ->
`{decision,reason_codes,policy_version,payload_digest,request_id}`.
`POST /matters/{id}/gateway/approve` accepts `{request_id}` -> exact-request approval.
`POST /matters/{id}/gateway/execute` accepts `{request_id}` -> collected public source metadata.
Default disabled networking; never fake a successful fetch. Approvals cannot override hard denials.

Empty arrays/explicit unavailable states are valid. Never display fixture legal data as authoritative.

Concurrent mutations use optimistic record revisions and return 409 rather than silently overwrite a newer
review or stale-state change. The initial server admits at most ten queued/running research jobs and executes
at most five concurrently in a single API process. Restarted unfinished jobs fail visibly; no silent replay.
