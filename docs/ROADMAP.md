# Approved product roadmap and implementation ledger

Baseline: 4 October 2026; research reconciliation: **5 October 2026**. Original planning envelope: **30–36 weeks**; the 9 October firm-workflow amendment adds an estimated **4–6 weeks** to the application critical path (provisional combined envelope **34–42 weeks**), conditional on approximately eight FTE, lawful source access and protected Turkish legal-editor capacity. This is a delivery sequence, not a claim that elapsed weeks, legal reviews or corpus acquisition have occurred. Re-estimate from representative acquisition/review throughput before committing a pilot date; the attachments' shorter fixed calendar and longer staffing estimates are inputs to that check, not replacement promises.

This is the canonical delivery plan. [Data and knowledge strategy](DATA_KNOWLEDGE_STRATEGY.md) specifies source families, refresh targets and retrieval requirements. [Research reconciliation](PLAN_RECONCILIATION_2026-10-05.md) records adopted proposals and unresolved claims. The same-day user amendment is specified in [legal analysis and sanitized BYOK deep research](LEGAL_ANALYSIS_AND_DEEP_RESEARCH.md). Those research revisions changed planning only. Subsequent implementation progress is recorded below: R01 offline contracts, evidence verification and extraction comparison are delivered; source approvals, legal review and provider activation are not granted by that work.

## Product contract

### Delivery authorization amendment — 11 October 2026

After reporting PR #49 merged, the user authorized the development agent to merge
subsequent roadmap PRs and continue to the next packet. This prospectively supersedes
the manual-merge instructions in earlier ledger entries. Merge only the reviewed
exact PR head after all required hosted checks pass, using ordinary repository
protections without an administrator bypass. Verify the resulting main commit and
report post-merge CI separately. This authority grants neither legal/source review
nor corpus publication, deployment or a weakening of security/quality gates.

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

**Current application sequence: W01 → W02 → W03**, with individually verified packets and manual PR merges. W01 and W02 are merged with verified exact main CI. W03 is merged at `f0595702679386f7ccce9d11a5cb4119b3b1552f` with verified exact post-merge main CI (`37950562133`); deployment and field qualification remain open. PR merge and deployment are separate evidence. R05A source-lineage renewal is merged in PR #35 with verified exact main CI. Registered model-authority trials and cohort reconciliation reached main through PR #36 at `3de49c8b991e6526ebdf1bc825b815db385a2201`, including PR #37. PR #38 merged into that dependency branch **after** #36 reached main. PR #39 integrated its reference-case intake and live authorization optimization plus registration-witness verification into main at `c2b0b3b1c7df49da171a92316855d1288724bf11`; its exact-head run `38050597031` passed. Exact post-merge main run `38053314945` also passed. Deployment remains a separate observation. Actual legal/source review and pre-execution registration remain open. Lawful corpus acquisition and independent legal review continue alongside this sequence. W01/W02 enter the national backbone gate, W03 enters the contract-workflow gate, and all three are mandatory before R08. Existing R01–R08 identifiers, evidence and legal gates remain unchanged.

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


### Delivered packet — R01 registration witness verification and main integration, 10 October 2026

PR #36 is verified merged into main at `3de49c8b991e6526ebdf1bc825b815db385a2201`
(11:43:28 UTC), including PR #37. PR #38 merged seven seconds later into the
dependency branch at `b34ab86264b882a1f5eac8c8ba1d6383941c1761`; main did not
contain its two implementation commits. This packet integrates that merged branch
onto the verified main base. The application code immediately after integration
is byte-identical to PR #38's tested head `2bd9dfa9cc10f7d559f55a303b14b02eb9765b30`.
Its exact-head run `38044253519` passed all three jobs; backend took 19m19s
(the remaining suite 17m41s), so further CI runtime reduction remains needed.

Offline case intake and extended scoring now optionally verify two to ten distinct
enrolled Ed25519 witnesses over exact raw casebook/protocol/snapshot/catalog and
registry digests. An independent registry pin is mandatory; no key is trusted from
the envelope or inherited from legal-source publication. The bounded registry
separates key identity and subject identity, rejects aliases/revocation/invalid
enrollment intervals, and restricts purpose to evaluation registration. All supplied
signatures must verify; malformed, changed, undeclared or unstable inventories
produce no partial report. Signature counts and fingerprints omit private identities
and legal content. Existing numeric scoring and unsupplied-witness behavior remain.

