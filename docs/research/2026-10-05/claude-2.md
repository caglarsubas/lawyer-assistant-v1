# Ontology and Knowledge-Graph Architecture for a Türkiye-First Legal Assistant (October 2026)

**Bottom line:** Build the *balanced production architecture* (Option B). Its core is three graphs:
- a provision-version graph keyed to Resmî Gazete events;
- a decision/passage graph that records Turkish authority types (İBK, Genel Kurul, daire, BAM, AYM) and evidenced treatments;
- a provenance/coverage graph.

Around them sit thin, editor-curated concept and issue/element layers for contracts, commercial disputes and employment. No international asset supplies Turkish legal content. Reuse the patterns (ELI/FRBR, ECLI, SKOS, PROV-O, SHACL, Web Annotation) and populate the Turkish content yourself from official sources.

## TL;DR

- **Recommendation: Option B.** It runs on your existing Jena/Fuseki + PostgreSQL + OpenSearch, with public and private stores kept separate. Retrieval is graph-assisted hybrid search: the graph filters and expands candidates, while text plus human review decide. First validated slice: employment termination (4857, 1475 m.14, 7036), HMK m.341/362/373 and Ek m.1, and Yargıtay 9. HD/HGK/İBK decisions from 2015.
- **Turkish specifics drive the schema.**
  - İBKs bind "Yargıtay Genel Kurullarını, dairelerini ve adliye mahkemelerini" (Yargıtay Kanunu m.45/5).\[1\]
  - AYM annulments take effect on RG publication or up to one year later, and "geriye yürümez" (Anayasa m.153).\[2\]
  - Daire decisions are persuasive.\[3\]
  - Chamber competence moves by published iş bölümü decisions; the latest is Büyük Genel Kurul 2026/1 (RG 30.06.2026 No. 33296).\[4\]\[5\]
  - Procedural thresholds now follow the filing date under 7550 sayılı Kanun. 2026 values: istinaf 50,000 TL and temyiz 682,000 TL, at a 25.49% revaluation rate.\[6\]\[7\]\[8\]\[9\]\[10\]
- **The evidence for graphs is suggestive, not conclusive.** SAT-Graph RAG (JURIX 2025) is an architecture paper, not a controlled benchmark against hybrid search.\[11\] Turkish legal NLP assets exist (BERTurk-Legal, HukukBERT, TLNER), but no public Turkish benchmark compares graph-assisted with hybrid retrieval.\[12\]\[13\]\[14\] Build a gold set and run per-module ablations before investing beyond Option B.

---

## Executive summary: four separate layers

| Layer | Contents | Storage | Visibility |
|---|---|---|---|
| **Ontology/schema** | Classes, properties, SKOS schemes, SHACL shapes, controlled vocabularies | Git → versioned release; Fuseki `urn:graph:schema/{version}` | Everyone |
| **Populated public knowledge** | Instruments, provision versions, RG issues, institutions/competences, decisions, passages, treatments, concepts, coverage | Fuseki public dataset (named graph per source × release) + PostgreSQL + OpenSearch | All tenants; signed offline releases |
| **Private matter instances** | Customers, matters, roles, documents, passages, assertions, issues, arguments, drafts, firm notes | Per-tenant Fuseki dataset + tenant PostgreSQL schema + tenant index | Authorised users; never leaves premises |
| **Derived retrieval indexes** | BM25, Turkish-normalised fields, vectors, path caches | OpenSearch / pgvector; rebuildable | Same ACL as source |

Private graphs reference public IRIs. The reverse never happens: public graphs carry no private IRIs and no inverse links. SHACL enforces this in CI, and separated networks and storage enforce it at runtime.

---

## Verified facts vs. design proposals

**[V]** = verified this round or in the prior sourcing round; **[P]** = design proposal; **[U]** = unverified or conflicting.

### Verified this round

1. **[V] ELI.**
   - The ELI ontology is at **v1.5** (EU Publications Office).\[15\]\[16\]
   - ELI-DL v3 and ELI-I v1 were both released 10/11/2023.\[17\]\[18\]
   - The model is FRBR-based: LegalResource / LegalExpression / Format, plus `LegalResourceSubdivision`. Licence: EUPL.\[19\]\[20\]
2. **[V] EuroVoc has no Turkish labels.** It covers 24 EU languages "plus in three languages of countries which are candidate for EU accession: Albanian, Macedonian and Serbian".\[21\]\[22\]
3. **[V] No Turkish ELI, ECLI or Akoma Ntoso implementation exists.** None was found at the Hukuk ve Mevzuat GM, MBS, Adalet Bakanlığı/UYAP or TBMM, nor in academic work. ECLI strings in Turkish texts appear only for EU and ECtHR decisions.\[23\]\[24\] MBS has operated since 1995.\[25\]
4. **[V] Akoma Ntoso.**
   - 1.0 is an OASIS Standard.\[26\]\[27\]
   - *v2.0 Part 2 (AKN 3.1)* reached Committee Specification 01 on 8 May 2026; public review ended 15 September 2026.\[28\]
   - Statements of use came from the EU Publications Office, UK National Archives, Xcential, BitNomos, CIRSFID and WHO.\[28\]
5. **[V] legislation.gov.uk.**
   - Uses FRBR/MetaLex: identifier URIs denote the *work*, and versions are *expressions*.\[29\]
   - Offers enacted, point-in-time (`/yyyy-mm-dd`) and prospective versions, plus `/data.akn`.\[29\]\[30\]
   - Licence: OGL v3.0.\[31\]\[32\]
6. **[V] LKIF-Core** (ESTRELLA) has 15 modules. Its last version is 1.1 (2008), and it is effectively unmaintained. The GitHub OWL files declare CC BY 4.0; the original release was LGPL.\[33\]\[34\]\[35\]
7. **[V] ECLI** has five colon-separated components and identifies a decision "at the work level". Its metadata use Dublin Core (Council Conclusions 2011/C 127/01 and 2019/C 360/01).\[36\]\[37\]\[38\]\[39\]
8. **[V] Binding force of İBKs and direnme.**
   - Yargıtay Kanunu m.45/5: "İçtihadı birleştirme kararları benzer hukuki konularda Yargıtay Genel Kurullarını, dairelerini ve adliye mahkemelerini bağlar."\[1\]
   - Under HMK m.373, the HGK decision on direnme binds in that file.\[3\]
   - Judges are otherwise not bound by non-İBK Yargıtay decisions.\[3\]\[40\]
