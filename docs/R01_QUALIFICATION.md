# R01 qualification, evidence verification and extraction calibration

R01 provides **offline planning contracts, evidence-file verification and extraction
comparison**. These tools turn the roadmap's source, asset, analysis, scenario and
research requirements into inspectable records and measure extraction discrepancies.
They do not populate the law corpus, perform legal analysis, sanitize text, approve
rights or enable an external provider.

## Inspect the dossier

From the repository root, using the existing backend environment:

```sh
backend/.venv/bin/python scripts/qualify_roadmap.py check qualification
backend/.venv/bin/python scripts/qualify_roadmap.py schemas
```

`check` reads five fixed JSON files, validates structure and cross-record references,
and prints a deterministic aggregate report with exact input hashes. `schemas` prints
the JSON Schema bundle. Neither command writes files, loads `.env`, imports application
settings, accesses the database or makes network requests. Python cross-record checks
are required in addition to JSON Schema validation.

Exit **0** means structurally valid. Exit **2** means invalid input. Neither exit status
means qualified, approved or ready for dispatch. The report always states
`runtime_authorization: none`, `production_qualified: false` and
`r01_exit_gate: independent_review_and_evidence_required`. No runtime service consumes
these files as authorization. Existing authenticated source review and independently
signed publication remain the only implemented paths to their respective actions.

The reader bounds each component to 2 MiB, rejects duplicate JSON fields/nonfinite
numbers, excessive nesting and excessive JSON traversal work, and rejects missing,
symbolic, hard-linked, special or oversized files. The directory must contain exactly
the five fixed components. Descriptor-based traversal rejects symlinked path components;
repeated captures and file/path identity checks detect changes. Diagnostics omit submitted
values and private paths. Unexpected entries cause rejection and are not opened.
Input hashes identify captured bytes;
they are not trusted signatures or proof that the input statements are true.

## Included contracts

| File | Content | Present evidence boundary |
|---|---|---|
| [Source catalog](../qualification/source-catalog.json) | 27 national source families; owner roles, candidate references, identity/representation/access requirements, coverage gaps and ten use dimensions | Every permission and review observation is pending; URLs are research references, never an acquisition allowlist |
| [Asset catalog](../qualification/asset-catalog.json) | 21 parser/OCR/NLP/model/vocabulary/evaluation candidates and source-family references | Versions, licences and suitability need qualification; missing values remain unknown, even where a dependency is already installed |
| [Analysis fixture](../qualification/analysis-fixture.json) | Synthetic issue, premises, evidence, rule/version, conditions, application, alternatives, defects, correction limits and provisional conclusion | Checks declared structure, reference roles and temporal consistency; unresolved critical defects withhold the affected conclusion. No legal Reviewed state is available |
| [Scenario fixture](../qualification/scenario-fixture.json) | Synthetic outbound candidate plus a separate private transformation map | Always preparation-only and non-dispatchable; privacy is not assessed. Role, negation, material-date, threshold and chronology mutations fail structural checks |
| [Research dossier](../qualification/research-dossier.json) | Three provider plans, twelve gates per provider, separate development/release evaluation, paired comparisons and calibration records | All providers disabled/unqualified; no account or key supplied; no evaluation results or real measurements recorded |

The source/asset catalog's ten dimensions include the existing six corpus uses plus
embedding, offline distribution, external research and training. The latter are planning
dimensions, not extensions of runtime permission. Training remains outside v1. A later
self-reported “permitted” observation still cannot authorize acquisition or publication.

The argument schema checks declared relationships, not whether a passage supports a
claim or a legal rule is correct. Likewise, a structurally faithful scenario can still
contain PII or identifying combinations. Real detectors, legal-fidelity assessment,
exact approval and the BYOK broker belong to later qualified packets.

## Record evidence without manufacturing qualification

Use an access-controlled working copy outside the repository for actual owner/reviewer
records. Keep committed analysis/scenario examples synthetic. The bundle check rejects
matter-private fixtures: private work products belong in authorized matter storage.
Treat working dossiers and reports as confidential operational material; they can reveal
source strategy, review gaps and stable evidence fingerprints.

The research dossier supports calibration measurements linked to declared evidence IDs
and SHA-256 digests, practice, unit, date and real/synthetic origin. Record measured
elapsed/reviewer time and assessed-item/disagreement counts; do not replace unknowns
with zero. Duplicate sample references and incoherent denominators are rejected.
Real and synthetic aggregates stay separate. Evidence authenticity and sample
representativeness still require independent review; `check` does not open the
referenced evidence. Use `evidence` below for physical file verification. Meeting a
count target does not satisfy R01 or establish coverage.

The seed retains 100 pages, 10 amendment chains and 30 decisions as sampling targets;
360 development tasks remain separate from at least 1,000 held-out tasks and 3,000
claims. Provider slice minima and paired-experiment sizes remain explicitly pending.
No observed timings means no measured throughput or replacement delivery estimate.
The 30–36-week/eight-FTE envelope remains provisional.

## Verify physical research evidence

Prepare a separate evidence directory containing exactly one `<sha256>.bin` file
for each digest in the research dossier's `evidence_records`. File contents must
have that exact SHA-256. Keep originals, manifests and reviewer records under
appropriate access controls; the verifier does not fetch a source or infer rights.

```sh
backend/.venv/bin/python scripts/qualify_roadmap.py evidence /absolute/dossier-copy \
  --evidence-dir /absolute/research-evidence
```

Like `check`, this command requires the dossier directory to contain **exactly
the five component files**. The evidence directory must also have an exact
inventory: extra files, missing files, symlinked path components, symbolic/hard
links, special files and changes detected across captures fail closed. Reads are
bounded to 20 MiB per evidence file, 128 MiB total and 2,000 entries; dossier
components retain their 2 MiB limits. This is a stable capture check, not a durable
filesystem snapshot: subsequent writes invalidate any assumption about current bytes.

