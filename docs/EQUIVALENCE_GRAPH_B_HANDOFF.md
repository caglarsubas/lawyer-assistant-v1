# Reviewed equivalence → private Graph B candidate

This continues [cross-source identity review](DECISION_EQUIVALENCE.md). It is
preparation for a separate publication review, not Graph B publication or a
global identity resolver. User deployment and actual legal qualification remain
separate gates.

## Exact prerequisites

`POST /api/v1/public-sources/{source}/decision-equivalence/graph-b-handoff`
uses the same `peer_source_id` and `register_source_id` query parameters as the
review workspace. The closed body contains `expected_revision` and all eight
source/mapping/identity revision pins. Only an authorized authenticated firm
curator/admin with CSRF protection can request it.

Both canonical identity opinions and the equivalence opinion must be current and
accepted. The relation must be `same_decision` with an explicitly selected anchor
from the two reviewed identities. All three sources require accepted provenance,
rights, extraction and legal-source assessments, including explicit export use.
Original source bytes, accepted passage hashes, full contributor histories and
the encrypted append-only ledgers must still verify. Account separation does not
prove independent qualified legal persons or substantive legal correctness.

The endpoint locks the requesting account/session and all three source heads in
sorted order. It verifies exact snapshots before and after compilation, including
current roles, identity reservations, source originals, ontology digest and
equivalence history. A changed or unresolved dependency withholds the whole
packet. PostgreSQL testing witnesses a register writer waiting while the packet
is compiled; a later changed source makes the old selection stale.

## Packet and evidence

`decision-equivalence-graph-b-handoff-v1` is a deterministic canonical JSON packet
with a content-addressed ID and envelope SHA256. Every physical file has its own
byte count, SHA256 and base64 bytes. It carries:

- All three original source packages and converted graph locator maps.
- Original decision, proceeding, institution and document-version tuples.
- The explicit canonical candidate and exact equivalence context/revision.
- Complete source, mapping, canonical identity and equivalence histories,
  including contributor identities, rejected opinions and superseded proposals.
- Ontology/compiler fingerprints and omitted mapping IDs for each source.
- Six reified identity candidates: two source paths each propose `decidedIn`,
  `issuedBy` and `hasDecisionVersion` for the chosen anchor.

The chosen anchor does not rewrite either original reservation or version. Pair
ordering does not alter the anchor or packet. Separate registers remain separate
review contexts; this endpoint never creates `owl:sameAs`, transitive aliases or
institution equivalence.

The RDF contains source-specific artifact/representation identities even when
physical bytes are equal. Both decision representations ground the alignment;
register passages support the `issuedBy` institution-identity candidate only.
Register evidence does not establish competence or territorial/temporal powers.
Actual institution genealogy and conditional competence need separate reviewed
assertions.

All six candidates retain `unreviewed` claim status and unknown legal validity.
No finality, legal force, citation treatment or legal-review signature is invented.
Exact original text slices and locator spans are checked alongside SHACL and
identity constraints. Structural validation is not legal truth. The intact RDF
retains `reviewPreparationOnly`, so current publication tooling rejects it.
Reviewer identities and private opinions remain in the confidential JSON and are
not inserted into candidate public RDF.

Bounds: 150 supporting passages across three sources; 6 MiB of complete source
files/converted locators; 16 MiB of complete JSON. Capture/ledger bounds from the
review contract still apply. No partial exports or truncated histories are given.

## Curator download and successor

The Turkish review workspace enables download only for current same-decision
acceptance and all-source export rights. Before saving, the browser verifies the
envelope, packet ID, exact firm/context/pins, complete histories and every original
file hash. Switching sources/accounts aborts requests, clears private state and
revokes temporary download URLs; downloaded files remain the operator's private
copies, not a shared cache. Server checks remain authoritative.

The next roadmap gate is a decision-specific, multi-source publication review
contract: independent legal-editor approval, institutional-register qualifications
and temporal scope, exact candidate signatures, withheld disagreements, and
publication/activation rollback validation. Existing generic source/provision
publication approval does not substitute for those gates.