9. **[V] AYM annulments (Anayasa m.153).** Decisions are final. An annulled provision ceases on RG publication or on a later date that "bir yılı geçemez", and "İptal kararları geriye yürümez."\[2\]\[41\]
10. **[V] Yargıtay chamber reduction.**
    - 6723 sayılı Kanun (adopted 1 July 2016; Anadolu Ajansı reports it entered into force on publication in the RG of 23 July 2016) set a reduction from 46 to 24 chambers (12 + 12) within six years.
    - Anadolu Ajansı ("Yargıtayda yeni dönem başladı") reported that, effective 1 July 2021, Yargıtay Birinci Başkanlık Kurulu decisions closed the 16. HD, with its work going to the 1. and 8. HD.
    - It also reported: "15. Hukuk Dairesinin numarası 6. Hukuk Dairesi olarak, 14. Hukuk Dairesinin numarası da 7. Hukuk Dairesi olarak değiştirildi" — i.e., the **15. HD became the 6. HD** and the **14. HD became the 7. HD** (Yargıtay's own document cites BBK decision No. 211 of 02/07/2021).
11. **[V] 2026 iş bölümü.**
    - Büyük Genel Kurul decision 2026/1 (29.06.2026) was published in **RG 30.06.2026 No. 33296**. It followed a Başkanlar Kurulu draft of 15.06.2026.\[4\]\[42\]
    - Civil chambers are grouped into four areas: Medeni, Gayrimenkul, Borçlar ve Ticaret, İş ve Sosyal Güvenlik.\[42\]
    - A newly competent chamber may not issue görevsizlik because it was not competent when the file first arrived.\[42\]
    - Transfers run automatically through UYAP.\[42\]
12. **[V] 7550 sayılı Kanun** (RG 04.06.2025, No. 32920, 1st mükerrer) followed AYM E.2023/182, K.2024/203 (04.12.2024) and rewrote HMK Ek m.1/2.\[7\]\[43\]
    - The filing date governs the thresholds in m.341, 362 and 369.\[7\]\[43\]
    - The transaction date governs m.200–201.\[7\]
    - Yargıtay HGK 02.07.2025, 2024/10-205 E., 2025/410 K. (as reported by Veli & Biçkin Hukuk Bürosu) held that for decisions rendered before 04.06.2025 "hükmün verildiği tarihteki parasal sınır esas alınacaktır."
13. **[V] 2026 parameters.**
    - Yeniden değerleme oranı: 25.49% (RG 27.11.2025 / 33090).\[8\]\[10\]\[44\]
    - HMK thresholds: istinaf 50,000 TL; temyiz 682,000 TL; duruşmalı temyiz 1,023,000 TL.\[9\]\[44\]\[45\]
    - Kıdem tazminatı tavanı: 64,948.77 TL for H1 2026 and **73,729.87 TL** for 01.07–31.12.2026 (Çalışma Genel Müdürlüğü; TÜRMOB).\[46\]\[47\]\[48\]
14. **[V] KVKK guide for lawyers.** *Avukatların Mesleki Faaliyetlerinde Kişisel Verilerin Korunmasına İlişkin Uygulama Rehberi* (KVKK Yayınları No. 115; announced 22.09.2026; prepared with TBB input).\[49\]\[50\]
    - The lawyer is the data controller.\[51\]
    - Data should be masked or anonymised before upload to generative AI.\[51\]\[52\]
    - Such uploads may trigger KVKK m.9 cross-border rules.\[49\]
    - Separately, TBB issued AI-use guidance on 28.08.2026 with four risk tiers.\[53\]
15. **[V] Fuseki access control.** Graph-level ACLs "only appl[y] to read-only datasets". `jena-permissions` is "planned for removal at Jena 6.0.0".\[54\]\[55\]
16. **[V] Retrieval evidence.**
    - LegalBench-RAG: 6,858 expert-annotated query–span pairs over more than 79M characters of English contracts.\[56\]
    - SAT-Graph RAG (arXiv 2505.00039, JURIX 2025): an LRMoo-inspired temporal graph for point-in-time retrieval and provenance.\[11\]\[57\] It is an architecture, not a head-to-head benchmark.
17. **[V] Turkish NLP assets.**
    - BERTurk-Legal (Öztürk, Özçelik & Koç, "A Transformer-Based Prior Legal Case Retrieval Method," SIU 2023; released as KocLab-Bilkent/BERTurk-Legal): pre-trained on a corpus of "332.662 Yargıtay karar metni"; scores 38.14 vs 18.87 for BERTurk on prior-case retrieval.
    - HukukBERT (arXiv 2604.04790): 92.8% segmentation pass rate.\[13\]
    - Çetindağ, Yazıcıoğlu & Koç, "Named-entity recognition in Turkish legal texts," Natural Language Engineering 29(3):615–642 (2023): covers Court, Law, Reference and Official Gazette entities. The token count (~123,000) is approximate in secondary sources. The separate TLNER dataset (Springer, 2026) reports "32,920 entity tokens and 100,867 total tokens".
    - Unofficial HF dump: 11,045,085 decisions with an unclear licence.\[58\]

The prior round's sourcing findings carry over unchanged:
- RG robots.txt disallows automated agents.
- MBS provides consolidated text only.
- Bedesten serves JSON.
- karararama returns 429 after ~5 fast requests.
- HUDOC translations are licensed non-commercial only.
- Commercial databases are protected by FSEK ek m.8 rights.
- FSEK m.31 makes official texts and court decisions free to reuse.

---

## 1. Three architecture options

| Dimension | **A. Lean** | **B. Balanced (recommended)** | **C. Comprehensive** |
|---|---|---|---|
| Goal | Prove version-correct statutes + passage retrieval beat plain hybrid | Production assistant for 3 practices with auditable evidence and private-matter reasoning | Nationwide 1920→ coverage, rule formalisation, firm-wide impact |
| Modules | 2 (core codes), 4 (decisions, passages, citations), 9 (minimal), small SKOS alias list | All 10; module 5 limited to ~40 editor-curated issue trees; module 10 dependency edges only | All 10 in full + LegalRuleML-style rules, AKN XML, Ottoman/early-Republic terminology, EU/ECtHR alignment |
| Storage | One Fuseki dataset + PostgreSQL + OpenSearch | Public Fuseki dataset (graphs per source/release) + per-tenant private datasets; PostgreSQL for text, spans and review | B + XML store, rule engine, analytics mirror |
| Retrieval | Hybrid + temporal filter | Interpret → expand → hybrid → bounded typed expansion (≤2 hops) → temporal + ACL filters → rerank → adverse pass → evidence | B + rule-based applicability suggestions |
| Legal editors | 1–2 | 3–4 + 1 knowledge engineer | 8–12 + academic partners |
| Main risk | Too thin for fact/argument tests | Editor throughput; unofficial endpoints | Cost; maintenance collapse (LKIF lesson) |
| First validated release | ~4 months | ~9–12 months | 3+ years |

**Why B:**
- **A falls short.** It cannot answer the comparable-facts, missing-evidence, contradiction or dependency tests, which need modules 5, 8 and 10.
- **C repeats the classic failure of legal ontologies:** comprehensive, but unmaintained and unpopulated.
- **B formalises only what is cheap and checkable:** identity, time, provenance, authority type and treatment events. Contested interpretation (issue trees, fact features) stays small, curated, and is grown only where evaluation shows gains.

**Tradeoffs:**
- B depends on 3–4 Turkish-qualified editors.
- Bedesten and karararama have no SLA.
- Issue trees will be incomplete, so the assistant must display their coverage status.

---

## 2. Module specification

### 2.1 Shared identifiers [P]

No official Turkish ELI/ECLI exists [V]. Mint internal, pattern-compatible IRIs that can be mapped to official identifiers later.

| Entity | IRI pattern | Natural key |
|---|---|---|
| Instrument (Work) | `tr:eli/kanun/4857`; unnumbered: `tr:eli/yonetmelik/{RG-date}/{sayı}/{seq}` | MBS tür/tertip/no; RG date/sayı |
| Provision | `…/madde/25`, `/fikra/2`, `/bent/b`, `/gecici-madde/1`, `/ek-madde/3` | MBS/RG structure |
| Provision version (Expression) | `…/madde/25/v/{validFrom}` | Amendment events |
| Text manifestation | `…/v/{date}/m/{sha256-12}` | Normalised-text hash |
| RG issue | `tr:rg/{yyyy-mm-dd}/{sayı}[/mukerrer/{n}]` | resmigazete.gov.tr |
| Institution epoch | `tr:org/yargitay/hd/9/epoch/{since}` | İş bölümü decisions |
| Proceeding | `tr:proc/{court}/{chamber}/E/{yıl}/{no}` | Esas no. |
| Decision | `tr:dec/{court}/{chamber}/{K-yıl}/{K-no}`; alias `TRX:…` (deliberately **not** `ECLI:TR`) | Karar no. |
| Passage | `{decision}/p/{n}` + Web Annotation selectors | Segmenter |
| Concept / issue | `tr:concept/{slug}`, `tr:issue/{practice}/{slug}` | Editors |
| Private | `urn:tenant:{tid}:matter:{mid}:…` | Never in public graphs |

One Esas file produces several decisions: first instance, istinaf, bozma, direnme, HGK. Hence **proceeding ≠ decision**.

### 2.2 Module table

| # | Principal entities | Key relationships | Temporal fields | Provenance | Privacy | Search problem → capability |
|---|---|---|---|---|---|---|
| **1 Concepts** | `skos:Concept`, Definition, TermVariant (alias, abbreviation, historical/Osmanlıca), qualified cross-lingual mapping | `broader/narrower/related`; `definedBy → ProvisionVersion`; `historicalTermOf` (*hizmet akdi*→*iş sözleşmesi*; *akit/mukavele*→*sözleşme*); `mustNotConflateWith` (*haklı neden* ≠ *geçerli neden*; *zamanaşımı* ≠ *hak düşürücü süre*; *fesih* ≠ *dönme* ≠ *ikale*); `approxMatch` + note (*ihtarname*, *ibraname*, *kıdem tazminatı* lack exact English equivalents) | `termInUseFrom/Until`; definitions inherit version dates | Definition → exact passage + review | Public; firm aliases in module 10 | Ambiguous/historic wording → **interpretation, safe expansion, distinction warnings** |
| **2 Legislation history** | Instrument (`eli:LegalResource`), Provision (`eli:LegalResourceSubdivision`), ProvisionVersion (`eli:LegalExpression`), TextManifestation, AmendmentEvent, RGIssue, TransitionalRule | `versionOf`; `createdBy/endedBy`; `amendmentType` {değişik, ek, mülga, yeniden düzenleme, ibare değişikliği, AYM iptal}; `successorOf` (BK→TBK); `transitionalRuleFor` (6101 for 818→6098; 6103 for 6762→6102; 4722 for 743→4721; 4857 m.120 keeping 1475 m.14); `refersTo` | kabul, RG yayım, yürürlük (per article), `validFrom/Until`, `dateStatus` {known, unknown, disputed, inferred} | Artifact (RG/MBS/TBMM), locator, derivation, reviewer | Public | Today's text substituted for historical law → **event-date versions; amendment/transitional alerts** |
| **3 Institutions & competence** | Institution, InstitutionCategory, InstitutionEpoch, CompetenceAssignment, Territory, ProceduralRoute | `instanceOfCategory`; `succeededBy` (renumbering); **separately** `competenceTransferredTo` with scope; `assignedBy` (iş bölümü decision + RG); `appealsTo` (first instance → BAM → Yargıtay, from 20.07.2016) | Epoch/assignment validity; transitional applicability | Each assignment cites an RG decision or law article | Public | Historic court names, forums → **forum identification; no false "same court" inference** |
| **4 Jurisprudence & treatment** | Proceeding; Decision (hüküm, ara karar, İBK, HGK/CGK, direnme, BAM, AYM norm, AYM BB, Danıştay İDDK, Uyuşmazlık); Passage with role (talep, savunma, tespit, gerekçe, hüküm, karşı oy); CitationOccurrence; Treatment | `inProceeding`; `reviews`; `treatmentType` {onama, bozma, kısmen bozma, düzelterek onama, kaldırma, direnme, direnmeye uyma, İBK ile aşılma, AYM iptali, AYM ihlal, kanun değişikliği ile etkilenme, atıf-nötr}; `citesProvisionVersion`; `authorityRole` | karar, tefhim, **kesinleşme** (often unknown), RG yayım, AYM effective date | Treatment → passage, extraction run, reviewer; **citation ≠ endorsement** | Public | Role-aware passages, procedural history → **weighted supportive/adverse authorities** |
| **5 Issues & arguments** | LegalIssue, Element, Exception, Defense, EvidentiaryQuestion, FactFeature, CandidateConsequence, Argument | `hasElement`; `elementGroundedIn`; `decisionTurnedOn FactFeature` (editor-asserted); `argumentSupports/Attacks`; `distinguishableBy` | Versioned with provisions | Elements → passages; review before ranking use | Trees public; **instances private** | Narrative → issues; missing facts; **comparison by legally relevant features** |
| **6 Procedure & deadlines** | ProceduralStage, Prerequisite (dava şartı arabuluculuk: 7036 m.3, TTK m.5/A), DeadlineRule, TriggerEvent, SuspensionCondition (adli tatil HMK m.104; mediation suspends limitation), Parameter + ParameterValue | `triggeredBy`; `duration` (2-week istinaf/temyiz; işe iade mediation/filing periods to confirm against current text); `valueBasisDate` {dava, karar, işlem, fesih}; `sourceRule` | `validFrom/Until` + basis-date semantics (7550 change) | Value → RG/genelge passage; computations list assumptions and open conditions | Public rules; private computations | **Missing inputs; auditable computations** (never a bare number) |
| **7 Practice graphs** | **Contracts:** clause types (cezai şart TBK 179–182, GİK TBK 20–25, fesih, rekabet yasağı, yetki/tahkim), Obligation, Performance, Breach, Notice (noter, KEP, e-tebligat), Amendment, Termination, Remedy. **Commercial:** Transaction, CorporateRole, AuthorityToRepresent (imza sirküleri, sicil), Debt, Guarantee (kefalet vs garanti), kambiyo senedi, cari hesap. **Employment:** relationship type, WorkPeriod, Remuneration, puantaj, TerminationEvent (İş K. 17, 18–21, 24–25), Claims (kıdem, ihbar, fazla mesai m.41, izin m.53, işe iade), Records (SGK hizmet dökümü, bordro, ibraname TBK 420, son tutanak) | Reuse modules 1/5; `instantiatesClauseType`; `evidencedBy Passage` | Private event dates with date status | Passage-level | Types public; instances private | **Clause search, comparison, extraction** |
| **8 Matter, facts, evidence** | Customer, Workspace, Matter, Person/Organisation vs RoleInMatter, Event, Document/Version, Passage, Assertion | `assertionStatus` {allegation, documentary statement, witness statement, judicial finding, lawyer hypothesis, legal conclusion, assumption}; `contradicts`; `correctedBy`; `aboutIssue → public IRI`; `supportsElement` | Event time with uncertainty; document date; recordedAt | Origin passage + run + status + reviewer | **Private, per tenant** | Timelines, contradictions, **public-law links without leakage** |
| **9 Provenance & coverage** | SourceArtifact, Representation, AcquisitionRecord, ExtractionRun, ReviewDecision, UsePermission, CorpusRelease, CoverageRecord | PROV-O; `permittedUse` {display, index, quote, train, offline-redistribute}; `sourceKind` {official text, official DB, commentary, summary, translation}; coverage by institution × chamber × year × doc type | System time (acquired/extracted/reviewed/released) separate from legal time | PROV chains to artifact hashes | Mirrors layer | **Audit; empty-result explanation** (absence vs gap vs failure) |
| **10 Firm knowledge & impact** | Playbook, ResearchNote, DraftingPattern, InternalInterpretation, ResearchOutput, DraftVersion | `dependsOn` (draft → argument → passage/version/treatment/release); `approvedBy`; `supersededBy`; change events → `impactFlag` | Approval and review-due dates | Approvals recorded | Private (firm/matter) | **Reuse approved knowledge; impact alerts** |

### 2.3 Turkish authority model (module 4)

| Decision type | Effect as modelled | Basis | Graph consequence [P] |
|---|---|---|---|
| Yargıtay **İBK** | Binding "benzer hukuki konularda"; published in RG; changed only by new İBK | YK m.45 [V]\[1\] | `binding-general`; scope = reviewed issue, never keyword-inferred |
| **HGK/CGK** after direnme | Binding in the file; persuasive-high elsewhere | HMK m.373 [V]\[40\] | `binding-in-proceeding` |
| **Daire** | Not formally binding; "yerleşik içtihat" is an editorial claim | [V]\[3\] | `persuasive`; "settled" only via reviewed `JurisprudenceLine` |
| **BAM** | Final below HMK m.362 threshold/listed matters, else temyiz-able | HMK 341/362 [V] | `finalityStatus` + `kesinleşmeTarihi` |
| **AYM iptal** | Erga omnes; effective on publication or deferred ≤1 year; not retroactive | Anayasa m.153 [V]\[2\] | `AmendmentEvent(iptal)` ends version at *effective* date |
| **AYM BB ihlal** / pilot | Binding in case; pilot addresses structural problems | 6216 [U] | Pilot flag only from text |
| **Danıştay İDDK/İBK** | Binding on administrative courts | 2575 [U] | As Yargıtay İBK |
| **Uyuşmazlık Mahkemesi** | Resolves inter-branch görev conflicts | Anayasa m.158 [U] | Feeds module 3 |
| **ECtHR** | Binding on Türkiye in the case | ECHR art. 46 [U] | Separate namespace; HUDOC licence limits |

We reject the US Shepard's model, which derives "good law" status and weight from court level. In Turkish law, weight depends on four things:
- decision *type*;
- *procedural position* (direnme);
- *finality*;
- later legislative or AYM events.

Treatments are sourced events, not flags.

### 2.4 Succession vs transferred competence (module 3)

```
hd/15/epoch/…  --succeededBy (renumbering)-->  hd/6/epoch/…
hd/16/epoch/…  --dissolvedOn--> [RG date]
   --competenceTransferredTo [scope]--> hd/1 ; --competenceTransferredTo [scope]--> hd/8
assign/2026-1/… assignedBy dec/yargitay/bgk/2026/1 ; publishedIn rg/2026-06-30/33296
```

Rules [P]:
1. A 2018 "15. HD" decision is not, in subject-matter terms, a decision of today's 6. HD.
2. A competence transfer does not merge case-law lines.
3. İş bölümü decisions are versioned like legislation.

Also load these timelines:
- BAM operational from 20.07.2016;
- military high courts abolished in 2017;
- mandatory mediation under 7036 (2017) and TTK m.5/A (2019);
- specialised courts.

### 2.5 Question path

| Step | Graph helps | Text/vector helps | Human needed |
|---|---|---|---|
| Question → concepts | Abbreviation/citation parsing ("İş K. 25/II-e", "TBK 347"), historic terms | Free-text intent | Ambiguity choice |
| → candidate issues | Elements, exceptions | Similar questions | Confirm framing |
| → relevant facts | Missing-element detection | Document extraction | Status, corrections |
| → provision versions | **Deterministic date-interval selection + transitional rules** | – | Legally relevant date |
| → comparable decisions | Procedural history, authority role, chamber epoch | Fact similarity | Comparability |
| → supporting/adverse passages | Role metadata, provenance | Span ranking | Final reading |

---

## 3. Reusable-asset inventory (research date: October 2026)

| Asset & link | Type | Owner | Version / maintenance | Coverage | Licence | Decision |
|---|---|---|---|---|---|---|
| SKOS — w3.org/TR/skos-reference | Vocabulary | W3C | Rec. 2009 | Neutral | W3C | **Adopt** |
| OntoLex-Lemon — w3.org/2016/05/ontolex | Lexical model | W3C CG | 2016 | Neutral | W3C CG | **Adapt** lightly |
| PROV-O — w3.org/TR/prov-o | Provenance | W3C | Rec. 2013 | Neutral | W3C | **Adopt** |
| SHACL — w3.org/TR/shacl | Validation | W3C | Rec. 2017 (1.2 work [U]) | Neutral | W3C | **Adopt** |
| Web Annotation — w3.org/TR/annotation-model | Selectors | W3C | Rec. 2017 | Neutral | W3C | **Adopt** |
| OWL-Time — w3.org/TR/owl-time | Time | W3C/OGC | Rec. | Neutral | W3C | **Align** |
| Dublin Core Terms | Metadata | DCMI | Stable | Neutral | CC BY 4.0 | **Adopt** |
| ELI ontology — data.europa.eu/eli/ontology | Ontology + URI pattern | EU Publications Office | **v1.5**; ELI-DL v3, ELI-I v1 | EU; no TR | EUPL\[15\]\[17\]\[20\] | **Adopt** classes; **adapt** URIs |
| ECLI — 2011/C 127/01, 2019/C 360/01 | Identifier + metadata | Council of the EU\[39\] | 2019\[36\]\[38\] | EU; Türkiye absent | Public | **Align** (no `ECLI:TR`) |
| Akoma Ntoso — docs.oasis-open.org/legaldocml | XML standard | OASIS LegalDocML TC | 1.0; v2.0/AKN 3.1 CS01 (May 2026)\[28\] | No TR use | OASIS | **Align** naming/FRBR; XML deferred to C |
| LegalRuleML 1.0 | Rules | OASIS | Standard [U] | Neutral | OASIS | **Reject for B** |
| LKIF-Core — github.com/RinkeHoekstra/lkif-core | Upper ontology | ESTRELLA/UvA | 1.1 (2008), unmaintained | EN | CC BY 4.0\[33\]\[34\] | **Inspiration only** |
| LRMoo / FRBR | Conceptual model | IFLA/CIDOC | [U] | Neutral | Open | **Align** |
| EuroVoc — op.europa.eu | Thesaurus | EU Publications Office | Maintained | **No Turkish**\[22\] | EU reuse [U] | **Reject as primary**; `closeMatch` subset |
| IATE — iate.europa.eu | Terminology | EU institutions | Non-EU languages "limited"\[59\] | Turkish unconfirmed | EU reuse | **Reference only** |
| legislation.gov.uk API | Design reference | The National Archives | Live | UK | OGL v3.0\[29\]\[32\] | **Model** for point-in-time |
| CourtListener / Harvard CAP | Citation-graph references | FLP / Harvard LIL | [U] | US | Open | Pattern only; reject US taxonomy |
| LegalBench-RAG — arXiv 2408.10343 | Benchmark | ZeroEntropy | 2024 | EN contracts\[56\]\[60\] | Public | **Adopt method** |
| SAT-Graph RAG — arXiv 2505.00039 | Architecture | de Martim | JURIX 2025\[11\] | Brazil | arXiv | **Design reference** |
| BERTurk-Legal — HF KocLab-Bilkent/BERTurk-Legal | Model | Öztürk, Özçelik & Koç (Bilkent) | SIU 2023 | TR | Check card | **Evaluate** |
| HukukBERT — arXiv 2604.04790 | Model | Academic | 2026 | TR\[13\] | [U] | **Evaluate** |
| TLNER / Çetindağ NER | Datasets | Academic | 2022–23 | TR\[12\]\[61\] | [U] | **Evaluate** |
| HF turkish-court-decisions | Unofficial dump | Individual | 2026 | TR\[58\] | Unclear | **Reject** as record |
| Lexpera, Kazancı, Legalbank, Sinerji, HukukTürk | Commercial | Publishers | Live | TR\[62\] | FSEK ek m.8 + contracts | **Licence only** |

---

## 4. Corpus-population plan

### 4.1 Source priorities

| Priority | Source | Use | Access / permitted use |
|---|---|---|---|
| P1 | MBS | Current consolidated baseline\[25\]\[63\] | Official; FSEK m.31; low-rate |
| P1 | Resmî Gazete | Original/amending texts, dates, İBK/AYM publication | Reusable texts, but robots.txt disallows agents → **governed manual/assisted import** or negotiated channel |
| P1 | TBMM KKBS | Gerekçe, committee reports | Targeted |
| P1 | Bedesten / karararama | Yargıtay 9./11./3. HD, HGK, İBK, 2015→ | Unofficial; ≥10 s spacing; hash responses |
| P1 | AYM BB + Norm | Annulments, BB | Official |
| P2 | emsal.uyap; Danıştay; SGK/GİB | BAM/first instance (selective); parameters | Per-source terms |
| P3 | HUDOC TR | ECtHR | Non-commercial → **legal review** |
| Licensed | Commercial DBs | Pre-2010 depth | Contracts govern indexing/offline redistribution |

Public accessibility is not permission for bulk acquisition or redistribution. Every source gets a `UsePermission` record, and the release builder excludes anything without one.

### 4.2 Identity, segmentation, citations [P]

**Identity**
- Instruments are keyed by MBS (tür, tertip, no) and anchored to their RG issue.
- Decisions are keyed by (court, chamber epoch, K no), plus the E no. for the proceeding.
- Copies of the same decision are de-duplicated by key + text hash. Each copy is kept as a separate artifact.

**Segmentation**
- Rule-based parsing of madde / fıkra / bent / alt bent, ek and geçici maddeler, and mülga markers.
- MBS "Değişik/Ek/Mülga" notes are treated as *claims* and verified against the RG.
- Versions are rebuilt by replaying amendments backwards and stay flagged `reconstructed` until an editor confirms them.

**Citations**
- A grammar covers the common variants: "4857 sayılı Kanun'un 25/II-e maddesi", "İş K. m.25/II(e)", "HMK 373/5", "Y.9.HD … E.… K.…", "YİBK 10.2.1956 1/1".
- Each citation resolves to a Provision, then to a version via the event date. When only the decision date is known, the result is flagged `heuristic-decision-date`.
- Classifying the treatment is a separate, reviewed step.

### 4.3 Extraction and review [P]

The pipeline runs: acquisition → hash → text → role segmentation → NER/citations → candidate relations → SHACL → editor queue. Review rules:
- İBK scope, AYM effects and `decisionTurnedOn` get two-person review.
- Citations and roles are checked by sampled QA (5% sample, 98% target).
- Rejected relations are kept so they are not re-proposed.

### 4.4 Backfill and updates [P]

**Backfill**
- **Phase 1:** post-2012 versions of TBK, TTK, 4857, 1475 m.14, 7036, HMK, 6325 and Tebligat K., plus predecessor maps (818→6098/6101; 6762→6102/6103; 1086→6100; 743→4721/4722; 1475→4857 m.120).
- **Phase 2:** 1980–2012.
- **Phase 3:** 1920→ for instruments still relevant (1475 m.14, 3095, 2004 İİK), via RG scans + OCR + editor confirmation.

**Updates**
- Daily RG check.
- Weekly MBS diffs and decision deltas.
- Event-driven loads for iş bölümü, AYM iptal, Jan/Jul parameters and the late-November YDO.
- Releases are immutable, signed and content-addressed. Offline bundles contain TriG + PostgreSQL dump + OpenSearch snapshot + SHACL report + coverage manifest.

---

## 5. Retrieval design

1. **Interpretation.**
   - Turkish normalisation: i/İ folding; diacritic-insensitive *search* fields with the original text preserved; lemmatiser.
   - Parse abbreviations, citations and dates.
   - Output: concepts, provisions, event date, matter scope, roles.
2. **Concept expansion.** Use only reviewed alt-labels, historic terms and depth-1 narrower concepts. Never expand across `mustNotConflateWith`; show the distinction instead.
3. **Candidates.** BM25 over Turkish-analysed passages plus a dense encoder chosen by evaluation (BERTurk-Legal/HukukBERT/multilingual). Keep separate provision, decision and tenant indexes.
4. **Bounded expansion.** At most 2 typed hops along whitelisted paths:
   - provision → valid versions → transitional rules;
   - decision → same proceeding → treatments;
   - passage → cited version;
   - issue → elements → `turnedOn` decisions.
   Fan-out cap of 50 per hop, plus a timeout.
5. **Filters.** Legal time (valid version, AYM effective dates); system time (pinned release); permissions (public + authorised tenant datasets only, resolved before the query is built).
6. **Rerank.** A cross-encoder plus explainable features:
   - passage role (gerekçe > iddia);
   - authority role (İBK > HGK > daire > BAM > first instance);
   - chamber-epoch and version match;
   - review status;
   - fact overlap.
7. **Adverse pass.** Search contrary element framing, bozma/İBK-aşılma treatments, opposite dispositions on the same issue, and later amendments or iptal. Reserve slots for these results.
8. **Evidence assembly.** Each claim gets a passage (artifact, release, selector, role, review status) plus a coverage statement, e.g. "Yargıtay 9. HD 2015–2026 indexed; first instance selective".

---

## 6. Illustrative implementation sample (explicitly SYNTHETIC)

> Every decision number, person, date and quote below is **synthetic**. The article numbers (4857 m.25–26) are given for orientation only, and the quoted texts are placeholders.

### 6.1 Public graph (`urn:graph:public/release/2026-10-01`)

```turtle
@prefix tlo: <https://kg.example.tr/ontology#> . @prefix eli: <http://data.europa.eu/eli/ontology#> .
@prefix prov: <http://www.w3.org/ns/prov#> .     @prefix skos: <http://www.w3.org/2004/02/skos/core#> .
@prefix oa: <http://www.w3.org/ns/oa#> .          @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
@prefix pub: <https://kg.example.tr/id/> .

pub:concept/hakli-neden-fesih a skos:Concept ; skos:prefLabel "haklı nedenle fesih"@tr ;
  tlo:mustNotConflateWith pub:concept/gecerli-neden-fesih ;
  tlo:definedBy pub:eli/kanun/4857/madde/25/v/2003-06-10 .

pub:eli/kanun/4857/madde/26 a tlo:Provision , eli:LegalResourceSubdivision ;
  eli:is_part_of pub:eli/kanun/4857 .
pub:eli/kanun/4857/madde/26/v/2003-06-10 a tlo:ProvisionVersion , eli:LegalExpression ;
  tlo:versionOf pub:eli/kanun/4857/madde/26 ;
  tlo:validFrom "2003-06-10"^^xsd:date ; tlo:dateStatus tlo:Known ;
  tlo:derivation tlo:ConfirmedAgainstRG ; tlo:reviewStatus tlo:EditorApproved ;
  tlo:hasManifestation [ a tlo:TextManifestation ;
      tlo:originalText "[SYNTHETIC PLACEHOLDER FOR OFFICIAL TEXT]"@tr ; tlo:sha256 "9f2c…" ] ;
  prov:wasDerivedFrom pub:artifact/rg-2003-06-10-25134 .
pub:artifact/rg-2003-06-10-25134 a tlo:SourceArtifact ; tlo:sourceKind tlo:OfficialText ;
  tlo:permittedUse tlo:Display , tlo:Index , tlo:Quote , tlo:OfflineRedistribute .

pub:dec/yargitay/hd9/2024/88801 a tlo:Decision ;                    # SYNTHETIC
  tlo:inProceeding pub:proc/yargitay/hd9/E/2023/99901 ;
  tlo:issuedBy pub:org/yargitay/hd/9/epoch/2016-07-20 ;
  tlo:kararTarihi "2024-03-12"^^xsd:date ; tlo:authorityRole tlo:Persuasive ;
  tlo:reviews pub:dec/bam/istanbul/9hd/2023/77701 ;
  tlo:disposition tlo:AgainstEmployer ;
  tlo:decisionTurnedOn pub:feature/fesih-6-isgunu-asildi .          # no kesinleşme date: unknown, not guessed

pub:dec/yargitay/hd9/2024/88801/p/14 a tlo:Passage ;
  tlo:inDecision pub:dec/yargitay/hd9/2024/88801 ; tlo:passageRole tlo:Gerekce ;
  tlo:citesProvisionVersion pub:eli/kanun/4857/madde/26/v/2003-06-10 ;
  tlo:selector [ a oa:TextQuoteSelector ;
     oa:exact "[SYNTHETIC] öğrenmeden itibaren altı iş günü geçtikten sonra yapılan fesih süresinde değildir" ] ;
  prov:wasGeneratedBy pub:extract/segmenter-v3-2026-09-20 ; tlo:reviewStatus tlo:EditorApproved .

pub:treat/0001 a tlo:Treatment ; tlo:treatmentType tlo:Bozma ;
  tlo:treatingDecision pub:dec/yargitay/hd9/2024/88801 ;
  tlo:treatedDecision pub:dec/bam/istanbul/9hd/2023/77701 ;
  tlo:evidencePassage pub:dec/yargitay/hd9/2024/88801/p/21 ;
  tlo:reviewStatus tlo:EditorApproved ; prov:wasAttributedTo pub:editor/E-07 .

pub:issue/employment/hakli-fesih-sure a tlo:LegalIssue ; tlo:hasElement pub:element/hfs/1 .
pub:element/hfs/1 a tlo:Element ;
  tlo:elementGroundedIn pub:eli/kanun/4857/madde/26/v/2003-06-10 .
pub:feature/fesih-6-isgunu-asildi a tlo:FactFeature ; tlo:featureOf pub:element/hfs/1 .
```

### 6.2 Private matter graph (`urn:tenant:T42:matter:M7`, tenant store only)

```turtle
@prefix tlo: <https://kg.example.tr/ontology#> . @prefix oa: <http://www.w3.org/ns/oa#> .
@prefix prov: <http://www.w3.org/ns/prov#> .     @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
@prefix pub: <https://kg.example.tr/id/> .        @prefix m: <urn:tenant:T42:matter:M7:> .

m:role/r1 a tlo:RoleInMatter ; tlo:roleType tlo:Isci ; tlo:player m:person/p1 .   # SYNTHETIC
m:event/fesih a tlo:Event ; tlo:eventDate "2025-03-10"^^xsd:date ; tlo:dateStatus tlo:Known .
m:event/ogrenme a tlo:Event ; tlo:dateStatus tlo:Unknown .                       # stays unknown

m:doc/d3/v1/p/2 a tlo:Passage ; tlo:inDocumentVersion m:doc/d3/v1 ;
  tlo:selector [ a oa:TextPositionSelector ; oa:start 1204 ; oa:end 1391 ] .

m:assert/a1 a tlo:Assertion ; tlo:assertionStatus tlo:DocumentaryStatement ;
  tlo:statement "Employer's report records absence on 2025-02-25." ;
  tlo:originPassage m:doc/d3/v1/p/2 ; tlo:supportsElement pub:element/hfs/1 ;
  prov:wasGeneratedBy m:extract/x9 ; tlo:reviewStatus tlo:LawyerConfirmed .
m:assert/a2 a tlo:Assertion ; tlo:assertionStatus tlo:Allegation ; tlo:assertedBy m:role/r1 ;
  tlo:statement "Employee alleges employer knew by 2025-02-20." ;
  tlo:originPassage m:doc/d5/v1/p/4 ; prov:wasGeneratedBy m:extract/x9 ;
  tlo:contradicts m:assert/a1 .

m:issue/i1 a tlo:MatterIssue ; tlo:instantiates pub:issue/employment/hakli-fesih-sure ;
  tlo:relevantEventDate "2025-03-10"^^xsd:date ;
  tlo:applicableVersion pub:eli/kanun/4857/madde/26/v/2003-06-10 ;
  tlo:applicabilityAssessment tlo:LawyerHypothesis ;
  tlo:supportingAuthority pub:dec/yargitay/hd9/2024/88801/p/14 .
m:draft/dilekce/v2 a tlo:DraftVersion ;
  tlo:dependsOn m:issue/i1 , pub:dec/yargitay/hd9/2024/88801/p/14 , pub:release/2026-10-01 .
```

### 6.3 SHACL constraints

```turtle
@prefix sh: <http://www.w3.org/ns/shacl#> . @prefix tlo: <https://kg.example.tr/ontology#> .
@prefix prov: <http://www.w3.org/ns/prov#> .

tlo:ProvisionVersionShape a sh:NodeShape ; sh:targetClass tlo:ProvisionVersion ;
  sh:property [ sh:path tlo:versionOf ; sh:minCount 1 ; sh:maxCount 1 ] ;
  sh:property [ sh:path tlo:dateStatus ; sh:minCount 1 ; sh:in ( tlo:Known tlo:Unknown tlo:Disputed tlo:Inferred ) ] ;
  sh:property [ sh:path prov:wasDerivedFrom ; sh:minCount 1 ] ;
  sh:sparql [ sh:message "Known needs validFrom; Unknown forbids placeholder dates." ;
    sh:select """SELECT $this WHERE { { $this tlo:dateStatus tlo:Known . FILTER NOT EXISTS { $this tlo:validFrom ?d } }
                 UNION { $this tlo:dateStatus tlo:Unknown ; tlo:validFrom ?d } }""" ] .

tlo:TreatmentShape a sh:NodeShape ; sh:targetClass tlo:Treatment ;
  sh:property [ sh:path tlo:treatmentType ; sh:minCount 1 ; sh:in ( tlo:Onama tlo:Bozma tlo:KismenBozma
      tlo:DuzelterekOnama tlo:Kaldirma tlo:Direnme tlo:DirenmeyeUyma tlo:IBKileAsilma tlo:AYMIptali
      tlo:AYMIhlal tlo:KanunDegisikligiIleEtkilenme tlo:AtifNotr ) ] ;
  sh:property [ sh:path tlo:evidencePassage ; sh:minCount 1 ; sh:class tlo:Passage ] ;
  sh:property [ sh:path tlo:reviewStatus ; sh:minCount 1 ] ;
  sh:property [ sh:path prov:wasAttributedTo ; sh:minCount 1 ] .

tlo:AssertionShape a sh:NodeShape ; sh:targetClass tlo:Assertion ;
  sh:property [ sh:path tlo:assertionStatus ; sh:minCount 1 ; sh:maxCount 1 ; sh:in ( tlo:Allegation
      tlo:DocumentaryStatement tlo:WitnessStatement tlo:JudicialFinding tlo:LawyerHypothesis
      tlo:LegalConclusion tlo:Assumption ) ] ;
  sh:property [ sh:path tlo:originPassage ; sh:minCount 1 ] ;
  sh:property [ sh:path prov:wasGeneratedBy ; sh:minCount 1 ] .

tlo:BindingRoleShape a sh:NodeShape ; sh:targetClass tlo:Decision ;
  sh:sparql [ sh:message "Binding role without reviewed scope and legal basis." ;
    sh:select """SELECT $this WHERE { $this tlo:authorityRole tlo:BindingGeneral .
       FILTER NOT EXISTS { $this tlo:bindingScope ?i ; tlo:bindingBasis ?b ; tlo:reviewStatus tlo:EditorApproved } }""" ] .

# Release gate, run over every PUBLIC graph before signing (validator targets all subjects):
tlo:NoPrivateIRIShape a sh:NodeShape ; sh:targetSubjectsOf tlo:releaseMember ;
  sh:sparql [ sh:message "Private urn:tenant: IRI in public release." ;
    sh:select """SELECT $this WHERE { $this ?p ?o .
       FILTER( STRSTARTS(STR($this),"urn:tenant:") || (isIRI(?o) && STRSTARTS(STR(?o),"urn:tenant:")) ) }""" ] .
```

### 6.4 Bounded SPARQL queries

**Q1 – Version valid on the event date**
```sparql
PREFIX tlo: <https://kg.example.tr/ontology#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
SELECT ?v ?from ?until WHERE {
  VALUES (?prov ?d) { (<https://kg.example.tr/id/eli/kanun/4857/madde/26> "2025-03-10"^^xsd:date) }
  ?v tlo:versionOf ?prov ; tlo:dateStatus tlo:Known ; tlo:validFrom ?from .
  OPTIONAL { ?v tlo:validUntil ?until }
  FILTER( ?from <= ?d && (!BOUND(?until) || ?until > ?d) ) } LIMIT 5
```

**Q2 – Later amendments, annulments and transitional rules to investigate**
```sparql
PREFIX tlo: <https://kg.example.tr/ontology#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
SELECT ?event ?type ?eff ?trans WHERE {
  VALUES (?prov ?d) { (<https://kg.example.tr/id/eli/kanun/4857/madde/26> "2025-03-10"^^xsd:date) }
  ?v tlo:versionOf ?prov . { ?v tlo:endedBy ?event } UNION { ?v tlo:createdBy ?event }
  ?event tlo:amendmentType ?type ; tlo:effectiveDate ?eff . FILTER(?eff > ?d)
  OPTIONAL { ?trans tlo:transitionalRuleFor ?event } } ORDER BY ?eff LIMIT 50
```

**Q3 – Adverse authorities (issue → feature → decision → treatment)**
```sparql
PREFIX tlo: <https://kg.example.tr/ontology#>
SELECT DISTINCT ?dec ?passage ?role ?laterTreatment WHERE {
  <https://kg.example.tr/id/issue/employment/hakli-fesih-sure> tlo:hasElement ?el .
  ?feature tlo:featureOf ?el . ?dec tlo:decisionTurnedOn ?feature ;
       tlo:disposition tlo:AgainstEmployer ; tlo:authorityRole ?role .   # opposite of client position
  ?passage tlo:inDecision ?dec ; tlo:passageRole tlo:Gerekce ; tlo:reviewStatus tlo:EditorApproved .
  OPTIONAL { ?t tlo:treatedDecision ?dec ; tlo:treatmentType ?laterTreatment } } LIMIT 25
```

**Q4 – Required element without supporting evidence (tenant dataset + public endpoint)**
```sparql
PREFIX tlo: <https://kg.example.tr/ontology#>
SELECT ?el WHERE {
  <urn:tenant:T42:matter:M7:issue/i1> tlo:instantiates ?issue .
  SERVICE <https://public.kg.local/sparql> { ?issue tlo:hasElement ?el }
  FILTER NOT EXISTS { ?a tlo:supportsElement ?el ; tlo:reviewStatus tlo:LawyerConfirmed ;
     tlo:assertionStatus ?s . FILTER(?s IN (tlo:DocumentaryStatement, tlo:WitnessStatement, tlo:JudicialFinding)) } }
```

**Q5 – Drafts depending on a changed source (≤2 hops)**
```sparql
PREFIX tlo: <https://kg.example.tr/ontology#>
SELECT DISTINCT ?draft WHERE {
  VALUES ?c { <https://kg.example.tr/id/dec/yargitay/hd9/2024/88801/p/14> }
  ?draft a tlo:DraftVersion .
  { ?draft tlo:dependsOn ?c } UNION { ?draft tlo:dependsOn ?mid . ?mid tlo:dependsOn|tlo:supportingAuthority ?c } } LIMIT 200
```

**Authorization-aware retrieval [P]:**
- **Tenant isolation:** give each tenant its own Fuseki dataset. Do not rely on graph ACLs inside a read-write dataset; they apply only to read-only datasets, and `jena-permissions` is slated for removal [V].\[54\]\[55\]
- **Matter access:** enforced in the application. Each matter maps to a named-graph list; queries use explicit `FROM NAMED`; default is deny.
- **OpenSearch:** per-tenant indexes with a `matter_id` filter.
- **Audit:** every query is logged.
- **Public endpoint:** read-only; it receives no private data and sends no telemetry when offline.

---

## 7. Prioritised delivery plan

| Phase | Scope | Exit criterion | Editor effort [P] | Engineering [P] |
|---|---|---|---|---|
| **0 (0–2 mo)** | Ontology v0.1 (ELI/PROV/SKOS/Web Annotation), SHACL gates, IRI policy, use-permission registry, signed releases | CI green; privacy-gate tests | 0.5 FTE knowledge engineer | 2 |
| **1 Smallest validated slice (2–6 mo)** | Employment termination: 4857 m.17–21, 24–26, 41, 53, 120; 1475 m.14; 7036 m.3; TBK m.420; HMK m.341/362/373 + Ek m.1; parameter tables 2016–2026; Yargıtay 9. HD/HGK/İBK passages 2015–2026 with roles/treatments; ~15 issue trees; private matter graph | Version-correctness ≥0.9; adverse recall > hybrid; zero exposure | ≈8 person-months (~300 provisions confirmed; ~3,000 decisions sample-reviewed) | 3 |
| **2 (6–12 mo)** | TBK general part (20–25, 117 ff., 146–161, 179–182); TTK m.4–5/A; kefalet/garanti; kambiyo; 3./11. HD lines; ~1,500 concepts; module 10 alerts | Same metrics per practice | 3–4 editors | 3–4 |
| **3 (12–24 mo)** | Predecessor codes (818, 6762, 1086) 1980→; BAM; AYM BB; licensed pre-2010 depth | ≥95% of RG amendment events since 2003 for core codes | +1–2 editors | 2 |
| **Maintenance** | Daily RG, weekly deltas, Jan/Jul parameters, YDO, iş bölümü | Weekly connected / monthly offline releases | ~1.5 FTE editors | 1.5 FTE |

**Costs [P/U].** Staff is the dominant cost. Infrastructure is 3–5 on-prem servers per installation plus GPU. Commercial licences, especially offline-redistribution rights, are the main uncertainty.

**Responsibilities:**
- Editors: versions, treatments, issue trees.
- Knowledge engineer: ontology and SHACL.
- Ops: acquisition and releases.
- Firms: private corrections and playbooks.

**Dependencies:** RG access permission; Bedesten/karararama stability; HUDOC commercial use; commercial offline terms; model licences.

---

## 8. Evaluation plan

**Systems.** All run on one frozen release, each adding a layer:
- **S0:** hybrid baseline (BM25 + dense + cross-encoder).
- **S1:** S0 + temporal provisions.
- **S2:** S1 + authority/treatment.
- **S3:** S2 + issues/features.
- **S4:** full Option B with the matter graph.

**Gold set [P].** 360 queries, 120 per practice. Each carries an event date, the expected version, span-level relevant and adverse passages (LegalBench-RAG style), and the decisive features. Subsets:
- ≥30% temporal queries that straddle an amendment (7550 date basis; 818→6098 transition);
- chamber-renumbering queries;
- empty-answer queries;
- synthetic private matters.

Two annotators plus adjudication; inter-annotator agreement is reported.

| Metric | Target (phase 1) [P] |
|---|---|
| nDCG@10, Recall@50 (passages) | S4 ≥ S0 + 10% relative |
| Version-correctness rate | ≥ 0.95 |
| Citation-resolution accuracy (provision / decision incl. chamber epoch) | ≥ 0.97 / ≥ 0.93 |
| Passage-role accuracy | ≥ 0.95 |
| Factual comparability (editor-rated, top-5) | ≥ 0.7 |
| Adverse-authority recall@10 | S4 ≥ S0 + 20% relative |
| Evidence-span precision (character level) | ≥ 0.85 |
| Empty-result explanation accuracy | ≥ 0.9 |
| Unauthorized-data exposure (red team, cross-tenant probes) | **= 0** (release blocker) |
| p95 latency | ≤ 3 s connected; ≤ 5 s offline |
| Review effort (editor min/relation; lawyer min/answer) | Tracked, trending down |

**Ablations.**
- Remove one module at a time from S4 (modules 1, 2, 3, 4, 5, 6, 9) and report paired-bootstrap confidence intervals.
- Keep a module only if it significantly improves a target metric without hurting latency or exposure.
- Also ablate hop limits (0/1/2) and the reranker's authority-role and passage-role features.

---

## Competency tests

| Test | Modules / relations |
|---|---|
| Which provision version was relevant on the event date? | M2 `versionOf`/`validFrom`/`dateStatus` + M8 `eventDate` (Q1); lawyer picks the relevant date |
| Which later amendments or transitional provisions need investigation? | M2 AmendmentEvent, `transitionalRuleFor`, AYM iptal; M6 basis-date (Q2) |
| Which decisions discuss the issue under comparable facts; what differences matter? | M5 `decisionTurnedOn`/`distinguishableBy` + M4 passages + M8 assertions; human judges comparability |
| Which authorities challenge the argument? | M4 treatments/dispositions, M5 `argumentAttacks`, M2 later events (Q3 + adverse slots) |
| Is a passage a party submission, finding or reasoning? | M4 `passageRole` + M9 extraction/review; stored, not inferred at answer time |
| Which required fact lacks evidence? | M5 `hasElement` + M8 `supportsElement`/status (Q4); allegations don't count |
| Which documents contradict an assertion? | M8 `contradicts` + `originPassage`; NLI proposes, lawyer confirms |
| Which outputs/drafts depend on a changed source? | M10 `dependsOn` + M9 releases + M2/M4 change events (Q5) |
| Missing result: no authority, or incomplete coverage? | M9 CoverageRecord, acquisition failures, permission exclusions |
| Can every substantive relationship be explained by source and review history? | M9 PROV chains + SHACL gates on treatments, assertions, binding roles |

## Permitted and prohibited inference [P]

**Permitted (automatic):**
- version selection by interval;
- transitive part-of;
- chamber-epoch resolution;
- impact propagation along `dependsOn`;
- reviewed concept expansion;
- candidate computations that show their source rule, assumptions and open inputs.

**Prohibited:**
- binding force from court level or citation counts;
- "good law" from finding no later treatment, since the absence may be a coverage gap;
- applicability or liability from taxonomy, similarity or graph paths;
- truth from accurate quotation;
- competence from succession;
- TR↔EN equivalence;
- treating a hypothesis as a conclusion.

## Assumptions

1. Kanun numbers are unique within the kanun series; other instrument types need RG-based keys.
2. Bedesten and karararama remain usable; if not, licensed sources fill the gap.
3. Turkish-qualified editors can be hired at the stated effort.
4. Customers accept weekly (connected) or monthly (offline) releases.
5. Effort and cost figures are planning estimates.
6. The synthetic examples simplify the law and are not legal statements.

## Unresolved questions

1. Is a lawful automated RG channel obtainable despite the robots.txt restrictions?
2. Will any Turkish authority adopt ELI or ECLI? None was found.
3. The 2026/1 iş bölümü was prepared by the Başkanlar Kurulu and approved by the Büyük Genel Kurul, not the earlier Birinci Başkanlık Kurulu route. What is its statutory basis, and what are the resulting chamber epochs? Verify from the RG text.
4. Secondary sources conflict on 2026 figures: senetle ispat is given as 41,000 vs 42,000 TL, and istinaf as 50,000 TL vs a computed 50,196 TL.\[6\]\[64\]\[65\] Confirm the official rounding first.
5. A practitioner site reports that 7589 sayılı Kanun (RG 31.07.2026) changed the tek hâkim threshold and administrative appeal routes.\[8\] This is unverified.
6. Is HUDOC's Turkish licence compatible with commercial use?
7. What are the commercial licences for BERTurk-Legal, HukukBERT and TLNER?
8. Does IATE contain Turkish entries? This is not confirmed.
9. Exact dates of the 2020–2021 chamber closures and renumberings need confirming from RG texts. BirGün reports the 23. HD closed on 4 February 2021 (files to the 15. HD) and the 17. HD on 8 April 2021 (files to the 4. HD). AA puts the 16. HD closure and the 15.→6. and 14.→7. renumberings at 1 July 2021 (BBK decision No. 211 of 02/07/2021). These are news reports only; load the dates from the RG.

## Caveats

- Evidence that graph-assisted retrieval beats strong hybrid search in law comes from architectures and prototypes. For Turkish law it is a hypothesis this plan tests.
- The details on AYM pilot judgments, Danıştay İBK and the Uyuşmazlık Mahkemesi are marked [U] and need confirmation by a public-law editor.
- The 2026 parameters come from multiple concordant secondary sources, plus the Çalışma GM post for the kıdem tavanı.\[47\] The RG or genelge text must be the source of record in module 6.

## Sources

1. [Hukuk Genel Kurulu'nun 2025/491 E., 2026/103 K. sayılı kararı - Hukuki Haber](https://www.hukukihaber.net/hukuk-genel-kurulunun-2025491-e-2026103-k-sayili-karari)
2. [Jurix](https://www.jurix.com.tr/article/36932?u=0&c=0)
3. [HMK Madde 373 Bozmaya Uyma veya Direnme](https://barandogan.av.tr/blog/mevzuat/hmk-madde-373-bozmaya-uyma-veya-direnme.html)
4. [YARGITAY HUKUK VE CEZA DAİRELERİ İŞ BÖLÜMÜ](https://istanbulbarosu.org.tr/haber/yargitay-hukuk-ve-ceza-daireleri-is-bolumu)
5. [Yargıtay Dairelerinin İş Bölümü (Ceza ve Hukuk) (2026)](https://kadimhukuk.com.tr/makale/yargitay-dairelerinin-is-bolumu-ceza-ve-hukuk/)
6. [2026 Yılı Yargıda Parasal Sınırlar - Bayram & Gedikli Hukuk ve Danışmanlık](https://bayram-gedikli.av.tr/2026-yili-yargida-parasal-sinirlar/)
7. [2026 İstinaf, Temyiz ve Senetle İspat Sınırı](https://smarthukuk.com/blog/2026-yargida-parasal-sinirlar-istinaf-temyiz)
8. [Yargıda Parasal Sınırlar 2026: Temyiz ve İstinaf Tablosu](https://hukukcularevi.com/hukuk-gundemi/2026-yargida-parasal-sinirlar-istinaf-temyiz-kesinlik-7550-sayili-kanun-dava-tarihi-esasi/)
9. [2026 Yargıda Parasal Sınırlar: İstinaf ve Temyiz](https://www.apilex.ai/tr/blog/yargi-parasal-sinirlar-istinaf-temyiz)
10. [Adli ve İdari Yargıda Parasal Sınırlar (2026)](https://kadimhukuk.com.tr/makale/adli-ve-idari-yargida-parasal-sinirlar/)
11. [\[2505.00039\] An Ontology-Driven Graph RAG for Legal Norms: A Structural, Temporal, and Deterministic Approach](https://arxiv.org/abs/2505.00039)
12. [Named-entity recognition in Turkish legal texts](https://www.researchgate.net/publication/361911556_Named-entity_recognition_in_Turkish_legal_texts)
13. [HukukBERT: Domain-Specific Language Model for Turkish Law](https://arxiv.org/html/2604.04790v1)
14. [A transformer-based prior legal case retrieval method](https://repository.bilkent.edu.tr/items/5fb0103c-3377-4577-a681-8f80ee84ce70)
15. [ELI Ontology - EU Vocabularies - Publications Office of the EU](https://op.europa.eu/en/web/eu-vocabularies/dataset/-/resource?uri=http%3A%2F%2Fpublications.europa.eu%2Fresource%2Fdataset%2Feli)
16. [Choose the experimental features you want to try](https://www.eur-lex.europa.eu/eli-register/background.html)
17. [interoperable-europe.ec.europa.eu](https://interoperable-europe.ec.europa.eu/collection/eli-european-legislation-identifier/solution/eli-ontology-draft-legislation-eli-dl/releases)
18. [interoperable-europe.ec.europa.eu](https://interoperable-europe.ec.europa.eu/collection/eli-european-legislation-identifier/solution/eli-i/releases)
19. [ELI ontology - EU Open Data Portal](https://data.europa.eu/eli/ontology)
20. [interoperable-europe.ec.europa.eu](https://interoperable-europe.ec.europa.eu/collection/eli-european-legislation-identifier/solution/eli-ontology/release/12)
21. [EuroVoc - EU Vocabularies - Publications Office of the EU](https://op.europa.eu/en/web/eu-vocabularies/eurovoc)
22. [EuroVoc - EU Vocabularies - Publications Office of the EU](https://op.europa.eu/en/web/eu-vocabularies/dataset/-/resource?uri=http%3A%2F%2Fpublications.europa.eu%2Fresource%2Fdataset%2Feurovoc)
23. [Türkiye Barolar Birliği Dergisi 135.Sayı](http://tbbdergisi.barobirlik.org.tr/Dergi/Dergi135/487/)
24. [karşılıklı güven ilkesi ile temel hakların korunması](https://avrupa.marmara.edu.tr/dosya/avrupa/mjes%20arsiv/Vol%2027_1/1_Gocmen.pdf)
25. [Mevzuat Bilgi Sistemi](https://www.mevzuat.tr/hakkimizda)
26. [Akoma Ntoso Version 1.0 - OASIS Open](https://www.oasis-open.org/standard/akn-v1-0/)
27. [Legal XML](https://en.wikipedia.org/wiki/Legal_XML)
28. [Invitation to comment on Akoma Ntoso v2.0 Part 2 (AKN 3.1) before call for consent as OASIS Standard - OASIS Open](http://www.oasis-open.org/2026/07/16/invitation-to-comment-on-akoma-ntoso-v2-0-part-2-akn-3-1-before-call-for-consent-as-oasis-standard/)
29. [Legislation.gov.uk » VoxPopuLII](https://blog.law.cornell.edu/voxpop/2010/08/15/legislationgovuk/)
30. [www.legislation.gov.uk Legislation Data Access, Formats & Completeness](https://cdn.nationalarchives.gov.uk/documents/cas-82049-legislation-date.pdf)
31. [feat(uk): point-in-time provision text, stored as intervals not snapshots by overthelex · Pull Request #2432 · overthelex/secondlayer](https://github.com/overthelex/secondlayer/pull/2432)
32. [API & MCP docs — UK Legislation Changes](https://uk-legal-changes.pages.dev/docs)
33. [lkif-core/lkif-core.owl at master · RinkeHoekstra/lkif-core](https://github.com/RinkeHoekstra/lkif-core/blob/master/lkif-core.owl)
34. [lkif-core/lkif-extended.owl at master · RinkeHoekstra/lkif-core](https://github.com/RinkeHoekstra/lkif-core/blob/master/lkif-extended.owl)
35. [LKIF-Core Ontology: A Commonsense-based Legal Ontology](https://www.estrellaproject.org/lkif-core/)
36. [EUR-Lex - 52019XG1024(01) - EN - EUR-Lex](https://eur-lex.europa.eu/legal-content/GA/TXT/?uri=CELEX%3A52019XG1024%2801%29)
37. [C\_2011127EN.01000101.xml](https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX%3A52011XG0429%2801%29&from=PL)
38. [ECLI - European Case-Law Identifier - EUR-Lex](https://eur-lex.europa.eu/content/help/eurlex-content/ecli.html?locale=en)
39. [European Case Law Identifier](https://en.wikipedia.org/wiki/European_Case_Law_Identifier)
40. [111 Araştırma Makalesi Geliş Tarihi: 30/12/2024 Kabul Tarihi: 6/3/2025](https://ayam.anayasa.gov.tr/media/6913/03-mehmet-emin-alparslan.pdf)
41. [anayasa mahkemesinin iptal kararı kazanılmış hakları ...](https://karamercanhukuk.com/yargitay-karari/anayasa-mahkemesinin-iptal-karari-kazanilmis-haklari-etkilemez)
42. [Yargıtay Dairelerinde Yeni İş Bölümü Belirlendi - Alomaliye.com](https://www.alomaliye.com/2026/06/30/yargitay-dairelerinde-yeni-is-bolumu-belirlendi/)
43. [7550 Sayılı Ceza ve Güvenlik Tedbirlerinin İnfazı Hakkında Kanun ile Bazı Kanunlarda Değişiklik Yapılmasına Dair Kanun - Alomaliye.com](https://www.alomaliye.com/2025/06/04/7550-sayili-ceza-ve-guvenlik-tedbirlerinin-infazi-hakkinda-kanun/)
44. [İstinaf Sınırı 2026: Kesinlik ve İstinafa Kapalı Kararlar](https://hukukcularevi.com/istinaf-kesinlik-siniri-2026-hangi-kararlara-istinaf-kapali/)
45. [2026 Yılı İstinaf ve Temyiz Sınırları](https://mefendizadehukuk.com/istinaf-ve-temyiz-sinirlari/)
46. [1 temmuz 2026 tarihinden itibaren vergiden istisna kıdem ...](https://www.turmob.org.tr/ekutuphane/Read/3e0209c4-df4c-4815-8d27-73f76ee34bce)
47. [Çalışma Genel Müdürlüğü on X: "📢 Kıdem Tazminatı ...](https://x.com/cgm_csgb/status/2079157224333562088)
48. [Kıdem Tazminatı](https://www.verginet.net/dtt/1/kidem-tazminati-tavani.aspx)
49. [KVKK'nın Avukatlar İçin Rehberi: Dosyayı Yapay Zekâya Yüklemek Yurt Dışına Aktarım Sayılabilir](https://sinanogluhukuk.com/tr/makaleler/kvkk-avukatlar-rehberi-yapay-zeka-yurt-disi-aktarim)
50. [Avukatlar İçin KVKK Rehberi 2026](https://www.gecmezhukuk.com/avukatlar-icin-kvkk-rehberi/)
51. [Avukatlar İçin KVKK Rehberi: Tevkil, Yapay Zekâ ve Veri Aktarımı - Alomaliye.com](https://www.alomaliye.com/2026/09/23/avukatlar-icin-kvkk-rehberi-tevkil-yapay-zeka-ve-veri-aktarimi/)
52. [Yapay zekâ kullanımına sıkı denetim: Avukatlar için KVKK’dan 15 altın kural](https://www.yenisafak.com/teknoloji/yapay-zeka-kullanimina-siki-denetim-avukatlar-icin-kvkkdan-15-altin-kural-4858741)
53. [Türkiye Barolar Birliği Tarafından Avukatlar İçin Yapay Zeka Kullanımı Tavsiye Rehberi Yayımlanmıştır - Duyurular](https://www.zumbul.av.tr/tr/duyurular/turkiye-barolar-birligi-tarafindan-avukatlar-icin-yapay-zeka-kullanimi-tavsiye-rehberi-yayimlanmisti)
54. [Apache Jena - Data Access Control for Fuseki](https://jena.apache.org/documentation/fuseki2/fuseki-data-access-control.html)
55. [Apache Jena - Adding Jena Permissions to Fuseki](https://jena.apache.org/documentation/permissions/example.html)
56. [\[2408.10343\] LegalBench-RAG: A Benchmark for Retrieval-Augmented Generation in the Legal Domain](https://arxiv.org/abs/2408.10343)
57. [An Ontology-Driven Graph RAG for Legal Norms: A Structural, Temporal, and Deterministic Approach](https://arxiv.org/html/2505.00039)
58. [hamzabagirsakci/turkish-court-decisions · Datasets at Hugging Face](https://huggingface.co/datasets/hamzabagirsakci/turkish-court-decisions)
59. [online-help.iate.europa.eu](https://online-help.iate.europa.eu/about)
60. [GitHub - zeroentropy-ai/legalbenchrag: This is the repo for the LegalBench-RAG Paper: https://arxiv.org/abs/2408.10343. · GitHub](https://github.com/zeroentropy-ai/legalbenchrag)
61. [A workflow-oriented and risk-aware system for Turkish legal named entity recognition: integrating transformer-based models with legal knowledge graphs](https://link.springer.com/article/10.1007/s44443-026-00915-z)
62. [LEXPERA - Hukuk Bilgi Sistemi: Mevzuat, İçtihat, Literatür & Örnekler](https://www.lexpera.com.tr/)
63. [T.C. Mevzuat Bilgi Sistemi - Google Play'de Uygulamalar](https://play.google.com/store/apps/details?id=tr.gov.tccb.mevzuat&hl=en_US)
64. [Kesin Karara Karşı İstinaf Yolu, Parasal Sınır ve İstisnalar 2026](https://www.apilex.ai/blog/kesin-karar-istinaf-siniri-2026)
65. [2026 YILI PARASAL SINIRLAR](https://www.mychukuk.com/post/parasal-s%C4%B1n%C4%B1rlar-2026)
