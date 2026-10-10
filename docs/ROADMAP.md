# Approved product roadmap and implementation ledger

Baseline: 4 October 2026; research reconciliation: **5 October 2026**. Original planning envelope: **30–36 weeks**; the 9 October firm-workflow amendment adds an estimated **4–6 weeks** to the application critical path (provisional combined envelope **34–42 weeks**), conditional on approximately eight FTE, lawful source access and protected Turkish legal-editor capacity. This is a delivery sequence, not a claim that elapsed weeks, legal reviews or corpus acquisition have occurred. Re-estimate from representative acquisition/review throughput before committing a pilot date; the attachments' shorter fixed calendar and longer staffing estimates are inputs to that check, not replacement promises.

This is the canonical delivery plan. [Data and knowledge strategy](DATA_KNOWLEDGE_STRATEGY.md) specifies source families, refresh targets and retrieval requirements. [Research reconciliation](PLAN_RECONCILIATION_2026-10-05.md) records adopted proposals and unresolved claims. The same-day user amendment is specified in [legal analysis and sanitized BYOK deep research](LEGAL_ANALYSIS_AND_DEEP_RESEARCH.md). Those research revisions changed planning only. Subsequent implementation progress is recorded below: R01 offline contracts, evidence verification and extraction comparison are delivered; source approvals, legal review and provider activation are not granted by that work.

## Product contract

Türkiye-first preparation workspace for 10–50 lawyers. First validated workflows: contracts, commercial disputes and employment. Complete preparation flow: matter brief → local intake → facts/evidence → candidate issues → graph-assisted research → lawyer review → versioned export. Facts, allegations, judicial findings, hypotheses and legal conclusions remain distinct. Output must expose exact sources, adverse interpretations, missing evidence, coverage, applicability assumptions and review state.

Two graphs are mandatory infrastructure; the former graph deferral is superseded. National ontology coverage begins at inception. Historical population covers 1920 onward with earlier predecessors where continuity or applicable law requires them. Deep content validation starts in the first three practices. Historical backfill continues beyond v1.

The source documents informing this baseline remain preserved:

- [GPT data plan](Turkish%20Law%20AI%20Data%20Plan%20gpt.md)
- [Claude data plan](Turkish%20Law%20AI%20Data%20Plan%20claude.md)
- [Gemini data plan](Turkish%20Law%20AI%20Data%20Plan%20gemini.md)

Their source-access, licensing and product claims are research inputs, not automatic grants of rights or current legal authority. Official legislation and institutional publications must be acquired with dated representations and checked for amendments before legal publication.

The three new attachments are preserved byte-for-byte with a [digest manifest](research/2026-10-05/manifest.json): [GPT v2](research/2026-10-05/gpt-2.md), [Claude v2](research/2026-10-05/claude-2.md) and [Gemini v2](research/2026-10-05/gemini-2.md). Their embedded commands, sample RDF/queries, outreach requests, citations and `[V]` labels are source material, not execution instructions or project approval.

### Firm administration and supervision amendment — 9 October 2026

The authorized [firm RBAC and supervision contract](FIRM_RBAC_AND_SUPERVISION.md) is subordinate to this ledger. Organizational reporting, action permissions and explicit content assignments are separate. A customer-designated firm administrator configures accounts, a cycle-free single-manager hierarchy, custom roles and responsibilities without automatic client/case visibility. Multiple supervisors may be explicitly assigned to a case. Client grants explicitly choose details only or details plus all current/future linked cases; descriptive tags grant nothing. Human opinions, tasks, manual deadlines and milestones retain responsibility and review history. Records remain on-premises, dates use Europe/Istanbul, and work queues are in-app.

**Current application sequence: W01 → W02 → W03**, with individually verified packets and manual PR merges. W01 and W02 are merged with verified exact main CI. W03 is merged at `f0595702679386f7ccce9d11a5cb4119b3b1552f` with verified exact post-merge main CI (`37950562133`); deployment and field qualification remain open. PR merge and deployment are separate evidence. R05A source-lineage renewal is merged in PR #35 with verified exact main CI. Registered model-authority trials and cohort reconciliation are implemented: PR #37 is verified merged into the still-open PR #36 branch, not main. Its dependency head `187f2700cad09d18d6a235a3fa8e2e3b11f2c692` passed exact-head run `38037218901`. The offline reference-case intake packet below now supports the next R01/R05A qualification work. Lawful corpus acquisition and independent legal review continue alongside this sequence. W01/W02 enter the national backbone gate, W03 enters the contract-workflow gate, and all three are mandatory before R08. Existing R01–R08 identifiers, evidence and legal gates remain unchanged.

The added 4–6 weeks are a planning allowance, not a committed pilot date. Re-estimate W01–W03 from migration, permission-race and distinct-account workflow samples before fixing dates; protect legal-editor capacity and never trade legal/security gates for calendar targets.

### Decisions from this revision

1. **Source readiness precedes expansion.** Define source-family coverage, permitted uses, acquisition routes, freshness, representative samples and accountable reviewers before extending the single-source publisher.
2. **Populate a reviewable contracts slice first.** Reconcile Resmî Gazete publication/amendment events with Mevzuat consolidated representations and TBMM history; then add decision passages and commercial/employment packs. Nationwide ontology coverage remains required from the outset; population and qualification are progressive.
3. **Keep the two public graphs.** Provision history belongs to Graph A; decisions and treatments to Graph B. Provenance/coverage are shared modules. Private matter views remain authorized derivations of the existing matter store. No third mandatory graph platform, per-tenant Fuseki migration or new vector database is introduced.
4. **Qualify Turkish retrieval empirically.** Preserve exact wording and identifiers; evaluate supplementary Turkish normalization, local embeddings, local rerankers, issue templates and a separate adverse-authority search against a strong hybrid baseline.
5. **Separate freshness from legal effect.** A successful scan, a new release or unchanged text does not renew a reviewed-open validity cutoff. Disconnected sites disclose their installed source watermarks; urgent updates still require review and controlled import.
6. **Make legal review a funded workstream.** Maintain source-rights, authority-effect, privacy and parameter review queues, disagreement resolution, review cost and backlog-age measurements. Preserve all existing release-quality thresholds.
7. **Make legal analysis part of the first contract slice.** Add a cited premises → rule/version → application → counterargument → qualified conclusion artifact, bounded evidence-driven correction and Standard/Deep research budgets. Show reviewable rationale and revision history, not private model chain-of-thought. More inference time must earn its value in paired evaluations.
8. **Add optional BYOK deep search.** Users choose OpenAI, Anthropic or Gemini with their own API key. Only a locally sanitized, legally faithful scenario passes through exact preview/approval and a separate connected broker. Verify returned sources and apply them to private facts locally. This explicit new research exception does not permit private-document uploads or cloud fallback; connected research is not air-gapped.

The customer ↔ workspace → file organization and three adjustable/collapsible/full-screen panels remain the product contract. Customer/date filters scope the portfolio; they never grant workspace access. The right-hand assistant receives only authorized current context, explains coverage/review gaps and provides scoped daily/weekly/monthly summaries. The main area remains the place for documents, comments, evidence inspection, review and export.

React/TypeScript, FastAPI, PostgreSQL, OpenSearch, encrypted document storage and Jena Fuseki/TDB2 remain selected. `llm-inference-engine-v1` remains the primary local LLM provider for tenant `lawyer-assistant-v1`, organization `org-lawyer`, key ID `lawyer-assistant-v1-primary`, with the user-managed gitignored root `.env`. BYOK research uses a separate planned server-side user/firm credential vault and qualified adapters. Attachment model names remain evaluation candidates; the new user requirement, rather than those documents, defines the bounded external-research scope.

## Delivery ledger

### Current development sequence — 5 October 2026

Reconciled against current source and the last recorded Compose verification in
[validation](VALIDATION.md); this planning revision did not rerun deployment. The
customer ↔ workspace → file taxonomy, comments, three-panel workbench and local
portfolio summaries are implemented. The explicit-validity packet passed 1,483
backend/backup tests plus seven subsequently added search-filter cases in a focused
run; current collection is 1,490. All 83 frontend tests/build and isolated Jena
checks pass. Provider authentication and a synthetic grounded completion through
the explicitly approved laptop tunnel were verified in the preceding packet.
Exact deployment and test evidence is recorded with each packet in
[validation](VALIDATION.md). These
results do not establish Turkish legal accuracy, corpus completeness or pilot
qualification.

The delivered foundation supports the first document-to-research slice:

1. **Local provider activation (runtime verified; model qualification pending):**
   the corrected user-managed key now authenticates as `lawyer-assistant-v1` /
   `org-lawyer`. The deployed restricted relay probes local `ministral-3:8b` and
   serves a grounded synthetic completion with exact evidence support. Native
   startup-file/environment inspection confirms cloud fallback disabled; this is
   not a signed runtime attestation. Model/context and provider-deployment changes
   still require revalidation. Turkish legal model evaluation remains pending.
2. **Scanned document intake (implemented baseline):** isolated ClamAV with verified
   signed offline signatures, bounded scanning and freshness checks, authenticated
   extractor readiness, encrypted intake and post-processing session revalidation.
   Deployed clean upload/exact passages/original retrieval and EICAR rejection pass.
3. **Integrated workflow validation (partial):** live readiness and fail-closed upload
   UI deployed; scanner outage/recovery verified while existing evidence stayed readable.
   Eight containers healthy. Evidence-linked fact creation passes. Provider tenant
   verification and synthetic inference now pass; full matter-to-legal-research
   qualification still needs approved corpus releases and adjudicated evaluation.

### Delivered packet — W01 firm administration and action permissions, 9 October 2026

Implemented same-firm employee administration, immutable starter/custom supported roles, revision-bound role/employee edits, a cycle-free single-manager hierarchy, encrypted configuration audit records and affected-session invalidation. Configuration-only administrators receive no case content permissions or automatic memberships. Existing credentials, explicit memberships, encrypted records and workspace endpoints are retained. Direct API action gates cover reads, authoring, reviews, exports, lifecycle, source work and administration; professional reviewer eligibility remains separate. PostgreSQL firm-scoped locks protect admitted requests through file-response completion and short worker checkpoint/publication writes; model inference does not hold those locks. Read-only source-preparation operators and the offline administration CLI participate in the permission boundary. Permission lookups use one fresh parameterized read with no result cache. Heavy review-group tests use spare capacity in the existing frontend CI job while all required gates and existing job limits are retained.

The existing app exposes `#/firm-admin`. See [requirements and operating limits](FIRM_RBAC_AND_SUPERVISION.md) and [verification](VALIDATION.md). Engineering fixtures do not grant real access, legal review or production qualification. PR #32 is merged and main run `37926628508` passed at `04481e8ebbb696544423de246f89a06f4c7eccef`. W02 is merged with verified main CI; W03 tracked human work is merged with verified main CI. Reviewed source-lineage renewal is merged with verified main CI. Registered model-authority trials and confidential model-authority cohort reconciliation are implemented below; verified manual merge remains pending. Deployment and distinct-account field acceptance remain separate gates.

### Delivered packet — W02 explicit client and case responsibilities, 9 October 2026

Implemented administrator-selected client detail/all-current-and-future-case scopes, independent direct case teams, multiple explicit supervisors/responsible lawyers, access explanations and configuration through opaque references without a content bypass. Validated routing links preserve origin-specific revocation. One-time migration retains memberships/credentials and converts client-owner visibility to details-only grants; no supervisors or all-cases assignments are inferred. Active/archived case configuration, portfolio counts, related clients, reviewer selection, governance and research authorization use current scope plus action permissions.

Assignment/relink changes serialize with admitted reads and worker publication, invalidate changed recipients' sessions and mark unauthorized research for cancellation. Browser views clear on revocation or failed verification; authenticated responses and downloads bypass caches. Encrypted audit history and revision conflicts retain reviewer visibility. PostgreSQL blocking/conflict tests, restricted offline Linux checks and synthetic production-build browser rehearsals pass; see [verification](VALIDATION.md) and [operating limits](FIRM_RBAC_AND_SUPERVISION.md). Existing CI job/step budgets remain and test groups are disjoint. PR #33 is merged at `6649b117144a5851626e78423a18fc350b9fb89c`; exact post-merge main run `37941600919` passed. Deployment/customer migration, suspended-browser behavior and target-host qualification remain separate. W03 manual dates, tasks and tracked written opinions are merged with verified main CI; the retained R05A sequence continues below.

### Delivered packet — W03 manual work and tracked human opinions, 9 October 2026

Implemented case-linked manual deadlines/milestones/tasks, independent recipient progress, written-opinion submission → supervisor revision → revised submission → acceptance histories, and scoped personal/supervisory in-app work views. Dates use explicit Europe/Istanbul wall time and UTC instants. Every actor, request version and exact reviewed submission is retained in encrypted records; optimistic revisions and PostgreSQL locks prevent conflicting acceptance. Editing question/title/date/recipients makes prior work Stale without overwriting it. No self-review, task-generated grant, hierarchy access, model opinion submission or automatic legal deadline calculation is provided.

