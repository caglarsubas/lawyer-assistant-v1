# Encrypted Graph B publication preparation

Trusted deployment-host operators can prepare a current six-assertion decision identity component and an encrypted, unsigned inclusion-permission request. This workflow does not accept a signature, install or activate a graph, authorize national serving, or establish professional qualification. It contacts no external service and generates no signing key.

Use the existing private store and the separately configured `LA_GRAPH_B_REVIEW_TRUSTED_KEY` and `LA_GRAPH_TRUSTED_REVIEW_KEY` public keys. Credentials, organization/tenant configuration and the repository-root `.env` remain operator-managed. Preparation uses the existing read-only database adapter, never application bootstrap or an impersonated HTTP login.

## Local preparation

Create a closed `signed-graph-b-selection-v1` JSON file containing the two sorted decision-source IDs, distinct institutional-register source ID, independent reviewer ID, exact signed-review/equivalence revisions and all source/mapping/identity pins. Copy the values from the current reviewed context; do not guess identifiers or automatically substitute revisions. See [current snapshot contract](GRAPH_B_PUBLICATION_SNAPSHOTS.md).

Supply an existing private evidence directory with `{sha256}.bin` audience/rights documents. Every file must match its content hash and an evidence reference in a currently accepted source-rights assessment. Each of the three sources must have at least one supplied source-linked document, and all six source-use rights must be accepted. Merely including such a document does not constitute an approved deployment audience.

```sh
python scripts/prepare_graph_b_publication.py prepare \
  --operator-id "$OPERATOR_ID" \
  --selection /private/review/selection.json \
  --evidence-dir /private/review/audience-evidence \
  --output /private/review/new-graph-b-packet

python scripts/prepare_graph_b_publication.py validate \
  /private/review/new-graph-b-packet --operator-id "$OPERATOR_ID"
```

Output directories must be new, with existing parents. Files are mode 0600; directories are mode 0700. Atomic no-replace output, deployment-bound inventory seals and final source/trust/history revalidation withhold or remove only newly created output when checks fail. Earlier packets remain historical evidence, not current permission. Interruption after rename removes the new artifact and sibling reservation.

`private-evidence.fernet` encrypts all private source selection/account/revision bindings, the exact signed review including appointment proof and accepted review key, and audience proof bytes with the existing deployment encryption key. The canonical manifest and HMAC verify the exact inventory; they are integrity checks, not legal review. Revalidation decrypts only in trusted local memory and compares every private field and public byte to a freshly reconstructed complete review.

Only the explicitly retained `public_input_paths` are public-review inputs: `inputs/structure.ttl`, `inputs/jurisprudence.ttl`, content-addressed evidence files, and `public-review-body.json`. Do not publish the private ciphertext, manifest/HMAC, `NOTICE.json`, or the complete packet. The desired public RDF retains unknown intervals and source-specific manifestations; it does not infer competence, finality or legal effects. Graph A is empty in this component; this packet must never replace the national corpus.

## Independent public review and inclusion request

A separately vetted public ontology/assertion reviewer must inspect the public files and sign the public body externally. The existing release tools independently verify that signature, original evidence, graph hashes, ontology and SHACL before preparing an immutable component. A private Graph B review signature cannot substitute for that public attestation.

An existing publication epoch must already have been initialized by the deployment operator. Supply a closed list of exactly three source permissions, one per source. Each requires `source_id`, `audience: deployment_shared`, sorted six `permitted_uses`, `evidence_sha256` and timezone-aware `expires_at`. Proof must be both retained in the encrypted packet and referenced by that exact source's current rights assessment. A proof accepted for another source cannot fill a missing permission.

```sh
python scripts/prepare_graph_b_publication.py request \
  /private/review/new-graph-b-packet \
  --operator-id "$OPERATOR_ID" \
  --prepared /private/review/externally-reviewed-component \
  --source-permissions /private/review/source-permissions.json \
  --reviewer "$PRIVATE_APPROVER_LABEL" \
  --approved-at "$APPROVAL_TIME" --expires-at "$EXPIRY_TIME" \
  --output /private/review/new-component-request
```

The retained `permission-request.fernet` is encrypted and unsigned. A trusted external signer can decrypt it only in local private memory. It binds the exact component ID/serving digest, public attestation key, ontology, private preparation manifest and snapshot, source-specific permissions and restore epoch. Approval time must follow current source/mapping and signed/public review events. Expiry must remain current, be no later than every source permission or the independent review appointment, and be within 90 days. Epoch, trust, prepared bytes, source histories and expiry are rechecked after durable output.

The exact request schema is `graph-b-component-permission-request-v1`, with `scope: component_inclusion_only`, `signed: false` and `national_release_serving_authorized: false`. Existing provision grants and runtime publication guards do not accept it. No command here imports a signature or grants installation.

The successor must add independently signed component-grant acceptance and full Graph A/Graph B assembly, then require every current component/source permission at install, activate, rollback and read. Complete legal/editor vetting, actual corpus and institutional history, key custody, deployment and lawyer/pilot qualification remain separate gates.