Output contains hashes and aggregate counts, without evidence IDs, source text,
reviewer identities or paths. `hashes_verified` means bytes match the supplied
declarations. An empty set is `no_records`. Neither status proves origin,
authenticity, legal review, sample representativeness or classification. Differently
serialized evidence can still describe the same source: underlying source-identity
deduplication is **not evaluated**, and sample independence is **not established**.
The dossier's `evidence_authenticated` remains false. No runtime consumes this
report as permission to ingest, publish or transmit data.

## Compare extraction with an independent transcription

`calibrate` reads a directory containing exactly these four files:

| File | Contract |
|---|---|
| `sample.json` | Versioned metadata; public-source or synthetic classification, practice, format, declared extractor/version, nullable measured elapsed time and hashes of the other three files; maximum 64 KiB |
| `raw.bin` | Exact original bytes, only hashed by this command; maximum 20 MiB |
| `extraction.json` | Export of the existing isolated extractor's `passages`, `warnings`, `page_count` and `passage_count`; maximum 9 MiB |
| `reference.json` | Independently authored passages with ordinal, locator, text and optional critical spans, bound to `raw_sha256`; declared complete/partial coverage; maximum 9 MiB |

```sh
backend/.venv/bin/python scripts/qualify_roadmap.py calibration-schemas
backend/.venv/bin/python scripts/qualify_roadmap.py calibrate /absolute/calibration-sample
```

Author the reference from the original source independently of extracted output;
copying output into the reference would defeat the comparison. The reference's
`unreviewed` or `operator_supplied` status never claims authenticated legal review.
Real samples must be lawful public-source samples under this contract. Matter-private
documents stay in authorized matter storage; a declared label is not PII detection.
Extract real originals through the existing authorized scanner/parser intake path,
then export its response for comparison. This CLI does not parse originals or bypass
intake controls. It uses no network, application settings, credentials or database.

Passages compare at their zero-based ordinals with exact locator and Unicode text.
Critical spans use zero-based Unicode codepoint offsets with an exclusive end,
covering date, amount, identifier, negation or exception. No fuzzy alignment,
normalization or LLM repair can hide an OCR difference. Reports include missing,
extra and uncovered passages, exact-match rates, critical-category matches and
warning counts; they omit text, locators and declared extractor identifiers.
The CLI also fingerprints the exact sample metadata bytes in `sample_sha256`,
alongside the original/extraction/reference hashes, for reproducibility.
Counts and hashes can still reveal operational metadata and need access control.

A partial reference scores only annotated passages; a passing subset does not
establish whole-document fidelity. Empty references cannot pass; categories with
no annotated spans have a null rate. Complete coverage is an operator declaration,
not proof that every page, footnote or table was transcribed. Warnings are counted,
not automatically adjudicated. The comparator bounds total text, passages, spans,
annotated comparison work and JSON nesting. Both artifacts and reference-to-original
binding must pass their hashes; malformed data is rejected before any report.

Exit **0** means the declared comparison passed; **1** means valid inputs contain
comparison failures; **2** means invalid or unstable inputs. These statuses never
grant legal review or corpus admission. Elapsed time in an operator-supplied sample
is reported, not remeasured or authenticated. Reference fidelity, metadata, sample
independence, privacy and legal meaning remain unestablished.

### Exercise the actual parser using invented data

The generator creates its own fixed Turkish TXT example with independently authored
expected passages, dates, an amount, identifier and negation. It calls the existing
bounded local parser and fails if its response differs from those expectations.
It accepts only a **new** destination under an existing non-symlink parent, writes
private permissions, and does not overwrite a previous run.

```sh
backend/.venv/bin/python scripts/build_calibration_fixture.py /absolute/new-synthetic-sample
backend/.venv/bin/python scripts/qualify_roadmap.py calibrate /absolute/new-synthetic-sample
```

The generated sample records parser-call wall time including startup and hashes the
local extraction implementation. This is synthetic engineering evidence, not
real-corpus throughput or reviewer time. It never accepts client input, updates the
dossier, approves a source or publishes a graph. CI runs this same generated sample
through comparison. Use the schemas to prepare separately reviewed real samples;
no real examples or inferred approvals are committed by this packet.

## Delivery boundary and next work

R01's engineering contracts, inspection, physical verification and comparison tools
are implemented. Its exit remains open
for accountable source/access/rights and semantic review, lawful representative samples,
actual extraction/reviewer measurements, legal/privacy fixture adjudication, provider
processing decisions and a capacity re-estimate. Owners are roles until actual people
are assigned; seeded records never impersonate reviewers.

These contracts prepare R02 multi-source design and R05A/R05B fixtures. They do not
waive the roadmap's dependencies or qualify a national ontology or legal work product.
See [delivery order](ROADMAP.md), [data strategy](DATA_KNOWLEDGE_STRATEGY.md) and
[analysis/BYOK contract](LEGAL_ANALYSIS_AND_DEEP_RESEARCH.md).

The backend image includes the five named seed files and the scripts, with no real
qualification evidence. A disposable
network-disabled container can inspect them without any deployment volumes or secrets:

```sh
docker run --rm --network none --read-only --cap-drop ALL \
  --security-opt no-new-privileges --tmpfs /tmp:size=16m \
  lawyer-assistant-api:r01-calibration \
  python /app/scripts/qualify_roadmap.py check /app/qualification
```

This uses the separately built validation image tag, not a running application service.
CI also checks the seed contracts and synthetic parser comparison; green checks are
not release qualification. No API/UI or application deployment change is required
for these offline engineering tools.
