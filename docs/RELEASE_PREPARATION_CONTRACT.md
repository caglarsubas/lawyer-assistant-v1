# Revision-bound graph review preparation

This packet creates local, firm-confidential review directories, never serving
releases. No signing, graph mutation, installation, activation or credential change.
No original dossiers, rights proof, identity evidence, reviewer text or firm IDs
are admitted to public candidate RDF. Entire directories stay private because
even authority selection is confidential metadata.

## Live snapshot boundary

`app.release_snapshot.locked_snapshot(store, source_store, *, operator_id,
source_id, expected_source_review_revision, expected_mapping_revision)` is a
context manager yielding `{package, state, source_review, binding}`. `package`
is the verified immutable source. `state` is the existing MappingState. The full
source review projection remains private. `binding` contains source digest fields,
firm/operator/source and head IDs, both revisions, and a deterministic SHA256
of exact source-review and mapping projections. The manager keeps locks until
the caller finishes atomic output; final checks detect changed package bytes.
It never creates database tables, audit rows or review records.

Lock existing active admin/curator operator, source-review head, then mapping
head. Operator must own the source review in their firm. Validate both expected
revisions, full existing ledger integrity, four accepted source assessments,
accepted current mappings and coverage. Require rights `storage`,
`local_processing`, `internal_display`, `export`, `indexing`, `local_inference`:
this review package anticipates corpus use and cannot broaden scope itself.
All accepted mappings are included, bounded by the existing200 limit. Reject
empty/unready state. No user, firm or owner information in public RDF.

`readonly_store(settings)` opens an existing PostgreSQL store without create_all,
bootstrap, audit or writes. SQLite is allowed only in explicit demo/test mode.
It supplies `session()` and `decode(row)` compatible with ledger validators.
Use the trusted offline operator-ID contract already used by manage_users.py;
an ID is not remote authentication. No web endpoint is introduced in this packet.

## Explicit identity and evidence inputs

Compiler function `app.release_preparation.compile_review(snapshot, registry,
resolutions, evidence:dict[str,bytes], ontology_root:Path)` returns a deterministic
`dict[str,bytes]` of review files plus a safe summary. It does not read arbitrary
paths, use a model, fetch URLs or mutate any store. The CLI bounds/validates files.

Registry schema `legal-identity-registry-v1`:

```
{schema_version, entities:[{id,kind,parent_id,evidence_sha256:[...]}]}
```

Kinds: `instrument`, `provision`, `provision_version`. IDs must use exact namespaces
`urn:tr-law:instrument:`, `urn:tr-law:provision:` and
`urn:tr-law:provision-version:` with a lowercase ASCII slug `[a-z0-9][a-z0-9.-]{0,119}`.
Instrument parent is null; provision parent is an existing instrument; version
parent is an existing provision. Require unique IDs, matching types,1–10 physical
evidence hashes/entity and maximum600 entities. Registry references are explicit
operator-reviewed proposals, not certified national identity facts. No labels,
dates, private arbitrary fields, external resolution or automatic ID minting.

Resolution schema `provision-identity-resolutions-v1`:

```
{schema_version, items:[{mapping_id,instrument_id,provision_id,provision_version_id}]}
```

At most200 unique entries. Resolve only current mapping IDs and require each
parent chain to match. Omitted mapping resolutions remain unresolved blockers.
Do not match human reference strings to IDs implicitly. Prevent distinct mapping
spans/identities from being collapsed onto one provision-version ID.

Evidence is supplied as a bounded digest-keyed local directory: at most128 files,
8MiB each and32MiB total. Unused evidence is rejected. Every registry
evidence hash and every latest rights-assessment evidence hash must match actual
bytes; reject missing or changed material. Rights evidence remains private.
The compiler requires the snapshot rights scope and revalidates source spans.

## Output and validation

Private files include `binding.json`, exact canonical `registry.json`,
`resolutions.json`, `review-report.json`, and required `private-evidence/<sha>.bin`.
Public-candidate files use `candidate/`: exact source bytes/text, converted locator
map, and the deterministic structure/jurisprudence RDF when all blocking inputs
are resolved. Split evidence at original source locators, preserving exact
Unicode offsets/text and whitespace gaps. No invented enclosing locator.

