# Deep Research Query: Ontology and Knowledge Graphs for a Türkiye-First Legal Assistant

Act as a legal knowledge engineer, Turkish legal researcher, and information-retrieval architect. Conduct deep research and propose an ontology and knowledge-graph architecture for a Türkiye-first legal assistant.

The objective is to improve **domain understanding, legal research quality, evidence traceability, and lawyer preparation workflows**. Explain how each proposed graph improves an actual assistant capability.

## Platform context and scope

Our initial practice areas are **contracts, commercial disputes, and employment law**. The architecture should support nationwide legal-domain coverage, with deeper population and validation in those three areas first. Historical coverage should begin in 1920, with earlier material included when necessary to explain continuity or applicable law.

The platform keeps confidential customer and matter information on premises. Public legal material enters through governed imports or a controlled external-data gateway. Strictly disconnected installations must work with offline releases. Proposals must support both deployment models.

Our starting architecture uses RDF/Turtle, SKOS, SHACL, Jena/Fuseki, PostgreSQL, and OpenSearch. Two logical public graph families already exist:

- **Legal structure:** concepts, legislation, provision versions, institutions, competences, legal positions, and procedures.
- **Historical jurisprudence:** proceedings, decisions, findings, arguments, reasoning, dispositions, citations, and qualified relationships between authorities.

These are initial schemas, not a populated or legally validated corpus. Propose improvements, extensions, and population strategies. A graph module does not necessarily require its own database.

Clearly distinguish **ontology/schema**, **populated public knowledge**, **private matter instances**, and **derived retrieval indexes**.

## Graph modules to investigate

Research the following graph modules and explain how they should connect:

| Graph module | What it should represent | How it should improve the assistant |
|---|---|---|
| **1. Legal terminology and concept graph** | Turkish legal concepts, definitions, aliases, abbreviations, historical terminology, broader/narrower concepts, related concepts, and carefully qualified multilingual mappings. Definitions must link to their sources and relevant versions. | Resolve ambiguous questions, recognize equivalent terminology, expand searches appropriately, and preserve distinctions between related legal concepts. |
| **2. Legislation and provision-history graph** | Instruments, articles, paragraphs, exact text versions, enactment, publication, commencement, amendment, repeal, transitional provisions, cross-references, and relationships between predecessor and successor provisions. | Retrieve the version relevant to an event date, trace amendments, identify transitional questions, and prevent substitution of today’s text for historical law. |
| **3. Institutions, jurisdiction, and competence graph** | Courts, chambers, boards, administrative bodies, territorial scope, institutional changes, procedural routes, and separately evidenced competences over time. | Identify candidate forums and relevant decision-making bodies, interpret historical court names, and avoid confusing institutional succession with transferred competence. |
| **4. Jurisprudence and authority-treatment graph** | Proceedings and individual decisions; court/chamber identifiers; dates and procedural stages; party submissions; judicial findings; reasoning; dispositions; dissenting opinions; citation occurrences; and evidenced treatment of earlier decisions or provisions. | Find relevant decision passages, follow procedural and citation history, identify conflicting interpretations, and retrieve supportive and adverse authorities. Citation alone must not imply endorsement or legal applicability. |
| **5. Legal issues, tests, fact patterns, and argument graph** | Legal questions, required elements, conditions, exceptions, defenses, evidentiary questions, candidate consequences, and arguments connecting facts to authorities. Represent which factual features matter to a particular issue. | Turn a narrative into researchable issues, identify missing facts, compare cases by legally relevant similarities and differences, and explain why an authority may or may not help. |
| **6. Procedure, remedies, and deadline graph** | Procedural stages, prerequisites, notifications, applications, remedies, triggering events, deadline rules, suspension/interruption conditions, and versioned computational parameters where appropriate. | Retrieve procedural requirements and expose missing inputs. Any calculation must identify its source rule, assumptions, relevant version, and unresolved conditions. |
| **7. Practice-specific graphs** | Contracts: parties, capacity, representation, clauses, obligations, performance, breach, notices, amendments, termination, and remedies. Commercial matters: transactions, corporate roles, authority, debt, guarantees, and disputed obligations. Employment: relationship status, dates, duties, remuneration, working arrangements, termination events, claims, and supporting records. | Improve clause search, document comparison, issue spotting, factual extraction, and authority retrieval for the first three practices. Reuse shared concepts across domains. |
| **8. Private matter, facts, and evidence graph** | Customers, workspaces, matters, participants and contextual roles, events, timelines, documents, passages, factual assertions, allegations, assumptions, contradictions, and lawyer corrections. Every assertion should retain its origin and status. | Answer questions across authorized matter documents, reconstruct timelines, locate exact evidence, identify conflicting accounts, and connect private facts to public legal issues without publishing private information. |
| **9. Source, provenance, review, and coverage graph** | Source artifacts and representations, acquisition records, document identities, extraction versions, exact passage locations, assertion provenance, permitted uses, review decisions, corpus releases, and coverage by topic, institution, and time period. | Make results auditable; exclude unsuitable sources; distinguish official text from commentary or summaries; and explain whether an empty result reflects absence, incomplete coverage, or failed retrieval. |
| **10. Firm knowledge and dependency-impact graph** | Approved playbooks, research notes, drafting patterns, internal interpretations, and dependencies between evidence, authorities, arguments, research outputs, and draft versions. | Reuse reviewed firm knowledge within permissions and flag affected work when evidence, a legal provision, an authority interpretation, or a corpus release changes. |

For every module, identify its shared identifiers and connecting relationships. Explain how a lawyer’s question moves through a path such as:

**Question → concepts → candidate issues → relevant facts → provision versions → comparable decisions → exact supporting and adverse passages.**

