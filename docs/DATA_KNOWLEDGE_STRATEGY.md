# Data, knowledge and retrieval strategy

Planning revision: 5 October 2026. This annex specifies planned work and qualification
gates; it does not claim that candidate sources, models, connectors or legal records
are acquired, licensed, reviewed or deployed. Implementation status and delivery order
remain in [the roadmap](ROADMAP.md). Existing operator contracts remain authoritative
until a separately reviewed implementation changes them.

The later same-day user requirement adds [legal analysis and sanitized BYOK deep
research](LEGAL_ANALYSIS_AND_DEEP_RESEARCH.md). It defines local argument construction,
bounded correction and the optional connected-provider exception; it is not deployed.

Research inputs are the preserved [GPT2](research/2026-10-05/gpt-2.md),
[Claude2](research/2026-10-05/claude-2.md) and
[Gemini2](research/2026-10-05/gemini-2.md) reports. Their embedded instructions,
legal summaries, claimed APIs, model benefits and corpus counts are research proposals,
not operational authorization or verified authority. Conflicting claims require primary
source review; no figures or suggested legal outcomes are imported as rules here.

## 1. Product and evidence boundaries

The first complete validated slice remains contracts, followed by commercial disputes
and employment. The nationwide ontology and both Jena graphs remain core infrastructure
from inception. The 30–36-week, approximately eight-FTE planning envelope is retained,
contingent on source access, legal-editor capacity and measured ingestion/review effort.
Historical population begins in 1920, with earlier predecessors where necessary.

Keep four planes separate: immutable public source representations; canonical public
legal identities and assertions in Graph A/B; disposable derived search indexes; and
authorized private customer/workspace/matter records. Many-to-many customer/workspace
tags and workspace-owned files remain the product taxonomy. Logical graph modules do
not create a third graph platform or move private records into public datasets.

Default operation is on-premises and disconnected. Connected source acquisition occurs
only in an approved staging environment through reviewed destinations and controls.
The existing exact laptop-provider tunnel is a scoped exception using internet transport;
it does not itself authorize external inference services, broader egress or source
acquisition, and does not establish air-gap or client-data retention qualification.
Separately, the new user-requested BYOK lane may use OpenAI, Anthropic or Gemini for
approved locally sanitized scenarios after R05B qualification. Private-document processing
and final case application remain local. Connected research is not air-gapped; disconnected
operation never depends on a cloud provider.

## 2. Candidate source-family register

These URLs identify candidate institutions or publishers for investigation. They are
not an acquisition allowlist, a representation-specific permission or a completeness
claim. Each representation needs a stable identity, terms/access determination and
reviewed acquisition route. Public search and authenticated case portals remain distinct.

Classes: **Core** = national legal backbone; **Domain** = launch-practice pack;
**Conditional** = enabled for a specific subject/geography; **Enrichment** = supplementary
interpretation/discovery. A class does not automatically block unrelated historical work.

