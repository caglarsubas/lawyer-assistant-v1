# Türkiye legal graphs — engineering baseline

Version 0.1.0 contains **135 classes, 109 relations and 51 SKOS domain concepts**.
Every module and domain is **UNREVIEWED**. This is a nationwide schema proposal, not
a reviewed representation of Turkish law or a populated institutional registry.
No historical legal corpus is bundled. The 5 assertion fixtures are conspicuously
synthetic, live under `fixtures/`, and are never loaded by the application.
Turkish is the primary display language for every class, relation and domain;
English labels and stable predicate codes are retained. Terminology is unreviewed.

Two logical public graph families share identifiers and evidence structures:

- `structure`: norms/provision versions, institutional genealogy, qualified
  competences, concepts, conditional legal positions and procedures.
- `jurisprudence`: proceedings, decisions, findings/arguments/holdings, dispositions,
  citation occurrences and qualified authority treatments.

Historical acquisition scope starts in **1920**, with earlier predecessors included
only when continuity or applicable law requires them. Contracts, commercial law and
employment are the first deeply validated practices. Broader schema coverage does
not establish corpus completeness. National review and historical acquisition are
separate gates.

`foundation`, `norms`, `institutions`, `legal_positions`, `procedures`,
`jurisprudence`, `evidence` and `private_overlay` are separate Turtle modules.
`build_catalog.py` is the editable declaration source for `catalog.json`, domain
SKOS and class/relation modules. `shapes.ttl` is independently maintained. Standard
RDF/Turtle and SHACL allow Jena/Fuseki, rdflib and pySHACL use. No property-chain rule
turns a citation into application, binding authority or support.

Run from the repository root:

```sh
backend/.venv/bin/python ontology/build_catalog.py
backend/.venv/bin/python scripts/validate_ontology.py
cd backend
.venv/bin/python -m pytest tests/test_graph.py -q
```

## Assertion contract and privacy

The [offline preparation adapter](../docs/RELEASE_PREPARATION.md) translates exact
accepted mappings and explicit identity proposals into confidential independent
review packets. It splits evidence at original locator boundaries and preserves
unknown dates as blockers. Candidate RDF carries `la:reviewPreparationOnly` and
is rejected by `releases.check_data` regardless of marker value or signature.
This draft format has no automatic promotion/signing/publication path.

Substantive relationships are reified `Assertion` records carrying subject,
predicate, object, exact evidence passage/artifact, graph family, scope, synthetic
flag, extraction method/version and review status. Assertions carry **legal valid
time** (`validFrom`, exclusive `validTo`) and **system time** (`recordedAt`,
exclusive `supersededAt`). Publication, decision, effect and finality dates remain
separate. Unknown validity never means currently applicable. Explicit open-ended
states additionally carry `validityEndStatus "open_ended"`, an inclusive
`validityCheckedThrough` date and separate `validityEvidence` passages on both
assertions and provision versions. A null `validTo` alone remains unknown. Dated
retrieval excludes dates after the checked horizon; history/evidence inspection
can show the record without establishing applicability. Conflicting versions of
one provision are rejected across the two families; an open interval is unbounded
for overlap detection, regardless of its check horizon. `temporal.py` enforces
the shared contract in addition to SHACL and independent source-byte checks.

Institution classes/categories are not actual institution instances. Organization,
appeal routes, competence, supervision and legal authority are separate relations.
An unresolved reference remains an `UnresolvedReference`; it cannot be used as a
resolved `ProvisionVersion`. An `applies` or `interprets` assertion requires an
exact resolved version, never an automatic latest-version substitute.

Private matter nodes and their assertions remain in a separate authorized storage
boundary. They may reference public identifiers; public graphs must not contain
private inverse references. `private_overlay` declares shared vocabulary only.
The public graph adapter requires explicitly public endpoints, evidence passages
and source artifacts. It excludes synthetic data and does not load fixture files.

## Bounded read tools

All payloads reject unknown keys. Dates use `YYYY-MM-DD`; `known_at` is an ISO
timestamp including its timezone. `graph` is `structure` or `jurisprudence`.
`limit` is 1–100 (default 30); `hops` is 1–2 (default 1). Entity/assertion IDs must
be absolute HTTP(S) or URN identifiers. Arbitrary SPARQL is not an API.

| Tool | Required input | Optional input |
|---|---|---|
| `locate_issues` | `query` | graph, as_of, known_at, limit |
| `resolve_authority` | `identifier` (exact IRI or canonical identifier) | graph, as_of, known_at, limit |
| `trace_norm_history` | `entity_id` | graph, as_of, known_at, hops, limit |
| `trace_institution_history` | `entity_id` | graph, as_of, known_at, hops, limit |
| `trace_decision_history` | `entity_id` | graph, as_of, known_at, hops, limit |
| `expand_authorities` | `entity_id` | graph, as_of, known_at, hops, limit |
| `get_evidence` | `assertion_id` | graph, as_of, known_at, limit |
| `get_coverage` | none | none |

