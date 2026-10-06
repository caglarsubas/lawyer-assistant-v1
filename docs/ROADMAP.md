# Approved product roadmap and implementation ledger

Baseline: 4 October 2026; research reconciliation: **5 October 2026**. Planning envelope: **30–36 weeks**, conditional on approximately eight FTE, lawful source access and protected Turkish legal-editor capacity. This is a delivery sequence, not a claim that elapsed weeks, legal reviews or corpus acquisition have occurred. Re-estimate from representative acquisition/review throughput before committing a pilot date; the attachments' shorter fixed calendar and longer staffing estimates are inputs to that check, not replacement promises.

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
Existing source/mapping/publication code is reused; the
research does not authorize real approvals, vendor contact or bulk acquisition.
Dependencies refer to completion of the relevant gate, not just code availability.

| ID / priority | Delivery packet | Dependencies / accountable lead | Exit evidence |
|---|---|---|---|
| **R01 / P0, in progress** | Source, asset and semantic qualification: offline catalogs, legal-analysis/scenario contracts, provider/evaluation dossier, physical evidence verifier, extraction comparator and reproducible calibration studies implemented; representative calibration and review pending | Legal ontology owner + data/source lead with application/security owners; source/provider dependencies documented | Source uses and routes reviewed; sample errors/reviewer time measured; argument/scenario fixtures adjudicated; provider processing/spend controls qualified; added effort estimated. Passing the dossier validator grants no approval |
| **R02 / P0, partial** | Multi-source snapshots, private preparation, exact public evidence, external public/private approvals, per-source deployment-wide grants/expiry and live revocation implemented; renewal requires a freshly reviewed release. Restricted-audience serving, same-release renewal and five-job/cancellation qualification remain | R01 contracts; actual source reviews remain mandatory; backend/platform + knowledge engineers | Revocation of any required source invalidates its dependent release/work; competing changes cannot produce mixed snapshots; cross-source evidence and privacy checks pass; bounded cancellation, throughput and lock latency measured on declared hardware |
| **R03 / P0** | First genuinely reviewed contract corpus: RG ordinary/mükerrer manifest; amendment/transition candidates; MBS reconciliation; TBMM enacted/history distinction; exact provisions and historical versions | R01 lawful samples and protected reviewers; R02 for combined releases; editors + ingestion team | Reviewed corpus and exact evidence ready for analysis; amendment chains/historical queries pass; discrepancies visible. Full legal-analysis/export qualification additionally requires R04, the relevant R05 decision slice and R05A |
| **R04 / P1** | Turkish lexical/citation normalization, local embedding and reranker evaluation, structured context packing; pinned model/index versions | R01 development benchmark; R03 representative approved corpus; retrieval/ML + legal adjudicators | Exact identifiers and original quotes preserved; hybrid and graph/metadata/rerank ablations on one snapshot; thresholds, error slices and resource budgets reported; no private-data or adverse-recall regression |
| **R05 / P1** | Decision population and research: proceeding/decision/manifestation identity; allegation/finding/reasoning/result/dissent roles; citation ambiguity queue; reviewed authority-treatment events; independent contrary-authority branch | R01 judicial source/effect contracts, R02, R04; knowledge engineers + domain editors | Supporting and adverse passages are inspectable with role, version, institution epoch and scope; treatment is not inferred from citation; missing courts/periods and unknown finality remain explicit |
| **R05A / P1, contract milestone** | Local legal analysis: issue/premise/rule/application/alternative artifact, adverse checks, bounded consistency/correction, Standard/Deep budgets, checkpoints and claim dependencies | R01 schemas; R03–R05 representative contract evidence; application/retrieval engineers + legal adjudicators | First contract task reaches reviewable analysis/export; consequential steps traceable; defects repaired or withheld; correction and depth compared with single-pass/Standard baselines |
| **R05B / P1, optional connected mode** | Sanitized BYOK deep search: local abstraction/fidelity, exact release, isolated vault/broker, OpenAI/Anthropic/Gemini adapters, untrusted return path and local application | R01 privacy/provider contracts; common broker/sanitizer qualification; R04–R05A for verification/final analysis; application/security + legal owners | Each adapter separately passes privacy, fidelity, authorization, entitlement/retention, cost/retry and citation gates. No private files, silent fallback or unapproved context; remote-tool disclosure explicit; disconnected operation independent |
| **R06 / P1** | Commercial/employment depth: issue/element/exception templates, non-equivalent terms, fact comparability, evidence gaps, audited calculation rules/parameters and firm playbooks | R03–R05A applicable source packs; R05B only for connected option; domain editors + product team | Practice scenarios pass; calculations expose event/basis dates, units, rounding, rules and missing inputs; no confident number on unresolved critical data; corrections and dependency re-review work |
| **R07 / P1** | Corpus operations/offline delivery: watermarks, signed full/delta packages, impact queues, restore/rollback and retention; bounded research jobs, revocation, cancellation, usage/spend and provider-state reconciliation | R02 manifest design starts early; local gate after R03–R06, connected gate after R05B; platform/security + source owners | Exact offline imports/recovery and stale-work handling pass; five-job operations respect privacy/budget; canceled/partial/ambiguous remote jobs visible; local deletion never claimed to erase provider-retained data |
| **R08 / release gate** | Lawyer-adjudicated legal/security/usefulness qualification and 10–20-lawyer pilot; local and connected modes scored separately | R01–R07 relevant gates; product owner + independent legal/security reviewers | Existing ~1,000-task/≥3,000-claim criteria plus argument/correction/depth/privacy/fidelity gates pass; signed-in workflow, offline recovery and preparation-time benefit accepted. Core qualification does not qualify BYOK adapters |

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
| Matter foundation | Implemented baseline | Authenticated sessions, CSRF, explicit membership, encrypted records/originals, audit metadata, offline user/member administration, session revocation | SSO/MFA, customer identity integration, broader concurrency/load qualification |
| Private portfolio/workbench | Implemented baseline | Many-to-many customer/workspace tags, date filters, workspace files/comments, three adjustable panels, contextual product guide and calendar portfolio summaries | Lawyer workflow acceptance, large-portfolio load/accessibility qualification, evaluated conversational guidance |
| Provider integration | Partial | Server-side adapter, restricted relay with optional explicitly approved laptop tunnel, authenticated lawyer tenant, local model/context checks, native fallback configuration inspection, deployed synthetic exact-evidence completion | Representative Turkish legal model evaluation, concurrency/context qualification, stronger runtime attestation, tunnel inspection/retention qualification and revalidation on provider changes |
| BYOK deep research | Pending | No external research-provider adapter or multi-user key vault; existing gateway is a narrow source fetcher | R05B privacy/fidelity gates, exact scenario release, isolated broker/vault, all three adapters, independent citation admission, local application and per-provider qualification |
| Graph A ontology | Partial | National category catalog, RDF modules, SKOS, relationship metadata, provenance/time model, SHACL | Legal-owner signoff, source-backed institutions/norms/competence, persistent identity/standards mappings, reviewed aliases and non-equivalent concepts, amendment/transition reconciliation |
| Graph B jurisprudence | Partial | Proceedings/decisions/opinions/content/citation/treatment types, validated synthetic edge cases | Lawfully acquired decisions, passage roles, duplicate manifestations, institution epochs, historical provision resolution, effect/treatment review, comparable-fact and adverse-authority evaluation |
| Graph retrieval | Implemented baseline | Eight typed tools, verified immutable serving releases, atomic activation/rollback, independent signed-source checks, bounded traversal, reviewed validity cutoffs with separate evidence and explicit unresolved data | Real-corpus recall, legal-owner-approved serving release, large-corpus startup/indexing/query performance and applicability evaluation |
| Document intake | Partial | Initial and extended adapters, bounded OCR, isolated scanner/worker, signed offline signatures, live readiness, deployed clean/EICAR checks, encrypted originals and session revalidation | Representative layout/table/header/footnote and legacy-format qualification, full scan handling, sandbox escape testing, supplied UDF before pilot |
| Preparation/review | Partial | Quotations, issue checklists, corrections, claim review, scenarios, contradiction links, argument notes, playbooks, immutable drafts and DOCX/PDF | R05A premise/rule/application rationale, bounded consistency/correction, qualified synthesis, multi-step scenarios, adverse discovery and lawyer adjudication |
| Search and reasoning | Partial | Local document excerpt windows and additive graph queries, bounded OpenSearch lexical/vector adapter with release/rights/review prefilters and reciprocal-rank fusion | Approved corpus/indexes, Turkish multi-field normalization, local embedding/reranker qualification, independent adverse search, evaluated issue reasoning and reviewed calculations |
| Source and corpus operations | Partial | Two registered TBMM acquisition representations; immutable staging, human source/mapping review and single-source publication; R01 offline source/use/asset catalog and inspection | Actual R01 qualification, lawful RG/MBS/judicial/domain adapters, multi-source publication, separate observation/review/import freshness, archive gaps and per-source watermarks |
| Boundary gateway | Partial | Default disconnected mode, limited public query policy, exact-digest approvals, DNS-bound fetch, registered TBMM staging and immutable quarantine catalog | Advanced local PII/entity/secret detectors, ethics rules, broader source adapters, qualified incoming content/rights verification, measured false positives |
| Revalidation | Partial | Source/fact/practice changes mark work stale; exact source/assertion/release impact and operator invalidation preserve content and snapshots | Automatic verified publication triggers, scalable dependency index and re-review queues |
| Operations | Partial | Restricted Compose, persistent stores, CI, five-volume encrypted backup tooling, fresh-target restore checks and isolated graph runtime rehearsals | Target-host builds, full recovery/rollback drill, signed offline distribution, quotas, five-job load, interrupted imports, cancellation and concurrency qualification |
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