Signed dates are checked against declared case registration and row measurement
dates. They are not trusted timestamps or execution-start records. Valid signatures
prove enrolled signing-key possession and committed bytes, not actual pre-run
registration, independent enrollment/currentness, professional independence, privacy,
legal/source approval or representativeness. Synthetic evidence still cannot qualify.
No real witnesses, private signing keys, provider calls, new network paths, runtime
authorization, graph mutations, schema migrations or deployment are created.
See [witness contracts](REFERENCE_CASE_INTAKE.md#independently-enrolled-registration-signatures)
and [validation](VALIDATION.md). This packet still requires manual PR merge and
its exact-head checks; it does not claim deployment or post-merge main qualification.

**Next qualification work:** lawful representative source/case samples, independently
authored source-linked references, measured extraction/review throughput, actual
witnessed pre-execution registration with reliable time/execution evidence, and
representative paired model/reviewer studies. R01/R03–R05/R05A remain partial.

### Delivered packet — R07 engineering: fresh authorization cost, 10 October 2026

PR #39 is verified merged into main at `c2b0b3b1c7df49da171a92316855d1288724bf11`.
Its exact-head run `38050597031` passed, but the backend job took 19m14s against
the existing 20-minute cap. This continuation addresses measured repeated work
before adding another product packet.

Every `require_matter` invocation now executes one prepared, fresh SQL statement
for account state, tenant/matter identity, independent content grants and current
action-role rows. No permission, scope, source validation or trial-currentness
result is cached. Direct and client grants remain independently revocable; errors
retain account/scope/action precedence. The caller's expected firm is pinned before
ORM refresh so a moved account cannot change its own authorization boundary.

Four isolated invented workflows reduced SQL statements from 213,202 to 112,927
(47.0%) with slightly more matter/trial-currentness checks. First-pair elapsed time
was 30.30s before / 25.57s after; this does not establish stable hosted or billing
savings. Twenty-seven new one-statement/current-state regressions cover revocation,
tenant changes, malformed/dangling roles, archived/missing matters and separate
grants. Full backend and real PostgreSQL race coverage remain required. No workflow
events, runners, execution groups, workers, retries, dependencies or time limits
change. See [CI measurement](CI.md#fresh-matter-authorization-cost--10-october-2026)
and [verification](VALIDATION.md).

This engineering packet requires manual PR merge and exact-head hosted checks.
Deployment, representative capacity and R07 operational qualification remain open.
The next product qualification priority remains lawful representative source/case
samples, independent source-linked reference review and measured extraction/review
throughput, followed by actual witnessed registration and paired model/reviewer
studies. R01/R03–R05/R05A legal gates remain partial.

### Delivered packet — R01/R03 registered source preparation, 10 October 2026

PR #40 is verified merged into main at `4eac0341a3ffdf2bb9bbf75ae4f71b80b131bf1d`.
All three post-merge main jobs passed in run `38058176402`. This packet moves from
synthetic intake rehearsals to a repeatable bridge for actual registered originals.

One operator CLI captures exact quarantined public bytes, requires cryptographically
verified fresh ClamAV databases and a clean disconnected scan, then transcribes HTML
in a second disconnected worker. Strict Turkish encodings, original source-code
ranges, exact UTF-8 passages, preserved acquisition provenance and measured individual
scan/parser calls feed the existing curator import/review path. Prepared files use
exclusive atomic publication; source changes, missing controls, worker failures and
unconfirmed cleanup produce no completed package. Application data, credentials,
provider calls, serving graphs and source/legal approvals are outside this operation.

The retained real TBMM 6101 acquisition from 4 October was scanned and prepared into
38 Windows-1254 passages, then verified in a separate public-only host staging catalog.
Neither that catalog nor these review files update the Docker deployment. Today's
registered acquisitions of 6101 and 6098 stopped at the gateway DNS timeout; nothing
was admitted by those attempts. The real sample remains rights/identity/fidelity/
sensitivity/legal review pending and explicitly not current consolidated law. Its
single-call measurements are not representative throughput or reviewer productivity.
See [preparation contract](REGISTERED_SOURCE_PREPARATION.md) and [verification](VALIDATION.md).

This engineering packet requires manual PR merge and exact-head checks. Next work
is approved connected-route restoration, diverse lawful source/case intake,
independent source-linked references and measured curator effort before actual
registered paired studies. R01/R03/R05A legal qualification, target-host capacity
and pilot acceptance remain open. No new CI jobs, retries or deadlines are added.

### Delivered packet — R01/R03 original-source fidelity inspection, 10 October 2026

PR #41 is verified merged into main at `7710ef7f5c3f542be3510dc086491f5bd3a51b12`;
all three post-merge jobs passed in run `38061667300`. The isolated TBMM route now
resolves and a fresh registered 6098 enacted text was acquired without changing
DNS, destinations, TLS checks or network/deadline policy. The earlier timeout's
root cause is not established and continued source availability is not assumed.

The 708,685-byte original passed the existing disconnected scan/preparation and
public-only host import path, producing 2,438 Windows-1254 passages. All recorded
source-code coordinates agree with that exact decoded original. Three selected
windows also pass HTTP inspection in a temporary local demo. Rights, identity,
sensitivity, extraction fidelity and legal applicability remain pending. This is
one contract-domain sample, not representative corpus coverage or current law.

Curators can now open a bounded inert original HTML source window beside an
extracted passage. Exact hashes, Unicode coordinates, shared strict decoding,
separate original-window paging and fresh access checks support accountable
fidelity review. No scripts/resources are executed and opening a window neither
selects a reviewed passage nor records acceptance. Other representations and
unverifiable locators retain the independent original-download path. See the
[inspection contract](SOURCE_REVIEW_CONTRACT.md#original-source-code-inspection)
and [verification](VALIDATION.md).

This packet still requires manual PR merge and exact-head hosted checks; nothing
is deployed or published. Next: qualified curators review the acquired 6098/6101
originals with measured active effort; expand lawful samples beyond this source,
representation and contracts; independently author source-linked references;
then conduct actual registered paired studies. R01/R03/R05A legal qualification,
representative throughput, target-host capacity and pilot gates remain open.

### Delivered packet — R01/R03 accountable curator active effort, 10 October 2026

PR #42 is verified merged into main at `52a3a7cd951fbe52c8b44094a00c1a58feef7916`;
all three post-merge jobs passed in run `38064746653`. Source fidelity inspection
now supports the next gate: collecting actual curator work separately from parser
timings, assignment elapsed time and synthetic study rehearsals.

Curators can record optional active seconds on each source assessment, identifying
their own timer declaration or an estimate. Empty/legacy durations remain unknown;
explicit zero is preserved. Records stay encrypted, firm-confidential and bound
to the same authenticated reviewer, immutable source artifacts and revision.
Totals include all verified assessments, including superseded decisions beyond
the visible history window, with timer declarations, estimates and unknown counts
reported separately. The existing JSON dossier carries the same metadata. No
automatic timer, timestamp-based guess or legal/publication approval is added.

Thirty-two new engineering regressions, a disconnected Linux source/snapshot
suite and a disposable browser workflow check the distinction, integrity,
confidentiality, legacy compatibility and downstream revalidation. Browser
durations are explicitly invented. A separate no-write check of the acquired
6098 package still finds revision 0, no assessments and no actual human effort.
See the [effort contract](SOURCE_REVIEW_CONTRACT.md#active-review-effort) and
[verification](VALIDATION.md). This packet requires manual PR merge and exact-head
hosted checks; it does not change the deployed application or source approvals.

Next: qualified curators review 6098/6101 with actual timer declarations and
adjudicated study records; expand lawful samples beyond TBMM HTML/contracts;
independently author source-linked references; then conduct actual witnessed,
registered paired model/reviewer studies. Timer declarations remain self-reported;
erroneous entries require study adjudication. R01/R03/R05A legal qualification,
representative throughput, target-host capacity and pilot gates remain open.

### Delivered packet — R01/R03 employment and commercial source intake, 11 October 2026

PR #43 is verified merged into main at `bba695c8d5c100253952f4a911794ce8d3cc76aa`.
The closed registry now includes the official TBMM enacted representations of
4857 (employment) and 6103 (commercial-code transition statute), alongside the two
contract entries. Domain labels organize intake; they do not determine applicability
or create legal graph assertions. The registry remains limited to TBMM HTML.

New acquisitions use an immutable v2 registry and a separate fixed Docker staging
image, without rebuilding or retagging the deployed API. The exact v1 contract
snapshot remains available for offline preparation: old manifest bytes and dates
are preserved, missing/unknown versions fail, and new entries cannot claim v1.
Shared strict provenance checks bind title, domain, exact URL, bytes and pending
states; the host rejects a stale acquisition worker before admitting output.

Both new samples were actually acquired within existing limits, scanned against
cryptographically verified official CVD databases and prepared disconnected:
4857 produced 616 passages from 247,132 bytes; 6103 produced 215 from 87,088 bytes.
A separate public-only host catalog and six no-write HTTP inspection windows work.
All passage digests/ranges are consistent with the retained originals; this is
not evidence of legally correct transcription. Rights, identity, fidelity,
sensitivity and legal review remain pending; effect/publication dates are unknown.
No sources, assertions or work products are promoted to a serving release.

See the [operator contract](REGISTERED_SOURCES.md), [verification](VALIDATION.md)
and [engineering receipt](evidence/registered-domain-intake-2026-10-11.json).
This packet requires manual PR merge and exact-head hosted checks. It does not
change the deployed app, provider, private matters or actual curator records.
The inherited main run `38068593529` timed out at the existing 18-minute backend
step limit near 99% completion. Local profiling identified uneven CI ownership;
119 source/model review tests now use existing spare runner capacity. Complete
collection still covers all 3,632 cases exactly once. The workspace group uses two
workers, matching the other groups; event configuration, runner count, retries
and every time limit are unchanged. No validation result/source cache or disabled
test is introduced. Hosted qualification is separate from local timing.

Next: qualified curators review all four acquired originals, recording actual
active effort and adjudicated study evidence; add other lawful source families
and representations; independently author source-linked references; then conduct
witnessed, registered paired model/reviewer studies. Current consolidated law,
jurisprudence coverage, legal qualification, representative throughput,
target-host capacity and pilot acceptance remain open.

### Delivered packet — R01/R03 versioned PDF source preparation, 11 October 2026

PR #44 is verified merged into main at `eea77d9ea5e8316e7f9546876d8d37083281df24`.
The next engineering packet adds one exact Ministry of Justice 6101 PDF route from
its official 2011 legislation index. A frozen v3 registry binds media type, filename,
representation and limitation; both earlier HTML snapshots remain immutable and
available for offline preparation. The PDF is an institution-hosted representation
with unverified version history, distinct from TBMM's copy and from a Gazette original.

After mandatory scanning, an isolated disconnected worker transcribes text-only
PDFs into page passages, exact text offsets and digests. It records the pinned
parser/adapter and preserves unusual glyphs. Unsupported/empty pages, encryption,
interactive/image/form features, unevaluated parsers, over-budget work and altered
page reports fail without a partial package. No OCR, text correction or provision
identity is inferred. Dates, rights, fidelity and legal review remain unknown/pending.

The actual connected attempt failed at the existing DNS deadline and admitted
no original. Synthetic native/Linux regressions and a real CVD scanner/parser
handoff on synthetic bytes verify engineering only; there is no real PDF catalog
entry, legal review, source-linked reference or serving publication. Existing
network/resource/CI limits and the deployed API remain unchanged. See the
[preparation contract](REGISTERED_SOURCE_PREPARATION.md#text-only-pdf) and
[receipt](evidence/registered-pdf-intake-2026-10-11.json). Manual PR merge and exact-head
hosted checks are required.

Next: successfully acquire the registered PDF through the approved bounded route;
have qualified curators compare every original page and assess identity, version,
rights and sensitivity; record the shared-work identity before study selection.
Continue actual review of the four TBMM originals, independently author references
and run witnessed paired studies. Two representations of 6101 are not two independent
study originals. RG/MBS current-law reconstruction, jurisprudence, national legal
qualification, representative throughput, target-host capacity and pilot gates stay open.

### Delivered packet — R01/R03 original PDF inspection and actual sample, 11 October 2026

PR #45 is verified merged into main at `05dd5b29f52f4918c0a4b8629cb6f77094c2f258`.
The curator workspace now offers an original PDF page comparison beside extracted
text. A typed read-only binding checks the complete page map without server-side
PDF parsing. The browser bounds and hashes the authenticated opaque attachment,
requires a dedicated local worker, checks parsed page count and draws only the
selected page with bounded canvas/zoom and cancellation. Existing HTML inspection,
independent download, selection and accountable review remain separate.

The existing fixed Ministry 6101 route also succeeded in one new invocation, without
network-policy, DNS, proxy or deadline changes. Its 218,901 original bytes passed
mandatory signature-verified disconnected scanning and the pinned parser, yielding
two exact page passages. Only a separate host public staging catalog is imported;
actual HTTP readback finds no owner, revision 0 and no assessments. Both retained
original pages were rendered and visually inspected with Poppler; that is not
qualified transcription or legal review. Browser automation was blocked at the
local verification URL, so end-to-end viewer/lifecycle acceptance remains open.

See the [inspection contract](SOURCE_REVIEW_CONTRACT.md#original-pdf-page-inspection),
[verification](VALIDATION.md) and [public engineering receipt](evidence/pdf-original-inspection-2026-10-11.json).
Manual PR merge and exact-head hosted checks are required. The deployed application,
provider, private matters, actual curator records and serving graphs are unchanged.

Next: complete browser acceptance, then qualified curators compare every original
PDF page and the four TBMM originals, recording actual effort and evidence of
identity/version, rights, sensitivity and fidelity. Adjudicate the shared-work
identity of the two 6101 manifestations before independent reference/study selection.
Independently authored references, witnessed paired studies, RG/MBS current-law
reconstruction, jurisprudence, national legal qualification, representative
throughput, target-host capacity and pilot gates remain open.


### Delivered packet — R01/R03 retained representation comparison, 11 October 2026

PR #46 is verified merged into main at `cd813d8e44c3cc84aa258f2d77cda611afb93675`.
Curators can now choose two retained packages, their exact passages and independent
Unicode offsets to inspect bounded literal wording differences. Full original-byte,
full extracted-text and selected-window equality remain separate. No normalization,
provision alignment, identity merge, legal version, current authority or study
independence is inferred. Reproducible unsigned JSON binds both complete artifact
sets and exact windows; download freshly verifies the same digest and permissions.

Both retained 6101 manifestations passed actual local HTTP/browser checks with no
source-review writes. The downloaded record matches the repeatable HTTP receipt.
Changing the selected passage clears the prior result. The previous local browser
block did not occur in this invocation; original PDF pages 1 and 2 now render in
an actual worker and switch cleanly. Normal and expanded comparison layouts were
inspected. This is bounded engineering acceptance, not qualified source fidelity,
shared-work adjudication or target-host/pilot acceptance. Both actual source ledgers
remain unassigned at revision 0 with no assessments.

See [comparison and handoff contract](SOURCE_COMPARISON.md), [verification](VALIDATION.md)
and [receipt](evidence/retained-source-comparison-2026-10-11.json). Manual PR merge
and exact-head hosted checks are required; no deployment, provider, matter, actual
human-review or serving-graph changes occur. CI jobs, complete gates and existing
limits are retained, with all 3,768 backend cases assigned exactly once.

Next: qualified curators use original inspection and retained comparison evidence
to adjudicate the 6101 shared work/version and review all acquired sources, retaining
actual effort and disagreements. Source assessments remain individual dossiers;
this tool grants no cross-source registry or independent-study qualification.
Independently authored references, witnessed paired studies, diverse RG/MBS and
judicial acquisition, reviewed history and national/pilot legal gates remain open.

### Delivered packet — R01/R03 human source relationship review, 11 October 2026

PR #47 is verified merged at `1b33e2da15812b2b53cdc6446d50e60eebf63966`;
exact main run `38124024422` passed all three jobs. The next packet adds an explicit
firm-confidential pair review after source comparison. A curator owning both source
dossiers can preserve unresolved or evidence-backed work/version opinions. Resolved
opinions require accepted identity assessments on both sources, explicit consistent
work/version references and additional supporting material beyond the comparison.

Each encrypted immutable event binds both historical review revisions and original
artifact sets, the exact regenerated comparison, actor, rationale, references and
optional declared effort. Canonical pair ordering and optimistic writes preserve
one history. Changed source reviews project Stale without changing old opinions;
renewal is explicit. No identity merge, transitive grouping, automatic independent
sample count, source permission or graph publication is added. The screen retains
disagreements and freshly exports a confidential, unsigned dossier.

Synthetic native/Linux tests, real PostgreSQL races and the disposable production
browser verify the engineering boundary. Real acquired 6101/TBMM source dossiers,
provider, private matters, serving release and deployed application are unchanged.
See [relationship contract](SOURCE_RELATIONSHIPS.md) and [verification](VALIDATION.md).
All 3,805 backend cases retain complete/disjoint collection in the unchanged CI
partition; runner counts, retries and deadlines are unchanged. Manual merge and
exact-head hosted checks remain distinct from deployment/legal qualification.

Next: qualified curators use the tools to review the actual acquired originals,
adjudicate their work/version relationships and retain real effort/disagreement
evidence. Independently author references and register witnessed paired studies;
continue lawful RG/MBS/judicial acquisition and historical reconstruction. These
human/corpus, national legal, representative throughput and pilot gates remain open.

### Delivered packet — R01/R03 confidential source-selection handoff, 11 October 2026

PR #48 is verified merged at `8bdb05275ff229d5559b696cd4092b8c12efbd94`;
exact main run `38129459620` passed all three jobs. Curators can now inspect two to
six retained packages together before reference/study intake. Every direct pair
has a missing, unresolved, stale or resolved state. Current conflicting work/version
declarations and separate source-assessment gaps remain visible; prior opinions,
classification counts and history fingerprints are retained. No transitive grouping,
identity merge, independent-original count or study qualification is inferred.

Read-only local endpoints freshly verify originals, encrypted source/pair heads,
complete event histories and authorization before returning a reproducible unsigned
firm-confidential snapshot. The browser checks exact receipt bytes and coverage,
clears old results on selection/navigation changes and freshly revalidates each
download. Exact pair links open comparison with both sources preselected while
passage selection remains manual. Work, history and receipt limits withhold partial
output; cooperative deadlines are documented separately from hard cancellation.

The 449-case isolated Linux suite, 376 frontend tests, production build and new
real-PostgreSQL concurrent-change rejection pass. A disposable synthetic browser
demonstrates conflicting/missing opinions, a newly stale download preserving old
opinions, exact navigation and cleared selection. Actual acquired source ledgers,
private matters, provider, serving graphs and deployed application are unchanged.
All 3,833 backend cases remain assigned exactly once in the unchanged CI partition;
no runners, retries or deadlines were added. See the [handoff contract](SOURCE_SELECTION.md),
[verification](VALIDATION.md) and [engineering receipt](evidence/source-selection-handoff-2026-10-11.json).
Manual PR merge and exact-head hosted checks remain required.

Next: qualified curators review the acquired originals and adjudicate shared work
and version, then independently author references and register witnessed paired
studies. The selection dossier assists this review without automatically enrolling
or counting originals. Lawful RG/MBS/judicial acquisition, reviewed historical
reconstruction, national legal qualification, representative throughput and
target-host/pilot gates remain open; R01/R03 are not complete.

### Delivered packet — R03 registered jurisprudence PDF intake, 11 October 2026

PR #49 is verified merged at `dda436732fa9dee4060bd4e17e680bce1eea2974`;
its exact-head hosted checks and all three post-merge main jobs in `38133240697` passed.
The next packet registers one fixed AYM individual-application PDF representation
for 2018/31036, separate from statute text. Immutable registry v4 preserves v1/v2/v3
membership and metadata; older acquisitions never resolve against today's registry.

The existing isolated PDF adapter and host admission retain decision-specific
limitations while preserving exact originals, acquisition manifests and page
locators. Legal effect, finality, opinion roles, personal-data suitability, identity
and rights remain unreviewed; dates remain unknown. No graph identity, authority
treatment, party correlation, current-law approval or retrieval publication is made.
The JavaScript decision-database shell is not an admissible substitute.

The first actual invocation stopped at the unchanged DNS deadline and admitted
nothing. 339 isolated Linux source/acquisition/preparation/import tests pass,
including legacy-v3 provenance preservation, fixed AYM transport, rejection of
reclassification/relocation, scan-first preparation and pending-review import.
See [registered sources](REGISTERED_SOURCES.md), [preparation](REGISTERED_SOURCE_PREPARATION.md)
and [verification](VALIDATION.md). Actual acquisition/fidelity/rights review,
independent references, national corpus and pilot qualification remain open.

Next engineering packet: source-bound decision identifier/date/citation candidates
with exact passage locations and explicit uncertainty. Candidate occurrences must
not become canonical identities, historical provision versions or authority
treatments without independent accountable review. Preserve unknown dates and all
source evidence; continue lawful acquisition and human review alongside this work.

### Delivered packet — R03 evidence-bound jurisprudence occurrences, 11 October 2026

PR #50 is verified merged at `3f819ecd85f1c79332e570be309952cd86f4a841`;
all three exact-head checks passed in `38134025268`. Post-merge main CI is
tracked separately. The dependent packet adds `tr-jurisprudence-occurrences-v1`: literal application,
case and decision numbers, labelled dates and numbered instrument/article mentions
in one retained curator-selected passage. Every occurrence carries exact Unicode
and value spans, source/raw/text/passage hashes, rule/version and stable identity.
Repeated, quoted and conflicting occurrences remain distinct. Separate syntax or
calendar hints never become canonical identities, source dates or legal facts.

Read-only curator API and the existing offline public-source CLI freshly verify
all original artifacts before and after extraction. Authorization is checked before
work and before response. Caller text/URLs, repeated or extra query parameters,
cross-passage matching, global caches, model/network/raw-parser calls, party
correlation and graph/review writes are unavailable. At 20,000 code points, 200
occurrences or 256 KiB evidence, exceeded budgets withhold the entire result.

37 new native regressions and 475 isolated Linux pipeline cases pass, including
registered AYM synthetic transcription/import, preserved unknown dates, exact CRLF/
NBSP/astral spans, conflicting occurrences, invalid calendars, raw corruption,
revocation and resource boundaries. All 3,880 backend cases remain assigned exactly
once in the unchanged CI partitions; no extra runners, retries or deadlines are added.
See [candidate contract](JURISPRUDENCE_CANDIDATES.md), [verification](VALIDATION.md)
and [engineering receipt](evidence/jurisprudence-occurrences-2026-10-11.json).

This packet delivers API/operator inspection, not curator UI, decision segmentation,
canonical decision mapping or a recall/quality benchmark. Next: expose candidates
beside exact original passages and implement firm-private, accountable decision
identity/date/citation review with preserved disagreements and independent release
review. Actual jurisprudence acquisition/fidelity/privacy review, reviewed graph
population, national qualification and pilot gates remain open.


## Delivered R03 packet — curator UI and accountable decision mapping (11 October 2026)

PR #51 is verified merged at `d6a4796e92eef6ee705a07ad4d6cfbb39fd0d98d`.
Its post-merge main run `38136788663` passed all three jobs. The next packet adds a
curator decision-mapping screen and encrypted firm-local review ledger, preserving
exact occurrence evidence, separate proceeding/decision/institution references,
unknown date roles and versions, human accountability and prior disagreements.
Current source-review ownership, dual revision pins, source use scopes and explicitly
reviewed extraction passages gate acceptance. Source-review changes stale acceptances.
No actual source approval, canonical graph identity, publication or deployment is inferred.

The candidate API remains additive and independently bounded. The UI inspects exact
passage text and available original representations, verifies occurrence receipts,
and clears or cancels old views on navigation/access changes. See
[decision mapping contract](DECISION_MAPPING.md) and [validation](VALIDATION.md).

Next packet: complete, revision-bound confidential decision-review dossiers and
handoff consistency checks. Independent legal/privacy/fidelity review of acquired
decisions, Graph B population and national/pilot qualification remain open.

## Delivered R03 packet — confidential decision review dossiers (11 October 2026)

PR #52 is verified merged at `9798987199ef49e49f2c630765bc0a1730bd6a37`;
all three exact-head checks passed in `38138989212`, and all three post-merge main
jobs passed in `38140262894`. The successor packet provides complete, revision-bound
firm-confidential dossiers: source and mapping histories, exact supporting passages,
accountable reviewers and original artifact hashes. Explicit accepted export rights
gate download. Draft evidence remains exportable for review without implying source
qualification; stale, corrupt, incomplete or oversized output is withheld entirely.

Literal identity/date/number conflicts and unresolved mappings block independent
review readiness. These checks neither resolve canonical identities nor prove legal
effect. Browser session scope now includes firm and role even when permissions are
unchanged, clearing private portfolio/source views on transitions. See
[decision mapping contract](DECISION_MAPPING.md), [validation](VALIDATION.md) and
[engineering receipt](evidence/decision-dossier-2026-10-11.json).

Next packet: canonical proceeding/decision/institution identity proposals with
independent review and a staged Graph B handoff. No automatic promotion from the
firm-private ledger. Real source acquisition, fidelity/privacy/legal review,
historical-version resolution, graph qualification and pilot gates remain open.

## Delivered R03 packet — canonical decision identities and independent review (11 October 2026)

PR #53 is verified merged at `e9ff93a87f082a25edc19b6f3ae8c9c7e82b9cca`;
its post-merge main run `38143052204` passed all three jobs. This packet adds
explicit institution/proceeding/decision identities, document-bound decision
versions and a complete encrypted private proposal/opinion ledger. A reviewer
account must be outside the proposer and the entire pinned source/mapping
contributor history. Ownership transfers cannot erase that history. Current
source/mapping changes invalidate identity acceptance; conflicting firm-local
identity reservations cannot silently be reused.

The curator screen exposes exact revision bindings, preserved opinions and stale
state. Separate-account review is not proof of separate people or legal truth;
global registry qualification, legal effect and publication remain false. The
initial contract covers one own decision per source, with explicit evidence;
multi-decision segmentation and cross-source equivalence remain open. See
[identity contract](CANONICAL_DECISIONS.md), [validation](VALIDATION.md) and
[engineering receipt](evidence/canonical-decisions-2026-10-11.json).

Next packet: evidence-backed, revision-bound private Graph B staging. Do not
automatically promote private identities, contributor names or reviewer opinions
to shared datasets. Actual source/legal review and R03/R05 release gates remain open.

## Delivered R03 packet — private staged Graph B handoff (11 October 2026)

PR #54 is verified merged at `c716de71fb5f37aa5d7df7549ea8e839c223f3ec` after
all three exact-head jobs passed in `38150833586`. Its post-merge main run is
tracked separately. This successor provides a deterministic, firm-confidential
handoff with original artifacts, complete review histories, compiler/ontology pins,
physical file hashes and a content-addressed packet ID. The three reified own-decision
identity relations remain unreviewed RDF candidates. Exact retained passage evidence,
current separate-account acceptance, accepted export rights and all three revisions
gate download; unresolved external registers, stale inputs and oversized output are
withheld. Source selection does not become shared graph data.

The curator screen verifies the complete JSON/file/packet hashes and reports private
staging status; the read-only source usage guide explains proposal, independent review
and handoff. Existing publication tooling rejects the intact preparation marker.
No graph mutation, signing, publication, legal-effect assertion or model call occurs.
See [handoff contract](GRAPH_B_HANDOFF.md), [validation](VALIDATION.md) and
[engineering receipt](evidence/graph-b-handoff-2026-10-11.json).

Next: explicit reviewed cross-source decision identity equivalence and external
institutional-register evidence, followed by a decision-specific publication review
contract. These must preserve source versions, private contributors and conflicting
identities. Real legal/editor approvals, ontology qualification, Graph B population,
retrieval evaluation and pilot gates remain open; R03/R05 are partial.
# R03 continuation — reviewed cross-source identities (12 October 2026)

PR #55 is verified merged at `257056245aafd4becf68f88a62e9d763fc69226a`;
post-merge main run `38153461750` passed all three jobs. This packet adds
accountable equivalence proposals/opinions across two independently reviewed decision
sources and a separate retained institutional-register source. Complete pinned
source/mapping/identity contributor histories define reviewer-account independence.
Exact retained evidence from every source, explicit canonical candidate selection,
preserved disagreement and staleness checks gate the private review. Existing
reservations and document versions remain unchanged; no national alias, competence,
legal effect, historical validity or graph publication is qualified.

See [contract](DECISION_EQUIVALENCE.md). Next packet: a complete, revision-bound
multi-source Graph B preparation handoff with the reviewed anchor and retained
register passages. Decision-specific publication review, signed legal/ontology
approval, national institutional genealogy, retrieval qualification and pilot gates
remain open. R03/R05 remain partial.

## R03 continuation — reviewed equivalence Graph B handoff (12 October 2026)

The private reviewed equivalence now nominates an explicit anchor for a
[three-source staged Graph B packet](EQUIVALENCE_GRAPH_B_HANDOFF.md). Original
identity reservations, two decision versions, institutional-register passages and
all review histories remain distinct and hash-bound. Six reified relationships
are unreviewed candidates with unknown legal validity; intact preparation RDF
cannot enter current publication tooling. No global or transitive equivalence,
competence inference, graph activation or user deployment is implied.

Next: the decision-specific multi-source publication review contract, independent
legal-editor and institutional/temporal qualification, exact candidate signatures,
withheld disagreements and activation/rollback validation. Actual legal-source
acquisition, licensed corpus coverage, reviewer qualification and legal/pilot
acceptance remain external requirements.

## R03 continuation — independently signed Graph B review (12 October 2026)

Built on verified PR #58 merge `b3b467744726ab783e5599bc2d0ee01cc8b7c15f`;
its main run `38198597168` passed all three jobs. A separate vetted reviewer public
key now verifies an externally signed, complete private review bound to three
sources, accepted equivalence, ontology, independent active reviewer and retained
appointment evidence. Institutional-register identity must cover the explicit
decision date; all six relationship intervals are assessed separately. Unknown
ranges remain unknown. Later rejection and stale trust/source/roles withhold approval.
The curator screen displays full history and the unpublished scope.

See [signed review contract](SIGNED_GRAPH_B_REVIEW.md). Next: deterministic public
Graph B signing inputs containing only reviewed public evidence and individually
qualified relationship intervals. Public attestation, decision-specific audience
authorization and activation/rollback qualification remain separate gates. Actual
legal-editor vetting, national genealogy, corpus coverage and legal/pilot approval
remain open; R03/R05 remain partial.

## R03 continuation — qualified Graph B signing inputs (12 October 2026)

PR #59 is verified merged at `260554131c2fb518eb935bea02a4615c82e0e158` after
all three exact-head checks passed in `38205716348`; its backend step completed in
16m06s within the existing cap. Main deployment/CI remain separately tracked.
Current externally signed private approval now gates a deterministic
[public signing-input slice](QUALIFIED_GRAPH_B_SIGNING_INPUTS.md), with six exact
identity relationships, independent temporal evidence, preserved decision versions
and physical quote/locator validation. Private appointment/account/history data
stay outside public inputs. The curator verifies and downloads the complete private
wrapper. Signed negative opinions can retain unknown dates/register windows;
positive approval cannot, and an older approval cannot bypass a later rejection.

Next: decision-specific bounded source/audience authorization, revocation/restore
invalidation, complete final-release assembly, activation/rollback and runtime
historical retrieval qualification. No production signatures, actual legal-editor
vetting, national ontology approval, legal-effect assertion, public graph write or
user deployment is supplied by these engineering fixtures. R03/R05 remain partial.

### R03 — current local Graph B publication snapshots (2026-10-12)

Implemented a transport-independent read-only reconstruction of signed decision, institutional-identity and temporal review for trusted local publication workflows. Exact current revisions, complete histories, original bytes, separately configured review trust, reviewer appointment, same-firm active accounts, all six source-use rights and ownership remain conjunctive. Shared PostgreSQL reads and exclusive preparation protect all source/identity/review heads and relevant reservations; final reconstruction withholds changed or caller-mutated output. This is preparation infrastructure, not audience authorization or public serving. The successor is a decision-specific signed publication grant and complete-corpus assembly qualification.

### R03 — encrypted Graph B preparation and source-specific inclusion requests (2026-10-12)

Implemented trusted local `prepare`, `validate` and `request` commands. Exact private signed-review bindings, credential and audience evidence are encrypted; public signing input bytes stay separate. An unsigned inclusion request binds a separately attested public component, all three source-specific deployment audience permissions, current source/review identities, appointment-limited expiry and restore epoch. Late changes or atomic-output interruption withhold new artifacts. It cannot authorize national serving or install the empty-Graph-A identity slice. The successor is signed component-grant acceptance and complete reviewed Graph A/Graph B assembly with live conjunctive guards for activation/rollback/read.

CI retains the same three jobs, two-worker test groups, retries and deadlines. Signed snapshot and new publication tests use spare capacity in the existing human-review group; existing review/signing-input cases stay on backend. Isolated TEST-ONLY fixture copies revalidate live state and never cache verdicts; exact collection establishes disjoint complete coverage instead of running either file twice or extending the backend cap.


### R03 — signed Graph B component inclusion grants (2026-10-12)

Implemented trusted local encrypted signing requests, external signature acceptance and live inclusion validation. The closed grant namespace uses a third independently configured public key, exact public component and private preparation digests, all three source-specific audience permissions, current review/equivalence/identity pins, appointment-limited expiry and restore epoch. Source/account/review locks cover bounded work; late changes withhold output and later negative reviews invalidate the next use. Serving actions are explicitly denied. [Operator contract](GRAPH_B_COMPONENT_GRANTS.md).

The PostgreSQL decision fixtures now build only their required sources; ordinary SQLite contracts copy the same invented empty baseline into independent case storage, then run actual startup, fresh authentication and current checks. Fresh setup builders and all real PostgreSQL race subjects remain active. CI retains three jobs, two workers per partition, the same deadlines and no retries or omitted tests. Hosted timing must be assessed from exact-head checks, not inferred from local measurements.

The successor is complete reviewed Graph A/Graph B assembly preserving every selected component and manifestation, independent public review of final assembled bytes, and conjunctive current serving authorization. Actual legal/editor vetting, corpus/institution history, production key custody, deployment and held-out pilot gates remain open. R03/R05 remain partial.


R03 CI follow-through: the first signed-component PR reached the backend step limit. Repeated initial analysis and unsigned review setup is now shared only as independent TEST-ONLY bytes, with new application/authentication contexts and complete per-case validation; accepted review/analysis verdicts are not reused. The exact-head hosted gate remains mandatory before merge. No job, worker, timeout, retry or test-coverage budget was expanded.

CI capacity follow-through: two PR63 backend runs hit the unchanged 18-minute step cap at 93%, without an assertion failure before cancellation. Peer test clients now reuse their own case’s running ASGI portal with independent logins/cookies/CSRF; real application lifespan, requests and authorization checks remain active. Passed-case scratch cleanup and bounded exec-enabled file-backed RAM storage address temporary-file latency without changing SQLite locking, jobs, workers, retries or deadlines. The final disconnected Linux backend partition passed 3,685 cases with 85 environment skips in 425.01s; all 4,182 collected cases remain disjointly assigned. Hosted runtime and billing improvement remain unestablished until the revised exact-head run finishes.

PR63’s next hosted run passed PostgreSQL, and all frontend/Python review tests passed, but final frontend reporting exceeded the five-minute job budget. All Python partitions now use the same bounded test-storage wrapper; actual Linux mount/unmount, independent authentication, source races, executable relay tests and nonzero pytest status preservation are checked. Existing three-job, two-worker and deadline budgets remain unchanged.

The same hosted head’s backend step passed in 14m45s and the PostgreSQL job passed in 4m26s. This supplies a successful hosted backend measurement after the earlier 18-minute timeouts; it does not supply a green whole workflow because frontend exceeded its cap. The shared-wrapper head still requires all three independent exact-head successes.

### R03 — one-transaction mixed Graph A/B preparation (2026-10-13)

PR #63 merged at `7f5ef8fd0d39fdf96b5f5d837fce9564ef0d5d72` after all three exact-head checks passed in `38297324243`; the tested head and main trees are identical. Backend completed its full partition in the 16m15s step window; frontend and PostgreSQL jobs passed in 4m51s and 4m39s. This is merge/CI evidence, not deployment or legal qualification.

The next prerequisite captures every selected structural source and signed decision-review context under one no-write transaction and a globally ordered account/source/context/reservation lock plan. Existing current-source, ownership, rights, identity, independent-review and appointment checks remain authoritative; both compiler contracts and unknown values are preserved. Multiple decision contexts may share a register. Later-member revocation, changed source/key/account state, caller mutation and aggregate limits withhold the entire result. No component grant, complete-corpus claim, graph assembly or serving permission is implied. [Contract](MIXED_GRAPH_SNAPSHOTS.md).

Real PostgreSQL qualification exercises five mixed readers with reversed selections, two independently signed contexts, shared institutional evidence and blocked writers in both source families. Fresh case-local peer transports retain separate authentication and actual handlers. The 36-second runtime authorization subject returns to the backend partition to protect frontend's five-minute margin; three jobs, two workers, retries, deadlines and all subjects remain unchanged. Exact-head checks remain mandatory before this prerequisite is merged.

Next: a deterministic declared complete Graph A/B assembly retaining the exact base inventory and every selected public component, current conjunctive audience/component grants, independent final attestation and separately qualified full-release serving authorization. Actual legal/editor review, national historical population, key custody, deployment and held-out pilot gates remain open. R03/R05 remain partial.

### R03 — complete declared A/B assembly and independent final attestation (2026-10-13)

PR #64 merged at `753a1925009c805ef17a4cfce16928ca9127fc56` with tested/main tree equality. All three exact-head checks passed in `38300946236`; main run `38302856405` also passed. The full backend step took 12m09s, frontend 3m27s and PostgreSQL 3m22s, within unchanged deadlines. This does not establish deployment or legal qualification.

The [declared assembly contract](DECLARED_GRAPH_ASSEMBLY.md) reconstructs the approved structural source set and every selected signed B component in one transaction. It preserves the complete active structural base and exact file inventory, every manifestation, unknown date/effect and all original evidence; duplicate/omitted components and conflicting identity definitions withhold the result. Cross-component SHACL, temporal and physical quote checks run on the union. Component membership is encoded inside the final graph hashes. A fourth, separately configured final-review key verifies externally supplied approval of the exact combined bytes; component signatures are insufficient. Private selection/grant metadata remains encrypted and all commands deny serving authority.

Qualification includes independent test copies with freshly checked permissions, original API-based setup, multiple reviewed contexts sharing a register, late changes/interruption, and real five-reader PostgreSQL locks across both families. Completeness applies to the declared corpus, not every national historical record. This packet accepts an empty initialized base or the entire retained structural source-set base; successive mixed bases require the full-release contract. R03/R05 remain partial.

Next: separately signed final-release audience authorization, conjunctive install/activation/rollback/runtime-read guards, retained mixed-base dependency reconstruction and atomic transition qualification. Actual legal/editor review, corpus population, production key custody, deployment and held-out pilot acceptance remain open.

Assembly CI follow-through: the first PostgreSQL run exposed redundant per-operation RDF validation before the five-reader barrier. Each operation now captures complete public bytes bound to freshly verified manifests; the union compiles those bytes, and all files/keys/permissions/base/source histories are checked again before return. No public validation or authorization verdict is shared across operations. Captured Turtle, N-Quads and manifest mutation tests remain mandatory; job, worker, retry and timeout budgets remain unchanged.

Full-suite executor qualification: the complete backend partition passed on bounded disconnected Linux ARM (3,732 passed, 87 environment skips, 522.76s), while the x86 hosted step timed out at 82% without a reported assertion failure. Backend CI therefore qualifies the standard pinned Ubuntu ARM runner; real PostgreSQL and frontend remain x86. Passive per-file phase timings expose any next bottleneck before timeout. No test, worker, job, retry or deadline budget is relaxed; hosted performance and the whole-workflow exact-head gate remain separate evidence.

Fixture-cost follow-through: the first ARM run reached 99% at the unchanged cap. Per-file phase timings identified repeated complete guard runs in copied fixture setup, before each actual test action. These redundant warm-ups are removed; independent bytes, real startup/login, public signature checks, fresh builders, positive source/permission subjects and isolation regressions remain. The 123 affected contracts passed locally; every production check and all 4,230 CI subjects remain in force.

### R03 — final serving candidates and bounded permission requests (2026-10-13)

PR #65 merged at `78d8c8cab429d94d46d5fa43cf33591d7d9687da` after all three exact-head checks passed in `38348633921`; tested and main trees are identical. The full backend step completed in 16m53s within the unchanged 18-minute cap. Main run `38350855100` remains a separate observation; neither merge nor fixture signatures establish deployment/legal qualification.

[Final candidate tooling](FINAL_GRAPH_CANDIDATES.md) constructs canonical serving artifacts from a current independently attested complete declared assembly. Every original A/B source and component permission remains conjunctive through staging. An encrypted unsigned whole-release request binds exact release/serving/ontology/review/packet/inventory/dependency hashes, every component, restore epoch, audience, six uses and a lifetime bounded by the shortest current component grant. A separately vetted fifth public key identifies the future permission signer; no key/signature/grant is generated or accepted. Invalid inputs fail before expensive construction, and changed sources/files/keys/epoch or atomic-output failures withhold the new artifact.

Next: acceptance of an externally signed whole-release permission and current install/activation/rollback/runtime-read guards, with explicit treatment of reviewed immutable base dependencies versus active-pointer transitions and later mixed-base inventories. Current candidates remain unpublished and unauthorized for serving. Actual legal/editor approval, national historical population, production key custody, deployment and held-out lawyer acceptance remain open; R03/R05 are partial.

### R03 whole-release serving permission — 13 October 2026

The [signed whole-release contract](WHOLE_RELEASE_AUTHORIZATION.md) introduces a
closed fifth-key authorization namespace, encrypted retained permission, explicit
final attestation-role selection and conjunctive current guards for install,
activation, rollback and runtime reads. The reviewed immutable structural base
remains a dependency after a valid pointer change; transitions require the real
publication lock, current rights and exact monotonic CAS. Unknown post-commit
failures require inspection and cannot authorize a replay. All original source,
identity, review, appointment and component-grant dependencies stay mandatory.

Engineering validation uses invented corpora and TEST-ONLY signatures, with real
PostgreSQL concurrency checks. Completion/merge evidence will be recorded after
exact-head CI succeeds. It does not approve production signatures, sources,
legal coverage, activation, deployment or field acceptance. The successor is
read-only whole-release transition reconciliation, followed by complete retained
mixed-base reassembly with no dropped manifestation or dependency.

### R03 read-only transition reconciliation

The operator [inspection contract](WHOLE_RELEASE_AUTHORIZATION.md#read-only-uncertain-transition-observation)
separates observed installation/pointer effects from present source permission
and proof of a particular command's commit. It uses existing locks, exact expected
before/after states, full public validation and the conjunctive current grant,
with explicit no-retry/no-repair receipts. Shared API/publisher Compose paths now
preserve the signed publication location without automatic packet rebinding.
Previous namespaces require renewed independent review rather than migration of
an approval. Complete reassembly onto a retained mixed base is the next gated
packet; source/legal qualification and production activation remain external.

### R03 complete retained mixed-base assembly

[Retained assembly](RETAINED_MIXED_ASSEMBLY.md) preserves the complete installed
mixed base, all public manifestations, original source preparations, component
grants and earlier whole-release permissions. Successors may add structural
source sets and decision contexts without dropping earlier dependencies. One
globally ordered original-source transaction reconstructs every earlier assembly;
fresh independent final attestation and whole permission bind the new inventory.
Frozen base inventories remain distinct from live CAS transitions. Explicit
depth, source, component, file and byte limits withhold oversized assemblies.

Qualification covers successive additions, shared registers, whole-byte
preservation, rollback, original-source withdrawal, changed artifacts/trust and
real PostgreSQL concurrency. CI groups remain disjoint under existing job caps,
two workers and no automatic retries. Exact-head checks and verified main trees
are required before merge; synthetic evidence confers no legal or deployment
approval. R03/R05 remain partial.

Next: read-only retained-dependency reconciliation, with private provenance and
explicit current-versus-recorded state, followed by independently qualified
corpus/retrieval integration. Licensed historical population, actual legal/editor
review, production key custody, activation and held-out lawyer acceptance remain
external gates.

Retained-assembly CI qualification: measured withdrawal reconstruction exceeded
the frontend job's existing five-minute cap. The complete eight-case withdrawal
group now runs once in a separate three-minute ARM job; all existing job caps,
two-worker limits and no-retry policy stay unchanged. The final-release and
PostgreSQL groups passed on the first head. Every exact-head check, including the
new disjoint withdrawal job, must pass before merge.

PR #69 merged at `8df632b3d790f4d502e0b2d0f52ff8f11eead740` after all five
exact-head checks passed for `1f4a3da27f83b35f72c7c0abf67ad8b4767aa6cc` in run
`38391251818`. Tested and main trees match. Post-main checks, production
deployment, real legal approval and held-out lawyer acceptance are separate.

### R03 read-only retained dependency observation

[Dependency inspection](RETAINED_DEPENDENCY_INSPECTION.md) binds a private
recorded-inventory receipt to the exact installed public bytes, original final
review packet and whole-release signature. Present permission is qualified
separately through the complete original-source guard. An installed inactive
target or a still-valid historical signature does not authorize serving; rights
withdrawal remains visible as withheld current permission. Changed/corrupt
provenance, configuration or pointer withholds the observation. No state is
initialized, repaired, published, or audited by this read-only operation.

The combined fifteen-case inspection/withdrawal group passed in an isolated
read-only, disconnected two-CPU container in 55.35 seconds. All 4,284 backend
subjects remain assigned exactly once across unchanged existing job caps, the
three-minute withdrawal/inspection job, two workers and no automatic retries.
Hosted exact-head qualification remains mandatory before merge. Fixture
signatures and engineering receipts do not confer legal or deployment approval.

Next: source-qualified corpus/retrieval integration using the guarded complete
release and explicit evidence/coverage boundaries. Licensed historical source
population, independent legal/editor review, production key custody and actual
lawyer evaluation remain open; R03/R05 stay partial.

Main qualification after PR #69 observed all 3,750 applicable backend tests
passing, with 87 PostgreSQL cases covered in their separate jobs, but the backend
step took 18m11s and exceeded its unchanged eighteen-minute cap. The measured
final-candidate contract group now runs exactly once in a separate three-minute
ARM job. All original subjects, job deadlines and worker/retry limits are
preserved; the six exact-head checks are required before the next merge. This
adds qualification headroom without interpreting a timed-out run as success.

### R03 source-qualified corpus retrieval

[Independent source retrieval](SOURCE_QUALIFIED_CORPUS_RETRIEVAL.md) searches the
exact public evidence in the guarded complete release. Missing graph paths or
unknown assertion dates cannot exclude source passages. Quotes retain physical
source, representation, locator, offsets and hashes; exact identifiers never
resolve by similarity. Unknown applicability, finality and authority treatment
remain unknown. Corpus scope and scan/result limits are explicit, with no assumed
national denominator.

One current source guard covers the bounded local operation, including every
retained source and grant. Workspace membership is checked before discovery and
before response; private queries/selections are neither shared nor cached.
Qualification includes actual signed bytes, current source withdrawal and the
retained mixed-release pipeline, plus bounded partial scans and membership loss.
Synthetic tests do not grant legal qualification or production activation.

Next: retain independent source nominations alongside authority candidates in
private research output and exports, preserving grounded quotation-only output,
coverage gaps and dependency revalidation. R03/R05 remain partial; licensed
population and independent lawyer acceptance remain open.

### R03 private research source nominations

[Saved source nominations](PRIVATE_RESEARCH_SOURCE_NOMINATIONS.md) connect the
independent source corpus to encrypted matter research, a separate inspection
panel and guarded DOCX/PDF exports. Original source identities, quote hashes and
coverage limits remain explicit. Reuse re-projects every saved quote against the
signed source inside the current whole-release guard; a zero-hit capture still
requires its exact release pin.

Lost permission or changed evidence projects stale state and withholds public
passages and graph paths while preserving the stored version and authorized
private evidence. A committed research job does not imply completed publication
authorization; the independent guard-exit callback remains required. Public
nominations stay outside private-document model prompts and legal conclusions.

Qualification covers actual signed research persistence/export and withdrawal,
saved identity/hash/uncertainty corruption, missing and mismatched pins, inert UI
quotes and complete disjoint CI assignment. Source availability does not clear
the legal-corpus gap. No production activation or legal approval is granted.

Next: typed exact evidence lookup and reproducible independent-source versus
graph-assisted discovery comparison, preserving adverse and unresolved authority
states and corpus limits. R03/R05 and real lawyer acceptance remain partial.

### R03 exact source evidence and discovery comparison

[Direct evidence lookup and comparison](EXACT_SOURCE_EVIDENCE_AND_DISCOVERY.md)
add a typed exact-identity route independent of lexical scan order, with expected
release/version pins, unknown legal effects, protected workspace reads and whole
quote budgets. Every retained source/grant remains a current dependency.

The development comparison captures independent source, ordinary authority and
graph-grounded discovery on the same snapshot and index receipt. Passage and
candidate-entity relevance have separate coverage/gold sets; source matches do
not resolve authorities. All planned cells remain visible, and unknown coverage
is unmeasured. Changed evidence or authorization discards a capture. Offline
scoring and hashes do not authenticate reviewer labels or qualify production.

Qualification includes exact lookup without enumeration, private/wrong-version
refusal, signed source and retained-grant withdrawal, source/graph evidence
corruption, frozen receipt checks, complete cell accounting and legacy benchmark
compatibility. CI subjects remain disjoint under existing deadlines, two workers
and no retries. Real population and held-out lawyer judgment remain open.

Next: accountable source nomination review linked to private analysis targets and
expanded independent development strata. R03/R05 remain partial.

CI qualification observed 84 PostgreSQL races passing in 208.36 seconds and 128
publication subjects passing in 72.25 seconds, but setup exceeded their shared
five-minute cap. Publication now runs exactly once in a separate three-minute
ARM job. All prior deadlines, two-worker/no-retry limits and complete subject
assignment remain unchanged. Seven exact-head checks are required before merge;
a cancelled job is not treated as successful qualification.

### R03/R05A private source-to-analysis independent review

[The source-review API](PRIVATE_SOURCE_ANALYSIS_REVIEW.md) freezes exact retained
passage/representation/quote/release identities against specific private analysis
targets. A different authorized lawyer records complete explained observations
and their own relationship interpretation without rewriting the nominator's
declaration, analysis or prior decisions. Support/adverse/distinction/unknown
remain matter annotations rather than public authority assertions.

Source and private basis checks bracket each operation. Existing authority-bound
drafts retain their dependencies without nesting their guards inside the new
source guard. Pending post-commit admissions remain withheld; changed evidence,
reviewer permissions or policies hide quotes and notes and block export.
Actual signed-source/private-ledger withdrawal and a real PostgreSQL competing
review race supplement the invented-document fixtures. All seven exact-head CI
checks remain mandatory; existing caps, workers and test partition coverage stay.

Next: a lawyer-facing source nomination and independent-review panel using these
typed contracts. Independent legal gold, historical/practice strata and measured
preparation benefits remain separate. R03/R05 and real lawyer acceptance remain
partial; this implementation grants no legal or production qualification.

### R03/R05A lawyer-facing source selection and independent review

[The source-review panel](SOURCE_REVIEW_PANEL.md) now connects saved research
passages to exact private analysis targets with a preview/freeze workflow,
explicit independent observations, separate interpretations, immutable histories
and guarded JSON/DOCX/PDF exports. It stays in the current analysis workspace,
with source evidence beside each action and technical records in disclosures.

Client checks verify exact UTF-8 quote hashes, offsets, source/representation and
release identities. Scope retirement and abort signals prevent delayed replies
or downloads from reappearing after a change. Source/private/permission failures
clear quotes, notes and forms. Unknown save outcomes retain the same payload and
nonce for explicit retry; pending receipts never become reviewed work.

Synthetic browser checks include preview invalidation, same-author denial,
independent adverse interpretation, withdrawal, exact exports, narrow layout and
manual recovery without automatic replay. Actual signed private-ledger and
PostgreSQL race tests supplement these interface checks. No CI cap, worker count,
test partition, provider credential or production activation is changed.

Next: explicit source-context renewal and version comparison while retaining
all original history, source dependencies and independent decisions. Real legal
gold, corpus coverage and preparation-time benefit remain unqualified; R03/R05
remain partial.

### R03/R05A explicit source-context renewal and version comparison

[Source-context renewal](SOURCE_CONTEXT_RENEWAL.md) creates a new immutable
private nomination from freshly inspected research and the current analysis.
It retains the exact parent manifest/review head, requires declarations for
every previous/new passage and compares representation/quote identities,
Unicode offsets and exact target hashes. Same-named targets with changed content
remain different. Old quotes and notes are withheld from metadata; their
original guarded detail route remains authoritative.

Retained passages require their original whole-release guard, sequentially with
the new guard. Explicit replacement does not revive old permissions or remove
the original record's dependencies. New work starts unreviewed and requires
a fresh independent source decision plus an explained map assessment bound to
the comparison SHA-256. Parent-head changes invalidate captured replacement
work; old decisions remain immutable. Post-commit failures stay pending without
automatic replay or historical finalization.

Engineering evidence includes actual signed-source/private-ledger renewal and
withdrawal, a real PostgreSQL parent-review/renewal race and wide/narrow browser
rehearsal. Source-review cases share the existing publication CI job; all seven
checks, deadlines, two workers and no-retry policy remain. Legal evaluation,
national coverage, productivity and deployment remain separate; R03/R05 partial.

Next: authorized source-review readiness and a prioritized re-review queue,
explaining dependency changes without silently rewriting reviewed work.

### R03/R05A authorized source-review observations and prioritized queue

[Source-review readiness observations](SOURCE_REVIEW_READINESS.md) provide a
bounded queue for the current authorized analysis. Recorded decisions remain
historical; current private-version/research/review/admission/renewal-parent changes
are separate observations. Public sources remain explicitly unchecked until an
original guarded inspection. No state grants legal readiness or export permission.

Date filters use source-record creation days in Türkiye. Priorities and counts
cover only the scanned window; remaining pages, unknown total coverage and budget
limits stay explicit. Listing runs no public graph validation per row and changes
no records, assignments, permissions or old decisions. Scope/role checks precede
queries and decryption; private joins do not read foreign payloads. Matter/firm
guards serialize sanctioned edits and access changes. Client failures retire late
replies and clear protected buffers. Existing independent review and renewal
choices remain blank and explicit.

Engineering qualification includes private changes, historical positives under
source withdrawal, pending/missing admissions, foreign routing, date and budget
bounds, real PostgreSQL review/version races, and wide/narrow browser rehearsal.
All seven CI jobs, two workers, deadlines and no-retry behavior remain. Legal
acceptance, national corpus coverage, productivity and deployment remain separate;
R03/R05 are partial.

Next: a bounded authorized portfolio source-review queue with customer/date
selection and explicit per-matter coverage, preserving the same fresh guarded
inspection and independent-review boundaries.

### R03/R05A portfolio source-review queue and customer/date filters

[The portfolio source-review queue](PORTFOLIO_SOURCE_REVIEW_QUEUE.md) extends
analysis-level metadata observations to the lawyer's currently authorized active
matters. A separate view under İşlerim applies OR customer matching, existing
workspace created/updated/relevant dates and separately named source-record dates.
Content grants and action permissions precede routing, joins, counts and decryption;
customer selection, ownership, hierarchy and tags never infer new grants.

Candidate windows and private observation work are bounded. Matter locks are
ordered consistently; an intervening inventory change returns no partial results.
Priorities/counts apply only to the current window, and empty/truncated/budget
windows do not imply portfolio completion. Historical decisions remain immutable;
public sources stay unchecked until their original guarded inspection. No review,
admission, assignment, source grant, graph assertion or retained work is rewritten.

The client verifies exact filters, clears changed scopes, retires delayed replies
and provides authorized matter-workbench links with identity references. Qualification
covers mixed scopes/customer grants, date axes, unknowns, opposite PostgreSQL
windows, changed-inventory races, signed withdrawal and wide/narrow navigation.
All seven CI checks, two workers, resource/time limits and complete exclusive
partition remain. Legal acceptance, national corpus, productivity and deployment
remain separate; R03/R05 are partial.

### R03/R05A exact-context navigation and guarded source-review handoff

[Exact context navigation](EXACT_SOURCE_CONTEXT_NAVIGATION.md) carries the selected
matter, analysis and immutable source-context identity from the portfolio queue.
A direct, access-checked metadata lookup avoids list-page dependence and rich
workspace loading. Frozen/current versions, stored review state, integrity and
admission state remain distinct from source authorization and legal readiness.
Pending admissions are never completed by navigation; unavailable relationships
remain unknown. Public-source verification stays unchecked.

Explicit tools remain pinned to the selected context/hash/version and preserve all
original evidence, private-basis, independent actor, review-head and mutation guards.
Renewal creates a separately navigable context requiring fresh independent review;
historical decisions remain immutable. Malformed/mixed selection closes the view;
changed target, filters, actor or refresh retire replies, downloads and protected
forms. The handoff assistant is a product guide without content reads or inference.

Qualification covers records beyond initial pages, corrupt/pending admission,
foreign/private boundaries, exact historical states, real PostgreSQL review-lock
serialization, actual signed withdrawal and browser races/review/history/narrow
layout. All seven hosted jobs, two workers, existing caps and the exclusive full
suite partition remain. Legal qualification, national coverage, productivity,
deployment and user acceptance remain separate; R03/R05 remain partial.

### R03/R05A exact historical-review navigation and metadata-only lineage

[Exact historical-review navigation](EXACT_HISTORICAL_REVIEW_LINEAGE.md) carries one
immutable private review event alongside its exact matter/analysis/source context.
Direct scoped lookup works beyond initial history pages and distinguishes selected
event, independently observed head, exact hashes/versions and admission status.

The metadata-only chain is bounded to ten records. Verified sequence/predecessor
links preserve recorded causal order; unknown dates, pending/corrupt admissions,
broken links and cycles stay explicit. Truncation and a continuation pointer do
not imply complete history. A different current head does not establish ancestry;
head reachability stays unchecked. Metadata reads neither source passages nor notes,
and performs no source authorization, inference, admission repair or mutation.

Explicit historical inspection pins the selected event hash plus the frozen
context/version under original source, retained-grant, private-basis, reviewer and
post-operation guards. Current export/new-review work starts from a fresh context
view; old decisions and nonces are never inherited. Typed history/head/continuation
links and changed-scope retirement preserve confidentiality and immutable history.
The assistant stays guide-only, with the existing three-panel layout retained.

Qualification includes non-latest and opposing decisions, bounded/broken/cyclic
history, pending admissions, content/actor changes, actual PostgreSQL head-update
serialization, signed-source withdrawal and browser navigation/races/narrow layout.
All seven jobs, two workers, existing caps and the exclusive full suite partition
remain. National coverage, legal accuracy, productivity, deployment and lawyer
acceptance remain separate; R03/R05 are partial.

### R03/R05A guarded portfolio source-review queue return

[Guarded portfolio return](GUARDED_PORTFOLIO_SOURCE_RETURN.md) carries exact bounded
customer OR, workspace date, source-record date and bucket intent through selected
context and historical-event navigation. A session-only bounded token book preserves
opaque identities and frozen evidence hashes without retaining source bodies,
review notes, customer names or prior results. Expiry, reload, principal changes and
mixed/duplicate routes close the handoff rather than guess a broader destination.

Return arrival shows captured intent. Explicit preparation restores portfolio
filters, and explicit fresh observation requests a bounded authorized queue window.
Only a selected context occurring in the window triggers a separate exact metadata
read. Frozen context/version/hash and current head identity/state must agree across
both observations; mismatch or failed access drops all partial results. These reads
are not an atomic snapshot or present source authorization. Missing targets remain
unobserved within the window, without automatic scans or deletion/coverage claims.

The original historical event stays distinct from the observed head/current version;
source, retained-grant, private-basis and independent-review guards remain in force.
Changed filters, refresh, actor/session, navigation and expiry retire delayed replies
and protected buffers. The assistant is guide-only; history and public graphs are
unchanged. All seven jobs, two workers, existing caps and exclusive full test
partition remain. Legal/corpus qualification, productivity, deployment and lawyer
acceptance stay separate; R03/R05 remain partial.

### R03/R05A selected-versus-current portfolio return comparison

[Return identity comparison](PORTFOLIO_RETURN_COMPARISON.md) shows separately timed
original and fresh review-head/current-version identities, alongside the unchanged
frozen evidence and selected historical event. The closed session-only intent now
retains the original head declaration and first version-observation time; follow-up
navigation cannot silently rebase these observations. Unknown values stay unknown.

Same/different identities are not legal effects, ancestry, current source permission
or independent approval. Frozen-versus-current version and selected-versus-head
relations remain separate. Explicit typed head/event/context follow-up retains the
exact customer/workspace/source-date filters and bounded intent token, requires
fresh matter authorization, and verifies frozen version/manifest and captured
selected-event hashes before tools. Mismatches, pending/unavailable states and
bounded-window omissions never promote readiness or inherit review decisions.

Qualification covers baseline preservation, same/changed/unknown identities,
pending/unavailable metadata, actual invented-record review/version append through
authorized APIs, pinned follow-up, source withdrawal, real PostgreSQL races,
late scope/session retirement and narrow layout. All seven jobs, two workers,
existing caps and complete exclusive partition remain. National/legal coverage,
professional independence, productivity, deployment and lawyer acceptance stay
separate; R03/R05 remain partial.

### R03/R05A guarded comparison-to-renewal handoff

[Comparison-to-renewal preparation](COMPARISON_RENEWAL_HANDOFF.md) captures a
bounded, session-only target attachment from a fresh portfolio comparison. Explicit
entry restores exact customer/workspace/source-date/bucket filters. Separate
before/renewal/after metadata observations pin the original frozen context and
captured target version/head/admission before opening renewal-only tools.

Research, passage inspection, mapping, preview and freeze stay explicit, with
target checks before/after protected operations and all original server guards.
Confirmed receipts bind a distinct successor version/hash; fresh authorized
successor navigation creates new comparison baselines with the same filters.
Original history and approval are never copied. Pending receipts permit separate
identity observation only, without write replay, inherited permission, admission
repair or a claim of verified parent lineage. Changed filters, target, rights,
session and expiry clear protected forms and retire delayed replies.

Qualification covers 694 frontend cases/build, 243 focused source cases, 263
publication cases, nine PostgreSQL races, actual signed-runtime withdrawal,
deployment contracts and invented-record browser renewal/new independent review,
post-commit pending result, drift, scope retirement and narrow layout. All seven
jobs, two workers, existing caps and the exclusive full backend partition remain.
Legal/corpus qualification, professional independence, productivity, deployment and
lawyer acceptance remain separate; R03/R05 stay partial.

### R03/R05A read-only renewal reconciliation and verified successor lineage

[Renewal reconciliation](RENEWAL_RECONCILIATION_LINEAGE.md) retains only a bounded,
actor-bound nonce/hash receipt after normal, pending or uncertain network results.
Explicit GET observation locates the exact submitting actor's request, checks the
canonical request/preview hashes and reconstructs one historical renewal link from
authenticated successor, parent and captured-review packets. Current parent head,
further ancestry, source permission and legal applicability remain unchecked.

Pending admission remains pending and withholds successor tools; unavailable or
unobserved requests gain no identity or retry permission. No POST replay, admission
repair, source/inference lookup or public graph update occurs. Complete admission
allows another explicit receipt/link observation and exact successor navigation,
preserving original customer/workspace/source-date/bucket filters, frozen versions
and immutable history. The new context inherits no old independent decision.
Changed filters/session/expiry and failed guards clear protected partial results.

Qualification covers 720 frontend cases/build, 255 focused source cases, 275
publication cases, ten real PostgreSQL races including concurrent private-version
editing, actual signed-runtime withdrawal, deployment contracts and browser lost
responses before/after commit, pending admission, no replay, separate review and
scope retirement. Seven jobs, two workers, existing caps and the complete exclusive
4,496-case backend partition remain. Legal/corpus qualification, professional
independence, productivity, deployment and lawyer acceptance stay separate;
R03/R05 remain partial.

### R03/R05A guarded parent-lineage navigation and separate successor review

[Guarded lineage follow-up](PARENT_LINEAGE_AND_SUCCESSOR_REVIEW.md) re-observes the
actor-bound renewal receipt/link/admissions around exact parent or successor
metadata lookups. The parent keeps its captured historical event/packet and frozen
version distinct from any later head. When no review was captured, that absence remains explicit.
Each explicit selection receives a separate bounded return intent with unchanged
customer OR, workspace dates, source-record dates and bucket; original baselines,
evidence and history are not rewritten.

Successor independent review has a separate intent-only entry. Exact filters,
version/head/admission observation, tool opening and original guarded content
retrieval are explicit steps. Another lawyer selects the context through their own
authorized session; tokens, old decisions and approval are not transferred. New
review controls start blank. Confirmation binds the new event ID/packet/decision
and predecessor to fresh authorized metadata under unchanged version/revision.
Uncertain writes close protected forms without POST replay, admission repair or
claiming a later head is the request's result. Scope changes retire delayed bodies
and links; the assistant stays guide-only and public graphs stay unchanged.

Qualification covers 743 frontend cases/build, 255 focused source cases, 275
publication cases, ten PostgreSQL races, actual signed-runtime withdrawal,
deployment contracts and browser real later-parent navigation, separate reviewer
sequence-one confirmation, truncated sequence-two response/history, actor denial,
late filter retirement and narrow layout. Seven jobs, two workers, existing caps
and the complete exclusive 4,496-case backend partition remain unchanged. All
legal/corpus, independence, productivity, deployment and lawyer acceptance gates
remain separate; R03/R05 stay partial.

Next: actor-bound read-only independent-review outcome reconciliation and exact
event navigation, preserving filters, evidence and history without write replay or
admission repair.

### R03/R05A read-only independent-review outcome reconciliation

The focused successor-review path now retains only a session-local request nonce,
canonical digest, frozen manifest/version and expected predecessor identity.
Successful, truncated, gateway and pending responses lead to an explicit read-only
lookup for the authenticated submitting actor. Context/review/predecessor admission
are reported separately. Unknown results grant neither absence nor retry permission;
no lookup repairs admission, replays a write, reads source bodies or infers the
submission from today's head. Scope, membership, independent-review permission,
packet/request integrity, typed proofs and consecutive predecessor identity are
checked locally before metadata is returned.

Guarded follow-up re-observes the exact outcome around fresh historical-event
metadata and creates a separate session token pinned to its packet hash. A later
opposing head or newer version remains separate. Exact customer OR, workspace
date field/range, source-record date range, bucket, evidence versions and immutable
review history are preserved; late filter/principal/expiry responses are retired.
Source rights/private-basis verification and consequential tools stay independent.
[Contract](INDEPENDENT_REVIEW_OUTCOME_RECONCILIATION.md) and
[engineering evidence](evidence/independent-review-outcome-reconciliation-2026-10-15.json).

Qualification includes actor/admin isolation, explicit content grants, mixed-context
routing, request/hash/version/predecessor substitutions, invalid proofs, real
PostgreSQL serialization, no-write/no-head/source checks and wide/narrow browser
rehearsal of real fixture commits with lost/truncated/gateway/pending replies.
Seven jobs, two workers, all deadlines and the complete exclusive backend partition
remain unchanged. Hosted exact-head checks, actual merge/main, deployment and legal
acceptance remain separate. R03/R05 remain partial.

Next: guarded direct reconciled-review return to the portfolio queue with the exact
selected historical event, original comparison baseline and fresh selected-versus-
current observations, without replay or source content.

### R03/R05A guarded reconciled-review return to portfolio

A completely admitted exact actor/request outcome now offers a separate guarded
direct queue-return action. Matching outcome observations surround fresh exact
historical metadata. The new session token clones the original intent and changes
only its selected event ID/packet hash. Original head/version observations and
unknown values remain unchanged; exact-event navigation keeps its distinct fresh
baseline. Later opposing heads and newer versions stay separate from the selected
decision and frozen evidence. Customer OR, workspace date field/range, source-record
date range and bucket are preserved.

Queue arrival and filter restoration read no source context or queue result until
the lawyer explicitly requests a new bounded window. An absent selected target
remains unobserved, without metadata fallback or automatic window traversal.
Packet substitutions, pending/unknown outcomes and late scope/filter responses
withhold the handoff. Existing content grants, source/private-basis and export/write
guards stay authoritative; no backend mutation, review replay, inferred grant,
source content or public-graph promotion is added.
[Contract](RECONCILED_REVIEW_PORTFOLIO_RETURN.md) and
[engineering evidence](evidence/reconciled-review-portfolio-return-2026-10-15.json).

Qualification covers original/selected/current identity separation, unknown
baselines, token/principal isolation, real fixture review/version changes and an
actual target outside the first queue window, plus source/publication and real
PostgreSQL regressions. Seven jobs, two workers, deadlines and the complete disjoint
backend partition remain unchanged. Hosted exact-head checks, merge/main,
deployment, legal qualification and lawyer acceptance remain separate; R03/R05
remain partial.

Next: explicit bounded current-head-to-selected review lineage from the returned
queue, with exact packet/head pins, fresh authorization and unknown/truncated paths
kept explicit, without legal-effect inference or automatic expansion.


### R03/R05A bounded returned-queue head-to-selected review lineage

An explicit returned-queue action now brackets one maximum-ten-record current-head
predecessor window with exact selected-event observations. Each observation pins
the frozen context/version/manifest, selected packet, captured current head packet,
current version/revision and admissions to the authorized queue comparison.
Consecutive member identities and predecessor links must resolve to the exact
selected event. Same-event and verified-path results are separate from legal
effects, source rights and readiness. Truncation, missing selection or
unavailable/pending members remain unknown without expansion, repair or replay.
Identity, access or revision drift clears the captured comparison.

Original head/version observations, selected/current identities, customer OR,
workspace date field/range, source dates, bucket and immutable evidence remain
unchanged. New observations/windows, filter/scope/principal/expiry changes and
navigation retire results and delayed replies. No source text, inference, export,
write, graph update or backend route/schema is introduced.
[Contract](RETURNED_REVIEW_HEAD_LINEAGE.md) and
[engineering evidence](evidence/returned-review-head-lineage-2026-10-15.json).

Qualification covers exact packets and bounded links, a real twelve-event fixture
history, pending/unavailable records, substitutions, final revision drift, denied
access, late filters and narrow layout, plus source/publication and PostgreSQL
regressions. A measured backend deadline failure relocates the single live-runtime
authorization integration into the existing PostgreSQL job; it is excluded from
the main selection and still executes with all live guards. Seven jobs, two
workers and deadlines remain unchanged; the complete exclusive 4,521-case
partition is preserved. Hosted checks, actual merge/main, deployment and legal
acceptance remain separate; R03/R05 stay partial.

Next: guarded exact-event navigation from verified path members, preserving the
original baseline and explicitly chosen packet, with fresh metadata observations
and separate source-content authorization. Unknown/truncated paths confer no link.


### R03/R05A guarded exact-event navigation from verified review paths

The returned queue now offers an explicit member handoff only from a complete,
admitted verified path. Five bounded metadata observations bracket one maximum-
ten-record head window with the original selected event and the chosen member.
Exact packets, frozen evidence, head/version/revision, admissions and the same
verified prefix must remain consistent. Unknown/truncated or changed paths grant
no link, expansion, repair or replay.

A separate session token clones the original intent, changing only the chosen
review ID/packet. Exact customer OR, both date ranges, workspace date field,
bucket, original baseline and unknown values remain intact. The destination
rejects event/context/write-flow redirection and freshly verifies the selected
packet; a new token for the same event triggers a new lookup. Other event controls
are withheld until a new queue selection. Even a return after failed metadata
keeps the event pin and original baseline while requiring fresh queue access.

New choices, observations/windows and filter/revision/scope/principal/expiry
changes retire links and delayed replies. Metadata continuity grants no source
rights or legal approval. Content, review, renewal and export keep their own
explicit guards; no backend route/schema, provider call or mutation is added.
[Contract](VERIFIED_REVIEW_PATH_NAVIGATION.md) and
[engineering evidence](evidence/verified-review-path-navigation-2026-10-15.json).

Qualification covers exact intermediate/endpoints, five-stage drift, substitutions,
pending/unavailable paths, token isolation, new-token refresh and pin-preserving
return, plus browser real fixture history and source/PostgreSQL regressions.
Seven jobs, two workers, deadlines and the complete exclusive backend partition
stay unchanged; deployment and legal acceptance are separate. R03/R05 remain partial.

Next: read-only handoff-versus-destination head/version comparison, keeping the
original queue baseline, selected event and independent source-content guards.

### R03/R05A guarded handoff-versus-destination identity comparison

Verified review-path tokens now retain a separately typed metadata observation of
the handoff's exact selected event, current head packet, current analysis
version/revision and five fresh-read timestamps. This does not overwrite the
original queue baseline or unknown values. The principal-bound in-memory book
keeps the same eight-entry/thirty-minute bounds and reload/eviction behavior.

The exact-event destination compares a fresh authorized metadata response with
that handoff observation. Same, different and unknown head/version relationships
and changed revisions are explicit. Immutable selected-event or same-head packet/
metadata substitutions, older observations and regressive revisions close the
comparison. Pending admissions remain pending; a later head never replaces the
chosen event. No source read or approval follows from a metadata match.

The disclosure keeps original baseline, frozen evidence, chosen event, handoff and
destination separate. Existing explicit queue return preserves customer OR,
workspace/source dates, bucket, original head/version observations, unknowns and
selected packet. Source tools retain their separate current checks. Filter,
revision, principal/scope, token/target, expiry and navigation changes retire old
comparisons and replies. No backend schema, review write, source-body read,
provider call or public graph mutation is added.

Qualification and limitations are recorded in the
[contract](HANDOFF_DESTINATION_IDENTITY_COMPARISON.md) and
[engineering evidence](evidence/handoff-destination-comparison-2026-10-15.json).
Seven CI jobs, two workers, existing caps and the complete backend partition stay
unchanged; hosted checks, merge, deployment and legal acceptance remain separate.
R03/R05 remain partial.

Next: guarded destination-comparison return and fresh queue reconciliation,
retaining separate handoff/destination observations and the original baseline.

### R03/R05A guarded comparison return and fresh queue reconciliation

Explicit return from a verified path destination can now retain a strictly typed
historical comparison receipt in the bounded principal-bound session book. Exact
customer OR, workspace/source date filters, bucket, original unknown baselines,
frozen evidence and chosen event/packet remain unchanged. Failed or unavailable
metadata keeps only the selection; it cannot invent a receipt or erase the pin.

Receipt details require a new authorized bounded queue window containing the
selected context and a fresh exact-event metadata read. Arrival/preparation alone
expose no retained comparison; an out-of-window target remains unobserved and no
window is automatically scanned. Reconciliation uses the existing GETs, compares
retained destination with fresh identities, and keeps original baseline, chosen
event, handoff and destination separate.

Strict guards reject changed filters/evidence, event or same-head substitutions,
nonmatching queue/head observations and regressive time/revision. Different and
unknown current identities remain explicit; pending admissions stay pending.
Scope/principal, filter/revision, expiry and navigation retire views and replies.
No source text, notes, review write/replay, admission repair, provider call, backend
schema change or public graph mutation is introduced.

See the [contract](COMPARISON_RETURN_RECONCILIATION.md) and
[engineering evidence](evidence/comparison-return-reconciliation-2026-10-15.json).
CI jobs, workers, caps and complete exclusive partitions remain unchanged. Hosted
checks, merge, main CI, deployment and legal acceptance stay separate; R03/R05
remain partial.

Next: guarded fresh-queue comparison-to-selected-event handoff, retaining exact
filters, frozen evidence and all separate historical observations.

### R03/R05A guarded comparison-to-event handoff

A successfully reconciled queue comparison can now explicitly prepare a separate
purpose-bound destination for its exact selected historical review event. Two
fresh authorized one-record metadata reads must retain the fixed evidence,
chosen packet, current head/version/revision, admissions and monotonic times.
Unknown or incomplete current identities and admissions, out-of-window targets,
changed responses, denied access and retired requests withhold the link. No
predecessor pointer is followed and no path from a current head is inferred.

The bounded session payload keeps the historical receipt, fresh queue observation
and preparation metadata separate. Original customer OR, workspace/source dates,
bucket, unknown baselines and frozen event/evidence pin remain unchanged. Arrival
requires a fresh exact-event read and rejects redirect, packet and same-head
substitution or regressive metadata. Later/different/unknown current identities
are displayed separately; no new head replaces the selected event.

Verified return preserves the original receipt. Unavailable metadata produces
only a pin-preserving selection return, without inventing a newer observation or
approval. Current matter-content grants and separate source-tool guards remain
mandatory. Filter/revision, scope/principal, expiry and navigation retire views,
links and late replies. No automatic source body, review/write replay, admission
repair, provider request, backend schema change or public graph mutation is added.

See the [contract](COMPARISON_EVENT_HANDOFF.md) and
[engineering evidence](evidence/comparison-event-handoff-2026-10-15.json). Seven CI
jobs, two workers, caps and complete exclusive backend partitions stay unchanged.
Hosted checks, merge, main CI, deployment and legal acceptance remain separate;
R03/R05 stay partial.

Next: guarded arrival-observation return and fresh queue reconciliation, retaining
prior observations and the original receipt without rebasing or approval transfer.

### R03/R05A guarded arrival return and fresh queue reconciliation

Explicit return from the comparison-event destination now retains a separately
typed fixed-depth arrival observation. Original receipt, queue, preparation,
customer OR, workspace/source dates, bucket, evidence/event pin and unknown
baselines remain unchanged. Failed, loading, blocked or retired metadata keeps
only the exact selection; no receipt, current admission or approval is invented.

Retained arrival details require a fresh authorized bounded queue window that
contains the selected context and a fresh exact-event read. Omitted targets stay
unobserved and reveal no retained details. Reconciliation reuses those existing
GETs, compares fresh identities with arrival separately from the older receipt,
and rejects immutable substitutions or regressive time/revision. Pending
admissions and unknown relationships remain explicit. No new head replaces the
selected historical event or implies a verified path.

The eight-entry/thirty-minute principal-bound memory book and current explicit
content grants remain. All lifecycle fences retire views and late replies. This
queue is read-only; older receipt preparation is withheld for arrival returns to
avoid discarding their history. Source tools retain independent current guards.
No source-body read, write/replay, repair, provider call, backend schema or public
graph change is added.

See the [contract](ARRIVAL_RETURN_RECONCILIATION.md) and
[engineering evidence](evidence/arrival-return-reconciliation-2026-10-15.json).
Seven CI jobs, two workers, caps and complete exclusive backend partitions remain
unchanged. Hosted checks, merge, main CI, deployment and legal acceptance remain
separate; R03/R05 stay partial.

Next: guarded arrival-preserving exact-event handoff from fresh reconciliation,
retaining fixed historical observations and fresh authorization without nesting
prior return chains or rebasing the original receipt.

### R03/R05A guarded arrival-preserving exact-event handoff

A freshly authorized arrival-return queue can now explicitly prepare its pinned
historical event through two fresh one-record metadata reads. Require known
current version/head and complete current admissions, stable evidence/event/head/
version/revision/admission metadata and monotonic times. Changed, denied, pending,
unknown or retired current observations withhold the destination; no pointer is
followed, retry performed or path inferred.

A separate fixed-depth purpose token retains the original arrival and all its
prior receipt/queue/preparation observations unchanged, plus new queue and
preparation metadata. Exact customer OR, workspace/source dates, bucket and
frozen evidence/event pin remain. Routes reject other events, context-only links
and write preparation before metadata access; a new token remounts even for the
same event.

Arrival requires fresh exact-event metadata. Compare new preparation and retained
arrival separately with the destination, reject immutable substitutions or
regressive metadata, and keep unknowns/pending admissions explicit. Verified
return restores the original arrival unchanged; unavailable reads keep only the
selection. No new historical arrival is implicitly captured or recursively
appended. Existing session bounds, content grants, lifecycle fences and source
checks remain. No automatic source read, review write/replay, repair, provider,
backend schema or public graph change is added.

See the [contract](ARRIVAL_EVENT_HANDOFF.md) and
[engineering evidence](evidence/arrival-event-handoff-2026-10-15.json).
Seven CI jobs, two workers, caps and complete exclusive backend partitions stay
unchanged. Hosted checks, merge, main CI, deployment and legal/lawyer qualification
remain separate; R03/R05 stay partial.

Next: guarded onward-destination return reconciliation through a separately typed
fixed-depth observation, keeping the original arrival and receipt unchanged.

PR94 CI qualification also exposed a final-authorization job timeout after all
21 tests passed. The [budget recovery](CI_FINAL_AUTHORIZATION_BUDGET.md) moves one
unchanged activation/rollback case into the existing graph-candidate group and
starts retained assembly first. All 4,521 cases remain exclusive and complete;
seven jobs, two workers and original caps remain. A cancelled job is not a pass.

### R03/R05A guarded onward-destination return reconciliation

Explicit return from an arrival-preserving destination now retains a separate
fixed-depth destination observation. The original arrival, receipt, queue and
preparation history, exact customer OR/workspace/source dates, queue bucket,
frozen evidence and selected review packet remain unchanged. Missing current
metadata returns selection only; inconsistent or redirected purposes fail
closed. The earlier handoff's selection-only destination retention boundary is
superseded by this explicitly typed capture.

After explicit filter restoration and a new authorized bounded queue containing
the target, existing exact-event metadata reads compare the retained onward
destination with fresh head/version/revision independently of the original
arrival and preparations. Outside-window targets disclose no retained details.
Immutable known-head/selected packet substitution, evidence/scope/filter drift
and regressive observations close the views. Unknowns and pending admissions
stay explicit; changed heads imply neither a path nor approval.

The existing eight-entry, thirty-minute, principal-bound memory book, opaque
tokens, clones and lifecycle fences remain. All comparisons commit together;
denied or late responses cannot restore private panels. Older onward preparation
is withheld where it would discard the new destination. No automatic body read,
write/replay, repair, provider, backend schema, public graph or deployment change
is added. Append-only independent review history stays intact.

See the [contract](ONWARD_DESTINATION_RETURN.md) and
[engineering evidence](evidence/onward-destination-return-2026-10-15.json).
R03/R05 remain partial. All seven jobs, two workers, deadlines and complete
exclusive 4,521-case backend partitions stay unchanged. Hosted checks, merge,
main CI, deployment and legal/lawyer qualification remain separate.

Next: guarded onward-return-preserving exact-event handoff, retaining the extra
destination alongside all original observations without recursive history or
silent rebasing.

PR95 hosted qualification exposed a five-minute PostgreSQL job cancellation
after all 95 cases passed. The [CI service-budget correction](CI_POSTGRES_BUDGET.md)
uses bounded disposable temporary storage, verifies unchanged durability settings
and starts costly concurrency groups earlier. All cases, workers and caps remain; the corrected head requires seven fresh
successful checks. The
cancelled attempt is not reclassified as successful.

Storage/order tuning alone did not protect the hosted PostgreSQL budget: its
unchanged SQLite runtime guard grew from 130 to 164 seconds. The job now uses the
standard native ARM executor already used by other backend checks, with explicit
architecture/durability reporting; the frontend job retains x86 coverage. This
requires fresh hosted qualification and establishes no universal timing/billing
guarantee. Both earlier attempts remain cancelled.

### R03/R05A guarded onward-return-preserving exact-event handoff

A freshly authorized onward-return queue can now explicitly prepare its pinned
historical event through two stable one-record metadata reads. Require known
current version/head and complete current admissions, exact evidence/event/head
pins and monotonic times, with current fences before/after each read. Drift,
denial, omitted/pending/unknown current metadata or retirement stops preparation
without retry, pointer walking or another request.

A separate fixed-depth purpose token carries the original OnwardReturn unchanged,
including all earlier receipt, arrival, queue and preparation history, plus new
queue/preparation observations. Exact customer OR, workspace/source dates, bucket,
frozen evidence and selected review packet remain. Alternate events, context-only
routes and write preparation close before metadata. Same-event new tokens remount
and require a fresh exact-event observation.

The destination compares new preparation and retained onward destination with
fresh arrival separately. All known immutable pins remain enforced; unknowns and
pending admissions stay explicit. Different heads imply neither a path nor
approval. Verified return restores the original onward return unchanged; this
arrival is not implicitly appended. Unavailable reads retain selection only.

Eight-entry/thirty-minute principal memory bounds, cloning, content grants and
lifecycle fences remain. Existing source tools stay separately guarded. No
source-body automation, write/replay, repair, provider, backend schema, public
graph or deployment change is added. Independent review records stay unchanged.
See the [contract](ONWARD_RETURN_EVENT_HANDOFF.md) and
[engineering evidence](evidence/onward-return-event-handoff-2026-10-15.json).
Seven jobs, two workers, deadlines and all 4,521 exclusive backend cases remain;
R03/R05 stay partial. Hosted checks, merge, main CI and legal/lawyer qualification
remain separate.

Next: guarded carried-arrival return reconciliation, through a separately typed
fixed-depth observation without rebasing the original onward return or nesting
arbitrary prior return chains.

### R03/R05A guarded carried-arrival return reconciliation

Explicit return from the onward-return-preserving destination now captures its
verified arrival as a separate fixed-depth observation. The original onward
return, receipt, arrivals, queues and preparations remain unchanged, as do exact
customer OR/workspace/source dates, bucket, frozen evidence and selected review
packet. Unavailable current reads retain selection only; inconsistent or
redirected purposes fail closed. No unobserved intermediate version is invented.

After explicit filter restoration, a fresh authorized bounded queue containing
the target and its existing exact-event GET compare the carried arrival with
fresh head/version/revision independently of older observations. Omitted windows
reveal no retained details. Immutable packet substitution, evidence/scope/filter
drift and regressive time/revision close all comparisons together. Unknowns and
pending admissions remain explicit; changed heads imply no path or approval.

The existing eight-entry/thirty-minute principal-bound memory, opaque tokens,
clones and lifecycle fences remain. Denied/late replies cannot reopen private
views. Existing preparation is withheld where it would discard this additional
arrival. No body automation, write/replay, repair, provider, backend schema,
public graph or deployment change is added. Independent review history remains.

See the [contract](CARRIED_ARRIVAL_RETURN.md) and
[engineering evidence](evidence/carried-arrival-return-2026-10-15.json).
All seven jobs, two workers, deadlines, qualified native ARM PostgreSQL settings
and all 4,521 exclusive backend cases remain. R03/R05 remain partial; hosted
checks, merge, main CI, deployment and legal/lawyer qualification stay separate.

Next: guarded carried-arrival-preserving exact-event handoff, retaining this
arrival and every original observation without rebasing or arbitrary recursion.

### R03/R05A guarded carried-arrival-preserving exact-event handoff

A freshly reconciled carried-arrival return can now explicitly prepare the
original selected historical event through a new fixed-depth purpose. Preserve
all earlier observations, exact customer/date/source-date/bucket filters,
frozen evidence and selected packet. Two stable one-record GETs check current
complete admissions, every retained identity pin and monotonic times/revisions.
Failure or retirement of the first read stops the second; no retry is added.

Reject alternate-event/context/write-purpose redirects before destination GET.
A fresh single exact-event GET compares new preparation and original carried
arrival independently; unknown/pending states remain explicit. Verified return
restores the original carried arrival unchanged. Unavailable reads yield selection
only; partial or conflicting metadata fails closed. No new destination is
implicitly captured, no review approval or legal effect is inferred.

Keep current matter content grants, scope/request fences, opaque tokens, cloned
bounded principal memory and immutable review history. No backend schema, body
read, automatic write, provider, public-graph or deployment change. All seven CI
jobs, workers, deadlines and complete exclusive backend selection are unchanged.
See [the contract](CARRIED_ARRIVAL_EVENT_HANDOFF.md) and its synthetic engineering
evidence. R03/R05 remain partial; corpus, legal and lawyer qualification remain
separate. Next: guarded carried-destination return reconciliation with a separate
observation of the new destination and unchanged earlier carried arrival.

### R03/R05A guarded carried-destination return reconciliation and CI headroom

The CI headroom prerequisite moves the complete 19-case model-cohort file from
the frontend workspace group into the existing main backend remainder. The
complete 4,521-case identity inventory, seven jobs, two workers and every cap
remain unchanged; no test, fixture logic or verdict is weakened. See
[the measured allocation contract](CI_FRONTEND_HEADROOM.md).

Explicit return from the carried-arrival handoff now captures a distinct verified
destination. Preserve the original carried arrival, all earlier snapshots,
exact customer/date/source-date/bucket filters, frozen evidence and selected
packet. Unavailable metadata yields selection only; partial or conflicting data
fails closed. No history or approval is rewritten or inherited.

A fresh authorized bounded queue and exact-event GET compare destination,
original arrival and preparations independently. Known packet pins and monotonic
clocks/revisions are checked; unknown/pending states remain explicit. Omitted,
denied or retired reads expose no retained-detail fallback. All panels commit
under current scope/revision/token fences. The older preparation is withheld
because it cannot carry the additional destination. No backend API, automatic
body read/write/provider call, public graph mutation or deployment change.

See [the contract](CARRIED_DESTINATION_RETURN.md) and its synthetic engineering
evidence. R03/R05 remain partial; legal, corpus and lawyer acceptance are separate.
Next: guarded destination-preserving exact-event handoff with unchanged history.

### R03/R05A guarded carried-destination-preserving exact-event handoff

A dedicated fixed-depth purpose carries the complete original carried destination
and every earlier observation unchanged. Its explicit preparation requires a
fresh authorized containing queue, known current head/version and complete
admissions, followed by exactly two stable selected-event `window=1` reads.
All original customer/date/source-date/bucket filters, frozen evidence and
selected/same-known-head packets remain bound. Failed, denied, drifting or retired
reads stop without retry; the older weaker preparation remains withheld.

Purpose and exact event are checked before the existing single fresh destination
GET. Separate comparisons preserve historical unknowns, pending admissions and
later independent heads/versions without inferring approval or a new path. New
tokens remount the same event. Verified return restores the original carried
destination unchanged; unavailable metadata yields selection only. Partial or
conflicting metadata closes. No automatic bodies, writes, provider calls or
shared graph mutations are introduced. Eight entries, thirty minutes and all
principal/scope/revision/request fences remain.

See [contract](CARRIED_DESTINATION_EVENT_HANDOFF.md) and synthetic engineering
evidence. The seven existing CI jobs and deadlines remain; one additional bounded
graph lane removes 91 complete cases from the saturated backend remainder.
Require all eight exact-head checks and at least thirty seconds observed
frontend/backend/graph margin as documented in
[CI partition qualification](CI_BACKEND_GRAPH_PARTITION.md). R03/R05 remain partial. Exact-head CI,
merge, main CI, deployment and legal/lawyer acceptance stay separate.
Next: separately capture this handoff's new destination on verified explicit
return and reconcile it with a fresh authorized bounded queue, preserving all
original observations through a fixed-depth contract.

### R03/R05A guarded destination-arrival return reconciliation

Frontend CI headroom is addressed first: move the complete 31-case Graph B
publication file to the existing native ARM graph group. Human review becomes 76
and graph runtime 122; all 4,521 backend identities and eight job configurations,
workers, caps, architectures and PostgreSQL settings remain. Both complete groups
are qualified before feature implementation; fresh hosted margin gates remain.

Explicit verified return now captures the destination handoff's actual arrival
separately, preserving the original destination and every earlier queue,
preparation and review observation unchanged. Exact customer/date/source-date/
bucket filters, selected event/packet, frozen evidence and all known historical
pins remain bound. Unavailable input yields selection only; partial or conflicting
metadata fails closed without replay or an invented receipt.

A fresh authorized bounded queue and its existing exact-event GET compare the
new arrival independently. Omitted windows disclose no retained details and
trigger no scan. Denied, inconsistent or retired observations clear all panels;
current scope/filter/revision/token fences protect commits. Unknown/pending states
remain explicit. The older handoff action is withheld because it cannot carry
this additional arrival. Eight principal-local entries and thirty-minute expiry
remain; no source bodies, automatic writes, provider calls or public graph updates.

See [contract](DESTINATION_ARRIVAL_RETURN.md) and engineering evidence. R03/R05,
legal/corpus/lawyer qualification and deployment remain separate. Next: guarded
arrival-preserving exact-event handoff carrying this complete fixed-depth record.


### R03/R05A guarded destination-arrival-preserving exact-event handoff

A dedicated fixed-depth purpose carries the complete saved destination arrival,
a fresh authorized containing queue, two stable exact-event metadata observations
and a new preparation. Original filters, frozen evidence, all historical packet
pins and every earlier arrival/destination/preparation remain unchanged. Current
unknown/pending states cannot prepare; historical states are preserved explicitly.

Destination validates purpose before its existing single fresh metadata GET,
remounts for a changed token, and compares new observations independently. Redirects,
substituted packets, regressions, denied access and late scope responses fail closed.
Verified return restores only the original arrival; unavailable return is selection
only. No source-body reads, automatic writes, provider calls or public graph updates.
Eight principal-local entries, thirty-minute expiry and all request fences remain.

Preserve CI coverage, workers and caps. After the initial frontend job reached
its five-minute cap, eliminate repeated history validation within each operation
and move the complete 17-case Graph B snapshot file to the existing graph job.
Human review becomes 59 cases and graph runtime 139; all 4,521 backend identities
and eight job configurations remain. Check all 14 retained observations and keep
the existing complete history validator. Fresh all-eight success and measured margins remain
merge gates. See [contract](DESTINATION_ARRIVAL_EVENT_HANDOFF.md) and engineering
evidence. R03/R05, legal/corpus/lawyer qualification, main CI and deployment remain
separate. Next: a dedicated return contract for this handoff's new destination.

### R03/R05A guarded handoff-destination return reconciliation

Frontend CI capacity is qualified first: the complete 27-case authority-cohort
file returns to the existing ARM backend remainder. X86 keeps private analysis
review and firm/proposal permissions. The full 4,521 identities remain disjoint;
all eight job configurations, workers, caps, architectures and PostgreSQL race
semantics remain unchanged. Receiving remainder is 3,843 cases; x86 human review
is 32. Local completion precedes feature edits; fresh hosted timing remains a gate.

Verified explicit return separately captures the handoff's actual destination
without replacing the saved arrival or any prior evidence/review observation.
A fresh authorized bounded queue and existing exact-event metadata GET compare it
independently. Exact customer/date/source-date/bucket filters, frozen evidence and
all known packet pins remain bound. Omission discloses no saved details and causes
no scan. Conflicting, denied or retired responses clear all panels atomically.
Unknown/pending states remain explicit; the weaker preceding handoff is withheld.

See [contract](HANDOFF_DESTINATION_RETURN.md) and synthetic engineering evidence.
Eight principal-local entries, thirty-minute expiry and all request fences remain.
No provider/public graph/source writes or deployment change. R03/R05 and legal,
corpus and lawyer acceptance remain partial/separate. Next: a dedicated guarded
handoff that carries this complete destination-return record without rebasing it.

### R03/R05A guarded handoff-destination-preserving exact-event handoff

A dedicated fixed-depth purpose carries the complete saved handoff destination
and every earlier observation unchanged. Explicit preparation requires a fresh
authorized containing queue, known current head/version and complete current
admissions, followed by exactly two stable selected-event metadata reads. All
17 retained observations, exact customer/date/source-date/bucket filters, frozen
evidence and historical packet pins remain bound. Unknown/pending history stays
explicit; drift, denial, substitution and retired replies close without retry.

Purpose and exact event are validated before the existing single destination
GET. New tokens remount the same event. Separate metadata comparisons establish
no path, selection change or review approval. Verified explicit return restores
the original complete saved destination unchanged; unavailable metadata yields
selection only, while partial/conflicting inputs fail closed. No further arrival
is implicitly captured. Eight principal-local entries, thirty-minute expiry,
all request fences and the withheld weaker purpose remain.

See [contract](HANDOFF_DESTINATION_EVENT.md) and synthetic engineering evidence.
No CI job/worker/deadline/architecture change or backend API, source body/write,
provider/public graph request or deployment change. All 4,521 backend identities
stay disjoint; all eight successful exact-head checks and measured margin gates
remain mandatory. R03/R05 and legal/corpus/lawyer qualification stay partial and
separate. Next: separately retain this handoff's fresh arrival on verified return
and reconcile it with a fresh authorized bounded queue without rebasing history.

### R03/R05A guarded handoff-destination-arrival return reconciliation

Qualify frontend capacity first by removing repeated complete-history validation
within each operation in two older handoffs, retaining all public-operation checks,
immutable pins, old tests and fresh awaited-read fences. All eight jobs, workers,
architectures, caps, 4,521 backend identities and PostgreSQL semantics remain.

Explicit verified return separately retains this handoff's actual arrival while
preserving the entire original handoff, saved destination and earlier observations.
Fresh authorized bounded queue reconciliation compares the arrival independently;
only a containing window permits the existing single exact-event metadata GET.
Omission reveals no saved details. Exact customer/date filters, frozen evidence,
all historical packet pins, unknown/pending states, principal/TTL bounds and
atomic retirement/failure clearing remain. Withhold the preceding handoff that
cannot carry this added arrival; no weaker-purpose substitution is allowed.

See [contract](HANDOFF_DESTINATION_ARRIVAL_RETURN.md) and dated synthetic engineering
evidence. No source/provider/public-graph writes or deployment change. R03/R05,
legal/corpus/lawyer qualification and main CI remain separate. Next: a dedicated
guarded handoff that carries this complete destination-arrival return unchanged,
with fresh qualification of frontend and graph timing margins before more work.

### R03/R05A guarded handoff-arrival-preserving exact-event handoff

A dedicated fixed-depth purpose carries the complete saved handoff arrival and
all 20 retained observations unchanged. Explicit preparation requires a fresh
authorized containing queue, known current head/version and complete admissions,
followed by exactly two stable selected-event metadata reads. Exact customer/date/
source-date/bucket filters, selected packet, frozen evidence and historical head
packets remain bound. Full validation occurs per public operation with private
local checks, avoiding repeated history work and preserving CI headroom.

Purpose and exact selected event are checked before the destination's existing
single metadata GET. Separate comparisons never rebase history or infer paths,
permission or approval. Unknown/pending states remain explicit. Drift, denial,
substitution and retired replies close without fallback; the weaker prior purpose
stays withheld. Verified explicit return restores only the entire original saved
arrival unchanged; unavailable metadata yields selection only. No further arrival
is captured implicitly. Principal/TTL bounds and all live request fences remain.

See [contract](HANDOFF_ARRIVAL_EVENT.md) and dated synthetic engineering evidence.
All 4,521 backend identities, eight jobs, workers, caps and PostgreSQL semantics
remain. No backend API, provider/public-graph/source write or deployment change.
R03/R05 and legal/corpus/lawyer acceptance stay partial/separate. Next: a dedicated
return contract retaining this handoff's new destination separately, reconciled
against a fresh authorized bounded queue without rebasing any prior observation.

### R03/R05A guarded handoff-arrival-destination return reconciliation

Explicit verified return separately retains this handoff's current destination
without replacing its saved arrival, preparation, evidence or review history.
All 22 prior observations and exact customer/date/source-date/bucket filters stay
bound. Fresh authorized bounded queue reconciliation compares the destination
independently, preserving all earlier flags. Only a containing window permits
the existing single exact-event metadata GET; omission discloses no saved details.

Strict schemas, all known head packets, monotonic time/revision, unknown/pending
states, principal/TTL bounds and atomic request retirement remain. Each public
call validates complete history afresh, with private operation-local checks to
avoid repeated work. Conflicting or denied observations clear every panel together.
Withhold the preceding handoff that cannot carry the added destination; no weaker
purpose substitution or automatic source/review/provider/public-graph write.

See [contract](HANDOFF_ARRIVAL_DESTINATION_RETURN.md) and dated synthetic engineering
evidence. The entire CI workflow, eight jobs, workers, caps, architectures,
4,521 backend identities and PostgreSQL semantics stay unchanged. R03/R05 and
legal/corpus/source-rights/lawyer acceptance remain partial/separate; no deployment
change. Next: a dedicated guarded exact-event handoff carrying this complete
saved destination return unchanged, with newly qualified CI timing margins.

### R03/R05A guarded handoff-arrival-destination-preserving exact-event handoff

A dedicated fixed-depth purpose carries the complete saved destination return
unchanged, preserving all 23 retained observations. Preparation requires a fresh
authorized containing queue, complete current admissions and exactly two stable
selected-event metadata reads. Exact customer/date/source-date/bucket filters,
selected packet, frozen evidence, known head packets and monotonic time/revision
remain bound. Full validation per public call uses private local checks, without
persistent verdict caches or weaker-purpose substitution.

Purpose and exact target are checked before the existing single destination GET;
new tokens remount the same event. Separate preparation/destination comparisons
never rebase history, choose a different event or imply a path, permission or
approval. Drift, denial and retired replies clear state; unknown/pending remains
explicit. Explicit verified return restores the whole original saved destination
return unchanged, without another capture, request or write. Unavailable metadata
yields selection only. All principal/TTL/request fences and confidential boundaries
remain. No backend API, provider/public-graph write or deployment change.

See [contract](HANDOFF_ARRIVAL_DESTINATION_EVENT.md) and dated synthetic evidence.
All previous 1,874 frontend cases and 4,521 backend identities remain; the entire
CI workflow, eight jobs, workers, caps and PostgreSQL semantics are unchanged.
R03/R05 and legal/corpus/source-rights/lawyer acceptance remain partial/separate.
Next: a dedicated return contract retaining this handoff's newer arrival separately,
reconciled against a fresh authorized bounded queue without rebasing prior history.

### R03/R05A guarded handoff-arrival-destination-arrival return reconciliation

Explicit verified return separately retains the destination-preserving handoff's
new arrival without replacing its complete purpose, filters, evidence or history.
All 25 prior observations remain bound. Fresh authorized bounded queue reconciliation
compares the new arrival independently and preserves every earlier flag. Only a
containing window permits the existing single exact-event metadata GET; omission
reveals no saved details and causes no target read or scan.

Strict fixed-depth schemas, all known head packets, exact customer/date/source-date/
bucket filters, monotonic clocks/revisions, explicit unknown/pending states and
principal/TTL/request fences remain. Public calls validate complete history afresh
using private local checks, with no persistent verdict cache. Denial, substitution,
regression and retired replies clear all panels atomically. Withhold the preceding
handoff that cannot carry the added arrival. Original API/return projections remain
unchanged; no source/review/provider/public-graph write or deployment change.

See [contract](HANDOFF_ARRIVAL_DESTINATION_ARRIVAL_RETURN.md) and dated synthetic
engineering evidence. All prior 1,961 frontend cases, all 4,521 backend identities
and the entire CI workflow/eight jobs/workers/caps/PostgreSQL semantics remain.
R03/R05 and legal/corpus/source-rights/lawyer acceptance remain partial/separate.
Next: a dedicated guarded exact-event handoff carrying this complete saved arrival
return unchanged, with newly qualified CI timing margins before merge.

### R03/R05A guarded handoff-arrival-destination-arrival-preserving exact-event handoff

A dedicated fixed-depth purpose carries the complete saved arrival return unchanged,
with a new authorized containing queue and exactly two stable selected-event metadata
reads at window one. All 26 retained observations, exact seven-field/customer-OR
filters, frozen evidence and known same-ID head packets remain bound. Each public
operation revalidates complete history, using private local checks without a
persistent verdict cache or weaker-purpose substitution.

Purpose and exact target validate before the destination's single metadata GET;
new tokens remount the same event. New preparation/current destination and saved
arrival compare independently without rebasing history or implying permission,
legal effect, approval or a path to a new head. Drift, denial and retirement clear
state; unknown/pending stays explicit. Explicit verified return restores the complete
original arrival return unchanged with zero requests/writes and no further capture.
Unavailable metadata yields selection only. Principal/TTL/request fences and private
matter boundaries remain; no backend/provider/public-graph/deployment change.

See [contract](HANDOFF_ARRIVAL_DESTINATION_ARRIVAL_EVENT.md) and dated synthetic
engineering evidence. All previous 2,043 frontend cases/78 files, all 4,521 backend
identities and the whole CI workflow/eight jobs/workers/caps/PostgreSQL semantics
remain unchanged. Require all eight exact-head checks and measured timing floors
before ordinary merge. R03/R05 and legal/corpus/rights/lawyer acceptance remain partial.
Next: separately retain this handoff's new destination and reconcile it against a
fresh authorized bounded queue, preserving the complete purpose and every dependency.

### R03/R05A guarded handoff-arrival-destination-arrival-destination return reconciliation

Explicit verified UI return separately retains the arrival-preserving handoff's
new destination without replacing its complete purpose, filters, frozen evidence
or history. All 28 prior observations stay bound. Fresh authorized bounded queue
reconciliation compares the new destination independently and preserves every
older flag. Only a containing target permits the single exact-event metadata GET;
omission exposes no saved details and triggers no target read or scan.

Strict fixed-depth schemas, known same-ID head packets, exact seven-field/customer-OR
filters, monotonic time/revision, explicit unknown/pending states and all principal/
TTL/request fences remain. Public operations revalidate complete history with private
local checks, without persistent verdict caches. Denial, substitution, regression
and retired replies clear panels atomically. Withhold the preceding handoff that
cannot carry the added destination. Original API/return projections stay unchanged.
No backend/provider/public-graph/deployment change; private metadata stays private.

See [contract](HANDOFF_ARRIVAL_DESTINATION_ARRIVAL_DESTINATION_RETURN.md) and dated
synthetic evidence. All prior 2,135 frontend cases/79 files, all 4,521 backend
identities and the entire workflow/eight jobs/workers/caps/PostgreSQL semantics
remain unchanged. Require all eight exact-head checks and measured timing floors
before ordinary merge. R03/R05 and legal/corpus/rights/lawyer acceptance remain partial.
Next: a dedicated exact-event handoff carrying this complete saved destination
return unchanged, with fresh bounded preparation and independently qualified CI margins.

### R03/R05A guarded handoff-arrival-destination-arrival-destination-preserving exact-event handoff

A dedicated fixed-depth purpose carries the complete saved destination return
unchanged with a fresh authorized containing queue and exactly two stable metadata
reads at window one. All 29 retained observations, exact seven-field/customer-OR
filters, frozen evidence and known same-ID head packets remain bound. Each public
operation revalidates complete history with private local checks, without a
persistent verdict cache or weaker-purpose substitution.

Purpose and exact target validate before the destination's single metadata GET;
a new token remounts the same selected event. New preparation/current destination
and saved destination compare independently, without rebasing history or implying
permission, legal effect, approval or a path to a new head. Drift, denial and
retirement clear state; unknown/pending remains explicit. Explicit verified return
restores the complete original return unchanged with zero action requests/writes
and no further capture. Unavailable metadata yields selection only. Principal/TTL/
request fences and matter confidentiality remain. No backend/provider/graph/deploy change.

See [contract](HANDOFF_ARRIVAL_DESTINATION_ARRIVAL_DESTINATION_EVENT.md) and dated
synthetic evidence. All prior 2,222 frontend cases/80 files, all 4,521 backend
identities and the whole workflow/eight jobs/workers/caps/PostgreSQL semantics
remain unchanged. Require all eight exact-head checks and measured timing floors
before ordinary merge. R03/R05 and legal/corpus/rights/lawyer acceptance remain partial.
Next: separately retain this handoff's new arrival and reconcile it against a fresh
bounded authorized queue, preserving the complete purpose and every prior observation.

### R03/R05A guarded handoff-arrival-destination-arrival-destination-arrival return

Explicit UI return now retains the complete preceding handoff and its verified
arrival separately with zero action requests/writes. All 31 prior observations,
exact seven-field/customer-OR filters, frozen evidence and known same-ID head
packets remain bound. The original exported return API and older return projections
stay unchanged. Each operation revalidates complete history with private local
checks and no persistent verdict cache.

A fresh authorized bounded queue permits one exact-event metadata GET only when
containing the selected record. Omission reveals no saved details and causes no
target read/retry/scan. Compare the separate arrival independently without rebasing
history. Unknown/pending stays explicit; denial, drift and retirement clear state.
Withhold the preceding handoff that cannot carry the new arrival. Principal/TTL/
request fences and private matter confidentiality remain. No backend/provider/
public-graph/deployment change.

See [contract](HANDOFF_ARRIVAL_DESTINATION_ARRIVAL_DESTINATION_ARRIVAL_RETURN.md)
and dated synthetic evidence. All prior 2,319 frontend cases/81 files, all 4,521
backend identities and the entire workflow/eight jobs/workers/caps/PostgreSQL
semantics remain unchanged. Source publication receives no additional workload;
its prior 14-second margin requires profiling before adding work there. Require all
eight exact-head checks and measured timing floors before ordinary merge. R03/R05
and legal/corpus/rights/lawyer acceptance remain partial.
Next: a dedicated exact-event handoff carrying this complete 32-observation arrival
return unchanged, with fresh bounded preparation and independently qualified CI margins.

### R03/R05A complete arrival-preserving exact-event handoff

A dedicated fixed-depth purpose carries the complete 32-observation arrival return
unchanged. A fresh authorized containing queue and exactly two stable metadata
reads at window one prepare the exact selected event. All prior observations,
seven-field/customer-OR filters, frozen evidence and known same-ID head packets
remain bound. Each public call validates complete history with private local
checks and no persistent verdict cache or weaker-purpose substitution.

Purpose and exact target validate before the destination's single metadata GET;
a new token remounts the same selected event. New preparation/current destination
and saved arrival compare independently without rebasing history or implying
permission, approval, legal effect or a new-head path. Unknown/pending stays
explicit; drift, denial and retirement clear state. Explicit verified return
restores the original complete 32-observation return with zero action requests/
writes and no further capture. Unavailable metadata yields selection only.
Principal/TTL/request fences and private matter confidentiality remain. No backend,
provider, public-graph or deployment change.

See [contract](HANDOFF_ARRIVAL_DESTINATION_ARRIVAL_DESTINATION_ARRIVAL_EVENT.md)
and dated synthetic evidence. All prior 2,412 frontend cases/82 files, all 4,521
backend identities and the entire workflow/eight jobs/workers/caps/PostgreSQL
semantics remain unchanged. Publication receives no additional workload; its prior
28-second margin remains recorded for profiling before future additions. Require
all eight exact-head successes and timing floors before ordinary merge. R03/R05
and legal/corpus/source-rights/lawyer acceptance remain partial.
Next: separately retain this handoff's new destination and reconcile it against a
fresh authorized bounded queue, preserving the complete purpose and every earlier
observation without rebasing history.

### R03/R05A complete-handoff destination return reconciliation

Explicit UI return now retains the complete preceding 34-observation handoff and
a newly verified destination separately, with zero action requests/writes. Exact
seven-field/customer-OR filters, selected packets, frozen evidence and known same-ID
head packets stay bound. Original exported return APIs and older return projections
remain unchanged. Every public call validates complete history using private local
checks and no persistent verdict cache.

A fresh authorized bounded queue permits one exact-event metadata GET only when
containing the selected record. Omission reveals no saved details and makes no
target read/retry/scan. Compare the destination independently without rebasing any
earlier observation or flag. Unknown/pending stays explicit; denial, drift and
retirement clear state. Withhold the preceding handoff that cannot carry the added
destination. Principal/TTL/request fences and private matter confidentiality remain.
No backend/provider/public-graph/deployment change.

See [contract](HANDOFF_ARRIVAL_DESTINATION_ARRIVAL_DESTINATION_ARRIVAL_DESTINATION_RETURN.md)
and dated synthetic evidence. All prior 2,514 frontend cases/83 files, all 4,521
backend identities and the complete workflow/eight jobs/workers/caps/PostgreSQL
semantics remain unchanged. No publication workload is added; its prior 22-second
margin stays visible for profiling before additions. Require all eight exact-head
successes and measured timing floors before ordinary merge. R03/R05 and legal/
corpus/source-rights/lawyer acceptance remain partial.
Next: a dedicated exact-event handoff carrying this complete 35-observation
destination return unchanged, with fresh bounded preparation and independent
qualification of CI margins.

### R03/R05A complete destination-preserving exact-event handoff

A dedicated fixed-depth purpose carries the complete 35-observation destination
return unchanged. A fresh authorized containing queue and exactly two stable
metadata reads at window one prepare the exact selected event: 37 observations
in total. Seven-field/customer-OR filters, selected packets, frozen evidence,
monotonic history and every known same-ID head packet remain bound. Each public
call validates complete history with private local checks, no cached verdict or
weaker-purpose substitution; validation precedes token allocation/eviction.

Purpose and exact target validate before the destination's single metadata GET.
Different tokens remount the same event. New preparation/current destination and
saved destination compare independently without rebasing earlier identities or
flags. Unknown/pending remains explicit; failure, denial and retirement clear
state. Explicit verified return restores only the complete original 35-observation
return with zero action requests/writes and no further arrival capture. Unavailable
metadata yields selection only. Principal/TTL/request fences, exact filters and
private matter confidentiality remain. No backend/provider/public-graph/deployment
change.

See [contract](HANDOFF_ARRIVAL_DESTINATION_ARRIVAL_DESTINATION_ARRIVAL_DESTINATION_EVENT.md)
and dated synthetic evidence. All prior 2,612 frontend cases/84 files and all
4,521 backend identities remain unchanged, as do the workflow/eight jobs/workers/
caps/PostgreSQL semantics. No publication workload is added; its last measured
32-second margin remains visible for profiling before additions. Require all eight
exact-head successes and measured timing floors before ordinary merge. R03/R05
and legal/corpus/source-rights/lawyer acceptance remain partial.
Next: separately retain this handoff's arrival and reconcile it against a fresh
authorized bounded queue, preserving the complete 37-observation purpose and every
earlier observation without rebasing history.

### R03/R05A complete-handoff arrival return reconciliation

Explicit UI return now retains the complete 37-observation handoff and a separately
verified arrival, with zero action requests/writes: 38 observations. Exact seven-field/
customer-OR filters, selected packets, frozen evidence and known same-ID head packets
remain bound. Original exported return APIs and older return projections stay unchanged.
Every public call validates complete history with private local checks and no cached
verdict; parent reconciliation avoids duplicate full-history validation in that helper.

A fresh authorized bounded queue permits one exact-event metadata GET only when
containing the selected record. Omission reveals no saved details and makes no target
read/retry/scan. Compare the saved arrival independently without rebasing earlier
observations or flags. Unknown/pending stays explicit; denial, drift and retirement
clear state. Withhold the preceding handoff that cannot carry the added arrival.
Principal/TTL/request fences, exact filters and private matter confidentiality remain.
No backend/provider/public-graph/deployment change.

See [contract](HANDOFF_ARRIVAL_DESTINATION_ARRIVAL_DESTINATION_ARRIVAL_DESTINATION_ARRIVAL_RETURN.md)
and dated synthetic evidence. All prior 2,719 frontend cases/85 files, all 4,521 backend
identities and the workflow/eight jobs/workers/caps/PostgreSQL semantics remain unchanged.
No publication workload is added; its last measured 14-second margin remains visible
for profiling before additions. Require all eight exact-head successes and measured
timing floors before ordinary merge. R03/R05 and legal/corpus/source-rights/lawyer
acceptance remain partial.
Next: a dedicated exact-event handoff carrying the complete 38-observation arrival
return unchanged, with fresh bounded preparation and independently qualified CI margins.

### R03/R05A complete arrival-preserving exact-event handoff

A dedicated fixed-depth purpose carries the complete 38-observation arrival return
unchanged. One fresh authorized containing queue and exactly two stable metadata
reads at window one prepare the exact selected event: 40 observations in total.
All prior selected packets, frozen evidence, seven-field/customer-OR filters,
monotonic history and known same-ID head packets remain bound. Every public call
validates complete history with private local checks and no cached verdict or weaker
purpose. Validation precedes token allocation and eviction.

Purpose and exact target validate before the destination's single metadata GET;
a new token remounts the same selected event. New preparation/current destination
and saved arrival compare independently without rebasing earlier identities or
flags. Unknown/pending stays explicit; failure, denial and retirement clear state.
Explicit verified return restores only the complete original 38-observation return,
with zero action requests/writes and no further destination capture. Unavailable
metadata yields selection only. Principal/TTL/request fences, exact filters and
private matter confidentiality remain. No backend/provider/public-graph/deployment
change.

See [contract](HANDOFF_ARRIVAL_DESTINATION_ARRIVAL_DESTINATION_ARRIVAL_DESTINATION_ARRIVAL_EVENT.md)
and dated synthetic evidence. All prior 2,822 frontend cases/86 files, all 4,521
backend identities and the workflow/eight jobs/workers/caps/PostgreSQL semantics
remain unchanged. No publication workload is added; its last measured 23-second
margin remains visible for profiling before additions. Require eight exact-head
successes and measured timing floors before ordinary merge. R03/R05 and legal/
corpus/source-rights/lawyer acceptance remain partial.
Next: separately retain this handoff's destination and reconcile it against a
fresh authorized bounded queue, preserving the complete 40-observation purpose
and every earlier observation without rebasing history.

### R03/R05A complete handoff destination-return reconciliation

Explicit UI return now retains the complete 40-observation purpose unchanged plus
one separate verified destination: 41 observations. A fresh authorized bounded
queue permits one exact-event metadata GET only when it contains the selected record.
Omission reveals no saved details and triggers no target read, scan or retry. New
preparation, saved arrival, saved destination and fresh queue compare independently;
all historical identities/flags, frozen evidence and seven-field/customer-OR filters
remain unchanged. Unknown/pending remains explicit. Capture makes zero action reads
or writes; unavailable metadata yields selection only. The original exported
38-observation return and all older projections remain unchanged.

Complete history validates afresh per public operation, with private operation-local
checks and no duplicate full parent validation in one reconciliation helper. Validate
before nonce allocation/eviction; retain eight entries/thirty minutes/principal/session/
reload closure and opaque URLs. Withhold the preceding purpose that cannot carry the
additional destination. Failure, denial, expiry and retirement clear all panels,
comparisons and links. No content-access bypass, provider/public-graph metadata,
backend change or deployment.

See [contract](HANDOFF_ARRIVAL_DESTINATION_ARRIVAL_DESTINATION_ARRIVAL_DESTINATION_ARRIVAL_DESTINATION_RETURN.md)
and dated synthetic evidence. All prior 2,934 frontend cases/87 files remain
byte-identical; 108 new cases cover every retained pin and separate destination.
All 4,521 backend identities and the workflow/eight jobs/workers/caps/PostgreSQL
semantics remain unchanged. PR118 exact-head frontend/backend/backend-test/graph-runtime
margins were 102/253/214/96 seconds; publication margin was 36 seconds. No publication
workload is added; profile before additions. Require eight exact-head successes and
measured timing floors before ordinary merge. Main CI is separate. R03/R05 and legal/
corpus/source-rights/lawyer acceptance remain partial.
Next: a dedicated exact-event handoff carrying this complete 41-observation return
with fresh bounded preparation, without rebasing any retained identity or flag.

### R03/R05A complete destination-preserving exact-event handoff

A dedicated fixed-depth purpose carries the complete 41-observation destination
return unchanged. One fresh authorized containing queue and exactly two stable
metadata reads at window one prepare the exact selected event: 43 observations.
All prior selected packets, frozen evidence, seven-field/customer-OR filters,
monotonic history and known same-ID head packets remain bound. Every public call
validates complete history with private operation-local checks, no cached verdict
and no weaker purpose. Validation precedes allocation and eviction.

Purpose and exact target validate before the destination's single metadata GET;
a new token remounts the same selected event. Preparation/current destination and
saved destination compare independently without rebasing earlier identities or
flags. Unknown/pending stays explicit; failure, denial and retirement clear state.
Explicit verified return restores only the complete original 41-observation return,
with zero action reads/writes and no further arrival capture. Unavailable metadata
yields selection only. Principal/TTL/request fences, exact filters and private
matter confidentiality remain. No backend/provider/public-graph/deployment change.

See [contract](HANDOFF_ARRIVAL_DESTINATION_ARRIVAL_DESTINATION_ARRIVAL_DESTINATION_ARRIVAL_DESTINATION_EVENT.md)
and dated synthetic evidence. All prior 3,042 frontend cases/88 files remain
byte-identical; 117 new cases cover every retained pin and bounded preparation.
All 4,521 backend identities and the workflow/eight jobs/workers/caps/PostgreSQL
semantics remain unchanged. PR119 exact-head frontend/backend/backend-test/graph-runtime
margins were 80/254/218/94 seconds; publication margin was 23 seconds. No publication
workload is added; profile before additions. Require eight exact-head successes
and measured timing floors before ordinary merge. Main CI is separate. R03/R05
and legal/corpus/source-rights/lawyer acceptance remain partial.
Next: separately retain this handoff's arrival and reconcile it against a fresh
authorized bounded queue, preserving the complete 43-observation purpose and
every earlier observation without rebasing history.

### R03/R05A complete handoff arrival-return reconciliation

Explicit UI return retains the complete 43-observation purpose unchanged plus one
separate verified arrival: 44 observations. A fresh authorized bounded queue permits
one exact-event metadata GET only when it contains the selected record. Omission
reveals no saved details and triggers no target read, scan or retry. New preparation,
saved destination, saved arrival and fresh queue compare independently; all historical
identities/flags, frozen evidence and seven-field/customer-OR filters remain unchanged.
Unknown/pending remains explicit. Capture makes zero action reads or writes; unavailable
metadata yields selection only. The original exported 41-observation return and all
older projections remain unchanged.

Complete history validates afresh per public operation, with private operation-local
checks and no duplicate full parent validation in one reconciliation helper. Validate
before nonce allocation/eviction; retain eight entries/thirty minutes/principal/session/
reload closure and opaque URLs. Withhold the preceding purpose that cannot carry the
additional arrival. Failure, denial, expiry and retirement clear all panels, comparisons
and links. No content-access bypass, provider/public-graph metadata, backend change
or deployment.

See [contract](HANDOFF_ARRIVAL_DESTINATION_ARRIVAL_DESTINATION_ARRIVAL_DESTINATION_ARRIVAL_DESTINATION_ARRIVAL_RETURN.md)
and dated synthetic evidence. All prior 3,159 frontend cases/89 files remain
byte-identical; 113 new cases cover every retained pin and separate arrival. All 4,521
backend identities and the workflow/eight jobs/workers/caps/PostgreSQL semantics remain
unchanged. PR120 exact-head frontend/backend/backend-test/graph-runtime margins were
76/261/227/71 seconds; publication margin was 17 seconds. No publication workload is
added; profile before additions. Require eight exact-head successes and measured timing
floors before ordinary merge. Main CI is separate. R03/R05 and legal/corpus/source-rights/
lawyer acceptance remain partial.
Next: a dedicated exact-event handoff carrying this complete 44-observation return
with fresh bounded preparation, without rebasing any retained identity or flag.


### R03/R05A whole-arrival-preserving exact-event handoff

A dedicated fixed-depth purpose carries the complete 44-observation arrival
return unchanged. One fresh authorized containing queue and exactly two stable
metadata reads at window one prepare the exact selected event: 46 observations.
All prior selected packets, frozen evidence, seven-field/customer-OR filters,
monotonic history and known same-ID head packets remain bound. Every public call
validates complete history with private operation-local checks, no cached verdict
and no weaker purpose. Validation precedes allocation and eviction.

Purpose and exact target validate before the destination's single metadata GET;
a new token remounts the same selected event. Preparation/current destination and
saved arrival/current destination compare independently without rebasing earlier
identities or flags. Unknown/pending stays explicit; failure, denial and retirement
clear state. Explicit verified return restores only the complete original
44-observation return, with zero action reads/writes and no further destination
capture. Unavailable metadata yields selection only. Principal/TTL/request fences,
exact filters and private matter confidentiality remain. No backend/provider/
public-graph/deployment change.

See [contract](HANDOFF_ARRIVAL_DESTINATION_ARRIVAL_DESTINATION_ARRIVAL_DESTINATION_ARRIVAL_DESTINATION_ARRIVAL_EVENT.md)
and dated synthetic evidence. All prior 3,272 frontend cases/90 files remain
byte-identical; 122 new cases cover every retained pin and bounded preparation.
All 4,521 backend identities and the workflow/eight jobs/workers/caps/PostgreSQL
semantics remain unchanged. PR121 exact-head frontend/backend/backend-test/graph-runtime
margins were 75/244/201/84 seconds; publication margin was 21 seconds. No publication
workload is added; profile before additions. Require eight exact-head successes
and measured timing floors before ordinary merge. Main CI is separate. R03/R05
and legal/corpus/source-rights/lawyer acceptance remain partial.
Next: separately retain this handoff's destination and reconcile it against a fresh
authorized bounded queue, preserving the complete 46-observation purpose and
every earlier observation without rebasing history.


### R03/R05A whole-handoff destination-return reconciliation

Explicit UI return retains the complete 46-observation purpose unchanged plus one
separate verified destination: 47 observations. A fresh authorized bounded queue
permits one exact-event metadata GET only when it contains the selected record.
Omission reveals no saved details and triggers no target read, scan or retry. New
preparation, saved arrival, saved destination and fresh queue compare independently;
all historical identities/flags, frozen evidence and seven-field/customer-OR filters
remain unchanged. Unknown/pending remains explicit. Capture makes zero action reads
or writes; unavailable metadata yields selection only. The original exported
44-observation return and all older projections remain unchanged.

Complete history validates afresh per public operation, with private operation-local
checks and no duplicate full parent validation in one reconciliation helper. Validate
before nonce allocation/eviction; retain eight entries/thirty minutes/principal/session/
reload closure and opaque URLs. Withhold the preceding purpose that cannot carry the
additional destination. Failure, denial, expiry and retirement clear all panels,
comparisons and links. No content-access bypass, provider/public-graph metadata,
backend change or deployment.

See [contract](HANDOFF_ARRIVAL_DESTINATION_ARRIVAL_DESTINATION_ARRIVAL_DESTINATION_ARRIVAL_DESTINATION_ARRIVAL_DESTINATION_RETURN.md)
and dated synthetic evidence. All prior 3,394 frontend cases/91 files remain
byte-identical; 118 new cases cover every retained pin and separate destination.
All 4,521 backend identities and the workflow/eight jobs/workers/caps/PostgreSQL
semantics remain unchanged. PR122 exact-head frontend/backend/backend-test/graph-runtime
margins were 61/282/244/96 seconds; publication margin was 14 seconds. No publication
workload is added; profile before additions. Require eight exact-head successes and
measured timing floors before ordinary merge. Main CI is separate. R03/R05 and legal/
corpus/source-rights/lawyer acceptance remain partial.
Next: a dedicated exact-event handoff carrying this complete 47-observation return
with fresh bounded preparation, without rebasing any retained identity or flag.


### R03/R05A whole-destination-preserving exact-event handoff

A dedicated fixed-depth purpose carries the complete 47-observation destination
return unchanged. One fresh authorized containing queue and exactly two stable
metadata reads at window one prepare the exact selected event: 49 observations.
All prior selected packets, frozen evidence, seven-field/customer-OR filters,
monotonic history and known same-ID head packets remain bound. Every public call
validates complete history with private operation-local checks, no cached verdict
and no weaker purpose. Validation precedes allocation and eviction.

Purpose and exact target validate before the destination's single metadata GET;
a new token remounts the same selected event. Preparation/current destination and
saved destination/current destination compare independently without rebasing earlier
identities or flags. Unknown/pending stays explicit; failure, denial and retirement
clear state. Explicit verified return restores only the complete original
47-observation return, with zero action reads/writes and no further arrival capture.
Unavailable metadata yields selection only. Principal/TTL/request fences, exact
filters and private matter confidentiality remain. No backend/provider/public-graph/
deployment change.

See [contract](HANDOFF_ARRIVAL_DESTINATION_ARRIVAL_DESTINATION_ARRIVAL_DESTINATION_ARRIVAL_DESTINATION_ARRIVAL_DESTINATION_EVENT.md)
and dated synthetic evidence. All prior 3,512 frontend cases/92 files remain
byte-identical; 127 new cases cover every retained pin and bounded preparation.
All 4,521 backend identities and the workflow/eight jobs/workers/caps/PostgreSQL
semantics remain unchanged. PR123 exact-head frontend/backend/backend-test/graph-runtime
margins were 53/283/245/90 seconds; publication margin was 42 seconds. No publication
workload is added; profile before additions. Require eight exact-head successes
and measured timing floors before ordinary merge. Main CI is separate. R03/R05
and legal/corpus/source-rights/lawyer acceptance remain partial.
Next: separately retain this handoff's arrival and reconcile it against a fresh
authorized bounded queue, preserving the complete 49-observation purpose and
every earlier observation without rebasing history.


### R03/R05A whole-handoff arrival return reconciliation

Explicit UI return retains the complete 49-observation handoff and a separate
verified reduced arrival: 50 observations. Zero action reads/writes or implicit
refresh. The original exported 47-observation return and older projections remain
unchanged. A fresh authorized bounded containing queue permits exactly one
selected-event metadata GET; omission exposes no saved metadata or target read.
Saved arrival/current queue compares independently, without rebasing older
identities, frozen evidence, filters, known packets, history or flags.

Full history validates afresh per public operation with private operation-local
checks; no duplicate full parent validation in one reconciliation helper. Validate
before allocation/eviction; preserve eight entries/thirty minutes/principal/session/
reload closure, opaque URLs and explicit same-firm matter membership. Withhold
weaker handoffs. Failure, denial, expiry and retirement clear panels and links.
Private metadata stays outside public graphs, providers, shared caches and telemetry.

See [contract](HANDOFF_ARRIVAL_DESTINATION_ARRIVAL_DESTINATION_ARRIVAL_DESTINATION_ARRIVAL_DESTINATION_ARRIVAL_DESTINATION_ARRIVAL_RETURN.md) and dated synthetic evidence. All prior 3,639 frontend
cases/93 files stay byte-identical; 123 new cases cover all 49 retained pins and
separate arrival. All 4,521 backend identities, workflow/eight jobs/workers/caps and
PostgreSQL semantics remain unchanged. PR124 frontend/backend/backend-test/graph-runtime
margins were 153/253/221/91 seconds; publication margin was 29 seconds. No publication
workload is added; profile before additions. Require eight exact-head successes and
measured timing floors before ordinary merge. Main CI is separate. R03/R05 and
legal/corpus/source-rights/lawyer acceptance remain partial. No deployment.
Next: a dedicated exact-event handoff carrying this complete 50-observation return
with fresh bounded preparation, preserving every retained observation.


### R03/R05A complete-arrival-preserving exact-event handoff

A dedicated fixed-depth purpose carries the complete 50-observation arrival return
unchanged. One fresh authorized containing queue and exactly two stable metadata
reads at window one prepare the exact selected event: 52 observations. All prior
selected packets, frozen evidence, seven-field/customer-OR filters, monotonic
history and known same-ID head packets stay bound, including arrival-only heads.
Every public call validates complete history using private operation-local checks,
with no cached verdict or weaker purpose. Validation precedes allocation/eviction.

Purpose and exact target validate before the single destination metadata GET; a
new opaque token remounts the same selected event. Preparation/current destination
and saved arrival/current destination compare independently. Earlier identities
and flags remain intact. Unknown/pending stays explicit; failure, denial and
retirement clear state. Explicit verified return restores only the complete
original 50-observation return, with zero action reads/writes and no further
destination capture. Unavailable metadata yields selection only. Principal/TTL/
request fences, exact filters and private matter confidentiality remain intact.
No backend/provider/public-graph/deployment change.

See [contract](HANDOFF_ARRIVAL_DESTINATION_ARRIVAL_DESTINATION_ARRIVAL_DESTINATION_ARRIVAL_DESTINATION_ARRIVAL_DESTINATION_ARRIVAL_EVENT.md) and dated synthetic evidence. All prior 3,762 frontend
cases/94 files remain byte-identical; 132 new cases cover every retained pin and
bounded preparation. All 4,521 backend identities and the workflow/eight jobs/
workers/caps/PostgreSQL semantics stay unchanged. PR125 frontend/backend/backend-test/
graph-runtime margins were 108/237/202/89 seconds; publication margin was 28 seconds.
No publication workload is added; profile before additions. Require eight exact-head
successes and measured timing floors before ordinary merge. Main CI is separate.
R03/R05 and legal/corpus/source-rights/lawyer acceptance remain partial.
Next: separately retain this handoff's destination and reconcile it against a fresh
authorized bounded queue, preserving the complete 52-observation purpose and every
earlier observation without rebasing history.


### R03/R05A complete-handoff destination return reconciliation

Explicit UI return retains the complete 52-observation handoff and one separate
verified reduced destination: 53 observations. Capture makes zero action reads/
writes or implicit refresh. The exported original 50-observation return and all
older projections remain unchanged. One fresh authorized bounded containing queue
permits exactly one selected-event metadata GET; omission exposes no saved
metadata or target read. Saved destination/current queue compares independently,
without rebasing older identities, frozen evidence, filters, known packets or flags.

Validate complete history afresh per public operation using private operation-local
checks, with no duplicate full parent validation in a reconciliation helper.
Validate before allocation/eviction; preserve eight entries/thirty minutes/principal/
session/reload closure, opaque URLs and explicit same-firm matter membership.
Withhold weaker handoffs. Failure, denial, expiry and retirement clear panels and
links. Private metadata stays outside public graphs, providers, shared caches and
telemetry. No backend/provider/public-graph/deployment change.

See [contract](HANDOFF_ARRIVAL_DESTINATION_ARRIVAL_DESTINATION_ARRIVAL_DESTINATION_ARRIVAL_DESTINATION_ARRIVAL_DESTINATION_ARRIVAL_DESTINATION_RETURN.md) and dated synthetic evidence. All prior 3,894 frontend
cases/95 files remain byte-identical; 128 new cases cover all 52 retained pins and
the separate destination. All 4,521 backend identities and workflow/eight jobs/
workers/caps/PostgreSQL semantics stay unchanged. PR126 frontend/backend/backend-test/
graph-runtime margins were 102/256/220/88 seconds; publication margin was 23 seconds.
No publication workload is added; profile before additions. Require eight exact-head
successes and measured timing floors before ordinary merge. Main CI remains
separate. R03/R05 and legal/corpus/source-rights/lawyer acceptance remain partial.
Next: a dedicated exact-event handoff carrying this complete 53-observation return
with fresh bounded preparation, preserving every retained observation.


### R03/R05A complete-destination-preserving exact-event handoff

A dedicated fixed-depth purpose carries the complete 53-observation destination
return unchanged. One fresh authorized containing queue and exactly two stable
metadata reads at window one prepare the exact selected event: 55 observations.
All prior selected packets, frozen evidence, seven-field/customer-OR filters,
monotonic history and known same-ID head packets stay bound, including heads
known only to the saved destination. Every public call validates complete history
using private operation-local checks, with no cached verdict or weaker purpose.
Validation precedes allocation/eviction.

Purpose and exact target validate before the single destination metadata GET; a
new opaque token remounts the same selected event. Preparation/current destination
and saved destination/current destination compare independently. Earlier identities
and flags remain intact. Unknown/pending stays explicit; failure, denial and
retirement clear state. Explicit verified return restores only the complete
original 53-observation return, with zero action reads/writes and no further
arrival capture. Unavailable metadata yields selection only. Principal/TTL/request
fences, exact filters and private matter confidentiality remain intact. No backend/
provider/public-graph/deployment change.

See [contract](HANDOFF_ARRIVAL_DESTINATION_ARRIVAL_DESTINATION_ARRIVAL_DESTINATION_ARRIVAL_DESTINATION_ARRIVAL_DESTINATION_ARRIVAL_DESTINATION_EVENT.md) and dated synthetic evidence. All prior 4,022 frontend
cases/96 files remain byte-identical; 137 new cases cover every retained pin and
bounded preparation. All 4,521 backend identities and workflow/eight jobs/workers/
caps/PostgreSQL semantics stay unchanged. PR127 frontend/backend/backend-test/
graph-runtime margins were 133/211/176/77 seconds; publication margin was 28 seconds.
No publication workload is added; profile before additions. Require eight exact-head
successes and measured timing floors before ordinary merge. Main CI is separate.
R03/R05 and legal/corpus/source-rights/lawyer acceptance remain partial.
Next: separately retain this handoff's arrival and reconcile it against a fresh
authorized bounded queue, preserving the complete 55-observation purpose and
every earlier observation without rebasing history.

CI capacity correction for this slice: the first eight-check success left only
21 seconds of frontend margin, so merge was withheld. Profiled stateless shape
and calendar validation removes repeated sort/serialization/date parsing while
retaining fresh complete-history checks and unchanged canonical encoding. All
97 submitted test files remain byte-identical; 35 new boundary/reference cases
bring the suite to 4,194 cases/98 files. Fresh exact-head hosted qualification
and a fresh rebuilt two-lawyer browser fixture remain required before merge.


### Guarded complete-handoff arrival return (55 retained observations)

An explicit verified return retains the complete55-observation purpose plus a
separate arrival56, with zero action reads/writes. Fresh authorized bounded queue
reconciliation uses one exact-event metadata read only when the selected record
is contained. Omission exposes no history. Preparation, saved arrival, older
destination and fresh identities remain independently compared; exact seven
customer/date filters, frozen evidence versions/manifests and independent review
history remain bound. The old53-observation API/projections remain unchanged.
Every public operation revalidates complete history afresh; operation-local
checks avoid duplicate parent validation within reconciliation. No weaker event
purpose, persistent verdict cache, recursive history model or private metadata
in public graphs/providers/shared caches/telemetry. Membership and eight-entry/
30-minute/session/reload/failure closure remain mandatory.

Qualification: unchanged4,194 cases/98 files plus133 new cases, fresh two-lawyer
synthetic browser with early/late arrivals and actual independent reviews before
private edits, full request logs, metadata-only disclosures, denial/omission/
unknown/pending/filter-retirement and reload; all4,521 backend IDs unchanged and
disjoint,11 PostgreSQL races and122 application-image hashes. Require all eight
exact-head checks and30s margins on frontend/backend job/backend test/graph
runtime. Preserve jobs/workers/caps/partitions and PostgreSQL semantics. No new
publication workload; prior margin28s remains a follow-up before adding work.
See the complete-handoff arrival-return contract and dated synthetic evidence.
R03/R05 remain partial; no legal/corpus/rights/lawyer acceptance or deployment.


### Guarded complete-arrival exact-event handoff (56 retained observations)

A dedicated58-observation purpose preserves the complete56 arrival return plus
fresh bounded queue and stable two-read preparation. A single exact destination
GET compares preparation/current and saved arrival/current independently. Explicit
verified return restores original56 unchanged with zero action IO, without another
destination capture. Seven exact customer/date fields/customer OR, frozen evidence
versions/manifests, all known head packets and independent review history stay bound.
Whole history is revalidated per public call with private operation-local checks;
no cached verdict, unchecked export, recursive history model or weaker purpose.
Preserve membership, eight-entry/30-minute/session/reload/failure closure. Private
metadata remains outside public graphs/providers/shared caches/telemetry.

Validation: unchanged4,327 cases/99 files plus142 new cases, fresh two-lawyer
synthetic browser covering actual independent reviews before private edits,
early/late preparations, redirects, stable reads/fences, unknown/pending, denial,
zero-IO original return and reload;4,521 unchanged disjoint backend IDs,11 PG races,
44 deployment contracts and122 application-image hashes. Require all eight exact-
head checks plus30s frontend/backend job/backend test/graph-runtime margins. Jobs,
workers/caps/partitions/PG durability unchanged. No publication workload; prior
publication margin29s requires profiling before additions. See the complete-arrival
handoff contract and dated evidence. R03/R05 remain partial; no legal/corpus/rights/
lawyer acceptance or deployment qualification.

### Guarded complete-handoff destination return (58 retained observations)

Explicit verified UI return now preserves the complete58-observation purpose and
one separately verified destination59 with zero action reads/writes. This extends
the preceding slice's UI behavior while keeping its original56-return API and all
older projections unchanged. A fresh authorized bounded containing queue permits
one exact-event metadata GET; omission exposes no saved history or target read.
Separate destination/current, preparation/current and earlier arrival/current
comparisons preserve all58 pins, saved-only heads, frozen evidence versions and
manifests, chronology/admissions and independent review history without rebasing.
All seven exact customer/date filters and customer OR semantics stay bound.

Every public call revalidates complete history afresh with private operation-local
checks and one full parent validation per reconciliation. No unchecked checker,
cached verdict, recursive history model or weaker event-purpose projection.
Preserve explicit matter membership, eight-entry/30-minute/principal/session/
reload closure and failure/filter/window/target retirement. Private metadata stays
outside public graphs/providers/shared caches/telemetry.

Qualification: unchanged4,469 cases/100 files plus138 new cases; fresh two-lawyer
synthetic early/late destination browser checks with actual independent reviews
before private edits, full request logs, omission/denial/packet substitution,
unknown/pending, exact filters, metadata-only disclosures and reload. Preserve all
4,521 disjoint backend identities,11 PostgreSQL races,44 deployment contracts and
122 application-image hashes. Require all eight exact-head successes and30s margins
on frontend/backend job/backend test/graph runtime. Jobs/workers/caps/partitions/PG
semantics remain unchanged. No publication workload; preceding margin26s requires
profiling before additions. See [contract](COMPLETE_HANDOFF_DESTINATION_RETURN.md)
and dated synthetic evidence. R03/R05 and legal/corpus/rights/lawyer acceptance
remain partial. Next: prepare an exact-event handoff carrying all59 observations;
its implementation and PR are unstarted in this slice.

### Guarded complete-destination exact-event handoff (59 retained observations)

A dedicated61-observation purpose preserves the complete59 destination return,
one fresh queue observation and one stable preparation. Explicit preparation uses
two exact-event window1 reads with scope/token fences before and after each read;
the first failure prevents the second read. One fresh destination GET compares
preparation/current and saved destination/current independently. A verified
explicit return restores original59 unchanged with zero action IO, without a new
arrival capture. All59 pins, known/saved-only head packets, frozen evidence
versions/manifests, exact seven customer/date fields/customer OR, chronology,
admissions and independent review history remain bound without rebasing.

Every public call revalidates complete history afresh with private operation-local
checks. No unchecked history export, persistent verdict cache, recursive history
model or weaker purpose projection. Preserve explicit matter membership, eight
entries/30minutes/principal/session/reload closure and complete failure/scope/
filter/window/target retirement. Private metadata remains outside public graphs,
providers, shared caches and telemetry.

Validation: unchanged4,607 cases/101 files plus147 new cases; a fresh two-lawyer
synthetic browser with actual independent reviews before private edits, exact
filters, early/late preparations, bounded reads, redirects, stale replies, denial,
unknown/pending, zero-IO original return, metadata-only history and reload. Keep
all4,521 backend identities and disjoint partitions,11 PostgreSQL races,44
deployment contracts and122 application-image hashes. Require all eight exact-head
checks and30s frontend/backend job/backend test/graph-runtime margins. Jobs,
workers/caps/partitions/PG semantics remain unchanged. No publication workload;
preceding PR publication margin26s requires profiling before additions. See the
[contract](COMPLETE_DESTINATION_EVENT_HANDOFF.md) and dated synthetic evidence.
R03/R05 and legal/corpus/rights/lawyer/deployment acceptance remain partial.
Next: separately retain this complete61-observation purpose and its verified
arrival, then reconcile through a fresh authorized bounded queue. That successor
implementation and PR are unstarted in this slice.

### Guarded complete-destination handoff arrival return (61 retained observations)

Explicit verified UI return now retains the complete61-observation purpose plus
a separately verified arrival62 with zero action IO. The original59-return API
body/signature and every older return projection remain unchanged. A fresh
authorized bounded containing queue permits one exact-event metadata GET; omission
exposes no saved history or target read. Compare saved arrival/current,
preparation/current and earlier destination/current independently, preserving
all61 pins, known/saved-only head packets, frozen evidence versions/manifests,
chronology, admissions, exact seven customer/date fields/customer OR and independent
review history without rebasing.

Every public call revalidates complete history afresh, with private local checks
and one full parent validation per reconciliation. No unchecked checker, cached
verdict, recursive history model or weaker event purpose. Preserve explicit matter
membership, eight entries/30minutes/principal/session/reload closure and complete
failure/filter/scope/window/target retirement. Private metadata stays outside public
graphs/providers/shared caches/telemetry.

Validation: unchanged4,754 cases/102 files plus143 new cases; fresh two-lawyer
synthetic early/late arrival captures, actual independent reviews before private
edits, exact filters, zero-IO capture, metadata-only disclosures, omission, packet
substitution, denial, unknown/pending, stale replies and reload. Preserve4,521
backend identities/disjoint partitions,11 PostgreSQL races,44 deployment contracts
and122 application-image hashes. Pre-publication local profiling measured clean
TypeScript4.6s/4.2s and two-worker suite50.4s/52.2s before/after. Actual hosted
qualification still requires all eight successes and30s frontend/backend job/
backend test/graph-runtime margins. Jobs/workers/caps/partitions/PG semantics stay
unchanged. No publication workload; profile before additions. See the
[contract](COMPLETE_DESTINATION_HANDOFF_ARRIVAL_RETURN.md) and dated engineering
evidence. R03/R05 and legal/corpus/rights/lawyer/deployment acceptance remain partial.
Next: a full-purpose exact-event handoff carrying the complete62-observation return
plus fresh queue and preparation observations. That successor implementation and
PR are unstarted in this slice.

### Complete arrival return to exact-event handoff (62 retained observations)

Explicit preparation retains the complete62 arrival return plus a fresh queue
and stable preparation, totaling64 observations. Two guarded `window=1` reads
must agree with the fresh authorized containing queue. Opening performs one
exact-event metadata GET, with independent preparation/current and saved
arrival/current comparisons. Verified explicit return restores original62
unchanged with zero action IO; the new destination is not captured in this slice.
Omission exposes no saved history or target read. Exact seven customer/date
fields, customer OR, evidence versions/manifests, all retained packets and review
history remain intact. No weaker purpose, cached verdict or permission bypass.

Validation adds152 cases to unchanged4,897 cases/103 files, complete frontend
profiling/build, a fresh two-lawyer synthetic browser rehearsal with18 actual
private edits,11 PostgreSQL races,44 deployment contracts,4,521 disjoint backend
identities and122 image-source hashes. CI jobs/workers/caps/partitions/semantics
stay unchanged; actual exact-head eight-check success and30s frontend/backend
job/test/graph-runtime margins remain merge gates. No publication workload or
unchanged-code timing retry. See [contract](COMPLETE_ARRIVAL_EVENT_HANDOFF.md)
and dated engineering evidence. R03/R05 and legal/corpus/rights/lawyer/deployment
acceptance remain partial. Next: a separately guarded complete64 destination
return; its implementation and PR are not included here.

### Complete arrival handoff destination return (64 retained observations)

Explicit verified return preserves the complete64 purpose plus a separate reduced
destination, totaling65 observations, with zero action IO. The original62-return
function body/signature and every older return projection remain unchanged.
A fresh authorized bounded containing queue permits one exact-event metadata GET;
omission exposes no saved history or target read. Saved destination/current,
preparation/current and earlier arrival/current comparisons remain independent,
with all64 pins, known/saved-only heads, evidence versions/manifests, exact seven
customer/date fields/customer OR and independent review history intact.

Public operations validate complete history afresh through private local checks,
with exactly one complete parent validation in reconciliation. No unchecked
checker, cached verdict, recursive history model, weaker event purpose or matter
permission bypass. Preserve eight entries/30minutes/principal/session/reload and
failure/filter/scope/window/target retirement; private metadata remains outside
public graphs/providers/shared caches/telemetry.

Validation adds148 destination-return cases and38 scalar-comparison cases to
unchanged5,049 cases/104 files, clean TypeScript and
full two-worker profiles/build, a fresh two-lawyer synthetic rehearsal with19
actual private edits after independent reviews,11 real PostgreSQL races,44
deployment contracts,4,521 disjoint backend identities and122 image-source hashes.
Jobs/workers/caps/partitions/PG semantics stay unchanged. Eight exact-head successes
and30s frontend/backend job/test/graph-runtime margins remain merge gates, with
preceding-main CI qualified separately. No publication workload or unchanged-code
timing retry. See [contract](COMPLETE_WHOLE_ARRIVAL_DESTINATION_RETURN.md) and dated
engineering evidence. R03/R05 and legal/corpus/rights/lawyer/deployment acceptance
remain partial. Next: a complete65-preserving exact-event handoff plus fresh queue
and preparation; its implementation and PR are unstarted in this slice.


The initial frontend check passed in272/300 seconds but failed the30-second
headroom gate; it was not merged and remaining CI work was cancelled. Profiling
identified repeated key and scalar-identity serialization. Stateless exact-key
and scalar-data comparisons remove that work, with canonical fallback for
unsupported values, no retained verdict and an unchanged canonical serializer.
All5,197 existing cases/105 files remain byte-identical;38 new equivalence cases
cover10,000 record pairs and edge cases. Full suite/build and a fresh complete
browser rehearsal qualify the substantive fix before new exact-head CI.


### Complete destination-history exact-event handoff (65 retained observations)

A dedicated purpose retains the complete65 destination return plus fresh queue
and stable preparation:67 observations. Explicit preparation uses exactly two
selected-event window1 metadata GETs with scope/token/operation fences before and
after both awaits; first failure stops the second. Destination opening uses one
exact metadata GET. Preparation/current and saved destination/current comparisons
stay independent. Explicit verified return restores the original65 unchanged,
without action IO or another arrival capture. Omission exposes no saved history
or target read; partial, conflicting and redirected inputs reject.

All65 selected pins, known/saved-only heads, evidence versions/manifests, chronology,
revisions/flags/admissions, exact seven customer/date fields/customer OR and
independent review history remain intact. Full history is validated afresh per
public call using private local checks and the unchanged stateless comparison
primitives/canonical fallback. No unchecked export, cached verdict, recursive
history model, weaker purpose or permission bypass. Preserve eight entries,
30minutes, principal/session/reload and failure/filter/window/target retirement;
private metadata stays outside public graphs/providers/shared caches/telemetry.

Validation adds168 cases to unchanged5,235 cases/106 files; clean TypeScript,
full two-worker profiles/build and a fresh two-lawyer synthetic rehearsal with20
actual private edits after independent reviews pass. Two full browser-rehearsal attempts exposed duplicate comparison/disclosure labels;
distinct new root labels and uniqueness assertions, full rebuild and fresh database
qualified the fix. Both failed attempts and all earlier assertions remain retained.
Eleven real PostgreSQL races,44 deployment contracts,4,521 disjoint backend identities
and122 application-image hashes pass. CI jobs/workers/caps/partitions/PG semantics
remain unchanged. Eight exact-head successes and30s frontend/backend job/test/graph
margins remain merge gates; preceding-main CI is qualified separately. No publication
workload, unchanged-code timing retry or bypass. Actual CI/merge receipts remain
separate from local capture. See [contract](COMPLETE_DESTINATION_HISTORY_EVENT_HANDOFF.md)
and dated engineering evidence. R03/R05 and legal/corpus/rights/lawyer/deployment
acceptance remain partial. Next: guarded complete67 arrival return; its implementation
and PR are unstarted in this slice.


### Complete destination-history arrival return (67 retained observations)

Explicit verified return now retains the complete original67 purpose unchanged
plus one separate reduced arrival:68 observations,with zero action IO. The
original exported65-return signature/body and all older APIs/projections remain
unchanged. A fresh authorized bounded containing queue permits one exact selected
metadata GET;omission reveals no saved identities,target scan,retry or fallback.
Saved arrival/current,preparation/current and earlier destination/current are
compared independently without rebasing. Preserve all67 pins,known/saved-only
heads,evidence versions/manifests,chronology,revisions/flags/admissions,exact7
customer/date/source-date/bucket fields/customer OR and independent review history.

Full history is validated afresh per public operation through private local
checks,with one full parent validation within reconciliation. No unchecked export,
cached verdict,recursive history abstraction,weaker event purpose or permission
bypass. Eight entries/30minutes/principal/session/reload and failure/filter/window/
scope/token/target retirement remain intact;private metadata stays outside public
graphs/providers/shared caches/telemetry. Existing stateless comparisons and the
canonical fallback/serializer are unchanged.

155 new cases extend unchanged5403 cases/107 files;all5558 cases/108 files and
build pass. Fresh two-lawyer synthetic rehearsal preserves both original67
purposes through21 actual private edits,with separate early/late captures before
denial-probe allocations evict old rows. Eleven real PG races,44 deployment
contracts,4521 disjoint backend identities and122 app-image hashes pass. Workflow,
eight jobs,workers,caps,architectures,partitions and PG semantics stay unchanged.
All8 latest exact-head successes and30s frontend/backend job/test/graph margins
remain merge gates;preceding-main CI is separately qualified. No publication
workload,unchanged-code timing retry or billing guarantee. See
[contract](COMPLETE_DESTINATION_HISTORY_ARRIVAL_RETURN.md) and dated engineering
evidence. R03/R05 and legal/corpus/rights/lawyer/deployment acceptance remain partial.
Next:all68-preserving exact-event handoff plus fresh queue and stable preparation;
its implementation and PR are unstarted in this slice.


### Complete arrival-history exact-event handoff (68 retained observations)

A dedicated purpose retains the complete original 68-observation arrival return
unchanged plus fresh queue and stable preparation: 70 observations. Explicit
preparation requires two stable selected-event window1 metadata GETs with fences
before/after both awaits; first failure stops the second. Opening performs one
exact metadata GET. Preparation/current and saved arrival/current comparisons
remain independent without rebasing. Explicit verified return restores the
original 68 unchanged with zero action IO; no further destination is captured.

Preserve all 68 pins, known/saved-only heads, immutable evidence versions/manifests,
chronology/revisions/flags/admissions, all seven exact customer/date/source-date/
bucket fields, customer OR and independent review history. Full history is
validated afresh per public operation using private local checks and unchanged
stateless comparisons/canonical fallback. No unchecked export, cached verdict,
recursive history abstraction, weaker purpose or permission bypass. Eight rows,
30-minute expiry, principal/session/reload and failure/filter/window/scope/token/
target retirement remain intact. Private metadata stays outside public graphs,
providers, shared caches and telemetry.

173 new cases extend unchanged 5,558 cases/108 files; all 5,731 cases/109 files and
build pass. Fresh two-lawyer synthetic rehearsal preserves original 68 early/late
returns through 22 actual private edits following independent reviews. Eleven real
PG races, 44 deployment contracts, 4,521 disjoint backend identities and 122 app-image
hashes pass. Workflow,eight jobs,workers,caps,architectures,partitions and PG
semantics remain unchanged. Require eight latest exact-head successes and 30s
frontend/backend job/backend test/graph-runtime margins,with preceding-main CI
separately qualified. No publication workload,unchanged-code timing retry or
billing guarantee. See [contract](COMPLETE_ARRIVAL_HISTORY_EVENT_HANDOFF.md) and
dated engineering evidence. R03/R05 and legal/corpus/rights/lawyer/deployment
acceptance remain partial. Next:guarded all70 destination return; implementation
and PR are unstarted in this slice.



### Complete arrival-history destination return (70 retained observations)

Explicit verified return retains the original70 purpose unchanged plus one
separate reduced destination:71 observations, with zero action IO. The original
70-event return restoring68 and every older API/projection stay unchanged.
Fresh authorized bounded containing-queue observation permits one exact metadata
GET; omission exposes no saved history, target read, scan, retry or fallback.
Saved destination/current, preparation/current and earlier arrival/current
comparisons remain independent, without rebasing.

Preserve all70 pins, known/saved-only heads, evidence versions/manifests, chronology,
revisions/flags/admissions, exact seven customer/date/source-date/bucket fields,
customer OR and independent review history. Full history is revalidated per public
operation with one complete parent validation within reconciliation. No unchecked
export, verdict cache, recursive abstraction, weaker event purpose or permission
bypass. Eight entries/30minutes/principal/session/reload and all retirement fences
remain intact. Private metadata stays outside public graphs/providers/shared
caches/telemetry; stateless comparison and canonical fallback remain unchanged.

160 new cases extend unchanged5731 cases/109 files; all5891 cases/110 files and
build pass. Fresh two-lawyer rehearsal preserves both original70 purposes through
23 actual private edits following independent reviews. The prepared schedule was
corrected before rehearsal: stronger71 return102 disables older preparation;
existing denial probes103..105 remain, then original100/101 produce successful
returns106/107. No replacement event or weakened earlier assertion. Eleven real
PG races,44 deployment contracts,4521 disjoint backend identities and122 app-image
hashes pass. Workflow/eight jobs/workers/caps/architectures/partitions/PG semantics
remain unchanged. Eight latest exact-head successes and30s frontend/backend job/
backend test/graph-runtime margins remain merge gates; preceding-main CI is
qualified separately. No publication workload, unchanged-code timing retry or
billing guarantee. See [contract](COMPLETE_ARRIVAL_HISTORY_DESTINATION_RETURN.md)
and dated engineering evidence. R03/R05 and legal/corpus/rights/lawyer/deployment
acceptance remain partial. Next:all71-preserving exact-event handoff with fresh
queue and stable preparation; implementation and PR are unstarted in this slice.


### Complete destination-chain exact-event handoff (71 retained observations)

A dedicated purpose retains the complete original71 return unchanged plus fresh
queue and stable preparation:73 observations. Explicit preparation uses two stable
selected-event window1 metadata GETs with operation/scope/token fences before and
after both awaits; first failure stops the second. Opening uses one exact metadata
GET. Preparation/current and saved destination/current remain independent.
Explicit verified return restores original71 unchanged with zero action IO; no
further arrival is captured.

All71 pins, known/saved-only heads, evidence versions/manifests, chronology,
revisions/flags/admissions, seven exact customer/date/source-date/bucket fields,
customer OR and independent review history remain intact. Validate full history
afresh per public call through private local checks and unchanged stateless
comparisons/canonical fallback. No unchecked export, cached verdict, recursive
abstraction, weaker purpose or permission bypass. Preserve eight rows/30minutes,
principal/session/reload and all retirement fences. Private metadata stays outside
public graphs/providers/shared caches/telemetry.

179 new cases extend unchanged5891 cases/110 files; all6070 cases/111 files and
build pass. Fresh two-lawyer rehearsal preserves original71 returns106/107 in new73
purposes108/109 before/after edit24, original71return110 and selection-only111..113.
Eleven real PG races,44 deployment contracts,4521 disjoint backend identities and
122 app-image hashes pass. Workflow/eight jobs/workers/caps/architectures/partitions/
PG semantics stay unchanged. Require eight latest exact-head successes and30s
frontend/backend job/backend test/graph-runtime margins; qualify preceding-main CI
separately. No publication workload, unchanged-code timing retry or billing
guarantee. See [contract](COMPLETE_DESTINATION_CHAIN_EVENT_HANDOFF.md) and dated
engineering evidence. R03/R05 and legal/corpus/rights/lawyer/deployment acceptance
remain partial. Next:guarded complete73 arrival return; implementation and PR
are unstarted in this slice.


### Complete destination-chain arrival return (73 retained observations)

Explicit verified return preserves the complete original73 handoff unchanged plus
one separate reduced arrival:74 observations, with zero action IO. Original
73-event return restoring71 and all older APIs/projections stay unchanged. Fresh
authorized bounded containing queue permits one exact metadata GET; omission
reveals no saved details, target read, scan, retry or fallback. Saved arrival/
current, preparation/current and earlier saved destination/current remain
independent, without rebasing.

Preserve all73 pins, known/saved-only heads, evidence versions/manifests, chronology,
revisions/flags/admissions, seven exact customer/date/source-date/bucket fields,
customer OR and independent review history. Validate complete history afresh per
public call, with one complete parent validation within reconciliation. No
unchecked export, cached verdict, recursive abstraction, weaker event purpose or
permission bypass. Preserve eight rows/30minutes/principal/session/reload and all
retirement fences. Private metadata stays outside public graphs/providers/shared
caches/telemetry; identity comparison rules/canonical fallback remain unchanged.

185 new cases (165 arrival guards plus20 equality parity cases) extend unchanged6070
cases/111 files; all6255 cases/113 files and
build pass. Fresh two-lawyer rehearsal preserves original73 early108/late109 in
successful74 returns114/115 around actual edit25. Stronger return110 disables
older73 preparation; existing111..113 denial probes remain, with no extra event
or replaced original. Eleven real PG races,44 deployment contracts,4521 disjoint
backend identities and122 app-image hashes pass. Workflow/eight jobs/workers/
caps/architectures/partitions/PG semantics remain unchanged. Require eight latest
exact-head successes and30s frontend/backend job/backend test/graph-runtime
margins; preceding-main CI is separately qualified. No publication workload,
unchanged-code timing retry or billing guarantee. See
[contract](COMPLETE_DESTINATION_CHAIN_ARRIVAL_RETURN.md) and dated engineering
evidence. R03/R05 and legal/corpus/rights/lawyer/deployment acceptance remain partial.
Next:all74-preserving exact-event handoff with fresh queue and stable preparation;
implementation and PR are unstarted in this slice.

Initial frontend success left19s, below the30s gate;that head was not merged.
CPU sampling identified repeated root canonical equality. A bounded stateless
plain-data fast path at two call sites preserves canonical fallback and complete
history validation,with all6235 initial cases/112files unchanged. Full local
suite60.745->53.820s;freshDB/fullbrowser rerun required before corrected submission.
No workflow/cap/worker/partition change or unchanged-code timing retry.

### Complete arrival-chain exact-event handoff (74 retained observations)

The complete original74 return remains unchanged,including original73 queue/preparation
and separate arrival. Fresh queue and stable preparation make76 observations. Explicit
preparation performs two stable window1 reads;opening uses one exact metadata GET.
Saved arrival/current,preparation/current and earlier saved destination/current remain
independent. Explicit verified return restores original74 unchanged with zero action IO;
no further destination capture or weaker purpose is added.

Preserve all74 pins,known/saved-only heads,evidence versions/manifests,history,seven exact
filters,customer OR and all confidentiality/retirement fences. Complete history is checked
afresh per public call;stateless equality fast path,20 parity cases and canonical fallback
are unchanged. All6255 prior cases/113 files remain byte-identical;184 new cases bring
the passing total to6439/114 files. Fresh two-lawyer rehearsal retains114/115 in116/117
around actual edit26,zero-IO original74return118 and selection-only119..121.

Eleven realPG races,44 deployment contracts,4521 disjoint backend IDs and122 app-image
hashes pass. Workflow,eight jobs,workers,caps,architecture,partitions andPG semantics stay.
Require eight latest exact-head successes and30s frontend/backend job/test/graph margins;
preceding-main CI qualified separately. No unchanged-code timing retry or billing guarantee.
See [contract](COMPLETE_ARRIVAL_CHAIN_EVENT_HANDOFF.md) and dated engineering evidence.
R03/R05 and legal/corpus/rights/lawyer/deployment acceptance remain partial. Next:complete76
destination return;implementation and PR unstarted in this slice.

### Complete arrival-chain destination return (76 retained observations)

Explicit verified capture retains the entire original76 handoff unchanged, including
original74, its queue/preparation and both timestamps. One separate reduced destination
makes77 observations, with zero action IO. The original76 return restoring74 and older
APIs remain unchanged. One authorized bounded containing queue permits one exact metadata
GET; omission reveals no history, scan, retry or fallback. Saved destination/current,
preparation/current and earlier saved arrival/current remain independent.

All76 pins, known/saved-only heads, evidence versions/manifests, history and seven exact
filters remain. Complete history is checked afresh per public call; reconciliation
validates one complete parent before private local checks. Stateless fast path,20 parity
cases and canonical fallback remain. Preserve eight rows/30minutes/principal/session/
reload and all retirement/confidentiality fences. No weaker event purpose or permission
bypass; private metadata stays outside public graphs/providers/shared caches/telemetry.

All6609 tests/115 files and build pass;170 new cases extend unchanged6439/114. Fresh
two-lawyer rehearsal preserves originals116/117 through successful77 returns122/123 around
actualedit27; stronger return118 disables older preparation, existing119..121 probes remain.
Eleven realPG races,44 deployment contracts,4521 disjoint backend IDs and122 app-image
hashes pass. Workflow/eight jobs/workers/caps/architecture/partitions/PG semantics remain.
Require eight exact-head successes and30s frontend/backend job/test/graph margins;
preceding-main CI qualified separately. No new publication workload,unchanged-code timing
retry or billing guarantee. See [contract](COMPLETE_ARRIVAL_CHAIN_DESTINATION_RETURN.md)
and dated evidence. R03/R05/legal/corpus/rights/lawyer/deployment acceptance remains partial.
Next:original77 exact-event handoff; implementation and PR unstarted in this slice.

### Complete destination-chain exact-event handoff (77 retained observations)

Original77 remains byte-identical, including complete76 preparation/queue/stamps and
separate destination. Fresh queue and stable preparation make79 observations. Two stable
window1 reads prepare; one exact metadata GET opens; verified return restores original77
with zero action IO and no arrival capture. All evidence pins, filters, review history,
private-matter confidentiality, independent identity comparisons and retirement fences
remain. No weaker purpose or cached verdict; stateless comparisons/canonical fallback
unchanged. All6798 tests/116 files and build pass;189 new cases extend unchanged6609/115.
Fresh two-lawyer rehearsal retains122/123 in124/125 around actualedit28, original77return126
and selection-only127..129. Eleven realPG races,44 deployment contracts,4521 disjoint IDs
and122 app-image hashes pass. Workflow/eight jobs/workers/caps/architecture/partitions/PG
semantics unchanged. Require all8 exact-head successes and30s frontend/backend job/test/
graph margins; preceding-main CI qualified separately. No publication workload, timing
retry or billing guarantee. See [contract](COMPLETE_FULL_DESTINATION_EVENT_HANDOFF.md)
and dated evidence. R03/R05 and legal/corpus/rights/lawyer/deployment stay partial.
Next:original79 arrival-return slice; implementation and PR unstarted.

### Complete destination-chain arrival return (79 retained observations)

Explicit verified return preserves the complete original79 handoff and adds a separate
reduced arrival:80 observations. Capture has zero action IO; fresh authorized queue plus
one exact metadata GET reconciles it. Independent comparisons, exact customer/date filters,
evidence versions, confidentiality and review history remain. Original77/earlier74 return
APIs and older projections remain unchanged. Stronger arrivals disable weaker preparation.
All6,973 frontend cases/117 files and build pass;175 new cases extend unchanged6,798/116.
Fresh two-lawyer rehearsal preserves124/125 in returns130/131 around actualedit29, stronger
return126 and selection-only127..129. Eleven realPG cases,44 deployment contracts,4,521
disjoint IDs and122 app-image hashes pass. Preceding-main eight-job qualification is
separate. Merge requires all8 exact-head successes and30s frontend/backend job/test/graph
margins;workflow,workers,caps,architecture,partitions andPG semantics remain unchanged.
No publication workload,timing retry,billing promise or deployment. See
[contract](COMPLETE_FULL_DESTINATION_ARRIVAL_RETURN.md) and dated evidence. R03/R05 and
legal/corpus/rights/lawyer acceptance remain partial. Next:original80 exact-event handoff;
implementation and PR unstarted.

### Complete arrival-chain exact-event handoff (80 retained observations)

Original 80 remains byte-identical, including complete79 handoff/preparation/queue/stamps and
separate arrival. Fresh queue and stable preparation make 82 observations. Two stable
window1 reads prepare; one exact metadata GET opens; verified return restores original 80
with zero action IO and no destination capture. All evidence pins, filters, review history,
private-matter confidentiality, independent identity comparisons and retirement fences
remain. No weaker purpose or cached verdict; stateless comparisons/canonical fallback
unchanged. All 7,167 tests/118 files and build pass; 194 new cases extend unchanged 6,973/117.
Fresh two-lawyer rehearsal retains130/131 in132/133 around actualedit30, original 80return134
and selection-only135..137. Eleven realPG races,44 deployment contracts,4521 disjoint IDs
and 122 app-image hashes pass. Workflow/eight jobs/workers/caps/architecture/partitions/PG
semantics unchanged. Require all eight exact-head successes and 30s frontend/backend job/test/
graph margins; preceding-main CI qualified separately. No publication workload, timing
retry or billing guarantee. See [contract](COMPLETE_FULL_ARRIVAL_EVENT_HANDOFF.md)
and dated evidence. R03/R05 and legal/corpus/rights/lawyer/deployment stay partial.
Next:original 82 destination-return slice; implementation and PR unstarted.

### Complete arrival-chain destination return (82 retained observations)

Explicit verified return preserves the complete original 82 handoff and adds a separate
reduced destination:83 observations. Capture has zero action IO; fresh authorized queue plus
one exact metadata GET reconciles it. Independent comparisons, exact customer/date filters,
evidence versions, confidentiality and review history remain. Original 80/earlier77 return
APIs and older projections remain unchanged. Stronger destinations disable weaker preparation.
All 7,348 frontend cases/119 files and build pass;181 new cases extend unchanged 7,167/118.
Fresh two-lawyer rehearsal preserves132/133 in returns138/139 around actualedit31, stronger
return134 and selection-only135..137. Eleven realPG cases,44 deployment contracts,4,521
disjoint IDs and 122 app-image hashes pass. Preceding-main eight-job qualification is
separate. Merge requires all eight exact-head successes and 30s frontend/backend job/test/graph
margins;all eight jobs,workers,caps,job runners,disjoint node groups andPG semantics remain.
Complete32-case review step moves from frontend to measured ARM backend headroom;48 x86
workspace permission cases remain.
No publication workload,timing retry,billing promise or deployment. See
[contract](COMPLETE_FULL_ARRIVAL_DESTINATION_RETURN.md) and dated evidence. R03/R05 and
legal/corpus/rights/lawyer acceptance remain partial. Next:original 83 exact-event handoff;
implementation and PR unstarted.

Initial exact-head CI passed all eight but frontend margin was only20s, below30s;
merge held. Root handoff CPU profiling drove current-timestamp parse reuse and existing
stateless scalar comparison reuse with canonical fallback. Complete history validation,
all118 prior test files and caps remain unchanged. Changed-source qualification
adds a 65-boundary differential test, full suite/build and fresh browser rehearsal.
Local two-worker suite:88.849 to68.679s. Initial and changed-source evidence remain
separate; new exact-head margins are required.

Source-only head also held at276s/24s frontend margin. Root CI load correction moves
the entire unchanged32-case review step to existing backend capacity (previously256s
job margin), preserving48 x86 workspace cases,all4,521 disjoint node IDs,eight jobs,
two workers and all caps. LinuxARM32-case verification passes in21.71s. No new
publication workload;new balanced-head CI must qualify all four receiving margins.

### Complete last-destination exact-event handoff (83 retained observations)

Original 83 stays byte-identical, including its complete 82 handoff and separate destination.
Fresh queue and stable preparation make 85 observations. Two stable window 1 metadata reads
prepare;one exact metadata GET opens;explicit return restores original 83 with zero action IO
and no arrival capture. All pins, exact filters/evidence versions, independent review history,
confidentiality and retirement fences remain. No cached verdict or weaker projection.
All 7,547 frontend cases/120 files and build pass;199 new cases extend unchanged 7,348/119.
Fresh two-lawyer rehearsal retains 138/139 in 140/141 around actualedit 32, zero-action return 142
and selection-only 143..145. Eleven realPG cases,44 deployment contracts,4,521 disjoint IDs
and 122 application image hashes pass. Eight jobs/workers/caps/runners/PG semantics and the existing
32-case backend/48-case x 86 allocation remain. Require all 8 exact-head successes and 30 s
frontend/backend job/test/graph margins;preceding-main CI qualified separately. No new
publication workload, timing retry, billing promise or deployment. See
[contract](COMPLETE_LAST_DESTINATION_EVENT_HANDOFF.md) and dated evidence.
R03/R05/legal/corpus/rights/lawyer acceptance remain partial. Next:original 85 arrival-return;
implementation and PR unstarted. Concise new artifact filenames avoid component-size limits.
