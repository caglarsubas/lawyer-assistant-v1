# Signed Graph B component inclusion

A trusted deployment-host operator can now request, accept and validate an externally signed **component inclusion grant**. It grants permission to include the exact reviewed six-assertion identity component in a later complete release. It cannot install, activate, roll back or serve that component as the national legal corpus.

Use three separately configured, independently vetted Ed25519 public keys:

- `LA_GRAPH_B_REVIEW_TRUSTED_KEY`: independent private decision, institution-identity and temporal review.
- `LA_GRAPH_TRUSTED_REVIEW_KEY`: public ontology/assertion attestation of the exact prepared component.
- `LA_GRAPH_B_COMPONENT_TRUSTED_KEY`: deployment audience and source-specific inclusion approval.

Distinct key material is required; three filenames for the same key are rejected. No command generates a key or signs an approval. Real key custody, reviewer appointment/professional vetting, rights and legal review remain deployment responsibilities. `.env` and provider credentials stay operator-managed.

## Offline operator workflow

First prepare and independently attest the public component using [Graph B preparation](GRAPH_B_PUBLICATION_PREPARATION.md). An existing publication epoch and the private source packet are required. The three-source permission list has the same closed source-specific rights contract as the earlier unsigned request.

```sh
python scripts/review_graph_b_component.py request \
  --prepared /private/review/reviewed-component \
  --packet /private/review/graph-b-packet --operator-id "$OPERATOR_ID" \
  --source-permissions /private/review/source-permissions.json \
  --reviewer "$INCLUSION_APPROVER" \
  --approved-at "$APPROVAL_TIME" --expires-at "$EXPIRY_TIME" \
  --output /private/review/new-component-signing-request
```

`grant-body.fernet` contains canonical signing inputs, encrypted with the existing deployment key. Its body declares the intended signed grant; **the body is not a signature or an accepted grant**. An authorized external signer decrypts only in trusted private local memory, checks the complete body and signs its canonical JSON. The external envelope has exactly `algorithm: Ed25519`, `body` and a base64 64-byte `signature`.

The closed body uses `graph-b-component-grant-v1`, `scope: component_inclusion_only`, `signed: true`, `national_release_serving_authorized: false` and the configured component key fingerprint. It binds the prepared public release/serving/ontology digests and public-review key; the private preparation inventory, source/review/equivalence pins and independent appointment; all three source-specific deployment audience permissions; approval/expiry; and publication epoch. Every field must equal a request reconstructed from the current original sources.

```sh
python scripts/review_graph_b_component.py accept \
  --prepared /private/review/reviewed-component \
  --packet /private/review/graph-b-packet --operator-id "$OPERATOR_ID" \
  --authorization /private/review/external-component-envelope.json \
  --output /private/review/new-retained-component-grant

python scripts/review_graph_b_component.py validate \
  --prepared /private/review/reviewed-component \
  --grant /private/review/new-retained-component-grant
```

Acceptance retains the original sealed preparation and encrypts the **whole signed envelope** as `grant.fernet`. Source selections, accounts, credential proofs, audience evidence and private signatures are never copied into public graph files. New directories are 0700, files 0600, no replacement or symlink traversal is accepted. A deployment inventory seal proves integrity, not legal approval. Existing grants remain historical evidence after revocation. Late validation failure or interruption removes only newly owned output; repeated acceptance never removes an existing directory.

## Current-use boundary

`GraphBComponentGrant.guard(info, grant, purpose="inspect" | "include")` is a trusted-host context manager. It reconstructs complete source/identity/equivalence/signed-review histories against the current configured private key, current active independent accounts and appointments, source bytes, ontology and exact revisions. It independently verifies the public attestation and component bytes and the separately signed inclusion grant. All three accepted rights assessments must retain the exact audience evidence and all required uses.

PostgreSQL inspect operations use shared account/source/identity/review locks; inclusion uses exclusive locks. Locks remain held through the caller's bounded work and current-state exit reconstruction. Key changes, expiry, public/preparation/grant bytes and restore epoch are checked at entry, after the caller and after source exit reconstruction. A failed context exit invalidates dependent output. Every new use must enter the guard again; there is no cached permission verdict. SQLite remains an optimistic demo boundary, not concurrency qualification.

Expiry must follow approval, remain current, be within 90 days and not outlive the independent review appointment or any source permission. A later negative review, rights change, account revocation, changed identity/equivalence/source pin, rotated key or restore epoch withholds the old grant. Unknown competence, finality and legal effects remain unknown.

The unsigned request, private review, public attestation, inclusion grant and national serving authorization have separate schemas and trust roles. Failure in one namespace is never retried through another. `install`, `activate`, `rollback` and `read` are explicitly rejected by this gate. Complete reviewed Graph A/Graph B assembly, independent review of the final assembled bytes and conjunctive national serving authorization are the next milestone. No actual national corpus, professional/legal qualification, production publication or user deployment is supplied by the engineering fixtures.