Only current recipients or explicit case supervisors with current case scope can inspect a request. Recipient-removing edits serialize with admitted reads, invalidate affected sessions and close browser views even when independent case access remains. Private opinion histories remain separate from model context and legal evidence/approval. The bounded work queue discloses its candidate/result limits and supports customer/workspace-date plus separate due-status filtering. Existing CI job budgets and complete, disjoint test partition remain. See [human workflow/API](HUMAN_WORKFLOW.md), [verification](VALIDATION.md) and [operating limits](FIRM_RBAC_AND_SUPERVISION.md).

PR #34 is merged at `f0595702679386f7ccce9d11a5cb4119b3b1552f`; exact post-merge main run `37950562133` passed. Target-host migration/restore, suspended/disconnected browser behavior, distinct-account customer acceptance and real legal/model/source qualification remain open. Reviewed renewal of inherited Stale source lineage is merged in PR #35 with verified main CI; registered same-input local-model authority trials are implemented below and await manual merge. Lawful corpus curation and independent legal review remain parallel requirements.

### Delivered packet — immutable serving releases and public source intake

1. **Implemented:** offline publication accepts independently reviewed graph bundles,
   prepares both graph families together, and activates or rolls back one exact
   release. Runtime TDB2 indexes are disposable, compiled from verified private copies;
   canonical signed payloads remain immutable. Active readers exclude activation.
2. **Implemented:** graph reads and research snapshots pin the signed serving release
   and activation sequence. Independent source checks reject changed quotes, rights,
   dates, identities and paths; a release switch prevents mixed-snapshot publication.
3. **Implemented:** separate public-source staging retains exact raw/text/locator
   hashes, supplied rights evidence and pending review states. A closed-registry,
   disposable connected-staging adapter acquires only fixed official TBMM URLs;
   scanning/extraction and offline import remain separate admission steps.
4. **Implemented:** source and serving-release readiness are separate in the app.
   Isolated real-Jena rehearsals verify query-only operation, reader locks and a
   nonlegal citation with exact evidence shared across the two graph families.
   Test signing keys and releases never enter the live corpus.

The live staging catalog contains the official TBMM enacted 6101 representation,
locally scanned and extracted into 94 exact Unicode line spans. It is explicitly
not a current consolidated text. Rights, identity and legal review remain pending;
both live graphs are empty. No staging record is available to research as authority.

At this checkpoint, the next priorities were provision-level extraction/identity
mapping and the first genuinely approved contracts release. The extraction and
publication foundations have since advanced as recorded below; the current order
is R01–R08. Signed-in production UI acceptance
remains a separate dependency; it does not block offline
source curation work.

Legal-owner ontology approval, licensed source packages and lawyer-adjudicated
evaluation remain required dependencies. No public corpus will be labeled legally
reviewed merely to exercise the publication pipeline. The earlier provider
credential mismatch has been resolved and live synthetic inference verified.

### Delivered packet — accountable source review

1. Added a curator workspace with integrity-checked, paginated source passages and
   a safe attachment download for comparison with the original.
2. Implemented source-review ownership and four separate assessments: permitted uses,
   source identity, extraction fidelity and legal/version suitability. Reviews are
   authenticated human records with evidence references, revision conflicts and
   append-only history, encrypted and restricted to the reviewing firm.
3. Kept immutable acquisition packages separate from review records. Completed
   assessments produce a review handoff dossier; they never publish graphs, change
   the imported rights state or enable agent retrieval automatically.
4. Exercised adversarial authorization/concurrency/integrity cases, including
   real PostgreSQL competing transactions and encrypted cross-firm substitution.
   Browser workflow acceptance used an isolated synthetic source; the existing
   live login credential mismatch remains separate from that test. Docker images
   were rebuilt and deployed; exact verification is in [validation](VALIDATION.md).

No real source assessment or legal approval was entered by the development
agent. Credentials and provider guards remain unchanged. The first actual reviewed
corpus release still needs accountable legal and rights review.

### Delivered packet — exact provision mapping

Implemented a staged provision-mapping workflow for reviewed source passages, preserving
source-version identity, Unicode spans, unresolved references, amendment and
transition distinctions. Candidate mappings must remain machine-proposed until
reviewed; do not silently substitute current provision identities for historical
ones. Connect accepted mappings to independently signed release preparation only
after actual rights, identity and legal-review evidence is available. Signed-in
acceptance with the user's current account credentials remains separate; provider
activation is now verified and never grounds for fabricating review records.

This packet delivers a complete staged workflow: deterministic heading candidates,
exact editable source spans, firm-confidential mapping proposals and authenticated
human review, historical identity/date fields, stale-review detection and an
unsigned mapping dossier. The source-review owner controls writes. Acceptance
requires accepted source reviews and the relevant local-processing scope. It does
not mint canonical graph identities, infer amendments, publish a release or enable
agent retrieval. Actual legal review remains a human dependency.

The packet is deployed. Validation includes exact Unicode/CRLF spans and locator
coverage, authorization/firm isolation, dual revisions, bounded ledger replay
against older-approval substitution, 15 real PostgreSQL concurrency scenarios,
and an isolated browser proposal → acceptance → stale conflict → explicit
reaffirmation flow. The live source still has no review or mapping records.

### Delivered packet — revision-bound graph review preparation

Implemented an offline operator adapter from current accepted source/mapping
ledgers to confidential, deterministic independent-review packets. Explicit typed
identity registries and mapping resolutions replace implicit free-text matching.
Physical rights/identity evidence and all six corpus-use scopes are required.
Unknown identities, an unknown start, an unknown end without the reviewed-open
declaration added below, source acquisition or unsupported text roles remain
explicit blockers. A null end date alone never means currently in force.

Candidate RDF splits evidence at admitted locators, retains exact source bytes
and excludes reviewer notes and firm-routing fields. Assertions remain unreviewed.
Both graph inputs carry a preparation-only marker rejected by the release validator
even with a trusted signature. A deployment-local HMAC protects the complete private
inventory; live validation reopens the owner, source, both ledgers and ontology.
Neither a saved dossier nor a correct hash establishes current approval.

The CLI is deployed in the API image; the publication guard is deployed in API and
Fuseki images. Validation includes137 final compiler/CLI tests,37 publication-gate
tests,42 snapshot tests,18 real PostgreSQL race scenarios and a network-none Linux
rehearsal with byte-identical macOS/Linux packets. Existing output is never replaced;
failed final checks discard only the invocation's own artifact. No real reviews,
signatures, graph installations or activation occurred. See
[operator commands](RELEASE_PREPARATION.md) and [validation](VALIDATION.md).

### Delivered packet — freshness-bound promotion and publication

Implemented deterministic provision conversion plus separate external public-review
and private deployment-sharing signatures. Private authorization binds exact
candidate/identity/evidence inputs, source/mapping revisions, six uses, audience,
expiry and restore epoch. Installation, activation, rollback and runtime graph/search
use now require current private authorization. Static legacy signatures cannot
bypass the broker. Private review routing and proof remain outside shared payloads.
Retained work becomes effectively stale after dependency revocation; saved content
and review history remain intact. Restore invalidates historical permission.

At that checkpoint, promotion supported closed-date, single-source provision snapshots;
the explicit-validity packet below extends the date model. No real
review, signing authority, graph publication or corpus qualification is supplied by
engineering tests. See [operator contract](PUBLICATION_AUTHORIZATION.md) and
[validation evidence](VALIDATION.md).

The 4 October runtime check found externally changed provider configuration and
correctly blocked inference. On 5 October, the user explicitly authorized the
laptop tunnel as an exception. The restricted relay now supports one exact HTTPS
hostname with DNS/IP pinning, TLS verification and request/response route binding.
The API retains its private route and all tenant, local-model and no-cloud-fallback
gates. Fresh native identity/model checks and synthetic generation through the
deployed tunnel pass; credentials were preserved. Tunnel request inspection is
enabled, so this does not establish zero retention or qualify client-matter use.
This mode uses internet transport and is not air-gapped; the default remains the
private native route. See [current evidence](VALIDATION.md) and
[activation contract](../deploy/provider/README.md).

### Delivered packet — explicit legal validity

Implemented an explicitly evidenced, reviewed open-ended validity state distinct
from an unknown end date. The curator records an exact supporting source span and
the inclusive date through which the status was checked. The UI requires a separate
passage preview before saving and shows that a later date requires renewed review.

The state passes through encrypted mapping review, deterministic preparation,
independent publication validation, graph traversal and lexical/vector search.
Unknown ends remain ineligible. Open-ended versions are returned only through their
checked-through date; historical evidence remains inspectable with applicability
explicitly unestablished. Separate public validity passages accompany graph/search
results. Overlapping versions fail validation even beyond the checked-through date;
that date is not a legal termination. Existing finite-date mapping records retain
their serialization and identities. The ontology digest changed, so preparation
against the old digest must be repeated and independently reviewed before publication.

Isolated end-to-end publication, real Jena queries and browser review/save checks
exercise synthetic sources only. They do not supply real legal review or activate a
corpus. See [verification evidence](VALIDATION.md).

### Next development sequence — attachments and legal-analysis/BYOK amendment

**R01 qualification remains in progress; its engineering contracts are implemented.**
R02 now uses those contracts to inspect sources, prepare private combined review
packets and enforce independently signed multi-source publication permission,
per-source audience/expiry constraints and live revocation. Actual source/legal
review and full operational qualification remain separate open gates.
R01 real-source review/evidence gates and the remaining roadmap gates are pending.
After merged PR #21, this packet implements optional [source-linked revision
adjudication](ANALYSIS_ADJUDICATION.md) in the existing human-review workflow:
exact predecessor/current drafts and quotes, all earlier-finding dispositions,
semantic/private-counterevidence observations and separately declared review time.
Actual changed steps, current quotes and targeted meaning/strength observations
are required for a repair declaration. Source/recipe/review changes invalidate the
comparison, and unresolved substantial findings prohibit positive review. This is
evaluation infrastructure; actual
representative adjudication and measured local-model feedback benefit remain open.
Public/historical synthesis still depends on genuinely reviewed R03–R05 evidence. Broader correction
and calibrated Standard/Deep analysis remain separate qualification gates.
Existing source/mapping/publication code is reused; the
research does not authorize real approvals, vendor contact or bulk acquisition.
Dependencies refer to completion of the relevant gate, not just code availability.

After merged PR #22, this packet implements [registered private analysis
comparisons](REGISTERED_ANALYSIS_COMPARISONS.md): freeze the rubric,
source/review/model pins, reviewers and budgets before either run; capture single-pass
and bounded-correction proposals from the same input through the existing queue;
retain separate authenticated-account observations and explicit active
preparation/verification/correction accounting. Failed, stopped,
missing and stale arms remain visible. Registration is not a release protocol or
legal approval; distinct accounts alone do not prove reviewer independence/expertise.
Provider round-trip time must remain separate from unreported GPU compute time.
Representative semantic/adverse qualification, full held-out protocols and real
R03–R05 source/effect approval remain mandatory; synthetic records, declared timings
and complete capture cannot establish a gain or qualify a release.

The delivered bounded engineering packet after merged PR #23 is confidential cohort
reconciliation for explicitly selected registered captures **within one authorized
workspace**. It freezes the exact selected captures, partitions incompatible
rubric/model/policy/budget and real/synthetic profiles, and exposes duplicate inputs,
declared-family/source overlap, reserved-family conflicts, differing reviewer outcomes
and unknown measurements. It preserves snapshots and shows subsequent changes without
rewriting them. Selection is a development inventory, not a held-out experiment.
Scorer rows and legal quality labels must not be inferred automatically.
Representative adjudication and R03–R05 source/effect gates remain the dependencies
for measured benefit and public synthesis; their human approvals cannot be supplied
by engineering fixtures. See the [cohort contract](ANALYSIS_COHORTS.md).

The delivered bounded engineering packet after merged PR #24 is **explicit,
source-backed public-authority context for private analysis**. A lawyer selects
exact assertion/passage/authority occurrences from retained, authorized research,
declares their role and links them to exact private draft steps. Signed source
evidence, historical provision versions, distinct research/event dates and serving
pins are frozen with the lawyer's declaration. Every inspection/export revalidates
publication permission and dependencies; private changes project Stale, while
publication/evidence failures withhold source bytes and export. Immutable snapshots
and truthful post-commit pending receipts are preserved. No model is dispatched,
draft/review changed, or unqualified legal-norm blocker cleared. See the
[public-authority context contract](ANALYSIS_AUTHORITIES.md).

The delivered bounded engineering packet after merged PR #25 is **source-bound
lawyer authority findings**. Every selected source receives six explicit human
observations on applicability, history, conditions, relationship, adverse authorities
and certainty. Immutable private records retain original evidence and all linked
draft targets, preserve disagreement and require exact basis/head/nonce checks.
Current technical records export with evidence; dependency changes project Stale,
and public-permission failures withhold quotations and potentially quoting notes.
Pending post-commit receipts remain withheld. Drafts, ordinary review decisions,
legal-norm blockers and qualification flags remain unchanged; no model is called.
See the [authority-findings contract](AUTHORITY_FINDINGS.md).