**R02 remains partial.** Next is bounded research-job cancellation and the declared
five-job operational baseline: throughput, lock wait, restore/rollback, resource
limits and failure recovery. Restricted-audience serving and same-release renewal
remain unsupported. R01 actual source/legal/privacy qualification continues to gate
real corpus publication; it cannot be replaced by synthetic approvals.

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
| 1: backbone | Weeks 3–10 | R02 multi-source release foundation; Graph A and genealogy; existing private/intake foundations; R03 RG/MBS samples | National type coverage reviewed; atomic multi-source authorization; evidenced reconstruction; private links isolated; five-job baseline measured |
| 2: contract slice | Weeks 6–18 | R03 reviewed contract pack, R04 retrieval, R05 first decisions, R05A rationale/correction and task/export | End-to-end contract analysis reviewed; premises/rules resolve to evidence; consistency defects corrected or withheld; source/time/rights gaps explicit |
| 3: deep research | Weeks 14–26 | R04–R05A historical/adverse and deeper local analysis; R05B sanitized BYOK adapters; R07 freshness/job controls | Measured depth benefit without critical applicability regression; each provider passes disclosure/fidelity/credential/citation gates; currentness limited by verified evidence |
| 4: practice depth | Weeks 22–30 | R06 commercial/employment packs, parameters, issue templates, playbooks, scenarios, corrections and R07 impact/distribution | Domain reviewers approve tasks; calculations reproduce from source rules; changed assertions correctly flag dependent products |
| 5: qualification | Weeks 31–36 | R07–R08 security/load/offline/restore tests, source/review operations and 10–20 lawyer pilot | Legal, graph, confidentiality, source coverage, usefulness and operational gates pass |