Explain where graph traversal helps, where full-text or vector retrieval helps, and where human interpretation remains necessary.

## Semantic and operational requirements

The proposals must satisfy these semantic requirements:

- **Time:** distinguish legal validity from when the system recorded information. Keep publication, decision, legal effect, and finality dates separate. Unknown dates must remain unknown.
- **Identity:** distinguish an instrument from its versions, a proceeding from its decisions, an institution from an institutional category, and a person from their role in a particular relationship.
- **Evidence:** consequential relationships must carry exact source passages, locators, source versions, extraction provenance, and review status.
- **Assertion status:** preserve the difference between an allegation, documentary statement, judicial finding, lawyer hypothesis, and legal conclusion. An accurate quotation does not automatically establish the truth of its contents.
- **Legal authority:** research Turkish distinctions between court types, decision types, and legal effects. Avoid importing a US precedent model without justification.
- **Uncertainty:** extraction confidence, source authenticity, legal review, and applicability to a matter are separate assessments.
- **Privacy:** private graphs may reference public authority identifiers. Public graphs must not expose private clients, matters, or inverse links to them. Propose authorization-aware retrieval.
- **Language:** support Turkish morphology, diacritics, abbreviations, citation variants, and historically changing terminology. Preserve original evidence text separately from normalized search representations.
- **Inference:** specify permitted and prohibited inference. Taxonomy membership, citation counts, textual similarity, or a graph path must not automatically establish liability, applicability, or binding force.

## Reusable standards, ontologies, and datasets

Investigate reusable standards and assets rather than assuming everything should be created from scratch. Relevant starting points include:

- [SKOS](https://www.w3.org/TR/skos-reference/) for concept organization, [PROV-O](https://www.w3.org/TR/prov-o/) for provenance, and [SHACL](https://www.w3.org/TR/shacl/) for structural validation.
- [Akoma Ntoso / LegalDocML](https://docs.oasis-open.org/legaldocml/akn-core/v1.0/os/part1-vocabulary/akn-core-v1.0-os-part1-vocabulary.html) for legal-document structure and [LegalRuleML](https://docs.oasis-open.org/legalruleml/legalruleml-core-spec/v1.0/os/legalruleml-core-spec-v1.0-os.html) for legal-rule representation.
- [LKIF-Core](https://github.com/RinkeHoekstra/lkif-core), [EuroVoc](https://op.europa.eu/en/web/eu-vocabularies), [ELI](https://op.europa.eu/en/web/eu-vocabularies/eli), and [ECLI](https://e-justice.europa.eu/topics/legislation-and-case-law/european-case-law-identifier-ecli-search-engine_en?language=en) as candidates for reuse, alignment, or identification patterns.

Determine their suitability for Turkish law, maintenance status, licensing, and integration effort. Distinguish ontologies, document standards, identifier schemes, thesauri, and populated datasets. Do not assume that an international asset supplies Turkish legal content.

Investigate Turkish official legislation, parliamentary, gazette, court, and institutional sources, alongside relevant academic or licensed collections. For each proposed source, verify available content, historical depth, identifiers, access mechanisms, update behavior, and permitted uses. Public accessibility alone must not be treated as permission for bulk acquisition or redistribution.

## Required deliverables

Your report should deliver:

1. **Three coherent architecture options:** a lean initial implementation, a balanced production architecture, and a comprehensive long-term architecture. Recommend one and explain its tradeoffs.
2. **A module specification:** principal entities, relationships, temporal fields, provenance requirements, privacy boundary, and the search problem each module addresses.
3. **A reusable-asset inventory:** direct links, owner, version or research date, language/jurisdiction coverage, license evidence, maintenance status, and whether to adopt, adapt, align, or reject each asset.
4. **A corpus-population plan:** source priorities, identity resolution, provision segmentation, citation resolution, extraction and review workflows, historical backfill, and update handling.
5. **A concrete retrieval design:** query interpretation, concept expansion, lexical/vector candidate retrieval, bounded graph expansion, temporal and permission filtering, reranking, adverse-authority retrieval, and evidence assembly.
6. **An illustrative implementation sample:** a small, explicitly synthetic RDF/Turtle example connecting a private issue to a public provision version, decision reasoning, and exact evidence; accompanying validation constraints and example bounded queries.
7. **A prioritized delivery plan:** the smallest useful validated slice, subsequent expansion, required legal-editor effort, maintenance responsibilities, costs, and unresolved dependencies.
8. **An evaluation plan:** compare ordinary hybrid search with graph-assisted search on the same corpus and queries. Measure retrieval relevance, historical-version correctness, citation resolution, factual comparability, adverse-authority recall, evidence accuracy, unauthorized-data exposure, latency, and review effort. Include ablations to identify which modules actually help.

## Initial competency tests

Use these questions as initial competency tests:

- Which provision version was relevant on the date of the disputed event?
- Which later amendments or transitional provisions require investigation?
- Which decisions discuss this issue under comparable facts, and what differences matter?
- Which authorities challenge the proposed argument?
- Is a quoted passage a party submission, judicial finding, or court reasoning?
- Which required fact lacks supporting evidence?
- Which documents contradict a factual assertion?
- Which research outputs and drafts depend on a changed source?
- Does a missing result mean no authority exists, or that coverage is incomplete?
- Can the system explain every substantive relationship through its source and review history?

## Research quality

Provide source-backed findings, explicit assumptions, and unresolved questions. Separate verified facts from proposed design choices. **The preferred proposal should show how a realistically obtainable, maintained, and reviewed graph improves search—not merely how to draw a comprehensive legal ontology.**
