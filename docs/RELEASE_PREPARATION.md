# Preparing a provision graph for independent review

This offline operator workflow connects accepted provision mappings to a private
review packet. It does not sign or publish a graph. The running application stays
available; no source package, review decision or graph dataset is changed.

For the subsequent externally signed conversion, private audience permission and
live publication checks, follow [publication authorization](PUBLICATION_AUTHORIZATION.md).
The preparation packet itself remains unsigned and unpublishable.

## Prerequisites

Use the existing source-review owner's account ID on the trusted deployment host.
The owner must still be an active admin or curator. All four source assessments
and every mapping must be accepted at the exact expected revisions. The rights
assessment must explicitly permit storage, local processing, internal display,
export, indexing and local inference. Local-display approval alone is insufficient.

Supply an identity registry and resolution plan matching the schemas in
[the contract](RELEASE_PREPARATION_CONTRACT.md). Each registry identity has a
typed canonical ID, an explicit parent, and physical evidence digests. Resolve
each mapping explicitly; its human-written reference string is never interpreted
as a canonical ID. Evidence files are named `<sha256>.bin` and must contain the
actual reviewed bytes. Include the latest rights-assessment evidence and all
identity evidence; neither a public URL nor an arbitrary digest proves rights.

Registry evidence proves that supplied bytes match the reference. A competent
human must still evaluate identity truth and legal rights. Identity entries remain
proposals until independent review. Source and identity documents stay inert.

## Commands

`scripts/prepare_legal_review.py` is included in the API image. Use an existing
private input directory and a new output directory whose parent already exists.
The paths below refer to the container filesystem. Stage the approved input files
in a mode0700 directory with mode0600 files; do not place them in public graph
volumes. Use the deployment's configured PostgreSQL connection and encryption key;
the tool does not initialize a database or create credentials.

```sh
docker compose exec -T api python /app/scripts/prepare_legal_review.py prepare \
  --operator-id EXISTING_SOURCE_REVIEW_OWNER_ID \
  --source-id EXACT_SOURCE_PACKAGE_SHA256 \
  --expected-source-review-revision 5 \
  --expected-mapping-revision 2 \
  --registry /tmp/legal-review-input/registry.json \
  --resolutions /tmp/legal-review-input/resolutions.json \
  --evidence-dir /tmp/legal-review-input/evidence \
  --output /tmp/legal-review-output

docker compose exec -T api python /app/scripts/prepare_legal_review.py validate \
  /tmp/legal-review-output --operator-id EXISTING_SOURCE_REVIEW_OWNER_ID
```

Revisions above are illustrative, not permissions or current production values.
Use actual current revisions. The tool rejects existing output paths, including
competing creation races. It writes private regular files to a sibling staging
directory and atomically renames without replacement. If the final source/review
check fails, it discards only the packet created by that invocation. Output under
`/tmp` is temporary; preserve needed packets in an approved encrypted review store
before recreating the container. The entire packet is confidential, including
which public authorities it selects.

On a configured local deployment the equivalent entry point is
`backend/.venv/bin/python scripts/prepare_legal_review.py`. Production requires an
explicit existing PostgreSQL connection; the Compose-generated database URL may
not exist in the host `.env`. SQLite is restricted to explicit synthetic demo
mode and an already-existing database/key. No cloud service is called.

## Reading the result

- `binding.json` binds the exact firm, owner, source artifacts and both ledgers.
- `registry.json` and `resolutions.json` preserve the explicit proposed identities.
- `private-evidence/` holds physical identity and rights proof. It never belongs
  in shared graph evidence or a public repository.
- `review-report.json` reports blockers and ontology/input digests.
- `candidate/` contains only allowlisted source evidence and, when possible,
  candidate graph inputs. Reviewer notes, firm IDs and assignment metadata are
  excluded. The enclosing packet remains private.
- `manifest.json`, its digest and a deployment-local HMAC protect the inventory.
  The HMAC is not a legal signature. Encryption-key rotation requires new packets.

Unknown identity resolution, acquisition time, validity start, or an unsupported
text role blocks RDF generation. A null end date remains **unknown** unless the
accepted mapping explicitly contains `open_ended_validity`: an inclusive
`checked_through` date and a fully covered supporting source span
(`evidence_start`, `evidence_end`). Its start must be known, its end must be null,
and the check date must fall between the validity start and the immutable review
event's UTC day. The supporting passage can be outside the provision body but
must belong to the same acquired source. Review that exact text in the mapping
screen; absence of a repeal in a document is never an automatic open-ended finding.

Open-ended status permits date-specific retrieval only through its checked date.
That date is not a legal end date. A later version conflicts with an earlier open
interval until its true end is reviewed; overlapping versions of one provision
are rejected. Closed periods remain start-inclusive and end-exclusive. Historical
inspection can retrieve expired reviewed records without asserting applicability.
Unknown-end records remain excluded even from those legal-history paths.
Amendment and quoted text are not silently turned into operative authority.

When candidate RDF can be generated, assertions remain `unreviewed` and carry a
preparation-only marker. The ordinary release validator rejects that marker even
with a trusted signature. Removing the marker and obtaining a new signature is
a separate privileged manual act; this workflow does not authorize or implement
it. Do not pass these files to a publisher.

Validation reopens current source/review data under locks, verifies the local seal,
recompiles against the current ontology and compares all exact bytes. A successful
result means current **at that check**, not an enduring grant of rights or legal
approval. Later source, mapping, owner, rights, evidence, identity or ontology
changes require renewed preparation and review. The implemented
[publication authorization](PUBLICATION_AUTHORIZATION.md) binds independent review
to the exact packet and enforces current private review bindings at installation,
activation, rollback and use. A standalone public signature cannot establish those
live ledger bindings or supply continuing permission.

The strengthened ontology changes its digest. Reprepare and independently review
affected packets/releases; do not edit sealed packets or reuse an old approval
as permission for new temporal semantics. Existing mapping records are retained
without rewriting their encrypted payloads.

Test fixtures and engineering-generated signatures are never legal approval.
See [validation](VALIDATION.md) for measured checks and remaining qualification.
