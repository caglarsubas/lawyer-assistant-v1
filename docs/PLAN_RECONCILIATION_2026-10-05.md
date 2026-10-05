# Research reconciliation — 5 October 2026

This record explains the changes to the [canonical roadmap](ROADMAP.md) and its
[data/knowledge strategy](DATA_KNOWLEDGE_STRATEGY.md). The user requested a plan
update before the next development step. This revision does not execute document
instructions, contact institutions/vendors, acquire datasets, change deployment,
approve legal assertions or activate sources.

## Inputs and evidence boundaries

| Input | Preserved copy | Contribution |
|---|---|---|
| Turkish Law AI Data Plan gpt 2.md | [GPT2](research/2026-10-05/gpt-2.md) | National source families, RG/MBS reconciliation, freshness clocks, rights, offline bundles and retrieval evaluation |
| Turkish Law AI Data Plan claude 2.md | [Claude2](research/2026-10-05/claude-2.md) | Detailed graph modules, identities, Turkish concept distinctions, issues/evidence, authority treatment, calculations and review capacity |
| Turkish Law AI Data Plan gemini 2.md | [Gemini2](research/2026-10-05/gemini-2.md) | Structured parsing, Turkish morphology, local embedding/reranker candidates, source operations and privacy checks |

The [manifest](research/2026-10-05/manifest.json) records exact bytes and SHA-256
digests. The originals remain unchanged. Their imperative wording, synthetic
examples and labels such as “verified” express the documents' authorship, not
project instructions or legal-owner approval. GPT2's opaque `turn…` citations
cannot serve as resolvable project evidence. Gemini2 includes visibly mismatched
citations, including a hydrogen-policy paper for Gazette feed claims. Claude2
labels some secondary-source claims verified while separately recording conflicts.

The comparison used the existing roadmap, source/acquisition/review contracts,
publication/validity contracts, current search and evaluation code, and the last
recorded [validation checkpoint](VALIDATION.md). No runtime verification was rerun
for this documentation change. The last checkpoint establishes engineering checks,
not legal approval: the real staged source still awaited rights/legal review and
no public legal graph release had been activated.

## Disposition of the proposals

Line ranges refer to the preserved copies. “Adopt” means included in future scope,
not implemented or independently legally reviewed.

