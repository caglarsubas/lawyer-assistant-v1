# Qualified Graph B public signing inputs

The current three-source equivalence and independently signed private review can
now produce bounded, deterministic public signing inputs. This is an unsigned
handoff. It grants no publication audience permission and writes no graph data.
The original unreviewed preparation packet remains rejected by publication tools.

## Current review and complete evidence

Only the active source owner/operator bound to the latest signed approval can
POST `/api/v1/public-sources/{source}/graph-b-review/signing-inputs` with
`peer_source_id`, `register_source_id`, exact review/equivalence revisions and all
pins. All three export rights, the complete signature ledger, credential hash,
current independent reviewer appointment, ownership, active accounts, configured
review key, ontology and original source bytes are revalidated. Sorted source
locks stay held through compilation. Final dependency, role, key and ontology
checks withhold the complete response on change; there is no partial result.
A later rejection/change request, expired appointment or stale review blocks export.

The compiler accepts no client RDF or arbitrary file paths. It emits six fixed
reified identity relations, preserving the reviewed canonical anchor and both
source-specific decision versions. Source-specific assertion identifiers derive
from public identities, evidence, temporal metadata and the intentional public
reviewer label/time. Private event/snapshot/account/firm identifiers are excluded
from public inputs. No `sameAs`, global alias, inferred competence or finality is
created. The register qualification remains **historical identity only**.

Each relation keeps its own separately signed dates and exact source evidence:
unknown has no bounds; closed is end-exclusive; open requires its reviewed horizon
and explicit physical validity evidence. Register bounds never become relationship
bounds automatically. The decision-date/register assessment remains retained in
the private signed review and supporting public passages; it is not silently
promoted to a new public date/competence property outside the ontology contract.

## Packet and public-file boundary

The downloaded JSON wrapper is **firm-confidential**, with exact private review,
equivalence and ontology bindings, SHA256s, byte counts and a content-addressed
packet ID. Do not publish that wrapper or `NOTICE.json`. Only explicitly listed
`public_input_paths` are designed for external public review:

- `inputs/structure.ttl` and `inputs/jurisprudence.ttl` (deterministic N-Triples,
  valid Turtle syntax); Graph A is empty for this identity slice.
- `evidence/{sha256}.bin`: deduplicated original public artifacts, full extracted
  text and converted complete locator maps.
- `public-review-body.json`: canonical unsigned template binding both graph
  hashes and the exact ontology digest.

Original private appointment bytes, organizational statements, contributor names,
account/firm IDs, complete private histories, private rationales and sealed policy
packets never enter these files. Exact quote/code-point/locator checks and full
SHACL/temporal preflight run before returning. Desired `legally_reviewed` RDF is a
public attestation target, not an installed or published assertion. The preflight
explicitly reports `legal_truth_verified=false` and cannot issue an attestation.
Budgets: 150 selected passages across all sources, 6 MiB distinct physical files,
16 MiB complete encoded response; oversized output is withheld without truncation.

The curator screen verifies the selected review/envelope, complete inventory,
every file hash and length, public-review graph hashes and packet ID before
triggering download. Selection changes/unmount/denial clear stale state and revoke
object URLs. Its confirmation explicitly says unsigned and unpublished.

## Independent release and runtime gates

A separately vetted national ontology/public assertion reviewer must inspect the
final public inputs and sign the public body **externally**. Its template label and
timestamp are prefilled from the private review; that national reviewer may update
those two attestation fields to their actual identity/review time before canonical
serialization and signing, retaining the exact scope, ontology and input hashes.
The application does not create a signing key, signature, qualification or grant.

Current release bundling independently verifies that public signature and all
physical quotes. A private Graph B signature alone fails that check. A verified
public bundle still cannot be installed without a separate live authorization
guard. The existing provision authorization contracts must not be reused for
decision identities. Decision-specific source/audience permission, revocation,
restoration epoch and activation/rollback remain the next implementation gate.
Assembly and review of a complete final Graph A/Graph B release, rather than
replacement with this limited slice, also remain an operator requirement.
Actual legal/editor vetting, institution genealogy and corpus/pilot qualification
remain external acceptance requirements. No production dataset is changed here.

## Unknown facts and negative opinions

A signing request now explicitly selects `approve` (default), `reject` or
`needs_changes`. An editor can record a signed negative opinion with
`qualifications.decision_on=null` and an explicitly unknown register identity
window, rather than inventing dates merely to reject a proposal. Supplied evidence
still resolves to the proper accepted sources, identities still match the pinned
equivalence, and appointment/independence/signature/history/current-role checks
still apply. Known claimed ranges retain all evidence constraints. Positive
approval still requires a decision date supported by both representations and
register identity covering that date. A latest negative opinion, including one
with unknown dates, blocks signing-input generation and preserves prior approval.
