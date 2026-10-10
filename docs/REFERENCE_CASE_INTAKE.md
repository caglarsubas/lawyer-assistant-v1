# Source-linked reference cases and family splits

This R01/R05A packet supplies **offline reference-case intake and optional physical
binding of later evaluation rows**. It links declared scoring hashes to inspectable
original source bytes, exact passages, pre-run references and post-run adjudication
receipts. It neither acquires a source nor runs a model. Runtime routes never
consume its reports as authorization.

Actual source rights, privacy assessment, reviewer expertise/independence, historical
applicability, sample representativeness and measured benefit remain separate human
gates. `reference_case_binding_pass` means supplied declarations and physical bytes
agree; it cannot authenticate those declarations. An observation record may be an
unverified statement. Matching extracted passages does not establish OCR fidelity
to an original PDF; use [extraction calibration](R01_QUALIFICATION.md) separately.

## Prepare the confidential inventory

Real working copies and reports belong outside Git in an access-controlled offline
evaluation area. This contract accepts declared public scenarios and synthetic
fixtures. Private client facts/documents remain in authorized matter storage; a
public label alone does not prove absence of PII. Hashes, family membership and
counts can themselves be confidential operational metadata.

The intake directory contains exactly `casebook.json`, `protocol.json` and
`snapshot.json`. The casebook pins their protocol/snapshot/rubric, source catalog,
registration time, source inventory, case roster, splits and reference records.
Use the existing local or single-provider extended protocol with excluded
development families and explicit unknown sample minima. Snapshot identifiers cover
ontology, graphs, corpus, model, policy, index and workflow. A separate catalog
directory contains only the pinned `source-catalog.json`.

A separate artifact directory contains exactly the declared `<sha256>.bin` files:

- Source originals, typed passage exports and separate rights/history records.
- Exact scenario/task inputs, typed reference answers and family-review records.
- Reviewer-independence and all six semantic observation records.
- With evaluation rows, separate post-run adjudication receipts.

Source identity, representation and proceeding identity remain distinct. Shared
norms do not define case families. Declared decision identity, decision representation
bytes, proceeding identity, identical task inputs and declared family identity do
connect cases. Their transitive components expose development/held-out overlap,
inconsistent families and mixed origins. No fuzzy matching, anonymized-party
correlation or near-duplicate discovery occurs. Related cases with different IDs
still require human grouping; unknown family records remain gaps. Development
reservations must match the frozen protocol.

## Author the reference before measuring

References bind the exact task/snapshot/rubric/case and preparation time. Citations
name source/ordinal and hash exact UTF-8 passage text. Support, adverse, context and
unresolved roles stay separate. Explicitly author the gold set: every gold item
needs a resolved passage and every declared adverse item belongs to that set.
Two declared reviewers and an independence record are inventory checks, not expert
certification. `recorded` never implies a verified semantic verdict.

Retain the relevant legal date, declared historical period, complete/partial reference
coverage, adverse-search completeness and applicability, historical-version,
conditions/exceptions, authority-treatment, adverse-authority and uncertainty
observations. Unassessed/unresolved dimensions cannot become recorded without
evidence. Dates check declared chronology; registration time is not authenticated
and does not prove the inventory existed before a run. Protect and timestamp actual
protocols through the accountable evaluation process.

```sh
backend/.venv/bin/python scripts/qualify_reference_cases.py --schemas
backend/.venv/bin/python scripts/qualify_reference_cases.py /evaluation/intake \
  --artifacts-dir /evaluation/artifacts --source-catalog-dir /evaluation/catalog
```

Exit **0** means declared intake checks pass; **1** means valid intake has review/
family gaps; **2** means invalid, replaced, oversized or unstable inputs, without
a partial report. Reports contain counts, gaps and input hashes; they omit prose,
locators, reviewer/case IDs, family hashes and private paths. Real/synthetic and
practice/period inventories remain separate. Quality/productivity metrics remain
unknown; no numerical nationwide-corpus completeness claim is made.

Limits: 1,000 cases/rows, 300 sources, 64 citations/reference, 32 sources/case,
1,000 passages/source, 2 MiB per structured component, 20 MiB per original,
128 MiB aggregate artifacts and 16,000 distinct digest-named files. Existing
dossier/calibration readers retain their default 2,000-entry cap; only explicit
case-artifact capture opts into the larger bound. Exact inventories, no-follow
descriptor traversal, regular single-link files, JSON work/duplicate/nonfinite
checks and final recaptures fail closed. This detects ordinary changes, not a
privileged host, and does not provide durable immutable storage.

## Bind later scores

```sh
backend/.venv/bin/python scripts/evaluate_release.py /evaluation/tasks.jsonl \
  --protocol /evaluation/intake/protocol.json \
  --snapshot /evaluation/intake/snapshot.json \
  --casebook-dir /evaluation/intake --case-artifacts-dir /evaluation/artifacts \
  --source-catalog-dir /evaluation/catalog
```

Every row matches a held-out case's input, family, practice, period, origin, protocol,
snapshot, rubric and provider scope. Gold/adverse sets match the source-linked
reference. A `legal-reference-adjudication-v1` artifact binds the raw casebook
digest, case ID, reference digest and canonical validated row excluding its own
`adjudication_evidence_sha256`. This avoids a hash cycle while detecting changed
scores, checks, pairs, annotators or timings. It is a receipt, not legal reasoning;
retain actual adjudication records independently.

Missing rows fail binding; extra/development rows, duplicate IDs, changed gold sets
or mismatched receipts are invalid. Synthetic rows cannot pass this gate. With
these options the scorer adds `gates.reference_case_binding`; a failed binding
prevents quantitative success. Without them, numeric compatibility remains and
`reference_cases.status: not_supplied` makes evidence limitations explicit. Neither
mode grants approval or bypasses sample/substantive gates. Workbench trials/cohorts
never automatically become scorer rows, references or qualified experiments.

## Exercise invented data

```sh
backend/.venv/bin/python scripts/build_reference_case_fixture.py /tmp/new-intake
backend/.venv/bin/python scripts/qualify_reference_cases.py /tmp/new-intake/intake \
  --artifacts-dir /tmp/new-intake/artifacts --source-catalog-dir /tmp/new-intake/catalog
```

The generator accepts only a new destination under an existing non-symlink parent,
creates owner-only files/directories and never overwrites. Two invented cases share
a norm with separate development/held-out families. It does not parse law, read
`.env`, call a provider or import application settings. `--with-evaluation` creates
a separate new example with one invented scored row and receipt. Inspect that
example through the scorer, which supplies the receipt inventory; it should exit
**1** because synthetic evidence and unknown minima cannot qualify.

Next: lawful representative source sampling, independently authored/adjudicated
references, measured review throughput, witnessed protocol registration and
representative paired trials. Qualified publication, model benefit, historical
coverage, Standard/Deep budgets, deployment and pilot acceptance remain open.