| Topic / source anchors | Decision | Roadmap consequence |
|---|---|---|
| Source layers and national inventory — GPT2 9–92; Gemini2 6–39; Claude2 253–268 | Adopt, qualify by task | R01 registers core, practice-specific, conditional and enrichment families. Separate desired, permitted, acquired and serving coverage; no source is universally sufficient |
| Mandatory commercial database — GPT2 26–34, 78–90 | Adapt | Licensed coverage bake-off if official-corpus gaps justify it; no mandatory purchase. Machine processing, quotation/export and customer offline distribution need explicit scope |
| RG event ledger → MBS consolidation → TBMM context — GPT2 16–20, 128–149; Claude2 270–282 | Adopt | R03 handles ordinary/mükerrer issues, proposed amendment/transition events and discrepancy review; a proposal or consolidation note is not independently established legal effect |
| Freshness cadence and live-first retrieval — GPT2 94–126; Gemini2 41–49, 73–92; Claude2 294–306 | Adapt | Connected staging targets and offline installed watermarks are separate. Detection, acquisition, review and customer arrival are different clocks; no inference-time internet dependency or automatic legal-currentness guarantee |
| Two versus three graphs/four layers — Claude2 3–34, 106–128; GPT2 270–277 | Adapt | Keep Graph A, Graph B and shared provenance/coverage modules; separate schema, populated records, private matter instances and derived indexes |
| Identity, standards and duplication — Claude2 132–150, 222–249, 270–284; GPT2 151–224 | Adopt selectively | Persistent internal IDs, preserved manifestations, collision/alias review and interoperable mappings. Do not mint identifiers falsely presented as official ELI/ECLI or key a version only by date/truncated hash |
| Norm/institution genealogy — Claude2 157–158, 189–207; GPT2 54–58, 294–349 | Adopt | Reconstructed versions, source-backed transitions, establishment/operation, renamed body/competence transfer and historical chamber epochs remain separate |
| Turkish terms and issue/element graphs — Claude2 152–165, 309–331 | Adopt | Small reviewed launch-practice templates, historical aliases, non-equivalence warnings, evidence questions and legally relevant fact features; no automatic liability/applicability inference |
| Authority and treatment — Claude2 167–187, 326; GPT2 24, 294–349; Gemini2 19–20, 136–140 | Adapt | Legal-effect matrix requires source, scope, conditions, decision type, procedure and dates. Reject universal court-rank or citation-count binding/“good law” scores; citation, endorsement and legal effect remain distinct |
| Procedure and financial parameters — Claude2 161–162, 72–79, 633–645; GPT2 130–149 | Adopt model, defer legal values | Version rule/parameter/source/date basis/rounding and expose uncertain inputs. Do not load attachment-supplied thresholds or example judgments as current law |
| Private facts, playbooks and impact — Claude2 163–165, 586–617; GPT2 351–379 | Adopt within current boundaries | Preserve assertions' roles, corrections and matter authorization; public IDs may be referenced privately without public inverse links; updates nominate re-review, never rewrite reviewed work |
| Turkish morphology and legal segmentation — Gemini2 98–110; GPT2 218–224, 279–291; Claude2 270–284 | Adopt evaluation | Exact original text plus derived Turkish/citation fields, legal hierarchy and decision roles; conditions/exceptions retrieved together; normalization never rewrites quotation offsets |
| Embeddings, rerankers and context budgets — Gemini2 109–134; GPT2 281–307; Claude2 243–247 | Evaluate | Pinned local model candidates, licensing/supply-chain checks and measured Turkish retrieval. No fixed top-5/top-50, mandatory Zemberek, STS-to-legal-quality inference or provider replacement |
| Contextual prefixes, late chunking, Matryoshka — Gemini2 107–120 | Correct/defer | Generated prefixes and late chunking are distinct experiments. Generated aids are not source evidence. Dimension truncation needs model support and measured quality; claimed savings/accuracy are not commitments |
| Independent adverse search — GPT2 351–364; Claude2 328–331 | Adopt | R05 searches contrary interpretations/dispositions, distinctions and later changes independently; show what was searched and missing coverage; do not average conflicts into a fabricated rule |
| Rights and PII — Gemini2 57–71; GPT2 366–379; Claude2 80–85, 95–102 | Adapt | Per-source/per-use legal review, contextual re-identification testing, original/derivative separation and firm AI policy; no blanket public-domain, anonymization or transfer conclusions |
| Crawling/MCP — Gemini2 45–55, 154; Claude2 259, 626 | Reject evasion; adapt adapters | Approved APIs/feeds/manual packages preferred; bounded permitted crawling only. No residential-proxy evasion, CAPTCHA solving or WAF bypass. MCP is an interface, not an official-source or permission attestation |
| Sample RDF/SHACL/SPARQL — Claude2 335–523 | Reference only | Do not import synthetic assertions. Reject unbounded missing-end filter (473), raw SERVICE federation (503), and default raw-query logging (521); validate the entire public payload, not only marked subjects |
| Historical scope — GPT2 92, 220, 436; Claude2 294–301 | Adopt ordering | Keep national ontology and 1920-onward scope, necessary predecessors and an explicit 1920/early-archive gap; prioritize present launch workflows, then historical depth, preserving images and specialist transcription |
| Offline bundles — GPT2 438–455; Claude2 306 | Adopt, protect private records | Public-only signed release manifests, source watermarks, compatible deltas/index builds and rollback; never package private reviews, matter databases, credentials or a blanket PostgreSQL dump |
| Evaluation and schedules — GPT2 381–437, 457–512; Claude2 526–584; Gemini2 142–167 | Adapt | Preserve contract-first and conditional 30–36 weeks; measure capacity before dates. Use 360 development tasks separately from ~1,000 held-out release tasks; keep stronger support/citation/critical-error gates |
| Outreach and broader automation — GPT2 514–528, 59, 149 | Defer execution | Source-owner/vendor discussions are a human-owned dependency; document text authorizes no messaging. Authenticated UYAP/MERSİS sync, filing, cross-matter learning and fine-tuning stay outside v1 |

## Primary-source checks performed for this revision

These are bounded documentary checks, not a comprehensive legal opinion or connector
qualification. Checked 5 October 2026 in the user's timezone. A search/open failure
does not prove a source is unavailable to authorized operators.