History tools show evidenced historical edges effective by the requested date;
applicability exploration/resolution excludes expired edges. Every path is bounded
to two hops with independently evidenced and time-filtered intermediate edges.
The adapter does not infer unstated legal relations. National review remaining
unreviewed keeps `legal_usable=false`, even for individually reviewed assertions.

Without Fuseki the mode is `catalog`: only schema classes and domain concepts are
shown. A configured but failing backend is `unavailable`, with no fixture or
catalog substitution for legal results. Fuseki URL is the server base; datasets
are `/structural/query` and `/jurisprudence/query`. Backend reads ignore environment
proxy settings, do not follow redirects, time out and stop after 2 MB of streamed
response bytes. They request identity encoding, reject compressed responses and
check a monotonic 15-second deadline on every available chunk; per-read timeouts
bound a stalled stream. Verified serving reads capture exact bundle/ontology hashes,
the serving receipt and activation sequence. Catalog-only snapshots retain their
catalog digest and never claim to represent a published corpus.

## Offline snapshot staging

The CLI creates a **new, content-addressed offline bundle** and never connects to
Fuseki or mutates a runtime database. It refuses an existing output path. Separate
proposed/reviewed Turtle files preserve assertion state. Raw inputs, ontology files,
physical evidence and an exact hash manifest are included; each source artifact's
SHA-256 must match an actual evidence file. Only referenced evidence is copied.
Public bundles reject synthetic/private data, evidence-less assertions, unknown
relations and direct consequential triples bypassing the assertion contract.

```sh
backend/.venv/bin/python scripts/validate_ontology.py fingerprint \
  --structure /approved-input/structure.ttl --jurisprudence /approved-input/jurisprudence.ttl

backend/.venv/bin/python scripts/validate_ontology.py create-bundle \
  --structure /approved-input/structure.ttl --jurisprudence /approved-input/jurisprudence.ttl \
  --evidence-dir /approved-input/evidence --output /staging/new-snapshot

backend/.venv/bin/python scripts/validate_ontology.py validate-bundle /staging/new-snapshot
```

Unsigned nonconsequential proposals may be staged, but publication remains blocked
pending national legal review. Consequential assertions require individually
recorded legal review **and** an Ed25519 attestation over the exact national
ontology and both original graph file hashes. Any assertion claiming legal review
requires this attestation. Supply `--review-attestation /review/attestation.json`
and `--trusted-review-key /review/reviewer-public-key.pem` when creating and the
trusted public key again when validating. The key is an operator-managed trust
input; an embedded key is never automatically trusted.

The attestation envelope is `{algorithm: "Ed25519", body: {...}, signature: "base64"}`.
Its body has exactly: `reviewer`, `reviewed_at`, `decision: "approve"`,
`scope: "national_ontology_and_assertions"`, `ontology_sha256`,
`input_graphs_sha256: {structure, jurisprudence}`. The signature covers UTF-8 JSON
with sorted keys, compact separators and unescaped Unicode. The CLI never creates
reviewer identities or signs legal approval itself.

An attestation proves signature integrity and the configured review identity;
reviewer qualification and legal correctness remain human governance obligations.
Staging never rewrites this baseline's unreviewed catalog status. Promoting a
reviewed snapshot into the runtime is a separate, explicitly governed operation.
Read-only files discourage accidental edits; manifest hashes and external review
signatures detect changes. This is not a claim of filesystem/WORM immutability.

Each evidence passage must additionally identify a `SourceRepresentation`, with a
SHA-256 of its UTF-8 extracted text, a hash of its JSON locator map and extractor
version. Passage offsets are **Unicode code-point offsets**, start inclusive and
end exclusive. The quote must equal that exact extracted-text span. Its locator
must contain the span in a map shaped as `{schema_version: 1, artifact_sha256,
text_sha256, extractor_version, spans: [{locator, start, end}]}`. Source bytes,
extracted text and locator maps must all be physically present in the evidence
directory. This catches fabricated quotes and misplaced locators even when the
original artifact's hash is correct. OCR/extraction fidelity to the original
document remains a separate QA and human-review obligation.

## Immutable serving publication

All installation, activation, rollback and application retrieval now require
[current private authorization](../docs/PUBLICATION_AUTHORIZATION.md), in addition
to public signature integrity. Conversion supports single-source provision snapshots
with finite dates or explicitly reviewed, evidenced open-ended validity bounded
for retrieval by its checked-through date. Preparation markers remain blocked.

[The serving operator guide](../deploy/fuseki/README.md) describes preparation,
installation, atomic two-family activation, rollback and independent trust mounts.
The runtime validates the signed bundle, builds disposable TDB2 indexes from its
canonical payloads, and exposes only query endpoints. Shared publication locks
exclude activation while readers run; compare-and-swap uses the release and
monotonic activation sequence. The API pins that release and checks original
signed relationships, evidence, temporal eligibility and runtime receipts.
Unsigned staging data, fixtures and legacy mutable datasets are never a fallback.

All returned relationships still retain `legal_usable=false`: publication review,
source grounding and applicability to a private matter are distinct judgments.
The application ships no independent legal approval key and creates none for
production. Engineering rehearsals use disposable keys and conspicuous test inputs
only in isolated storage.