The delivered bounded engineering packet after merged PR #27 is **separate-account
semantic/adverse observations on retained authority comparisons**. Exact source/draft
snapshots, six semantic dimensions and every original finding disposition stay linked.
Account exclusions cover the candidate author, original reviewer and comparison author.
Per-reviewer heads preserve disagreement; explicit assessed/unassessed counts, unknown
adverse recall and selected-source inspection scope never imply legal correctness or
corpus completeness. Private exports revalidate dependencies, rights and current content scope.
No model call, positive legal verdict, blocker clearance or qualification score is added.
See the [adjudication contract](AUTHORITY_ADJUDICATIONS.md).

Registered fixed-evidence **human authority revision trials** now freeze the baseline
before revision and retain source-linked comparisons, two assigned-account observations
and explicit original/revised work time. The original draft predates registration; this
is not a model benchmark. See [trial contract](REGISTERED_AUTHORITY_TRIALS.md).
Confidential within-workspace authority-trial cohort reconciliation now freezes exact
selected records, separates incompatible profiles and inventories overlap and unknowns.
See the [group contract](AUTHORITY_TRIAL_COHORTS.md). Source-bound local authority
revision proposals now use the existing bounded queue and explicit lawyer adoption;
selected evidence and continuing permission dependencies are retained. See the
[proposal contract](AUTHORITY_PROPOSALS.md). The 9 October amendment schedules
W01 → W02 → W03 → reviewed source-lineage renewal are merged with verified exact
main CI. Registered same-input local-model authority trials and confidential cohort
reconciliation are implemented; verified manual merge remains pending.
Representative cases and lawful reviewed source samples
remain necessary; engineering captures cannot supply human legal approval or measured
benefit.
Actual R03–R05 rights, identity, legal-effect and historical reviews remain required
for the first usable legal workflow. Synthetic fixtures cannot supply those
approvals, semantic support, competence, binding force or adverse completeness.

| ID / priority | Delivery packet | Dependencies / accountable lead | Exit evidence |
|---|---|---|---|
| **W01 / P0, merged; qualification pending** | Firm administration, single-manager hierarchy, custom supported roles and enforced action permissions; preserve explicit memberships, credentials and endpoint compatibility | Application/security lead; current private foundation | Cycle/self/cross-firm relationships denied; administrator configuration separated from content; custom roles cannot bypass supported permissions; migration has no inferred grants; audits and concurrent checks pass |
| **W02 / P0, merged; qualification pending** | Explicit client scopes and case teams; multiple supervisors/responsible lawyers; effective-access explanations; revocation throughout retrieval, jobs and cached disclosure | W01; application/security lead | Details-only/current-and-future-case scopes and multiple-client cases verified; only administrators change teams; assignments constrain nav, documents, search, assistant, reviews and exports; active-operation revocation and cross-firm isolation pass |
| **W03 / P1, merged; field qualification pending** | Manual deadlines/milestones, delegated tasks, tracked human written opinions, personal and supervisory work views | W02; application/product lead | Distinct accounts complete supervisor request → lawyer submission → revision → acceptance; independent recipient/history/status records; tasks grant no access; Istanbul dates and scoped upcoming/overdue queues verified |
| **R01 / P0, in progress** | Source, asset and semantic qualification: offline catalogs, legal-analysis/scenario contracts, provider/evaluation dossier, physical evidence verifier, extraction comparator, reproducible calibration studies and scoped analysis/privacy scoring implemented; representative calibration and review pending | Legal ontology owner + data/source lead with application/security owners; source/provider dependencies documented | Source uses and routes reviewed; sample errors/reviewer time measured; argument/scenario fixtures adjudicated; provider processing/spend controls qualified; added effort estimated. Passing the dossier validator grants no approval |
| **R02 / P0, partial** | Multi-source snapshots, private preparation, exact public evidence, external public/private approvals, per-source deployment-wide grants/expiry and live revocation implemented; renewal requires a freshly reviewed release. Bounded cooperative research admission/cancellation, publication races and coordinator/restart controls implemented; synthetic application/recovery and signed-graph lifecycle drills measured; authorized release-specific lexical index builds/rebuilds and shared PostgreSQL runtime-read locks implemented. Restricted-audience serving, same-release renewal and representative five-job/resource qualification remain | R01 contracts; actual source reviews remain mandatory; backend/platform + knowledge engineers | Revocation of any required source invalidates its dependent release/work; competing changes cannot produce mixed snapshots; cross-source evidence and privacy checks pass; bounded cancellation, throughput and lock latency measured on declared hardware |
| **R03 / P0** | First genuinely reviewed contract corpus: RG ordinary/mükerrer manifest; amendment/transition candidates; MBS reconciliation; TBMM enacted/history distinction; exact provisions and historical versions | R01 lawful samples and protected reviewers; R02 for combined releases; editors + ingestion team | Reviewed corpus and exact evidence ready for analysis; amendment chains/historical queries pass; discrepancies visible. Full legal-analysis/export qualification additionally requires R04, the relevant R05 decision slice and R05A |
| **R04 / P1, partial** | Versioned Turkish fields, literal-citation occurrences, frozen-snapshot development capture/scoring and auditable private quotation context implemented. Real benchmark, authority resolution, local embedding/reranker evaluation and public/issue/adverse context packing pending | R01 development benchmark; R03 representative approved corpus; retrieval/ML + legal adjudicators | Exact identifiers and original quotes preserved; hybrid and graph/metadata/rerank ablations on one snapshot; thresholds, error slices and resource budgets reported; no private-data or adverse-recall regression |
| **R05 / P1** | Decision population and research: proceeding/decision/manifestation identity; allegation/finding/reasoning/result/dissent roles; citation ambiguity queue; reviewed authority-treatment events; independent contrary-authority branch | R01 judicial source/effect contracts, R02, R04; knowledge engineers + domain editors | Supporting and adverse passages are inspectable with role, version, institution epoch and scope; treatment is not inferred from citation; missing courts/periods and unknown finality remain explicit |
| **R05A / P1, partial, contract milestone** | Lawyer-authored private issue/premise/rule/application/alternative drafts, revision/hash-bound source selections, deterministic declared-structure checks, immutable revisions, stale projection and exact-version DOCX/PDF implemented. Bounded local-model proposals, up to one structural repair pass, shared job checkpoints, idempotent receipts and human adoption with model provenance implemented. Immutable version-bound lawyer review findings, conditional private-draft decisions, withheld change requests and source/review dependency revalidation implemented. Opt-in selected-finding proposals with actual edit links, manual/unresolved outcomes and accepted-pass provenance implemented. Optional source-linked before/after adjudication, all predecessor-finding dispositions, targeted semantic observations and declared review time implemented. Registered same-input private trial capture with frozen inputs/rubric/provider policy, two authenticated-account observations and explicit active effort implemented; trial candidates stay unadopted. Confidential within-workspace cohort freeze/reconciliation, separate exact profiles, family/source overlap, differing reviewer outcomes, unknown measurements and immutable stale projection implemented. Explicit exact-passage public-authority context linked to private draft targets, pinned historical/source/serving identities, immutable snapshots, pending receipts and permission/dependency revalidation implemented. Immutable source/context-bound lawyer applicability, history, conditions, relationship, adverse and certainty findings, preserved original evidence, review heads and permission/dependency revalidation implemented. Source-linked revised-draft comparisons against retained authority findings with explicit dispositions, changed targets/quotations and dependency revalidation implemented. Separate-account semantic/adverse observations on exact authority comparisons, explicit selected-source scope, per-reviewer immutable disagreement and revalidated exports implemented. Registration-before-revision human authority trials with exact fixed case/source inputs, two assigned-account observations, declared original/revised active effort, immutable capture history and revalidated private JSON implemented. Confidential human authority-trial groups with exact profiles, declared overlap, unknown observations/effort, immutable stale/withheld projection and revalidated JSON implemented. Opt-in selected public-authority finding proposals, exact source/target responses, bounded local inference, explicit Needs-review adoption and inherited source-permission guards implemented. Explicit reviewed renewal of retained unchanged source bindings is implemented; exact new human assessments preserve original model/evidence history and require re-review after edits. Registered same-input local-model authority trials with original-review/admitted-renewal identities, frozen full inputs, bounded unadopted candidates, two source-linked account observations, explicit non-overlapping effort, preserved disagreements and current guarded JSON are implemented; confidential model-authority cohort reconciliation with separate exact profiles, full two-arm histories, overlap/disagreement/unknown inventories and guarded immutable exports is implemented. Representative independent public adjudication, qualified public synthesis, representative semantic/adverse checks, measured benefit, Standard/Deep qualification and broader correction remain | R01 schemas; R03–R05 representative contract evidence; application/retrieval engineers + legal adjudicators | First contract task reaches reviewable analysis/export; consequential steps traceable; defects repaired or withheld; correction and depth compared with single-pass/Standard baselines |
| **R05B / P1, optional connected mode** | Sanitized BYOK deep search: local abstraction/fidelity, exact release, isolated vault/broker, OpenAI/Anthropic/Gemini adapters, untrusted return path and local application | R01 privacy/provider contracts; common broker/sanitizer qualification; R04–R05A for verification/final analysis; application/security + legal owners | Each adapter separately passes privacy, fidelity, authorization, entitlement/retention, cost/retry and citation gates. No private files, silent fallback or unapproved context; remote-tool disclosure explicit; disconnected operation independent |
| **R06 / P1** | Commercial/employment depth: issue/element/exception templates, non-equivalent terms, fact comparability, evidence gaps, audited calculation rules/parameters and firm playbooks | R03–R05A applicable source packs; R05B only for connected option; domain editors + product team | Practice scenarios pass; calculations expose event/basis dates, units, rounding, rules and missing inputs; no confident number on unresolved critical data; corrections and dependency re-review work |
| **R07 / P1** | Corpus operations/offline delivery: watermarks, signed full/delta packages, impact queues, restore/rollback and retention; bounded research jobs, revocation, cancellation, usage/spend and provider-state reconciliation | R02 manifest design starts early; local gate after R03–R06, connected gate after R05B; platform/security + source owners | Exact offline imports/recovery and stale-work handling pass; five-job operations respect privacy/budget; canceled/partial/ambiguous remote jobs visible; local deletion never claimed to erase provider-retained data |
| **R08 / release gate** | Lawyer-adjudicated legal/security/usefulness qualification and 10–20-lawyer pilot; local and connected modes scored separately | R01–R07 relevant gates **and W01–W03**; product owner + independent legal/security reviewers | Existing ~1,000-task/≥3,000-claim criteria plus argument/correction/depth/privacy/fidelity gates pass; signed-in workflow, offline recovery and preparation-time benefit accepted. Core qualification does not qualify BYOK adapters |

R03 source samples, R04 benchmark preparation and procurement feasibility may run
in parallel with R02 once R01 defines their boundaries. Broad scraping, additional
domains and historical bulk backfill must not displace the first qualified task.
R05A argument fixtures and R05B synthetic adapter work may also start after R01;
real legal analysis and outbound use wait for their respective evidence/privacy gates.
Local analysis must not depend on BYOK availability. All three provider choices remain
planned; an unqualified provider is disabled rather than silently substituted.
If an official channel is unavailable, use an approved manual package or a licensed
feed and declare reduced coverage; do not bypass access controls or invent evidence.

The first R01 calibration cycle should sample born-digital/scanned pages, amendment
chains and decisions across all three practices. A starting planning sample is
100 pages, 10 amendment chains and 30 decisions, subject to lawful availability;
synthetic fixtures test mechanics but cannot establish real extraction/review cost.
Use observed throughput, disagreements and access lead times to re-estimate the
30–36-week envelope before committing dates or population counts. Include the added
reasoning, sanitizer, provider and evaluation effort; do not assume it fits the same
staffing/calendar without measurement.

`Implemented` means executable code exists with targeted local checks. `Partial` means a usable foundation exists but the described end capability is incomplete. `Pending` means no completion claim. Legal and customer review are recorded separately from software tests.