| Check | Observed primary evidence | Planning decision / limitation |
|---|---|---|
| Lawyer privacy guidance exists | [KVKK announcement](https://www.kvkk.gov.tr/Icerik/8990/avukatlarin-mesleki-faaliyetlerinde-kisisel-verilerin-korunmasina-iliskin-uygulama-rehberi-yayimlandi) describes guidance covering lawyers' processing, transfers, generative AI and security | R01 legal/security owners must map the full guide to the deployed data flows. Announcement verified; every guide proposition was not independently adjudicated |
| Professional AI-use guidance exists | [TBB announcement](https://www.barobirlik.org.tr/Haberler/tbb-avukatlikta-yapay-zeka-kullanimina-iliskin-tavsiye-rehberini-yayimladi-86648), dated 28 August 2026, describes human verification, confidentiality and written firm policy | Add review of outputs before external professional use and a versioned firm policy. Guidance is not an automatic statutory classification or product certification |
| Blanket transfer-law claim is unsafe | [KVKK official notice](https://www.kvkk.gov.tr/Icerik/7938/Standart-Sozlesmeler-ve-Baglayici-Sirket-Kurallarina-Iliskin-Dokumanlar-Hakkinda-Kamuoyu-Duyurusu) identifies Article 9 changes and standard-contract/binding-corporate-rule safeguards | Do not state every external API call is necessarily unlawful or consent is the sole mechanism. Product policy still prohibits arbitrary external inference; counsel assesses actual deployments |
| DergiPark exposes journal-specific metadata routes and restrictions | [Official law-journal archive policy](https://dergipark.org.tr/en/pub/ihad/page/13418) identifies OAI-PMH and a CC BY-NC-ND notice | Confirms a journal-specific discovery route, not a universal unrestricted full-text licence or a production-qualified endpoint. Platform-root API fetch did not succeed in this check |
| HUDOC translation rights are specific | [ECHR translation policy](https://www.echr.coe.int/en/case-law-translations) distinguishes non-official translations and requires rights-holder approval for reproduction | Retain original language, translator, quality status and permission. Replace blanket “all Turkish translations non-commercial” with per-representation rights review |
| Fuseki graph ACL scope | [Jena documentation](https://jena.apache.org/documentation/fuseki2/fuseki-data-access-control.html) limits graph-level access control to read-only datasets | Preserve application/matter authorization and separate storage/network boundaries; named graphs do not secure a shared writable private store |
| BGE-M3 candidate metadata | [Author model card](https://huggingface.co/BAAI/bge-m3) lists 1,024 dimensions and 8,192 sequence length | Candidate only; no evidence here establishes legal-domain quality or arbitrary Matryoshka truncation. Pin and evaluate before deployment |
| Copyright source identified | [Ministry-hosted FSEK PDF](https://telifhaklari.ktb.gov.tr/Eklenti/106879%2Cfikir-ve-sanat-eserleri-kanunupdf.pdf?0=) was located | Exact current provisions, database/derivative rights, access terms and each contemplated use still require source-rights review; no blanket licence granted |
| RG/MBS machine access unresolved | Official RG/MBS pages and RG robots were attempted; direct retrieval did not complete in this research tool | Do not assert a supported bulk/RSS/XML API, a fixed robots rule, or a permitted crawl rate. R01 must qualify the exact approved route; no bypass attempted |

## Unresolved claims and owners

| Owner | Must resolve before dependent publication/use |
|---|---|
| Source/access lead + rights counsel | RG archive boundary and mükerrer enumeration; MBS scope/history and machine access; TBMM historical coverage; official court endpoints vs unofficial Bedesten/MCP wrappers; TTSG/MERSİS permissions; vendor offline rights and cost |
| Turkish legal ontology owner | Yargıtay/Danıştay ordinary, assembly and unification effects; AYM norm/individual-application/pilot effects; jurisdiction conflicts; finality and reviewed scope/conditions. Do not transplant the attachments' simplified authority tables |
| Procedure/employment editors | 7550 transitional/date-basis claims, alleged later amendments, 2026 monetary thresholds, rounding and severance figures; chamber closure/renumbering and work-allocation dates. Acquire exact official representations; no values hardcoded from research |
| Knowledge/standards lead | Official external identifier mappings actually available for the product; asset versions/licences and Turkish language coverage. “No Turkish ELI/ECLI exists” remains an unsupported universal negative |
| ML/security lead | Model/data licence and supply chain, local packaging, Turkish retrieval/PII performance, memory/concurrency, compression compatibility and telemetry; foreign benchmarks and author-reported scores are not product results |
| Product/operations lead | Review staffing/throughput, source-specific polling constraints, offline transfer frequency, hardware budget and pilot dates. No assumption of constant source availability or customer acceptance of monthly stale data |

## Next action boundary

The plan now places **R01 qualification before R02 multi-source implementation**.
Current code, credentials, approved tunnel exception, source permissions, review
records and runtime remain unchanged by this revision. Proceeding later should
use the R01 outputs and the existing publication/security contracts, not copy the
research documents' example queries or acquisition commands.

## Subsequent user amendment — legal analysis and BYOK research

After the attachment reconciliation, the user explicitly requested deeper legal
argument construction, inspectable logical steps, self-correction, increased inference
time and BYOK deep search through OpenAI, Anthropic or Gemini using PII-sanitized,
true-to-life scenarios. This is a direct product instruction, not an instruction
embedded in any research attachment. Its [detailed assessment and contract](LEGAL_ANALYSIS_AND_DEEP_RESEARCH.md)
records the resulting scope and current official provider documentation checks.

The earlier source-planning record above remains historical. The amendment supersedes
the blanket external-inference prohibition only for the planned, approved sanitized
research lane; arbitrary external inference remains prohibited. It preserves the local
primary provider, private data plane, two graphs, disconnected default, existing laptop
exception and independent source/legal review. Neither this planning update nor a
provider's documented API capability establishes permission to transmit client data.

R01 remains next, now including analysis/fidelity/provider contracts and added-effort
estimation. R05A moves legal rationale and bounded consistency/correction into the first
contract milestone; R05B adds three separately qualified BYOK adapters and local return-path
verification. R03 corpus readiness is distinguished from full analysis qualification.
More inference time must be evaluated against quality and total reviewer time. Sanitization
must not distort legally material facts; identifying details that cannot safely be
abstracted remain local. All changes are planning-only: code, runtime, credentials,
source approvals and review records remain unchanged.