Critical path: legal semantics/review capacity → lawful source acquisition → representative extraction → identity/version resolution → release publication → retrieval/synthesis evaluation → pilot. Application feature completion alone cannot satisfy these gates.

These overlapping windows describe the original staffed program, not a new clock
starting from this revision or an assertion that its review gates have passed.
For planning, allocate approximately three Turkish legal editors (including the
ontology owner), two knowledge/retrieval engineers, two application engineers and
one platform/security engineer. Independent consequential review must have protected
capacity. If access or reviewer capacity falls short, reduce populated scope or
extend dates; do not lower legal gates. Measure reviewer minutes, rejected/reworked
assertions, acquisition delay, index growth and hardware cost. Do not assume the
attachments' fixed server counts, vendor prices or claimed model savings.

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
key/job isolation and per-provider evidence checks. These new gates need scorer/schema and
test implementation; the current scorer below does not yet enforce them. Keep privacy and
legal-fidelity evaluations separate, and do not achieve safety merely by blocking useful work.

The executable scoring contract is `backend/app/evaluation.py`. Supply one independently adjudicated held-out `TaskScore` per JSONL row and a separate snapshot JSON containing ontology/graphs/corpus/model/policy IDs:

```sh
backend/.venv/bin/python scripts/evaluate_release.py /evaluation/adjudicated-tasks.jsonl \
  --snapshot /evaluation/snapshot.json
```

This emits aggregate metrics and domain/period/relationship breakdowns, and exits nonzero on unmet quantitative gates. Empty denominators remain unknown, duplicate tasks are rejected, small perfect samples cannot pass the sample gates, and preparation-time measurements must include verification/correction. Even passing quantitative results do not automatically certify production or replace the independent legal/security/operations gates.

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