| Workstream | State | Delivered baseline | Remaining release work |
|---|---|---|---|
| Matter foundation | Implemented baseline | Authenticated sessions, CSRF, explicit direct/client scopes and case responsibilities, encrypted records/originals, audit metadata, offline user/member administration, session revocation | SSO/MFA, customer identity integration, broader concurrency/load qualification |
| Private portfolio/workbench | Implemented baseline | Many-to-many customer/workspace tags, date filters, workspace files/comments, three adjustable panels, contextual product guide and calendar portfolio summaries | Lawyer workflow acceptance, large-portfolio load/accessibility qualification, evaluated conversational guidance |
| Provider integration | Partial | Server-side adapter, restricted relay with optional explicitly approved laptop tunnel, authenticated lawyer tenant, local model/context checks, native fallback configuration inspection, deployed synthetic exact-evidence completion | Representative Turkish legal model evaluation, concurrency/context qualification, stronger runtime attestation, tunnel inspection/retention qualification and revalidation on provider changes |
| BYOK deep research | Pending | No external research-provider adapter or multi-user key vault; existing gateway is a narrow source fetcher | R05B privacy/fidelity gates, exact scenario release, isolated broker/vault, all three adapters, independent citation admission, local application and per-provider qualification |
| Graph A ontology | Partial | National category catalog, RDF modules, SKOS, relationship metadata, provenance/time model, SHACL | Legal-owner signoff, source-backed institutions/norms/competence, persistent identity/standards mappings, reviewed aliases and non-equivalent concepts, amendment/transition reconciliation |
| Graph B jurisprudence | Partial | Proceedings/decisions/opinions/content/citation/treatment types, validated synthetic edge cases | Lawfully acquired decisions, passage roles, duplicate manifestations, institution epochs, historical provision resolution, effect/treatment review, comparable-fact and adverse-authority evaluation |
| Graph retrieval | Implemented baseline | Eight typed tools, verified immutable serving releases, atomic activation/rollback, independent signed-source checks, bounded traversal, reviewed validity cutoffs with separate evidence and explicit unresolved data | Real-corpus recall, legal-owner-approved serving release, large-corpus startup/indexing/query performance and applicability evaluation |
| Document intake | Partial | Initial and extended adapters, bounded OCR, isolated scanner/worker, signed offline signatures, live readiness, deployed clean/EICAR checks, encrypted originals and session revalidation | Representative layout/table/header/footnote and legacy-format qualification, full scan handling, sandbox escape testing, supplied UDF before pilot |
| Preparation/review | Partial | Quotations, issue checklists, corrections, claim review, scenarios, contradiction links, argument notes, playbooks, immutable drafts and DOCX/PDF; lawyer-authored private rationale with exact source pins and deterministic structural checks; bounded local proposals with explicit adoption and immutable provenance; exact-version human review decisions/findings and optional source-linked revision adjudication with conditional private-draft scope; registered same-input comparisons, separate assigned-account observations, active effort records and private exports; explicit within-workspace cohort snapshots, incompatible-profile separation, overlap/disagreement/unknown inventories and stale projection; exact public-authority contexts, retained lawyer findings and source-linked revised-draft comparisons with explicit dispositions | Qualified public/legal synthesis, representative semantic/adverse verification, measured correction benefit, calibrated Standard/Deep budgets and multi-step scenarios |
| Search and reasoning | Partial | Local document excerpt windows and additive graph queries, bounded OpenSearch lexical/vector adapter with release/rights/review prefilters and reciprocal-rank fusion; sealed release-specific index builder, Turkish original/normalized/folded fields, source-verified literal citation occurrences, exact source-span hints and explicit selection | Approved corpus/indexes, citation/alias identity review and Turkish benchmark/ablations, local embedding/reranker qualification, independent adverse search, evaluated issue reasoning and reviewed calculations |
| Source and corpus operations | Partial | Two registered TBMM acquisition representations; immutable staging, human source/mapping review and single/source-set publication with current private rights; R01 offline source/use/asset catalog and inspection | Actual R01 qualification, lawful RG/MBS/judicial/domain adapters, representative source-set qualification, separate observation/review/import freshness, archive gaps and per-source watermarks |
| Boundary gateway | Partial | Default disconnected mode, limited public query policy, exact-digest approvals, DNS-bound fetch, registered TBMM staging and immutable quarantine catalog | Advanced local PII/entity/secret detectors, ethics rules, broader source adapters, qualified incoming content/rights verification, measured false positives |
| Revalidation | Partial | Source/fact/practice changes mark work stale; private analysis checks fact/document/passage/contradiction/check and human-review recipe dependencies at read/export, review heads invalidate older proposals and prepared work; exact source/assertion/release impact and operator invalidation preserve content and snapshots | Automatic verified publication triggers, scalable dependency index and re-review queues |
| Operations | Partial | Restricted Compose, persistent stores, CI, five-volume encrypted backup tooling, fresh-target restore checks, isolated graph runtime rehearsals and bounded cooperative research jobs | Target-host builds, full recovery/rollback drill, signed offline distribution, quotas, representative five-job load, interrupted imports and hard interruption/resource qualification |
| Retention and governance | Partial | Scoped legal holds, append-only policy/events, dry-run erasure inventory, revision-checked archive/restore, minimal audit metadata | Legally qualified retention schedules, physical deletion across derived stores/caches/backups, audit anchoring and key rotation |
| Product/legal qualification | Pending | Test harness, acceptance specification and R01 provider/evaluation/calibration dossier contracts | Actual development/held-out tasks and adjudication, source/role/adverse ablations, KVKK/TBB firm-policy mapping, funded reviewers, statistical reporting, pilot and time-savings measurement |

### Delivered R01 engineering packet — offline qualification contracts

Added strict, versioned source/asset, legal-analysis, scenario and research-planning
contracts with a bounded offline CLI and synthetic examples. The seed inventories
27 source families and 21 assets; all use observations and source/legal reviews
remain pending. OpenAI, Anthropic and Gemini plans are explicitly disabled and
unqualified. Real measurements and adjudicated evaluation results remain absent.

The checker reports exact input hashes, coverage/review gaps, separate real/synthetic
calibration and provisional capacity. It validates references, temporal/role consistency,
declared material-fact preservation and critical-defect withholding without claiming
semantic truth or PII detection. It cannot create publication, legal-review or dispatch
authority and does not load credentials or application state. CI includes the check.

R01 is **partial**, not complete: actual reviewer assignments, lawful samples, source
and semantic decisions, privacy/fidelity adjudication, measured review costs and
capacity re-estimation are still required. R02 is not marked ready merely because the
schemas validate. See [operator usage](R01_QUALIFICATION.md) and [verification](VALIDATION.md).

### Delivered R01 follow-up — evidence bytes and extraction calibration

The offline CLI now checks the physical files referenced by research evidence
records, requiring an exact bounded inventory and matching SHA-256 values. It
rejects linked/special files, changed captures and missing or altered bytes.
An empty evidence set is explicitly `no_records`; physical integrity does not
authenticate source provenance, reviews or independent sample selection.

A separate comparator checks exported extraction text, passage order/locators and
annotated date, amount, identifier, negation and exception spans against an
independently supplied reference bound to the original bytes. Partial references
leave unscored content visible. It neither parses arbitrary originals nor assesses
semantic/legal correctness. A generator exercises the actual local TXT parser on
fixed invented Turkish text, with independent expected passages and measured parser
call time. CI covers this synthetic path; its timing is not real-corpus throughput.

No real source sample, lawyer review, corpus admission or provider call was added.
The next qualification work remains lawful representative samples, independent
transcriptions and review/error measurements, followed by capacity re-estimation.

### R01 engineering milestone — reproducible calibration studies

Multi-sample studies now bind the exact five-file dossier fingerprint and every
original, extraction, reference and sample metadata artifact. The offline CLI
recomputes comparisons, rejects duplicate raw originals, metadata records and
declared source identities, and verifies unchanged captures before reporting.
Byte deduplication and operator-declared identities do not establish independent
selection across differently represented or unidentified sources.

Results separate real/synthetic cohorts and practice, format, layout and unit
strata. Aggregate rates sum numerators and denominators; missing strata, partial
references, unannotated critical categories and missing timings remain visible.
Parser comparisons and declared reviewer disagreements are separate. Document
counts never substitute for the 100-page/10-chain/30-decision planning sample.
No automated capacity estimate or source-use permission is inferred.

The milestone's engineering acceptance is a reproducible three-practice synthetic
study through the actual bounded parser, adversarial duplicate/change checks, CLI
and CI integration, and isolated Docker verification. This delivers the tool for
the next qualification cycle; R01's real sample, rights, legal/privacy review and
capacity gates remain pending. See [operator usage](R01_QUALIFICATION.md) and
[verification](VALIDATION.md). Those checks alone do not qualify R02.

### R01 engineering milestone — scoped legal-analysis and privacy scoring

After merged PR #12, the offline release scorer accepts a frozen local or single-provider
protocol and independently supplied task judgments. It checks premise/authority grounding,
critical inference/fact/omission/role errors, adverse retrieval, paired correction/depth,
privacy/fidelity, approval/key/spend isolation, returned evidence and operations. Unknown
slice/metric/pair minima, incomplete assessments and synthetic records cannot produce a
complete quantitative pass. The older score format remains core-only with a non-passing
complete-qualification flag. No runtime permissions or providers are activated.

This R01/R08 engineering dependency proceeds alongside the remaining R02 operational
gates; it does not replace their representative latency/inference qualification. The
next source, analysis and BYOK evaluations can use executable contracts rather than
unimplemented acceptance prose. Real evidence, sufficient reviewed sample sizes, confidence
intervals and actual R05A/R05B execution remain pending. See [scorer guide](EVALUATION.md)
and [verification](VALIDATION.md).

### R05A engineering milestone — source-bound local authority proposals

PR #30 merged as `4c77c49aecdf933cc9224292667a8fba5d2f871e`; its exact post-merge
main CI run `37887856160` passed. The next packet lets lawyers select 1–5 unresolved
source/dimension findings from the latest Current authority review. The local model
receives only selected original source evidence alongside the fixed private draft,
uses the existing one/two-pass queue and supplies exact source/actual-edit responses.
A rejected repair cannot replace accepted-pass provenance. A lawyer inspects and
explicitly adopts a hash-bound candidate into a new unreviewed version.

Source-context/review seals, public nomination/release pins and continuing permissions
protect generation, publication, adoption, inherited manual/model revisions, reads
and exports. Pending committed content stays withheld until clean final guard exit;
missing lineage also fails closed. Generic research status/cancel cannot bypass these
checks. Source denial culls quotations and potentially quoting candidate/iteration
text. Changed review heads or recipes project Stale and close source-dependent export.
The private research wrapper becoming Stale during adoption does not replace the
original public source binding. Original documents, reviews and drafts stay immutable.

No legal-norm blocker, review finding or qualification flag is automatically cleared.
**R05A remains partial.** Explicit reviewed revalidation of inherited source lineage
and registered same-input local-model authority trials remain pending after the
9 October W01 → W02 → W03 amendment. Preserve prior evidence and reasons. Lawful real sources, independent semantic/adverse
qualification, measured benefit and qualified public/history synthesis remain open.
See [workflow/API](AUTHORITY_PROPOSALS.md) and [verification](VALIDATION.md).

### R05A engineering milestone — confidential human authority-trial groups

PR #29 merged as `8baaa698079da9d3d46fbc54ab1b1efe552eca79`; its PR checks passed.
This packet freezes 2–12 explicitly selected human revision registrations within one
workspace, retaining missing/partial/stale captures and exact original source evidence.
It partitions exact recipes/rubrics/workflow/origin profiles, inventories repeated
fixed inputs and baseline versions, private documents across declared families,
exact public passages and optional reserved-family overlap. It retains separate
current assigned-account judgments, source links, declared active work and separate
adjudicator effort with explicit unknowns. Differing outcomes are not voted away.

Frozen records remain immutable. Exact preview/nonce checks, workspace row locks,
precommit revalidation and clean-exit admission protect writes. Current reads pin
relevant private records, heads, participants and recipes so repeated changes to
already-stale evidence are detected. Changes project Stale and close export; missing,
moved or denied ancestry withholds all copied notes/passages. Private JSON is serialized
then revalidated inside the source guards. Bounds preserve complete selected evidence
without truncation. Existing encrypted retention and source privacy boundaries apply.

This is a selected-record inventory of human revisions. Baselines predate registration;
no blinded/randomized experiment, independent expertise, qualification score, adverse
recall, model benchmark or preparation-time gain is established. No provider calls,
permissions, migrations, CI capacity/deadline changes or deployment are added.
**R05A remains partial.** Source-bound local authority proposals are now delivered
in the following engineering milestone. Actual lawful
source/history/effect review and representative Turkish legal qualification remain
mandatory for public synthesis and measured Standard/Deep benefit.
See [workflow/API](AUTHORITY_TRIAL_COHORTS.md) and [verification](VALIDATION.md).

### R05A engineering milestone — registered fixed-evidence human authority trials

PR #28 merged as `86566953c798b3a2af9cb0a42cdee9f370e88d27`; its exact PR and
post-merge main checks passed. This packet registers before revision of a current
lawyer-authored baseline. It freezes issue/posture/date, premises, selected private
passages, facts/contradictions, original source context/history/review and fixed
semantic/finding rubrics. A candidate or comparison created before registration,
changed case inputs or model-assisted draft cannot enter this human-only workflow.

Two authorized lawyer/admin accounts must differ from operator, baseline/source authors,
and later candidate/comparison authors. The operator pins their current immutable
source-linked observations without inferring expertise or real independence. Original
versus revised active preparation, verification/review and correction seconds are
explicit and nullable; zero is distinct from unknown. Shared setup, full verification/
correction and non-overlap require separate confirmations. Partial captures remain
visible. Completion means records present, including possible unassessed judgments;
no legal correctness, repair, adverse recall or improvement is calculated.

Registration precedes revision, **not baseline preparation**. Baseline effort is
retrospective; there is no randomized/blinded experiment, model/provider protocol or
single-pass/correction model execution. Existing bounded local-model comparisons remain
separate. Workspace locks, exact nonce/basis/head pins, clean-exit admissions, immutable
history, stale projection, complete content withholding and post-serialization private
JSON revalidation preserve the existing privacy boundary. No source rights, provider,
network, schema, job/worker/retry/timeout or deployment permission changes are introduced.

