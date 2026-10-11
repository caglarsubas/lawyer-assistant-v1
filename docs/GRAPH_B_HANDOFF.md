# Private staged Graph B handoff

This R03 packet follows [canonical identity review](CANONICAL_DECISIONS.md).
It compiles one own decision's identity candidates, with complete private review
history and physical evidence. It does not populate a graph service or authorize
publication. Ordinary citation/application/treatment mapping remains in the private
ledger and is listed explicitly as omitted from candidate RDF.

`POST /api/v1/public-sources/{source_id}/decision-identities/graph-b-handoff`
accepts only `expected_revision`, `expected_mapping_revision` and
`expected_source_review_revision`. Current admin/curator role, `source.curate`,
CSRF, all current source/mapping reviews, a current independent-account identity
acceptance and explicit accepted export rights are mandatory. Identity acceptance
alone is insufficient to compile or publish a graph.

## Exact evidence requirement

Every identity, institution and latest independent-review evidence reference must
resolve to `source:{source_id}:passage:{passage_id}`, with that retained passage's
exact SHA256 and current accepted extraction coverage. Own-decision mapping spans
must also fall within that coverage. No free-text reference, remote URL, hash without
physical evidence, other source or external register is silently resolved. Such
references can remain in private identity review, but this initial handoff is
withheld until supported. Multi-source identity/equivalence evidence is a successor
contract, not an inference from matching numbers or names.

## Artifact contract

The JSON envelope contains exact UTF-8 `evidence_json` plus its SHA256. Its
`decision-graph-b-handoff-v1` payload carries:

- Firm-confidential scope, source artifact binding and all three review revisions.
- Complete ordered identity, source-review and mapping histories, including authors,
  disagreement and superseded proposals. These records remain private.
- Base64 original retained artifacts, a hash-linked converted locator map and sorted
  deterministic `candidate/jurisprudence.nt` bytes. Each file has its exact size/hash.
- An ontology fingerprint, compiler version and a content-addressed packet ID. The
  ID hashes canonical metadata, private histories and all file hashes/sizes; repeated
  requests for unchanged inputs yield identical bytes. Hashes are not signatures.
- Three reified, evidence-backed relationship **candidates**: `decidedIn`, `issuedBy`
  and `hasDecisionVersion`. Their subjects/objects have distinct types. They remain
  `unreviewed` with unknown legal validity/effects. No direct authority-treatment,
  jurisdiction, binding-effect, date or finality relationship is invented.

Candidate RDF contains only source-derived legal identity/evidence nodes, not reviewer
names, private matter links or review notes. RDF `scope=public` describes the proposed
source data; it is not an audience grant for this firm-private transport artifact.
The exported `reviewPreparationOnly` marker causes existing publication bundle tooling
to reject the intact candidate graph. It is removed only in an in-memory engineering
validation view. No generated signing key, signed approval or graph update is supplied.

## Validation and concurrency

The existing RDF/SHACL and physical quote-grounding validator checks types, relation
families, required metadata, exact original Unicode spans and locator/hash bindings.
Conformance does not prove that a reviewer correctly identified the issuing court or
decision, qualify the unreviewed ontology, or establish legal truth. The packet keeps
`signed`, `graph_updated`, `global_registry_qualified`, `legal_effect_verified` and
`publication_eligible` false.

Physical inputs are bounded to 2 MiB total, at most 50 supporting passages and 8 MiB
for the entire JSON packet. Exceeding any limit withholds the whole packet. The
current source row and actor are locked while compiling. Full histories, identity
reservations, original artifacts, role and ontology fingerprint are revalidated
before response. Source/mapping/identity changes, rejected review, corruption or
stale pins prevent handoff. The browser independently checks byte hashes, complete
history sequences, firm/source/revision bindings and packet identity before download;
scope changes clear private state and pending downloads.

## Remaining release work

Independent professional/source/privacy/fidelity/legal review, national identity
equivalence, historical institutional identity, typed authority treatments and exact
norm-version resolution remain required. A decision-specific, externally reviewed
publication contract, signed ontology/assertion approval, rights/audience grant and
serving qualification must precede shared Graph B use. Existing provision publication
workflows are unchanged. The handoff is an implementation milestone, not corpus or
pilot acceptance.