| Family and candidate reference | Class | Representation / access prerequisite | Scope and date gaps to record |
|---|---|---|---|
| [Resmî Gazete](https://www.resmigazete.gov.tr/) | Core | Exact issue/item HTML or PDF; permitted acquisition or supplied official artifact | Ordinary and every mükerrer issue; corrections, missing issues and early archive coverage |
| [Mevzuat Bilgi Sistemi](https://www.mevzuat.gov.tr/) | Core | Dated official consolidated representation; verify available interfaces and uses | Consolidation snapshot is not complete historical version history |
| [TBMM](https://www.tbmm.gov.tr/) | Core | Enacted texts, proposals, reports and minutes; representation-specific route | Enacted versus consolidated text, legislative periods and missing reports |
| [AYM](https://kararlarbilgibankasi.anayasa.gov.tr/) | Core | Official decision representation and type; reviewed access | Review type, opinions, publication/editorial versions and unknown finality |
| [Yargıtay](https://karararama.yargitay.gov.tr/) | Core | Official decisions and institution/work-allocation publications; permitted route | Chamber epoch, decision/proceeding identities, unpublished periods |
| [Danıştay](https://karararama.danistay.gov.tr/) | Core | Official chamber/board decision representations; permitted route | Decision type, procedural stage, publication coverage and historical units |
| [UYAP Emsal](https://emsal.uyap.gov.tr/) | Core | Publicly published emsal only; independently reviewed acquisition | Selective regional/first-instance publication; never all UYAP files |
| [Uyuşmazlık Mahkemesi](https://www.uyusmazlik.gov.tr/) | Core | Official jurisdiction-conflict decisions; verify exact collection | Inter-branch coverage, procedural context, dates and missing decisions |
| [Sayıştay](https://www.sayistay.gov.tr/) | Conditional | Official chamber/appeal material; distinguish representations | Public-finance subject, decision stage, fiscal year and absent periods |
| [ÇSGB](https://www.csgb.gov.tr/) and [SGK](https://www.sgk.gov.tr/) | Domain | Official circulars, notices, rules and parameter publications | Employment scope, effective periods, corrected tables and historic values |
| [Ticaret Bakanlığı](https://ticaret.gov.tr/) | Domain | Official commercial/consumer/e-commerce/customs publications | Rule versus explanation, affected sector and effective status |
| [TTSG](https://www.ticaretsicil.gov.tr/) / [MERSİS](https://mersis.ticaret.gov.tr/) | Domain / Conditional | Licensed or expressly authorized registry representation; no credential scraping | Company identity, representation authority, historical notices; account-bound services separate |
| [KVKK](https://www.kvkk.gov.tr/) | Domain | Official decisions, summaries and guides; preserve document type | Redaction, decision versus summary, version and specific scope |
| [Rekabet Kurumu](https://www.rekabet.gov.tr/) | Domain | Official decisions and regulatory publications | Market/conduct context, redactions, procedural stage and corrections |
| [GİB](https://www.gib.gov.tr/) | Domain | Official legislation, circulars, published rulings and guidance | Document-specific effect/context, taxpayer redaction and effective period |
| [SPK](https://www.spk.gov.tr/), [BDDK](https://www.bddk.org.tr/), [TCMB](https://www.tcmb.gov.tr/) | Conditional | Separate regulatory and numerical-data channels | Banking, markets/payments and rate series; each with applicable dates |
| [MASAK](https://masak.hmb.gov.tr/) | Conditional | Official rules, guides and notices; reviewed update route | Subject-specific obligations, replacements and superseded guidance |
| [KİK](https://www.ihale.gov.tr/) / [EKAP](https://ekap.kik.gov.tr/) | Conditional | Public rules/decisions versus account-bound procurement data | Tender/proceeding stage, restricted areas and historical publication |
| [TÜRKPATENT](https://www.turkpatent.gov.tr/), [EPDK](https://www.epdk.gov.tr/) and sector agencies | Conditional | Per-agency rules, decisions, tariffs and permitted representations | Never assume full decision access; sector and period coverage explicit |
| [TBB](https://www.barobirlik.org.tr/) and official local bars | Domain / Enrichment | Professional materials, guides, journals and forms with item-level rights | Professional rule versus recommendation/commentary; local practice and author rights |
| [DergiPark](https://dergipark.org.tr/), [TR Dizin](https://search.trdizin.gov.tr/), [YÖK theses](https://tez.yok.gov.tr/UlusalTezMerkezi/) | Enrichment | Per-journal OAI/metadata where available; full text only with reviewed rights | Article/thesis licence, language, version, embargo and metadata-only coverage |
| [HUDOC](https://hudoc.echr.coe.int/) / [ILO NORMLEX](https://normlex.ilo.org/) | Conditional / Enrichment | Official international materials; translation and use rights separately reviewed | Original-language authority, translation status, jurisdiction and instrument relationship |
| Municipalities, local authorities and professional bodies | Conditional | Specific official site and territory; permitted targeted acquisition | No nationwide local-law completeness assumption; monitored geography/period shown |
| Other ministries, regulators, universities and public institutions | Conditional national long tail | Institution-owned legal publications with a separately approved route | Map each enabled national legal category to its competent source family; do not assume a finite URL list is exhaustive |
| [LEXPERA](https://www.lexpera.com.tr/), [Kazancı](https://www.kazanci.com/), [Legalbank](https://legalbank.net/), [Lebib Yalkın](https://lebibyalkin.com.tr/) and peers | Enrichment | Contractual feed/import with machine-use and offline-distribution scope | Unique coverage, publication delay, editorial additions and licence expiry |
| Official newsrooms and licensed news services | Enrichment | Approved signal feeds; metadata/link-only unless full-text use permitted | Discovery/change signals only; never legal authority or proof of effect |
| [TBMM](https://www.tbmm.gov.tr/) / [State Archives](https://www.devletarsivleri.gov.tr/) and other audited historical collections | Core historical lane | Cataloged artifacts, access rights and specialist transcription review | Explicit 1920–early-1921 gap investigation, earlier predecessors and scan/transcription uncertainty |

Authenticated UYAP synchronization and registry integrations remain outside v1; customer
supplied documents may use existing authorized private intake. Commercial supplementation
is optional: run a stratified coverage/rights bake-off before a procurement decision.
Neither a subscription nor an unofficial MCP endpoint grants machine-use permission.
Blocked access requires an approved export, negotiated channel or explicit coverage gap;
rotating residential proxies, CAPTCHA bypass and disguised clients are not acquisition plans.

### Launch-practice source packs

These are candidate scope identifiers for R01 review, not approved interpretations or
current consolidated texts. Each pack needs a bounded corpus/period manifest, source
rights, dependency links, competency questions and a named domain reviewer.

| Pack | Initial instruments / evidence families to qualify | First user capability |
|---|---|---|
| Contracts | TBK 6098 and transition material 6101; relevant predecessor 818; HMK 6100 and predecessor 1086; mediation 6325; enforcement 2004 and applicable interest/notice rules | Clause/obligation/breach/notice/remedy review, alternative issue framing, source-supported contract preparation |
| Commercial disputes | TTK 6102 and transition material 6103/predecessor 6762; contract/procedure dependencies; registry/representation evidence, Ticaret/Rekabet/GİB/KVKK and selectively financial regulators | Authority to represent, debt/security and commercial dispute preparation, distinguishing guarantees and relevant transaction types |
| Employment | 4857, relevant preserved/predecessor 1475 provisions, 7036, 5510, 6331, 6356 and applicable TBK/procedure rules; SGK/ÇSGB publications and reviewed parameter series | Employment termination preparation, work/remuneration evidence, competing date scenarios and auditable candidate calculations |
| Cross-cutting | Constitutional and relevant treaty sources; AYM/appropriate judicial decisions; institutional/competence and transition history; professional guidance | Forum and procedure candidates, rights issues, alternatives and honest coverage limitations |

The first three packs include parent/context passages, exceptions and related procedural
requirements rather than isolated popular articles. Historical predecessor chains are
expanded where the user's event dates require them, even before broad archive backfill.
Employment termination is the next controlled practice evaluation, not a replacement for
the agreed first contract workflow. No threshold, monetary value or deadline is adopted
from the attachments without its exact official rule, period and review.

## 3. Source, asset and rights qualification

R01 will maintain a source-family register plus representation/asset records. Record owner,
stable identifier, exact official/candidate URL, access mechanism, acquisition constraints,
jurisdiction/domain/period, expected identifiers, terms evidence/date, responsible reviewer,
review status, update policy and known gaps. A staged count is not a coverage denominator.

For each artifact retain raw/extracted hashes, representation version, language, publication
and acquisition times, exact locators, extraction/OCR/model versions, fidelity findings and
redaction/translation status. Keep legal work, expression/version and physical representation
distinct; cross-source copies keep their own rights, extraction and provenance records.

| Rights dimension | Existing contract / planned extension |
|---|---|
| Storage, local processing, internal display, indexing, local inference, export | Existing six-use contract retained; every required use needs current evidence |
| Embedding and derived indexes | Planned explicit conditions within processing/indexing scope; no inference from public access |
| External research processing | Planned separate provider/tool/asset permission and processing assessment; local-inference or export permission alone does not authorize cloud submission. Only approved minimized scenarios and rights-cleared public research material may enter R05B |
| Offline transfer, redistribution and permitted audience | Planned granular scope, territory/customer/install limits and retention/revocation obligations |
| Training/fine-tuning and model derivatives | Planned asset-register restriction; model fine-tuning remains outside v1 |
| Source authenticity, extraction fidelity, legal review and sensitivity | Separate assessments; no combined label can substitute for all of them |
| Conditions, expiry, renewal and withdrawal | Bind exact assets/versions, audience, evidence and review; preserve prior decisions |

The asset register also covers ontology vocabularies, parsers, OCR, embeddings, rerankers,
NER models and evaluation datasets: owner/version/hash, licence, permitted uses, language,
hardware/limits, maintenance, measured suitability and replacement plan. Align selectively
with SKOS, PROV, SHACL, Web Annotation, OWL-Time, ELI and legal document models; imported
terminology does not create Turkish legal equivalence or an official Turkish identifier.

Evaluate Turkish NLP assets and local multilingual embedding/reranking candidates on our
own corpus. No model card, vector size, contextual prefix or dimensionality reduction
establishes Turkish legal accuracy. Unofficial corpora and source adapters may be inspected
as engineering references, never silently promoted to authentic or licensed source records.
Candidate investigations include Zemberek, Turkish legal NER resources, BERTurk-Legal,
HukukBERT, BGE-M3 and local cross-encoders; each needs task suitability and licence review.
Full Akoma Ntoso conversion, LegalRuleML rule engines, a Neo4j replacement and analytics
mirrors are not v1 prerequisites. Interoperability mappings must preserve our stable IDs.

## 4. Acquisition, legal change and historical reconstruction

The planned lane is approved acquisition → quarantine and local scanning → exact extraction
→ identity/role/citation candidates → structural validation → accountable review → independent
publication authorization → immutable release. No source or model text can approve itself.

RG processing will inventory date, issue identity, ordinary/mükerrer designation and exact
item/artifact hashes. A detected change proposes affected instruments/provisions and any
commencement, transition, repeal or institutional event. These remain candidates until
the requisite legal review establishes their effect and supporting passages.

MBS reconciliation compares a dated consolidated representation with reviewed publication
events. Differences enter an explicit queue: pending consolidation, extraction mismatch,
missing event, disputed amendment target or unknown effect. Neither the newer fetch nor
the consolidated wording silently overrides the other. Unresolved “current” claims are
qualified or withheld; an available current text never substitutes for a historical version.

Prioritize the contract slice and its necessary procedural/transition dependencies. Expand
commercial and employment packs after measured fidelity and review throughput. Backfill
recent relevant versions first, then older periods and predecessor instruments, while
the national ontology stays complete in type coverage. Publish missing periods explicitly.
Reconstructed versions retain reconstruction steps and review status; historical scans and
pre-Latin-script material retain image evidence and specialist transcription uncertainty.

## 5. Exact-preserving parsing, identity and Turkish retrieval fields

Keep original bytes and exact extracted text unchanged. Derived Unicode normalization,
Turkish-aware i/İ and ı/I casing, diacritic-insensitive aliases, apostrophe normalization
and morphology live in separate search fields with mappings back to exact passage spans.
Do not stem quotations or overwrite the evidence with generated contextual descriptions.

The [R04 retrieval baseline](TURKISH_RETRIEVAL.md) implements independent original,
Turkish-normalized and accent-folded token fields alongside the existing Turkish
stemming channel. It preserves source text/identifiers and returns bounded exact
token spans. Citation identity resolution, qualified morphology/aliases and the
representative development benchmark remain pending.

Segment statutes into instrument/article/paragraph/subparagraph, additional/temporary
provisions and editorial notes. Segment decisions into submissions, allegations, findings,
reasoning, disposition and separate opinions; unknown roles remain unknown. Preserve tables,
footnotes, annexes, page coordinates and extraction omissions. Citation numbers, dates,
amounts and negative/exception wording need targeted fidelity qualification.

Resolve identities by reviewed official identifiers and institution epochs before hashes;
similarity only nominates duplicate candidates. Distinct proceedings/decisions do not merge
because wording matches. Preserve literal citation occurrences, ambiguous targets and
unresolved versions. Decision date may be a search clue, never an undisclosed substitute
for the legally relevant event date or a proof of applicability.

## 6. Ten logical modules within the existing architecture

| Logical module | Home and core content | Qualification focus |
|---|---|---|
| 1. Concepts and terminology | Graph A: SKOS concepts, definitions, aliases, historical terms and distinctions | Versioned definitions; reviewed expansion; no assumed translation equivalence |
| 2. Legislation and provision history | Graph A: norms, exact versions, amendment/transition events | Publication versus effect; splits/merges; unknown and reviewed-open validity |
| 3. Institutions and competence | Graph A: bodies, chambers, epochs, territories, conditional assignments | Succession distinct from transferred competence and procedural review |
| 4. Decisions and treatment | Graph B: proceedings, decisions, roles, opinions, citations and sourced treatments | Citation not endorsement; case reversal not general change of interpretation |
| 5. Issues, tests and arguments | Graph A reviewed issue templates; Graph B evidenced issue treatment; private applications | Elements/conditions/exceptions nominate questions, not liability conclusions |
| 6. Procedure, remedies and calculations | Graph A rule/parameter versions; private inputs and scenarios | Reviewed date basis, triggers, rounding, exclusions and unresolved facts |
| 7. Practice-specific vocabulary | Graph A shared types; Graph B decision connections; private instances | Contracts first; commercial/employment reuse types without factual conflation |
| 8. Matter facts and evidence | Authorized private store/overlay: events, allegations, evidence, hypotheses, corrections | Provenance, contradictions and membership before joins or traversal |
| 9. Sources, provenance and coverage | Shared public provenance across A/B; confidential review proof stays private | Exact support, rights, review and four independent coverage dimensions |
| 10. Firm knowledge and impact | Private approved playbooks, interpretations and dependency records | No promotion to public authority; changed inputs queue re-review |

Review consequential authority effects, competence and interpretations against exact
applicable primary sources. Limited entailment may organize types; it cannot infer
liability, binding force, finality or competence from hierarchy, popularity or succession.
Named graphs and SHACL are not confidentiality boundaries; existing isolated stores,
application authorization and query-only Jena services remain required.

Plan a second qualified reviewer for consequential effect/competence/parameter changes
and disputed interpretations, with disagreements retained and adjudicated. Machine
citation checks and sampled extraction QA cannot replace these reviews. Retain rejected
proposals with their source/model versions so they are not repeatedly suggested unchanged;
a materially changed source can open a new, traceable review.

## 7. Retrieval, reasoning and calculations

The broker first resolves authorized matter scope, candidate issues and relevant dates.
Independent lexical-original, lexical-normalized, exact-citation, local semantic and
structured-metadata channels run alongside bounded graph discovery. Rights/release/time
filters apply within each channel before results are exposed; incomplete graphs cannot
exclude evidence independently found by ordinary search.

RRF combines candidates; a qualified local reranker considers issue and factual fit,
passage role, procedural posture, reviewed legal effect, historical version, source and
review quality. There is no universal court-ranking score. Candidate counts and reranker
budgets are experiments constrained by local capacity, latency and five-job operation.
Default graph expansion remains two typed hops with node, fan-out, time and cancellation
limits. Agents receive existing typed tools, never raw SPARQL, federation or graph writes.

A separate adverse-authority branch reserves review space for contrary interpretations,
material distinctions, rejected arguments and later relevant changes. Exact-source evidence
verification follows candidate discovery. Every substantive conclusion needs support and
applicability checks; citation existence alone cannot prove truth or eliminate hallucination.

R05A adds a local issue → premises → rule/version → application → adverse argument →
qualified conclusion record to the first contract slice. Deterministic checks and a
bounded evidence-driven critique/revision loop flag contradictions, missing exceptions
and unsupported inferences. Retain the revised claims, evidence and unresolved defects;
automated correction cannot confer legal review. Standard/Deep budgets add research time,
not permission or confidence. Compare their measured benefit on frozen tasks.

Optional R05B reports are discovery leads only. Retrieve admissible originals, verify
exact passages/versions and apply findings to private facts locally. Inaccessible sources
remain unresolved; an external citation cannot bypass corpus review or graph publication.

Calculation records bind the source rule and parameter version, event/date-basis choice,
currency/unit, trigger, calendar, rounding, suspension/interruption assumptions and inputs.
Competing plausible date bases produce separate labeled scenarios. Unknown or stale required
inputs block definitive numbers; models do not invent rates, thresholds or deadline rules.

R04–R06 use a 360-query development set, 120 per practice, for tuning and error analysis.
It is separate from the approximately 1,000 held-out adjudicated release tasks and at least
3,000 substantive claims. Compare strong lexical, hybrid, temporal/authority and graph
variants on identical frozen corpora; ablate modules and hop counts. Track adverse recall,
span fidelity, passage roles, version/citation accuracy, reviewer effort, latency and cost.
Preserve all stronger roadmap release gates; architectural novelty is not measured benefit.

## 8. Public personal data and private originals

Publicly accessible material may contain personal data. Preserve officially published
redactions and review residual sensitivity, purpose and rights before shared indexing.
Quarantine unsuitable representations; create separately identified reviewed redacted
derivatives when lawful and useful. Every modification needs provenance back to restricted
original evidence. Local PII detection proposes action; it cannot certify anonymization.
Qualification includes Turkish names and roles, TCKN/VKN, contact/address/IBAN patterns,
health/criminal information, rare-event contextual linkage, images/tables and hidden
document metadata. Residual disclosure and unnecessary masking are measured separately.

Private client originals remain encrypted, authorized evidence with legal holds and
retention controls. Do not irreversibly destroy facts merely to create embeddings. Any
necessary minimized derived representation stays within the authorized private scope.
No reidentification, automatic cross-decision party correlation, cross-matter learning or
public inverse links may disclose matters or a lawyer's selection of public authorities.
Exact-payload external approval does not permit original client documents, private
excerpts or secrets in research content. BYOK credentials are injected only as provider
authentication by a separate broker, never forwarded as scenario text or source queries.

Ingress and egress policies cover local PII/secret detectors, prompt-injection isolation,
destination/request binding and rights/provenance checks. Generic public legal requests
may use the approved gateway; sanitized matter-specific requests need approval bound to
exact payload and destination. Missing mandatory checks fail closed for that action.
Prompts, query narratives and matter-selected authorities are not logged by default;
minimal audit records retain action, authorized scope, versions and result status.

R05B sanitization also measures legal fidelity: removing dates, rounding amounts or
merging roles can change the legal problem. Preserve legally material facts locally;
release only faithful abstractions, or research a general rule and finish locally.
Hypotheticals remain labeled alternatives, not invented case facts. Contextual linkage
and cumulative disclosures across requests need explicit tests. Scenario mappings,
approvals, reports and remote job IDs remain confidential matter records. A provider's
own search queries are not all locally inspectable; disclose and qualify that processing
scope or disable provider-managed web tools. See the [release and broker contract](LEGAL_ANALYSIS_AND_DEEP_RESEARCH.md).

## 9. Freshness, offline releases and operational qualification

Track source publication/detectability, last successful scan, acquired representation,
legal validity, system knowledge, accountable review/expiry, release creation and customer
import separately. A source scan cannot renew the reviewed-open checked-through horizon.
Signed-release age cannot establish current law; missing timestamps remain unknown.

| Source class | Conditional connected-staging pilot target | Reconciliation / failure behavior |
|---|---|---|
| RG | p95 acquisition lag ≤30 minutes from detectable publication | Ordinary/mükerrer manifest reconciliation; gaps block unsupported current-law claims |
| Critical regulatory and calculation sources | p95 ≤4 hours | Event-driven affected-rule refresh; unresolved parameter/date disables definitive calculation |
| Watched MBS representations | Target ≤4 hours after detectable change | RG-linked targeted checks; discrepancy queue, no automatic consolidation assumption |
| Court publications | p95 ≤12 hours | Rolling recent-publication recheck and identifier audit; disclose delayed coverage |
| Other regulators / local monitored sources | Initial 24-hour target, adapted per source | Territory and source-specific warnings; unmonitored sources explicitly labeled |
| Academic / licensed enrichment | Contract- and publication-driven daily/weekly targets | Metadata-only or licensed deltas; outage cannot invalidate unrelated primary evidence |
| Disconnected customer | Agreed release/import cadence, measured age and watermark | No live-source SLO; show included-through data and missed/expired review obligations |

These are proposed service targets only where lawful supported access and capacity permit.
Acquisition targets measure detectable publication to completed quarantine acquisition.
Report review/publication backlog and customer transfer/installation delay separately,
together with end-to-end age. Reconcile hashes/identifiers and refresh affected versions/indexes only;
do not re-embed unchanged corpora or silently rewrite reviewed work.

Offline public releases will carry source-specific watermarks, raw/representation hashes,
graph/index/model compatibility, permitted-use summaries, known gaps, QA, predecessor and
signature. Keep confidential rights proofs, reviewer routing and all private matter data
outside public bundles. Verify complete manifests before atomic installation; qualify
interrupted imports, staged deltas, rollback, stale permissions and encrypted recovery.

## 10. Delivery ownership and order

| Roadmap packet | This annex's contribution | Accountable owners / exit evidence |
|---|---|---|
| R01 | Source/asset/semantic qualification | Legal owner, source owner and knowledge engineer: reviewed scope, rights/access gaps and sample cost |
| R02 | Bounded multi-source release and five-job capacity | Backend/security/operations: deterministic admission, private proof isolation and load results |
| R03 | RG/MBS contract corpus | Editors/data engineering: reconciled source events, exact versions and explicit missing coverage |
| R04 | Turkish hybrid retrieval and local reranker | Retrieval team/editors: frozen-corpus comparison and evaluated asset selection |
| R05 | Decision roles/treatments and adverse search | Legal editors/knowledge engineers: exact evidence, uncertainty and adverse recall |
| R05A | Local legal rationale, consistency and deeper analysis | Application/retrieval team + legal adjudicators: first contract analysis, correction regression and Standard/Deep comparison |
| R05B | Optional sanitized BYOK research | Security/application + legal owners: privacy/fidelity, isolated credentials, three qualified adapters, source verification and local application |
| R06 | Issue/evidence reasoning and calculations | Practice lawyers/application team: commercial/employment scenarios and reviewed rule/date basis |
| R07 | Offline freshness, impact and operations | Operations/security/source owners: signed distribution, recovery, revocation and re-review queues |
| R08 | Held-out qualification and lawyer pilot | Independent legal/security/product reviewers: unchanged release gates and measured preparation benefit |

Rights negotiations, actual legal approvals, source signing and pilot participation require
accountable people and recorded evidence. Planning does not perform these actions. The
roadmap remains the authoritative priority ledger; historical/long-tail expansion continues
after the first validated release without changing nationwide ontology scope.