**R05A remains partial.** Confidential authority-trial cohort reconciliation is delivered;
representative lawful public source samples, independent Turkish legal qualification,
public synthesis, held-out release tests and measured Standard/Deep benefit remain open.
See [workflow and API](REGISTERED_AUTHORITY_TRIALS.md) and [verification](VALIDATION.md).

### R05A engineering milestone — separate-account comparison adjudication

After merged PR #27, an account distinct from the candidate author, original
source reviewer and comparison author can inspect the exact frozen pair and
record six semantic/logic observations plus a judgment on every original finding
opinion. Assessed declarations link exact before/after targets, private quotes and
original public passages. Accounts are separated; professional independence and
semantic correctness are not automatically established.

Adverse inspection explicitly names selected sources and limitations, or records
no search. Assessed/total counts expose missing review; full-corpus coverage and
adverse recall remain unknown. Each reviewer has a separate immutable history,
head and nonce; competing opinions remain visible without consensus or approval.
Source denial withholds potentially quoting content and clears cached ancestors;
changed dependencies make records stale. Current private JSON/DOCX/PDF exports
revalidate all bindings after rendering. No draft, blocker, original finding,
provider permission or qualification flag changes.

**R05A remains partial.** Registered fixed-evidence human authority trials are delivered
above; model comparisons, representative legal qualification and measured benefit remain.
Confidential authority-trial cohort reconciliation is delivered. Actual source/legal review,
representative semantic/adverse evidence, public synthesis, held-out qualification
and measured benefit remain open. See [adjudication contract](AUTHORITY_ADJUDICATIONS.md).

### R05A engineering milestone — authority-linked revised-draft comparison

After merged PR #26, a later private draft can be compared with one exact retained
public-authority review. The original context/findings and both private versions
remain inspectable. Every original source/dimension receives an explicit explained
human disposition and selected target/quotation links. Actual changed targets are
required for an addressed declaration; replacement mappings remain human judgments.
No blocker, ordinary review, qualification flag or original finding is changed.

The expected stale original draft/research remains visible. Current private
facts/documents/review heads, exact public source pins/bytes/permissions and the
current retained research identity are checked separately. Changes make saved
comparisons stale or withheld; final-save/export guards prevent partial output.
Encrypted immutable history, serial workspace locks, head/nonce conflicts and
pending post-commit receipts retain disagreement and uncertain completion.

The opt-in interface starts with blank dispositions and unknown review time;
source and change details remain collapsed. Known comparison denial clears cached
ancestor views. Latest Current comparisons export privately as JSON/DOCX/PDF.
Synthetic host/Linux checks, real PostgreSQL races and browser save/download/
stale/withheld rehearsals passed. **R05A remains partial**: separate-account semantic/adverse observation capture
now follows this packet; representative lawful source
review, public synthesis, held-out qualification and measured benefit remain open.
See [comparison contract](AUTHORITY_COMPARISONS.md), [evaluation boundaries](EVALUATION.md)
and [verification](VALIDATION.md).

### R05A engineering milestone — explicit public-authority context

Lawyers can select 1–8 exact public-source occurrences from one retained research
record in an authorized workspace, declare their role/reason and link each to
1–12 exact private analysis steps. The server regenerates quotes and metadata from
the signed release, pins the historical provision and source representation
separately, and preserves research/event date differences and unknown applicability.
Source citation, treatment, competence and effect remain distinct relationships.

A preview digest and per-user nonce bind an immutable encrypted snapshot under the
workspace lock. A separate post-commit receipt records completion, never ongoing
publication rights; incomplete authorization stays withheld after retry/recovery.
Every inspection/export reopens the publication guard. Private/review/research
changes produce a stale projection; public permission, pin or evidence failures
withhold the manifest and all source bytes. JSON/DOCX/PDF attachments require Current
and discard partial output on final dependency/permission failure. Selection and
history are explicit, paginated and bounded; no public inverse matter links exist.

This is an engineering context record, not legal support. It does not clear the
existing unqualified legal-norm blocker, qualify applicability/binding force,
resolve semantic/adverse completeness, alter an analysis/review, feed a model or
publish real source data. **R05A remains partial**. Follow-up packets now bind lawyer
findings and revised-draft comparisons to this exact context; qualified synthesis and representative independent
R03–R05/R05A evaluation remain open. See the [context contract](ANALYSIS_AUTHORITIES.md)
and [validation evidence](VALIDATION.md).

### R05A engineering milestone — confidential comparison cohorts

