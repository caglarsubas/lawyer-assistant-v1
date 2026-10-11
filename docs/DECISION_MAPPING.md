# Accountable jurisprudence mapping

Curators open **Karar eşleştirmelerini aç** from a source review. At
`#/sources/{source-package-sha256}/decisions`, select a retained passage, inspect
its exact text and available original HTML/PDF representation, then inspect its
literal number, date and citation occurrences. The source must already be admitted
through the controlled staging workflow. This screen performs no acquisition,
inference, party matching or public graph mutation.

Each occurrence starts with unknown identity, event role and treatment. A proposed
mapping retains the exact candidate, passage identifier, extractor version, Unicode
coordinates and source hashes. The proposal does not resolve a document identity.
The assigned source reviewer can append an acceptance, request for changes or
rejection with rationale and evidence references. Prior interpretations remain in
an encrypted, firm-confidential append-only ledger; the latest 50 events and every
current mapping are displayed. No human review of real legal material was performed
by the implementation or its synthetic tests.

Acceptance requires current accepted rights, source identity, extraction and legal
reviews, local processing/display permissions, and extraction review of **every
supporting passage**. Both mapping and source-review revisions must match. Support
is an exact retained Unicode span that includes the selected occurrence; all
non-whitespace content must have admitted locator coverage. This establishes source
binding, not the truth of the reviewer's legal interpretation.

The typed interpretation separates:

- The occurrence's role: this decision, cited authority, editorial information or unknown.
- Proceeding, decision and institution references. A self-identity interpretation
  needs all three; a numbered norm cannot identify the document's own decision.
- Citation target and its historical version, with unknown versions left null.
- Decision versus publication date. A known date must equal that exact occurrence's
  valid calendar value and have the matching event role. Source metadata is not rewritten.
- Citation, quotation, application and distinction. A specific treatment requires
  an explicit cited-authority role and target; it is the accountable reviewer's assertion.

References are opaque human-supplied references awaiting independent identity
resolution. They neither create canonical graph entities nor prove legal effect.
Finality, binding force, competence, majority/dissent, decision segmentation and
adverse-authority classification remain outside this first mapping contract.
Unknown values remain unknown. Source-review changes stale every prior acceptance,
and explicit re-review is required. Rejection preserves prior accepted reasoning.

## Local API

All routes require an authenticated current admin/curator with `source.curate`.
Mutations also require CSRF, origin checks and the current source-review owner.

- `GET /api/v1/public-sources/{id}/decision-mappings`: virtual empty state or
  verified firm-local projection and bounded history, without writes.
- `POST /api/v1/public-sources/{id}/decision-mappings`: exact `passage_id`,
  `candidate_id`, rationale and both expected revisions.
- `POST /api/v1/public-sources/{id}/decision-mappings/{mapping_id}/review`:
  typed interpretation, decision, rationale, evidence references and both revisions.

Reads and writes verify encrypted source/firm/head/event bindings and contiguous
revision history; projections must match latest events. Limits are 200 mappings
and 1,000 events per source and firm. PostgreSQL source row locks and revision
compare-and-swap protect competing writes. Reauthorization and source-review checks
run again before commit. Browser conflicts refresh current state without replaying
a mutation. Access loss clears the confidential view; source/user changes unmount
and cancel previous work. Browser occurrence receipts verify package/passage hashes,
exact Unicode slices and stable candidate identities before display.

`handoff_ready` means all listed mappings have current accepted reviews and the
source reviews are ready. It is not legal qualification, corpus completeness,
permission to export, independent release review or graph-publication eligibility.
The source stays staged and `publication_eligible` is always false. No deployment or
serving-release change accompanies this packet.

## Complete confidential review dossier

`POST /api/v1/public-sources/{id}/decision-mappings/dossier` takes both expected
revisions and requires current curator authorization, CSRF and accepted rights with
explicit `local_processing`, `internal_display` and `export` scopes. It is a read
operation: it does not append a review, approve a source or publish a graph. Authorized
curators may export a draft while other reviews are pending; draft status remains
explicit. Export does not require source ownership, which still gates review writes.

The exact JSON contains firm/exporter identity, acquisition hashes, current source
assessments, all source and mapping events (including events beyond the UI's latest
50), and exact supporting passages with hashes and locators. Both histories are
verified completely. Source row and identity locks, revision pins, a fresh artifact
check and final reauthorization withhold stale or corrupted output. The 4 MiB limit
withholds the complete dossier rather than returning partial history. The response
contains SHA256 over its exact bytes; this integrity digest is not a signature.

Handoff checks compare only literal reviewer-declared decision references. Conflicting
proceeding/institution references, same-kind numbers or same-role dates for one
declared decision retain alternative values and contributing mapping IDs. They do not
merge equivalent identities, infer legal effects or find every legal inconsistency.
Independent-review readiness additionally requires current accepted source/mapping
reviews, a reviewed self-identity and no unresolved mapping or literal identity
conflict. Canonical identity resolution, verified legal effect and publication
eligibility remain false even when this engineering handoff check passes.

The browser verifies envelope, firm, exporter, source/version/artifact bindings,
revisions, complete ordered histories and supporting passage hashes before creating
an inert JSON download. It revokes temporary URLs and cancels old operations on
access loss or navigation. Session refresh compares user, firm, role and permissions;
the portfolio and private source workspaces reset when any access scope changes.
Already downloaded files require the firm's local document controls.

Next: independently reviewed canonical decision/proceeding/institution resolution
and a staged Graph B handoff contract, retaining unresolved references and explicit
legal/privacy/fidelity release gates.