Unknown legal starts, unknown ends and source acquisition remain unknown in the
report and block release-compatible RDF generation. An accepted resolution may
instead supply the optional object below; omission retains the legacy meaning
of null end dates, and an explicit null object is rejected:

```json
{
  "valid_from": "2025-01-01",
  "valid_until": null,
  "open_ended_validity": {
    "checked_through": "2025-12-31",
    "evidence_start": 0,
    "evidence_end": 58
  }
}
```

These are illustrative fields inside a complete resolution, not real legal data.
The supporting span must be nonblank, at most20,000 Unicode characters, fully
covered by verified locators in the same source, and independently checked even
when outside the provision's body. `checked_through` is inclusive and must be at
or after `valid_from` and at or before the immutable mapping review's UTC day.
Acceptance, ledger replay and compilation enforce the same rule. Open status
cannot coexist with a known legal end. Legacy dictionaries omit the new field;
their existing null date fields and sealed history remain unchanged.

Candidate assertions and their provision version both retain
`la:validityEndStatus "open_ended"`, `la:validityCheckedThrough` and separate
`la:validityEvidence` links. Supporting passages receive the same public rights,
exact quote, source representation and locator checks as other evidence. Private
review references are never substituted for public passages. The extra links
count toward compilation budgets and the complete state participates in identity
fingerprints. Public review timestamps cannot predate the checked horizon.

Finite applicability is `[valid_from, valid_until)`; open applicability includes
the checked-through day and excludes later dates. Historical inspection still
requires a known, reviewed, evidenced interval and never implies applicability.
For overlap detection an open interval remains unbounded, including at the
maximum calendar date; its check horizon is not treated as a legal termination.
Conflicting/reversed intervals are rejected;
unknown role and amendment/quoted-text mappings also block authority-version
emission; operative/transitional roles stay explicit. No legal-effect or amendment
relation is inferred. Independent review is still necessary for all generated
identity/version assertions. Registry IDs and source text are untrusted data.

When RDF is generated it carries `la:reviewPreparationOnly true` and claim status
`unreviewed`. `ontology.releases.check_data` must reject that marker before any
publication, irrespective of signatures. Normal SHACL and exact grounding checks
can be run internally on an in-memory copy without the marker only for structural
QA; this does not grant publication eligibility. Deterministic sorted N-Triples
are valid Turtle inputs. Unknown fields and duplicate IDs are rejected.
Reject more than 25,000 evidence links before allocating RDF graphs; count only
non-whitespace source-locator intersections. Count body passages against both
proposed relationships per mapping, and each temporal-proof passage against both
relationships plus the provision version. Capacity failures never truncate
evidence or mappings.

Report fields include schema version, input digests, mapping/resolved counts,
blockers, `rdf_generated`, `signed:false`, `publication_eligible:false`,
`confidentiality:firm_confidential`. No current-legal-authority claim.

CLI `scripts/prepare_legal_review.py prepare` accepts `--operator-id`,
`--source-id`, `--expected-source-review-revision`, `--expected-mapping-revision`,
`--registry`, `--resolutions`, `--evidence-dir`, `--output`.
`validate <directory> --operator-id` rebuilds all files from current locked
ledgers, supplied identities/evidence and current ontology, then compares the
entire exact package. It rejects changed reviews, ownership, rights, source,
identity plan, missing/extra files, traversal, symlinks and byte tampering.
It emits only safe counts/status/digests. Validation is true only at that instant.

Never overwrite an existing output. Build in a sibling mode0700 staging directory,
write mode0600 regular files, then atomically rename without replacing. Include a
canonical inventory manifest and digest; these detect corruption, not signatures.
Bind ontology bytes even when unresolved inputs prevent RDF generation.
Seal the canonical manifest with `store.preparation_mac(bytes)`, an HMAC using a
domain-separated key derived from the existing encryption key. This detects an
edited identity plan even if someone recomputes the unsigned file inventory. It
is deployment-local integrity protection, not a reviewer signature or authority
to publish. Key rotation requires re-preparation. No key is written to a packet.
No timestamp is inserted into deterministic payloads. Freshness comes from the
live check, not a self-reported package timestamp. Validation cannot rely solely
on a saved dossier or historical ciphertext. No automatic signing path exists.