PR #23 merged as `e427f66f9c7da7273f107d6452e68a3dd9ed47ab`; its three PR checks
and [exact post-merge main CI](https://github.com/caglarsubas/lawyer-assistant-v1/actions/runs/37715917289)
passed. The follow-up packet freezes 2–12 explicitly selected registered captures
from one authorized workspace, bound to an exact preview digest and idempotent
nonce. Exact rubric/provider/policy/budget/recipe and real/synthetic profiles remain
separate. Repeated inputs/versions, declared-family/source overlap, reserved-family
conflicts, different reviewer judgments and unknown measurements remain visible.

The report retains every selected capture and original passage. It neither votes
on differing judgments nor computes a legal quality or benefit score. Complete
capture remains bookkeeping, including unassessed dimensions and unresolved
findings. Raw elapsed/provider round-trip timings stay distinct from unknown GPU
compute and separately declared active/reviewer time. A later dependency change
marks the current projection stale without rewriting the frozen encrypted report.
Live dependency hashes also detect new changes to already-stale comparisons.

Workspace authorization precedes selection, joins, inspection and attachment
export. Preview/freeze use the existing matter lock plus ordered existing job-row
locks; final checks reject changed inputs. Missing selected records remain explicit;
routing or integrity failures fail closed. Snapshots are bounded to 16 MiB, with
paginated listings and no partial output. Existing retention inventories, legal
holds and backups include these records; physical erasure remains a separate gate.

Synthetic host/Linux tests, real PostgreSQL freeze/cancel races and browser
preview → freeze → changed dependency → stale download checks passed. No inference,
dependency, migration, new CI job/budget/retry/worker, external permission or live
application deployment was added. **R05A remains partial**: representative independent
semantic/adverse qualification, held-out release protocols, measured benefit,
reviewed public/history synthesis and calibrated Standard/Deep remain open. See
[cohort contract](ANALYSIS_COHORTS.md), [scoring boundaries](EVALUATION.md) and
[verification](VALIDATION.md).

### R05A engineering milestone — source-linked private revision adjudication

PR #21 merged as `76055d9622081750182d1ae26d91c86d00c70ab0`; its three PR
checks and [exact post-merge main CI](https://github.com/caglarsubas/lawyer-assistant-v1/actions/runs/37622349199)
passed. This packet adds an optional human assessment to the existing private review
workflow. The immediate predecessor/current pair, exact content/source hashes,
baseline review and all its findings are fixed by the server. Lawyers inspect actual
typed changes and selected quotations, record six semantic/private-counterevidence
observations, and separately declare repaired, withheld or unresolved findings.

A repair declaration requires a surviving actual edit, a current quotation and
affirmative meaning/strength observations on that same changed step. Substantial
unresolved findings or needs-change observations prohibit positive conditional
review. Both drafts' dependencies are rechecked before commit, at projection/export
and in proposals pinned to that review. New reviews, altered snapshots or recipes
invalidate the comparison without rewriting history. Legacy receipts stay compatible.

The interface begins without affirmative choices; detailed steps, sources and
historical declarations remain collapsed. Exact-version DOCX/PDF retains the
comparison, original findings and source text. Optional declared review seconds
stay separate from full preparation time and model-benefit measurement. No inference
occurs in adjudication, and assessment text is not automatically added to prompts.

Synthetic host/Linux, browser/export and real PostgreSQL race checks establish
these engineering bindings only. **R05A remains partial**: real independent
semantic/adverse adjudication, reviewed public/historical synthesis, measured local
model benefit, broader correction and calibrated Standard/Deep remain open. The
follow-up reproducible comparison-trial capture is delivered above under frozen protocols.
No dependency, migration, CI job, retry, worker, external permission or live app
deployment is added. See [adjudication contract](ANALYSIS_ADJUDICATION.md) and
[verification](VALIDATION.md).

### R05A engineering milestone — review-informed local proposals

PR #20 merged as `e82e33c9d2d6aff0d416984c1d271ca4eb93adfb`; its three PR
checks and exact post-merge main CI passed. This engineering packet connects
immutable lawyer findings to explicit, bounded local-model revision proposals. A lawyer selects up
to five findings from the current version's latest change request. The server
pins their source review, exact version and content hash; every selected finding
requires a typed response linked to a permitted actual edit or a clearly stated
manual/unresolved outcome. Review text remains untrusted input and is shared only
through this opt-in local proposal workflow.

Existing fixed facts, rules, evidence, dependencies, access gates and two-pass
budgets remain. A new review, source/version change or policy change invalidates
the proposal. Human adoption creates a new Needs review draft with feedback
provenance; no finding is automatically resolved and prior reviews remain
immutable. Representative semantic/adverse qualification and public/historical
synthesis remain open. The next analysis gate is source-linked semantic/adverse
adjudication with measured feedback benefit; a structural response link does not
establish correction quality. No new provider destination, CI job, dependency or
runtime deployment is included in this packet. See [feedback contract](ANALYSIS_FEEDBACK.md)
and [verification](VALIDATION.md).

### R05A engineering milestone — immutable private-draft lawyer review

PR #19 merged as `c96bbd03ac0e8f79c9ecae7bad132cbf15282cad`; its three PR checks
and exact post-merge main CI passed. The next engineering packet now records human
criteria, linked findings and decisions against an immutable draft ID/content digest,
analysis revision and expected review head. All five criteria must be explicitly
addressed for conditional private acceptance; stale sources, critical structural
checks or unresolved critical/major findings block it. Change requests withhold the
screen/export assessment even when machine checks pass.

Reviews and their predecessor links are immutable encrypted private records.
Current Reviewed is a human projection; original Needs review content/checks and
model lineage stay unchanged. A later decision preserves older judgments; a new
text version starts unreviewed. Source/check/review-recipe changes project Stale.
Review-head changes invalidate older proposals and preparation products; quotation
snapshots retain the review ID without adding reviewer prose to model prompts.
Exact-version exports include declarations and recheck the head after rendering.
Concurrent reviews serialize on the matter lock; identical retries return one event,
while a competing decision returns a conflict. No provider call occurs in review.

Synthetic application/browser checks, isolated Linux checks and two real PostgreSQL
review-head races establish engineering behavior only. Human declarations do not
prove source interpretation, resolution of earlier findings or public authority.
**R05A remains partial**: representative semantic/adverse review, reviewed
public/historical synthesis, broader correction, calibrated Standard/Deep and paired
lawyer-adjudicated accuracy/time benefit remain open. R01/R03 reviewer/source gates,
remaining R02 operations and R05B privacy/provider qualification are unchanged.
No new dependency, migration, CI job, retry, worker or external permission is added.
See [review contract](ANALYSIS_REVIEWS.md) and [verification](VALIDATION.md).

### R05A engineering milestone — bounded local-model proposals

PR #18 merged as `1966089b36b4c5a24b59aec7979ca7544ba18ac9`; its checks and exact
post-merge main CI passed. Building on that workbench, the next packet now provides
separate encrypted local-model proposals for fixed private-analysis inputs.
Application interpretations, existing condition assessments and conclusion prose
may be proposed; facts, roles, sources/ranges, rules/conditions, alternatives and
step dependencies remain fixed. One call is bounded to 120 seconds; structural
repair permits at most one further call within 240 seconds total. Each call keeps
the existing 1,000-token cap, complete prompt accounting and provider guards.

The declared-structure critic rejects new critical defects and retains unresolved
or rejected work without granting legal approval. Shared job admission, cancellation,
deadlines, recovery and safe request receipts prevent duplicate inference on retry.
Changed source versions/dependencies or provider policy block adoption. The lawyer
inspects exact sources, then explicitly adopts into a new Needs review version with
a reason, retaining model origin, notes and prompt/source pins. Prior versions stay
immutable, including when competing adoptions return a conflict. UI and DOCX/PDF
disclose AI contribution; later manual changes retain its provenance.

This is engineering support for a constrained private correction loop, not complete
R05A legal synthesis or calibrated Standard/Deep research. Reviewed public/history
context, semantic/adverse verification, broader correction and paired adjudicated
quality/time benefit remain open. R05B BYOK research stays separate. No CI job,
worker, timeout, dependency or inference permission was expanded. See
[proposal contract](ANALYSIS_SUGGESTIONS.md) and [verification](VALIDATION.md).

### R05A engineering milestone — source-linked private analysis drafts

After merged PR #17, the first runtime analysis slice lets lawyers record an issue,
ledger premises or explicit assumptions, private rule candidates, conditions and
exceptions, application steps, alternatives and a provisional conclusion. Exact
passage hashes/document revisions and fact revisions bind the observed inputs;
changed selections return a conflict instead of silently using newer content.

Deterministic checks inspect declared dependencies. Missing conditions, incompatible
assessments, unsupported steps and linked open contradictions withhold the affected
conclusion. Allegations and unknowns remain qualified. A private document cannot
qualify a public legal norm; semantic support and legal applicability always need
review. No check promotes a draft to Reviewed or an unconditional legal conclusion.

Corrections append encrypted immutable versions with a change note and structural
comparison. Fact/source/contradiction/recipe changes project Stale without rewriting
history. The UI exposes source spans and collapsed details; exact-version DOCX/PDF
retains checks and uncertainty, with authorization/freshness rechecked after rendering.
Research snapshots retain analysis references without inserting authored rationale
into the quotation provider prompt. See [workbench contract](ANALYSIS_WORKBENCH.md)
and [validation](VALIDATION.md).

This delivers the lawyer-authored private-analysis engineering slice. R05A remains
partial. At the manual-workbench milestone, approved public sources, historical
applicability, semantic/adverse verification, automatic correction, Standard/Deep
budgets and adjudicated benefits were pending. The following proposal packet
delivers only the bounded private structural-correction portion. R05B's sanitizer/broker/vault/adapters remain
separate, disabled work. No real review, provider request or deployment is granted
by the synthetic checks.

### R04 engineering milestone — inspectable private evidence context

After merged PR #16, deterministic packing retains original spans/hashes, rotates
across documents and exposes scanning, passage, text and complete serialized-prompt
limits. Every omission is counted; unexamined candidates remain explicit. Long
sentence/line fragments are labeled and unsplittable tokens omitted. The model
receives only the question and quotation entries; source metadata and the manifest
stay in the encrypted matter product. Provider guards and exact-claim checks remain.

Lawyers inspect prepared excerpts and open full original passages; DOCX/PDF exports
retain limits, ranges and digests. Recipes are invalidation dependencies. Old work
remains readable without retroactive manifests. See [context contract](CONTEXT_PACKING.md)
and [validation](VALIDATION.md).

This completes the private quotation context slice. Public parent/exception
expansion, issue/supporting/adverse allocations, evaluated reranking, reviewed
decision roles and R05A analysis remain pending. No real source review, legal
qualification, live provider call or deployment is granted by these tests.

### R04 engineering milestone — reproducible retrieval comparison

After merged PR #15, a bounded development benchmark compares
the original lexical baseline, four Turkish lexical channels and the default
citation-assisted channel set on one sealed index and authorized graph snapshot.
It captures every query/profile outcome, including partial, unavailable and unexecuted
work, preserving existing source checks, permissions and candidate budgets.
The offline scorer reports authority Recall@20, graded nDCG@10, adverse discovery,
explicit text-query targets and paired differences with family-grouped uncertainty.
Mixed snapshots and authorization changes discard capture; incomplete outcomes
cannot disappear from aggregate denominators. No new API/agent profile selector,
provider access or CI topology is introduced. See [benchmark guide](RETRIEVAL_BENCHMARK.md).

This packet prepares measurement. The real 360-query/three-practice inventory,
two-reviewer adjudication, reviewed citation identities, embeddings and rerankers
remain pending; synthetic results cannot qualify retrieval or the product.

### R04 engineering milestone — source-verified literal citation discovery

After merged PR #14, v3 managed indexes add a bounded, independent channel for
explicitly labeled esas, karar, application and law numbers. Original literals,
leading zeros, label roles and codepoint offsets are preserved. Each nominated hit
must contain the queried key in its independently verified source; forged index
keys cannot substitute for evidence. Colliding numbers remain separate unresolved
occurrences, with no inferred court, case pairing, citation target, legal effect
or provision version.

The v1/v2 readers remain compatible. New fields require a new explicitly selected
index; no existing index or deployment is changed automatically. Citation query
overflow reports a coverage gap while other channels continue. Existing candidate,
execution and CI budgets remain. See [citation retrieval](CITATION_RETRIEVAL.md) and
[validation evidence](VALIDATION.md).

This completes the literal-occurrence engineering slice, not R04 or citation
identity resolution. The next citation work requires reviewed target identities,
institution/version context and an ambiguity queue; the real-source and retrieval
benchmark gates remain open.

### R04 engineering milestone — exact-preserving Turkish retrieval

After merged PR #13, new managed indexes retain the Turkish stemming baseline and
add independent original-token, Turkish-normalized and diacritic-folded channels.
The same derivation runs on source text and queries, with pinned recipe/Unicode
versions. Exact evidence, authority IDs, locators, dates and hashes remain unchanged;
bounded match hints point back to original codepoint spans. Alias collisions remain
distinct candidates and do not confer legal equivalence or resolve citations.

New channels share a 200-candidate budget and existing deadlines/authorization checks.
The builder bounds derived-field bytes, seals and verifies a new generation, and
never rewrites or automatically selects an old index. Existing v1 indexes remain
readable. [Migration and operator details](TURKISH_RETRIEVAL.md) describe the contract.

This R04 engineering slice can proceed alongside remaining R02 qualification and
R01/R03 real-source reviews. Synthetic tests establish software behavior; they do
not establish real-corpus recall or improved legal preparation. Reviewed citation
identities, the 360-query development set, retrieval ablations, local model assets,
adverse-authority evaluation and representative performance remain pending.

### R02 engineering foundation — consistent multi-source review snapshots

The [source-set inspector](RELEASE_SNAPSHOT_SET.md) captures 2–8 explicitly selected
sources in one session. Each independently satisfies its current owner, firm, rights,
source-review and accepted-mapping contract. PostgreSQL locks the operator and source
heads deterministically; all source bytes, reviews and account state are revalidated
before use and on exit. The aggregate caps are 64 MiB of source artifacts and 400
mappings. Safe summary output follows successful exit; source selection and hashes
remain confidential. SQLite demo mode is explicitly optimistic.

This packet delivers the snapshot/inspection foundation, with PostgreSQL race tests,
while leaving **R02 partial**. It creates no combined graph or publication authorization.
The subsequent preparation packet below adds canonical identity/version conflict
handling and public/private candidate inventories; the publication milestone adds
per-source sharing grants, expiry, new-release renewal and live revocation.
Full research-job cancellation, throughput and lock-latency
qualification remain open; five simultaneous test inspections establish concurrency
behavior only. R01 lawful samples, actual legal/privacy review and capacity estimates
are still required before product qualification.

### R02 engineering milestone — combined independent-review preparation

The [combined preparation command](RELEASE_SET_PREPARATION.md) composes the locked
source set into a deterministic, confidential review packet with source-qualified
mapping resolutions, a shared explicit identity registry, exact evidence and
cross-source identity/version conflicts. Unknowns and conflicts withhold both graph
candidates. Compatible finite versions may share identities across different source
offsets; repeated open-ended versions require explicit proof reconciliation. Private
proofs stay outside the source-candidate inventory. The generated graph retains
unreviewed assertions and preparation-only markers.

Preparation and revalidation bind current source revisions, operator state, physical
bytes and ontology. A final-check failure discards only newly created output. The
distinct packet format is rejected by existing single-source publication readers.
See the [verification record](VALIDATION.md) for the synthetic engineering evidence;
no source approval, release or live deployment is created by this work.

Preparation remains independently useful without granting permission. The publication
milestone below supplies the separate signed authorization boundary.

### R02 engineering milestone — independent source-set publication permission

The [source-set publication workflow](SOURCE_SET_PUBLICATION.md) accepts external
public review and private deployment permission for 2–8 current sources. Each source
requires an explicit `deployment_shared` grant, all required uses, its own current
rights-proof reference and a bounded expiry. The release cannot outlive any member
grant; every grant is capped at 90 days after approval. Restricted or conditional
audiences fail closed rather than entering the shared graph.

The existing runtime guard recognizes the distinct signed format. Installation,
activation, rollback and use revalidate the complete locked selection, exact
prepared graphs, physical evidence, current ontology, key, epoch and expiry. A
change to any required source denies the dependent release. Private selection
manifests, rights proofs, operator/firm identities and workflow timestamps stay outside public
artifacts. PostgreSQL qualification includes an actual runtime guard holding off a
second-source rights writer and denying subsequent use after revocation.

Renewal is explicit re-review: a fresh public timestamp, new externally signed
release and new private authorization. Existing records remain immutable; old
expired or revoked rollback targets remain denied. The single-source format and
commands retain their strict boundary. Synthetic engineering tests do not establish
real legal rights, qualified human review or a populated national corpus.

**R02 remains partial.** Research job controls, synthetic encrypted recovery,
five-job application and signed-graph lifecycle baselines are delivered in the
engineering milestones below. Production qualification still requires representative
inference/corpus throughput and lock wait, resource ceilings, public-source ingestion
overlap, and populated graph rollback/failure recovery. Restricted-audience serving and same-release
renewal remain unsupported. R01 actual source/legal/privacy qualification continues
to gate real corpus publication; it cannot be replaced by synthetic approvals.

### R02 engineering milestone — research admission and cancellation (6 October 2026)

After merged PR #6, the coordinator retains five workers and ten admitted jobs,
reserves capacity before persistence, and physically removes queued cancellations.
Running work records `cancelling` until its next checkpoint; occupied capacity stays
reserved until the worker exits. Deadlines include queue time and are checked before
retrieval/inference stages and publication. Stop intent and product publication
serialize on the same record; completed products remain intact when publication
commits first. Archiving requests a stop and blocks later private publication.

One coordinator owns the database; a second startup cannot recover live work.
PostgreSQL ownership is checked during admission and research, including publication;
lost ownership fails closed and requires restart. Shutdown records stop intent and
joins workers; startup records unfinished work as `interrupted` without replaying it.
The UI continues polling while stopping and distinguishes interruption, cancellation
and an expired budget. See [operator contract](OPERATIONS.md#research-job-lifecycle)
and [verification evidence](VALIDATION.md).

Synthetic qualification covers five occupied workers/ten admissions, cancellation
replacement without accumulating queue entries, provider-stage cancellation,
revocation/archive/deadline checkpoints, SQLite optimistic rollback and real
PostgreSQL cancellation/publication ordering, five concurrent publication versions,
archive ordering and coordinator loss. These are engineering checks, not evidence of
production throughput, legal review or corpus qualification.

**Cancellation remains cooperative:** an in-flight dependency must return before
acknowledgement. The budget is not a hard process-interruption deadline and does not
prove upstream inference stopped. Large-corpus resource limits, full restore/rollback
and production five-job throughput remain R02/R07 gates; R02 is not complete.

### R02 engineering milestone — isolated recovery rehearsal (6 October 2026)

After merged PR #7, an opt-in, disposable Docker drill exercises the existing
encrypted five-volume cold backup. It records backup/restore/startup times and
verifies PostgreSQL records, document decryption, OpenSearch persistence,
graph/source bytes, interrupted-job recovery and publication-epoch invalidation.
Corrupt archives and nonempty restore targets are rejected without changes. Exact
images, source fingerprints, hardware and the synthetic workload appear in its
report; the drill stays outside routine CI. It also verifies restoration of the
previously running service set. See [operator instructions](OPERATIONS.md#disposable-synthetic-recovery-drill)
and [measured verification](VALIDATION.md).

The drill exposed and fixed inherited read-only mounts preventing graph restore.
The helper now mounts exactly five verified named volumes directly, excludes
unrelated host binds and preserves the API's configured shutdown grace.

This packet establishes a repeatable engineering recovery baseline. Empty-corpus
Fuseki startup and synthetic documents do not qualify populated graph rollback,
real legal permissions, production RPO/RTO or five-job throughput. Representative
load, ingestion overlap, lock waits and resource ceilings remain the next R02 gates.

### R02 engineering milestone — five-job application baseline (6 October 2026)

After merged PR #8, an opt-in isolated load drill uses five workspaces and mixed
synthetic document formats. It observes five occupied workers, ten admitted jobs,
capacity rejection, queued/running cancellation, a PostgreSQL row-lock wait,
document ingestion during research, stale-result handling and fresh research waves.
It records request/job timings, sampled container CPU/memory/PID use and kernel
memory/process high-water marks under declared limits. The driver runs separately
from the measured API/database. The drill stays outside routine CI and leaves the
live deployment untouched. See [operator profile](OPERATIONS.md#five-job-application-baseline)
and [verification evidence](VALIDATION.md).

The provider is a controlled synthetic dependency. These results establish an
application baseline only; real inference latency, reviewed public corpus retrieval,
large-volume source ingestion and production capacity remain separate R02 gates.
The fixture covers private document ingestion and a deliberately induced row-lock
wait, not concurrent public-graph import/reindexing or ordinary production lock
latency. The latter scenarios, sustained-load qualification and populated graph
rollback remain the next operational packets. R02 is not complete.

### R02 engineering milestone — signed graph lifecycle drill (6 October 2026)

After merged PR #9, a repeatable Docker drill passed against the existing immutable
publication functions and real Fuseki/TDB2 runtime with invented RDF and disposable
trust. Both datasets continued serving A while B installed. SIGKILL during a
partial C import left A unchanged and the partial stage inspectable; retry installed
C without activating it. Recreated containers rebuilt matching A/B graph inventories.
Corrupted active B failed startup without fallback; rollback restored A with a
new sequence. Live activation, stale sequences and corrupted rollback targets
were refused. The [evidence record](VALIDATION.md) binds exact image/source identities,
small-fixture timings, resource peaks and confirmed cleanup. The workload remains
opt-in outside routine CI; ten fast isolation/failure contracts join the existing
deployment step. See the [operator profile](OPERATIONS.md#disposable-signed-graph-lifecycle-drill).

This packet does not grant real publication permission or qualify a legal corpus.
Its test-only authorization guard is separate from the application's private
review/revocation ledger. Sustained representative load, OpenSearch reindexing,
five research jobs during public ingestion, encrypted populated-graph restoration
and production recovery objectives remain open R02/R07 gates.

### R02 engineering milestone — release-bound public search indexes (6 October 2026)

After merged PR #10, the index builder closes the missing path from approved
signed evidence to a usable public lexical index. The trusted operator builds a
new concrete index from the active graph under the publication read lock and
current private source-set authorization. Exact passage/assertion/authority
identities preserve historical alternatives. Rebuilds leave the selected index
intact; complete readback, a write block and ready metadata are required before a
new index can be selected explicitly. Managed readers recheck index state before
and after retrieval, alongside the signed-source and live permission checks.

The builder performs no source acquisition, legal approval, automatic selection,
index deletion or embedding inference. A dedicated opt-in Docker test passed against
OpenSearch 2.19.3 with two synthetic signed sources and the actual private
authorization implementation on SQLite, outside routine CI. It proved old-index
search during a paused rebuild, partial-build rejection, write-block enforcement,
exact historical evidence and second-source revocation. The [verification record](VALIDATION.md)
binds the clean code commit, source/test fingerprints and confirmed cleanup.
Private review locks can delay concurrent operations; PostgreSQL contention
qualification remains open. Representative recall, ranking, adverse-authority
coverage, production scale and five model jobs during public ingestion remain
R02/R04/R07 qualification gates.


### Delivered packet — R05A retained-source binding renewal, 10 October 2026

An authorized lawyer can load the exact current draft and original retained public contexts, map each source to current targets, and record all six assessment dimensions. The explicit action creates a sealed human assessment and a new **Needs review** draft version. Original quotes, context/review seals, model/job/pass contributions and previous versions remain unchanged. Unresolved findings remain unresolved; binding freshness does not establish source approval or legal correctness. W03 human-opinion acceptance is independent.

Current source permissions, original evidence, graph pins and completed admissions remain mandatory. Changed private evidence must first be refreshed through a new ordinary draft version; incompatible source/review contracts and revoked or changed public evidence cannot be renewed here. Later semantic edits, review-head/recipe changes or renewal-reviewer access loss stale the renewed binding. PostgreSQL publication locks, exact preview/version/revision checks, idempotent receipts and post-commit admission protect races and late guard failure. Cached affected views clear on denial; versioned exports include retained and renewal provenance. See [renewal contract](AUTHORITY_REVALIDATIONS.md) and [verification](VALIDATION.md).

PR #35 is merged at `5ee45d1782da1da7cd36c2b729345d9377719847`; exact post-merge main run `37969967765` passed. Deployment, lawful corpus acquisition, actual legal review and release qualification remain open. The next registered model-authority trial packet is implemented below and awaits manual merge.

### Delivered packet — R05A registered same-input model authority trials, 10 October 2026

Implemented immutable registration before local-model calls for a current original public review or the latest admitted retained-source renewal. Both arms freeze one private draft, exact public passages/full human assessment, one to five explicitly selected open findings, provider/recipe/budget pins, rubric/family/origin and two distinct existing authorized accounts. Original review and renewal identity remain separate; renewed human judgments never rewrite original evidence or model responses.

The existing queue runs single-pass versus conditional bounded structural correction with permanent receipts, cooperative cancellation and at most three calls per pair. Candidates stay unadopted. Both assigned accounts record source-linked semantic/adverse judgments for both arms and all source dimensions; the operator separately declares complete, non-overlapping active effort. Immutable histories preserve disagreement and unknown measurements. Complete capture is neither legal qualification nor measured benefit.

Current source/admission checks, private evidence/draft/review changes, provider-policy pins and all participants' access govern reads, publication and confidential JSON exports. Changed inputs block work/export; source/admission denial withholds quoted histories. Pending post-commit receipts cannot be repaired by retry. Limits reject oversized histories rather than truncating evidence. Existing CI job names and deadlines remain; isolated PostgreSQL races use two bounded workers without restarts/retries. Exact collection is disjoint and complete. See [model-authority trial contract](REGISTERED_AUTHORITY_MODEL_TRIALS.md), [verification](VALIDATION.md) and [operations](OPERATIONS.md).

This engineering packet awaits verified manual PR merge. The follow-up confidential registered model-authority trial cohort freeze and reconciliation is implemented below, keeping incompatible exact profiles, source/family overlap, reviewer disagreement and missing measurements explicit. Independent lawful corpus/legal review, representative Turkish semantic/adverse evaluation, measured real-model benefit, Standard/Deep qualification and deployment remain open.

## Two-graph specification

Graph A covers legal classification; norms/provision versions; institutions and their units; conditional competence/jurisdiction; actors/roles/positions; objects/transactions; procedures/remedies; evidence/burdens/presumptions; time/calculation rules; and sources/governance. National fields include constitutional, administrative, tax, criminal, civil, commercial, employment/social security, family, succession, property, enforcement/insolvency, consumer, competition, IP, data protection, finance, procurement, environment, migration and international/conflict subjects.

Graph B distinguishes proceedings from decisions, decisions from source representations, allegations from findings, majority from dissent, citation from endorsement/application/effect, and same-proceeding reversal from conflicting later interpretation. Ordinary, unification, constitutional-review, individual-application and jurisdiction-conflict decisions need separately reviewed effect models.

Norm genealogy includes amendment, repeal, replacement, renumbering, split/merge and transition rules. Institutional genealogy separates establishment from operation, reorganization/succession/abolition and competence transfer. Concept development and evidenced historical influence do not imply current authority. Organizational hierarchy, appellate routes, territory, chamber allocation, supervision and normative force use distinct relations.

Every substantive relationship is a reified assertion: subject/predicate/object; conditions and exceptions; exact source representation/passage; extraction/software/model versions; review/reviewer; legal validity interval; system recording/correction/supersession times; sensitivity/rights/release identifiers. Unknown dates/effects stay unknown. Contradictions coexist. Publication, decision, effect, finality and acquisition dates are separate. Machine-proposed, source-verified, legally-reviewed, disputed, rejected and superseded states are mapped explicitly in the ontology. Direct citations may be source-verified; consequential competence/effect/interpretation requires legal review.

Four independent coverage reports are mandatory: ontology types, actual institutions/competences/history, acquired corpus by source/domain/period, and assertion evidence/review quality. Unknown corpus totals remain unknown. Neither ontology size nor graph density establishes legal completeness.

## Agent contract

Extract local matter facts/roles/dates/posture and uncertainty. Nominate multiple legal issue candidates. Resolve historical provisions/institutions/rules. Query graphs and lexical/vector search independently. Traverse only approved relationships within explicit depth/node/time budgets. Retrieve supporting and adverse authorities, inspect original passages, check applicability, and present alternatives and gaps.

Tools: `locate_issues`, `resolve_authority`, `trace_norm_history`, `trace_institution_history`, `trace_decision_history`, `expand_authorities`, `get_evidence`, `get_coverage`. Default maximum two hops; deeper steps require a separately bounded workflow, not arbitrary query code. No raw agent SPARQL, graph writes, federation or schema edits. Graph paths nominate authorities; source passages support conclusions. Missing graph links must not suppress ordinary-search results.

Private facts and all matter-selected public authorities remain confidential. Join/traversal/cache/export authorization precedes computation. No public inverse matter links, automatic anonymized-party correlation, or private-to-public knowledge promotion. Named graphs are not a security boundary.

### Legal reasoning and connected research amendment

R05A exposes a source-backed legal rationale: issue → facts/allegations/assumptions →
applicable rule/version/conditions → application → adverse argument → qualified conclusion.
Local checks detect unsupported deductions, temporal errors, contradictions and missing
exceptions. Bounded retrieval/revision records what changed and why; unresolved critical
defects withhold the affected conclusion. Machine checks cannot mark work legally Reviewed.
Standard and Deep modes change time/token/search budgets, not access rights or evidence gates.

For optional R05B research, build and sanitize the scenario locally. Remove direct and
contextual identifiers, secrets and confidential details while preserving legal meaning.
Keep the original-to-scenario map private. If an identifying date, amount or other fact
cannot be generalized faithfully, research the general rule or keep the issue local;
never invent realistic facts. Preview and approve the exact provider/model/tool/budget
envelope. Keys are server-side and scoped; provider-managed downstream searches require
explicit disclosure because their individual queries cannot all be locally preapproved.
Returned reports are untrusted leads: admit original passages and verify applicability
before local synthesis with the private facts. See the [complete contract and provider
checks](LEGAL_ANALYSIS_AND_DEEP_RESEARCH.md).

## Phases and exit gates

| Phase | Window | Deliverables | Exit gate |
|---|---:|---|---|
| 0: contracts | Weeks 1–4 | R01 source/asset/rights dossier, national inventory, identity/time model, analysis/scenario contracts, provider/privacy matrix and capacity estimate | Modeling boundaries reviewed; lawful samples or blockers; analysis/fidelity fixtures; extraction/review and added BYOK effort measured; pilot estimate reassessed |
| 1: backbone | Weeks 3–16 (provisional) | R02 multi-source release foundation; Graph A and genealogy; existing private/intake foundations; **W01/W02** administration and explicit scoped responsibility; R03 RG/MBS samples | National type coverage reviewed; atomic multi-source authorization; evidenced reconstruction; private links isolated; W01/W02 access/migration/revocation gates pass; five-job baseline measured |
| 2: contract slice | Weeks 6–24 (provisional) | R03 reviewed contract pack, R04 retrieval, R05 first decisions, R05A rationale/correction and task/export; **W03** human supervisory workflows | End-to-end contract analysis reviewed; premises/rules resolve to evidence; consistency defects corrected or withheld; source/time/rights gaps explicit; W03 distinct-account workflow accepted |
| 3: deep research | Weeks 14–32 (provisional) | R04–R05A historical/adverse and deeper local analysis; R05B sanitized BYOK adapters; R07 freshness/job controls | Measured depth benefit without critical applicability regression; each provider passes disclosure/fidelity/credential/citation gates; currentness limited by verified evidence |
| 4: practice depth | Weeks 22–36 (provisional) | R06 commercial/employment packs, parameters, issue templates, playbooks, scenarios, corrections and R07 impact/distribution | Domain reviewers approve tasks; calculations reproduce from source rules; changed assertions correctly flag dependent products |
| 5: qualification | Weeks 35–42 (provisional) | R07–R08 security/load/offline/restore tests, source/review operations and 10–20 lawyer pilot | Legal, graph, confidentiality, source coverage, usefulness, **W01–W03** and operational gates pass |

Critical path: legal semantics/review capacity → lawful source acquisition → representative extraction → identity/version resolution → release publication → retrieval/synthesis evaluation → pilot. Application feature completion alone cannot satisfy these gates.

These overlapping windows retain the original program start and provisionally
include the added W01–W03 critical-path allowance. They do not restart the clock
or assert that review gates have passed; re-estimate from measured access, migration
and human-workflow throughput before committing a pilot date.
For planning, allocate approximately three Turkish legal editors (including the
ontology owner), two knowledge/retrieval engineers, two application engineers and
one platform/security engineer. Independent consequential review must have protected
capacity. If access or reviewer capacity falls short, reduce populated scope or
extend dates; do not lower legal gates. Measure reviewer minutes, rejected/reworked
assertions, acquisition delay, index growth and hardware cost. Do not assume the
attachments' fixed server counts, vendor prices or claimed model savings.

## Firm-workflow qualification and ownership

Application/security owns W01/W02 and application/product owns W03. A customer-designated firm administrator is accountable for actual grants; organizational managers and case supervisors are different roles. Test reporting cycles/self-reporting/cross-firm links, denied unassigned managers, multiple case supervisors, both client scopes including later-linked cases, administrator/content separation, unauthorized role/team changes, revocation during active work and cache clearing, and migration without access expansion. Use distinct authenticated accounts for administration → supervisor inspection → deadline/milestone/task assignment → each lawyer’s opinion → revision request → acceptance, with retained audit/review history. No automatic legal deadline calculation, external notification or AI-authored opinion is included. See the subordinate contract for packet delivery status and detailed acceptance.

## Qualification specification

Approximately 1,000 held-out lawyer-adjudicated tasks and ≥3,000 substantive claims, separated from training/prompt development. Include graph/history cases and insufficient-evidence tasks. Record denominator, corpus/snapshot/model/policy, adjudicator disagreements and confidence intervals. Report by domain, historical period and relationship type when sample sizes support it.

Build a separate development benchmark of about 360 tasks (120 per launch practice),
with at least 30% spanning temporal transitions, alongside citation, passage-role,
contrary-authority, OCR, concept-confusion and missing-coverage cases. Two independent
annotators and adjudication produce exact relevant/adverse spans. Split by source,
decision/proceeding and near-duplicate family to prevent development/held-out leakage.
The development set cannot substitute for the held-out release suite. Add paired
single-pass/correction and Standard/Deep cases plus scenario fidelity, contextual
reidentification and provider-isolation slices. Freeze sufficient per-provider/slice
denominators in R01 rather than infer qualification from aggregate results.

| Metric | Release target |
|---|---:|
| Citation resolvability | 100% |
| Observed substantive claim support | ≥99.9% |
| Critical misapplication, wrong version, omitted issue, fabricated authority | 0 in release suite |
| Recall@20 / exact identifier retrieval, within documented coverage | ≥95% / ≥99% |
| Appropriate qualification or abstention on insufficient evidence | ≥95% |
| Satisfactory completion of answerable tasks | ≥80% |
| Legitimate sensitive tasks supported safely, including local completion | ≥98%; not an external-transmission quota |
| Median preparation time saved, including checking/correction | ≥30% |

These are unmeasured targets for the current baseline, not a universal negligible-error guarantee. A high support score achieved by returning almost nothing cannot pass the usefulness gate.

Add the following **planned qualification dimensions**; they are not yet implemented
in the current score command and do not replace the stronger table above:

| Dimension | Measurement / gate |
|---|---|
| Source coverage/freshness | Expected vs acquired ordinary/mükerrer issues within an explicitly bounded manifest; publication/observation, review and installation delay reported separately; unknown denominators remain unknown |
| Legal time and identity | No critical wrong-version, institution-epoch, transition/date-basis or treatment errors; unresolved references excluded from legal conclusions and counted separately |
| Adverse evidence and passage roles | Known contrary-authority Recall@20 target ≥95% on answerable covered tasks; report allegation/reasoning/dissent confusion and factual comparability separately, with no critical role misattribution |
| Retrieval usefulness | Frozen-snapshot lexical → hybrid → temporal/metadata → bounded graph → local reranker/issue-feature ablations; nDCG@10 and paired uncertainty intervals; graph discovery/time benefit without reduced correctness |
| Privacy and rights | Zero unauthorized cross-matter/public disclosure or prohibited use in the suite; redaction residuals/contextual re-identification measured separately from legitimate-task passage |
| Runtime and review cost | Five-job p50/p95 latency, cancellation, peak RAM/GPU, bytes per representation/index, reindex/restore times and reviewer minutes; initial retrieval-only p95 budget ≤5 seconds on declared pilot hardware, to be ratified after R02/R04 samples |
| Offline packages | Every admitted package passes signatures, inventory, compatible base/version, rights, cross-link and rollback checks; display source watermarks, gaps and installed age |

Do not adopt weaker citation, span-support or wrong-version targets from the
attachments. A model's STS score or a foreign legal benchmark does not qualify
Turkish legal retrieval, and a graph ablation does not remove the approved national
ontology or temporal/provenance foundations.

The [analysis/BYOK qualification matrix](LEGAL_ANALYSIS_AND_DEEP_RESEARCH.md#8-delivery-and-measurable-gates)
adds zero critical unsupported deductions or scenario fact mutations, zero seeded prohibited
outbound disclosures, bounded correction/depth comparisons, cumulative disclosure tests,
key/job isolation and per-provider evidence checks. The [extended scorer](EVALUATION.md) now
enforces their declared observation, sample and paired-comparison gates per mode/provider.
Real experiments, authenticated adjudication and independent qualification remain pending. Keep privacy and
legal-fidelity evaluations separate, and do not achieve safety merely by blocking useful work.

The executable extended scoring contract is `backend/app/qualification_scoring.py`. Supply
one independently adjudicated held-out task per JSONL row, a complete pinned snapshot and
a frozen mode/provider protocol with explicit sample minima. See [input contracts and
migration](EVALUATION.md); legacy `TaskScore` files now produce core metrics only:

```sh
backend/.venv/bin/python scripts/evaluate_release.py /evaluation/adjudicated-tasks.jsonl \
  --snapshot /evaluation/snapshot.json --protocol /evaluation/protocol.json
```

This emits aggregate core/analysis metrics, practice breakdowns, slice coverage and paired
quality/time/cost measurements, and exits nonzero on unmet or unknown quantitative gates. Empty denominators remain unknown, duplicate tasks are rejected, small perfect samples cannot pass the sample gates, and preparation-time measurements must include verification/correction. Even passing quantitative results do not automatically certify production or replace the independent legal/security/operations gates.

Graph release requires all mandatory catalog categories legally reviewed; no blocking SHACL/identity/time/cross-link errors; evidence for every substantive assertion; no critical invented competence/history/treatment/version; explicit unresolved references and gaps; reproducible snapshots; no matter leakage; and a controlled graph-versus-no-graph discovery/reviewer-time comparison without reduced correctness.

Required edge cases: historical/current institutions, established/not operational bodies, territory changes, conditional review routes, majority/dissent, ordinary/special-effect decisions, deferred effects, provision split/merge, conflicting interpretations, unknown finality and missing corpus periods. Test five simultaneous research jobs, query cancellation, ingestion overlap, partial imports, reindexing, rollback, encrypted recovery and complete network disconnection.

## Operating rules and ownership

The legal ontology owner signs semantic changes and national coverage. Knowledge engineers implement ingestion/identity/query systems. Legal editors review consequential assertions. Application/security teams enforce access, agent boundaries and safe deployment. Source owners document licenses and refresh obligations. All reviews identify an actual accountable person; engineering fixtures cannot impersonate legal review.

R01 includes a firm AI-use policy and data-flow review against current official
KVKK/TBB guidance, with versioned obligations and a named legal/security owner.
Record lawful processing purpose, controller/processor roles as actually deployed,
retention, sensitive-data handling, export review and incident response. Public
judgments can still contain personal data. Masking is not proof of anonymity;
private originals and legally material facts stay protected rather than being
indiscriminately deleted to create embeddings. The exact approved laptop tunnel
remains a documented internet-transport exception, with inspection/retention
qualification outstanding; it grants no additional external inference or acquisition
destinations. The later user-requested R05B BYOK lane is a separate, optional research
exception with its own privacy, provider and processing review; it does not relax the
local-provider boundary. See the [verification/disposition record](PLAN_RECONCILIATION_2026-10-05.md)
and [BYOK contract](LEGAL_ANALYSIS_AND_DEEP_RESEARCH.md).

Published graph releases are immutable; research records graph/ontology/corpus/model/policy/source versions. Updates create new versions and re-review requirements, never silently rewrite reviewed products. Rights revocation, deletion and legal holds must reach documents, assertions, indexes, caches, exports under control and backups according to retention policy.

Outside v1: autonomous filing, authenticated UYAP/MERSİS account synchronization,
autonomous client communications, outcome prediction, automatic cross-matter learning
and model fine-tuning. Defer full Akoma Ntoso conversion, a general LegalRuleML engine,
unqualified embedding compression and separate private graph infrastructure unless
a later measured need justifies them. No proxy/CAPTCHA/WAF evasion or unrestricted
remote MCP/federation is planned. Nationwide ontology maintenance continues;
additional validated practices and historical population follow the first three.


### R02 engineering milestone — concurrent authorized readers (6 October 2026)

After merged PR #11, runtime authorization uses shared PostgreSQL row locks for
both single-source and source-set releases. Five verified readers can hold guards
at once; an index rebuild can coexist with search on the previous sealed index.
Preparation and publication actions remain exclusive. Account, source-review and
mapping writes remain excluded through guard exit; entry/exit integrity, expiry,
revocation and final result checks are unchanged. No authorization cache is added.

The opt-in search drill now uses real PostgreSQL as well as OpenSearch. It tests
five searches during a paused rebuild, a database-observed rights-writer wait,
committed revocation disabling all index generations and rejection before network
use. Both authorization schemas have row-by-row writer and concurrent-reader
regressions in the existing PostgreSQL CI job. Heavy Docker qualification remains
outside routine CI; no job, dependency, retry or time-limit increase is introduced.
See [operator contract](OPERATIONS.md#build-or-rebuild-a-public-search-index) and
[verification evidence](VALIDATION.md).

**R02 remains partial.** Long builds still delay review/revocation writes, and
queued writers may delay new readers. Representative capacity, revocation latency,
five actual inference jobs during public ingestion, restricted-audience serving
and same-release renewal remain open. Real source/legal approval and legal-retrieval
quality require their separate R01/R03/R04 gates.


### Delivered packet — R05A confidential model-authority trial groups, 10 October 2026

Lawyers explicitly select 2–12 admitted registered model-authority trials in one
authorized workspace, preview exact complete captures and freeze an immutable
confidential inventory. Original-review/admitted-renewal identity, origin, rubric,
dimension, provider-policy and arm budget profiles remain separate. Both arms,
retained candidate passes, full source/history records, source-linked account
observations and non-overlapping effort declarations are retained. Exact input/
version duplicates, declared family/reserved overlaps, shared private documents
and repeated public passages are reported without pooled accuracy or benefit.
Missing observations and timings remain unknown; different reviewer labels stay
visible without automatic adjudication. Freezing never calls a model or adopts a
candidate. The opt-in workbench supports preview, history, Current/Stale/Withheld
inspection and confidential guarded JSON export.

All private parents are resolved before public joins. Changed evidence, trial runs,
observations, effort, provider policy or participant access invalidate current
exports without rewriting snapshots. Source/admission denial withholds all quoted
history. Workspace row locks serialize freezes; exact preview and live authorization
are checked before commit and again before completing admission. Late committed
failures retain permanently pending receipts; retry cannot override them. Export
rechecks after serialization and through guard exit. The complete/disjoint CI partition moves one existing runtime-authorization
case from the near-limit PostgreSQL job into the existing frontend group step;
job count, deadlines, coverage and no-retry policy are unchanged. See [contract](REGISTERED_AUTHORITY_MODEL_COHORTS.md),
[verification](VALIDATION.md) and [operations](OPERATIONS.md).

This engineering packet awaits manual PR merge. The user's PR #36 merge report was
not yet reflected by the GitHub API at preparation time; the verified dependency
head is `b9f884e559c0c0de34ceee78be8400fb10dcf25f` with successful exact-head run
`37979906924`. Main remains independently verified through PR #35; this does not
claim PR #36 deployment or post-merge main qualification.

**Next R05A qualification priority:** representative lawful Turkish source/case
intake, independent source-linked semantic/adverse review, frozen family splits and
measured paired model/reviewer effort. Actual legal/source approval, representative
model benefit, Standard/Deep budgets, target-host operation and pilot acceptance
remain open; a complete synthetic inventory cannot satisfy those gates.


### Delivered packet — R01/R05A source-linked reference-case intake, 10 October 2026

The offline intake checker now binds original source bytes, exact passage exports,
case inputs, independently supplied reference answers, reviewer/history/rights
records and declared development/held-out families to one protocol/snapshot/rubric.
It preserves missing review evidence and separate real/synthetic practice/period
inventories. Shared norms do not merge case families; shared decision/proceeding
identities, decision representations, inputs and family labels form transitive
components exposing leakage and inconsistent groupings. No near-duplicate identity
is inferred automatically.

Optional scorer integration binds every later held-out row, explicit gold/adverse
set and post-run receipt to the exact pre-run reference. Missing rows fail binding;
changed sources/inputs/scores, undeclared files, mixed scopes and invalid receipts
fail closed. A 1,000-case synthetic boundary rehearsal exercises the bounded roster,
not a representative legal benchmark. Reports contain counts/gaps/fingerprints
without private prose, locators or reviewer identities. Existing numeric-only
scoring remains compatible and explicitly reports missing reference-case evidence.
All approval, authenticity, privacy, independence and production flags remain false;
physical binding alone cannot establish any of them.

This engineering packet awaits manual PR merge. Verified continuation base:
PR #37 merged into PR #36 at `187f2700cad09d18d6a235a3fa8e2e3b11f2c692`, with
successful exact-head CI `38037218901`; GitHub still reports PR #36 open. Main
remains independently verified through PR #35. No deployment or actual source/legal
approval is implied. CI adds only a small offline fixture check within existing
job counts and deadlines. See [reference intake](REFERENCE_CASE_INTAKE.md),
[scoring](EVALUATION.md) and [verification](VALIDATION.md).

**Next qualification priority:** obtain lawful representative samples and independent
source-linked reference review, measure review/extraction throughput, witness actual
family/protocol registration and run representative paired model/reviewer studies.
R01, R03–R05 and R05A remain partial. Standard/Deep budget calibration, target-host
operation and pilot acceptance remain open. Source/legal approvals cannot be
supplied by synthetic engineering records.


The reference-intake packet also reduces repeated live authorization work found
after its first hosted backend suite reached 99% and hit the existing deadline.
`require_permission` now reads current user and all role rows in one fresh joined
statement; unmanaged/empty-managed, dangling, foreign, malformed and revoked-role
semantics remain explicit. Expected firm is pinned before refresh, and no permission
result is cached. The profiled workflow drops from 84,872 to 68,308 SQL statements
with the same 206 trial revalidation calls. This is an operational engineering
improvement, not legal qualification or a universal performance claim. Existing
CI coverage, jobs, workers, deadlines and no-retry policy remain unchanged.
