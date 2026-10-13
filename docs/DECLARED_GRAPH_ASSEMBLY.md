# Complete declared Graph A/B assembly and independent final attestation

Trusted local operator tooling combines one approved structural source set with
every declared Graph B component. **Complete means complete for the declared
inventory and retained active base.** It does not mean acquisition of
every Turkish judgment, national ontology approval, or legal applicability.

## Dependencies and trust

- Existing initialized publication root (`LA_GRAPH_RELEASE_DIR`), original source
  storage, encrypted review database and restore/publication epoch.
- A retained `legal-release-source-set-authorization-v1` under the configured
  data directory's `release-authorizations/<release-id>` namespace.
- One to eight retained signed Graph B component inclusion grants. Each contains
  its original sealed preparation and all three source-specific audience proofs.
- Four distinct vetted Ed25519 public keys: `LA_GRAPH_TRUSTED_REVIEW_KEY` for
  component public review/A permission; `LA_GRAPH_B_REVIEW_TRUSTED_KEY` for private
  decision review; `LA_GRAPH_B_COMPONENT_TRUSTED_KEY` for B inclusion; and
  **`LA_GRAPH_FINAL_REVIEW_TRUSTED_KEY`** for the final combined bytes.

Keys are independently configured; changing filenames does not establish key
separation. Operators must establish professional qualification, key custody and
reviewer independence outside this engineering contract. No command generates a
key, signs an approval, approves source rights, or uses the inference provider.

## Exact declaration

`legal-declared-graph-selection-v1` is a closed private JSON object:

```json
{
  "schema_version": "legal-declared-graph-selection-v1",
  "operator_id": "CURRENT-SOURCE-OWNER",
  "expected_base": null,
  "structure": {
    "release_id": "EXACT-64-HEX-COMPONENT-ID",
    "prepared": "/trusted/structural-prepared",
    "grant": "/configured-data/release-authorizations/EXACT-ID"
  },
  "jurisprudence": [{
    "release_id": "EXACT-64-HEX-DECISION-COMPONENT-ID",
    "prepared": "/trusted/decision-prepared",
    "grant": "/trusted/encrypted-inclusion-grant"
  }]
}
```

Replace placeholders with actual verified identifiers; they are deliberately not
valid inputs. `expected_base` is required. For a populated deployment, provide the
exact current `active.json` object (format version, release ID, serving digest,
previous release ID, sequence), and include its **whole** structural source-set
component. Missing roots, changed pointers, unsupported prior mixed/single-source
base namespaces, duplicates, empty families and undeclared files fail closed.
Inactive installed releases remain retained for rollback; they are not implicitly
part of the active corpus. This release prepares the first mixed corpus from an
empty initialized publication root or an existing structural source-set base.
Successive mixed bases use the [complete retained dependency contract](RETAINED_MIXED_ASSEMBLY.md)
and the original externally signed whole-release permissions; no missing base
inventory is treated as empty.

## Assembly guarantees

The assembler holds the existing publication shared lock and a single no-write
database transaction with globally sorted account/source/context/reservation
locks. A and B source selection is derived from verified grants rather than
untrusted replacement RDF. Every source, original byte, complete review history,
owner, active independent appointed reviewer, current permission, key, expiry and
restore epoch remains conjunctive. No family-specific guard opens a nested
transaction. SQLite demo uses optimistic reconstruction; PostgreSQL supplies
actual dependency row locks.

The compiler includes every component's original triples in its respective graph
and retains every physical artifact/text/locator manifestation. Identical evidence
bytes are deduplicated by hash; separate decision versions remain separate.
Conflicting definitions of a shared identity are withheld for explicit review,
including apparently benign differing descriptions; no silent reconciliation or
inference is performed. Combined SHACL, temporal and exact Unicode passage/locator
checks run across both families. These establish structural integrity, not truth.

The public inventory records component release/serving/input hashes, the entire
retained base file inventory, and ontology digest. Its canonical JSON and digest
are also encoded **inside Graph A**, so final graph signatures cover membership
and retained-base completeness. The sorted N-Triples serialization is valid Turtle
and deterministic for the same exact inputs. Unknown legal dates/effects and
original assertion evidence/review states are preserved.

## Local workflow

Run with the application dependencies available and trusted local paths:

```bash
python scripts/assemble_legal_graphs.py prepare \
  --selection /trusted/private-selection.json \
  --reviewer 'VETTED INDEPENDENT FINAL REVIEWER' \
  --reviewed-at 'EXACT-TIMEZONE-AWARE-REVIEW-TIME' \
  --output /trusted/new-assembly

python scripts/assemble_legal_graphs.py validate /trusted/new-assembly

python scripts/assemble_legal_graphs.py accept \
  --packet /trusted/new-assembly \
  --attestation /trusted/externally-signed-final-review.json \
  --output /trusted/new-reviewed-assembly

python scripts/assemble_legal_graphs.py validate \
  /trusted/new-reviewed-assembly --reviewed
```

The first command creates unsigned `public-review-body.json` for external review
and signing of the exact final graph hashes and ontology. Final review must follow
all component reviews and permission approvals. The final public reviewer label
cannot equal the operator ID or any component public reviewer label; the separately
configured final key must differ from all three component trust roles. Labels/key
separation cannot independently prove that two humans are different.

Acceptance requires a strict externally supplied Ed25519 envelope with exactly
`algorithm`, `body`, `signature`, the exact requested body and a 64-byte signature.
Component signatures cannot attest the union. The final input graphs also pass the
actual public bundle validation path. Acceptance does not retain an executable
serving release or activate a graph; the artifact is a reviewed preparation packet.

Private declaration paths, source/grant selections and dependency bindings are
encrypted in `dependencies.fernet`. Original source/audience/credential proofs stay
in their encrypted retained grants. Public input bytes, public reviewer labels,
component hashes and the final public attestation are intentional public content.
The wrapper is deployment-sealed, firm confidential, mode 0700/0600, immutable and
bounded by the existing 96 MiB/256-file packet limits and 64 MiB union budget.

Validation reconstructs current permissions and sources on every use. A changed
later member, final/component key, pointer, original artifact, grant or epoch, or
expired permission invalidates the entire packet. Final reconstruction occurs
after bounded work. Failed or interrupted output creation removes only the new
artifact owned by that invocation; existing evidence is never overwritten.

Each operation verifies component signatures/RDF afresh. Within that same
operation, the compiler consumes captured bytes bound to those verified manifests
instead of repeating identical RDF checks. Every private/public file is read and
hashed again at exit; all keys, lifetimes, base inventory, original database/source
histories and output bytes remain checked. No verdict is reused across operations.

## Next gate

All commands return `national_release_serving_authorized: false`. The reviewed
assembly is not accepted by an A-only or B-only serving grant. The next packet
must issue a separate externally signed final-release audience permission and
reconstruct **every** A/B dependency for install, activation, rollback and runtime
read, including successive mixed bases. Actual legal editor vetting, licensed
corpus coverage, deployment and held-out lawyer acceptance remain separate gates.
