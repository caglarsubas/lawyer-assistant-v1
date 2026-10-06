# Independent publication permission for a source set

This R02 engineering workflow extends the [existing two-approval model](PUBLICATION_AUTHORIZATION.md)
to **2–8 reviewed provision sources**. An external public attestation approves the
exact ontology, transformed graph bytes and supporting passages. A separate external
private authorization binds the complete source selection, current review revisions,
physical rights proofs, audience, expiry and local publication epoch. Neither the
CLI nor the application signs, creates signing keys or performs independent legal review.

The initial shared graph supports only `deployment_shared` permission. Every source
must explicitly permit that audience and all six existing uses. A firm-only,
conditional, missing or otherwise restricted grant is rejected. Such a source must
not be admitted to the shared graph; a private audience-partitioned corpus remains
future work. A source's ordinary acceptance does not itself establish sharing rights.

## Prepare the two external approvals

Use a current, unblocked [source-set preparation packet](RELEASE_SET_PREPARATION.md)
on the trusted deployment host. Operator IDs select existing authorized local
accounts; these commands are not remotely authenticated endpoints. All selected
sources must have the same active assigned operator and firm. The existing policy
epoch must already be initialized, or initialize it once with:

```sh
python scripts/review_set_publication.py init-policy
python scripts/review_set_publication.py candidate /private/source-set-packet \
  --operator-id CURRENT_REVIEW_OWNER \
  --public-reviewer 'Intentional public reviewer label' \
  --reviewed-at PUBLIC_REVIEW_TIMESTAMP_WITH_TIMEZONE \
  --output /private/source-set-signing-inputs
```

The candidate operation holds the current source-set review locks and rebuilds the
packet before conversion. Both graph families must carry exactly the selected
source markers. Conversion removes those markers, changes the supported provision
assertions to `legally_reviewed`, and substitutes the intentional public reviewer
and public review time. It preserves canonical identities, relationships, exact
quotes, legal dates and checked-through evidence. A public review cannot precede
the mapping review or open-ended validity horizon. Unresolved preparation blockers
prevent conversion.

An independent reviewer inspects the complete candidate and externally signs the
canonical `public-review-body.json`. Use the existing `validate_ontology.py
create-bundle` and `graph_releases.py prepare` commands from the
[publication operator sequence](PUBLICATION_AUTHORIZATION.md#operator-sequence).
Supply only the candidate `inputs/` graphs and hash-named `evidence/` directory
when building the public bundle. Do not copy the private packet or NOTICE into it.

Next, prepare a private JSON list with exactly one permission for every source:

```json
[
  {
    "source_id": "REPLACE_WITH_FIRST_64_CHARACTER_LOWERCASE_SHA256",
    "audience": "deployment_shared",
    "permitted_uses": [
      "export", "indexing", "internal_display", "local_inference",
      "local_processing", "storage"
    ],
    "evidence_sha256": "REPLACE_WITH_PHYSICAL_RIGHTS_PROOF_SHA256",
    "expires_at": "REPLACE_WITH_TIMEZONE_AWARE_SOURCE_PERMISSION_EXPIRY"
  }
]
```

The example is illustrative and must contain all 2–8 real selected source IDs.
Each proof must exist in the private packet and appear in that source's current
rights assessment. Proofs cannot be borrowed from another source merely because
their bytes are present somewhere in the combined packet. The same proof may cover
multiple sources only when each source's assessment explicitly references it.
The external signer remains responsible for the proof's legal meaning and scope;
the code checks exact evidence binding and the signed declarations.

```sh
python scripts/review_set_publication.py request /private/prepared \
  --packet /private/source-set-packet --operator-id CURRENT_REVIEW_OWNER \
  --trusted-review-key /trusted/reviewer.pem \
  --reviewer 'Private accountable reviewer' \
  --approved-at APPROVAL_TIMESTAMP_WITH_TIMEZONE \
  --expires-at RELEASE_PERMISSION_EXPIRY_WITH_TIMEZONE \
  --source-permissions /private/source-permissions.json \
  --output /private/source-set-authorization-request
```

The requested release expiry must be no later than **every source's permission
expiry**. Both the release and each source grant are bounded to at most 90 days
after approval. A source expiry here bounds this signed grant; it is not a claim
about the underlying licence's full duration. Approval must follow the public review
and every relevant source/mapping review. Future approvals, expired intervals,
omitted or duplicate sources, altered bindings, unsupported audiences and extra
fields are rejected. Unknown licence conditions must be resolved by the independent
reviewer before approval; they are not inferred from source text by this workflow.

The reviewer externally signs canonical `authorization-body.json` in an envelope
with exactly `algorithm: "Ed25519"`, `body` and base64 `signature`. The body uses
`legal-release-source-set-authorization-v1` and
`reviewed-provision-set-promotion-v1`. Only the configured trusted public key is
accepted; an embedded input key cannot grant permission.

```sh
python scripts/review_set_publication.py accept /private/prepared \
  --packet /private/source-set-packet --operator-id CURRENT_REVIEW_OWNER \
  --trusted-review-key /trusted/reviewer.pem \
  --authorization /private/externally-signed-source-set-authorization.json
```

Acceptance verifies in a private staging directory, then checks the durable record
again. Existing records are never replaced. A failed final check removes only this
invocation's output. Successful acceptance does not install or activate graphs.
Use the existing guarded install/activate/rollback commands and publisher service.
The narrow fifth-level private record path accommodates
`packet/candidate/sources/<source_id>/raw.bin`; ordinary packet readers still admit
only four path components. All directories are 0700 and files 0600.

## Continuing authorization and renewal

The application's existing guard dispatches only the two recognized signed formats.
Each format independently verifies its own signature, packet, current reviews and
public bytes. Existing single-source preparation/promotion remains strictly
single-source; its CLI cannot silently accept a source-set packet.

At install, activation, rollback and application read boundaries, the guard locks
the complete selection in deterministic order, rebuilds the current packet, verifies
the exact public graph/evidence inventory and current ontology, and rechecks the
authorization, key, epoch, packet and expiry on exit. A revoked right, changed
mapping/review, reassigned/inactive owner, changed source bytes or expired permission
on **any** selected source blocks the entire dependent release. Search and retained
work inherit the existing authorization/staleness checks; saved content is not
silently rewritten. Fuseki remains internal and does not independently authorize
private permissions. SQLite is optimistic demo storage, not transactional qualification.

Renewal requires a **fresh public review timestamp and externally signed release**,
followed by a fresh private approval of the complete current source set. The new
release ID receives a new immutable record. The operator installs and activates
it through the normal guarded transition. Old records remain for audit, and old
expired or revoked releases cannot become valid rollback targets through renewal.
There is no background renewal, extension of an old signed expiry or replacement
of an accepted authorization under the same release ID.

## Public/private boundary and remaining gates

The public bundle contains only the exact ontology, promoted graphs, public
attestation, graph partitions and deduplicated physical source evidence. It excludes
private bindings, source-selection inventories, account/firm IDs, workflow timestamps,
permission declarations and proof files. Public reviewer attribution is deliberately
provided for publication. The full packet and all signing-input directories remain
confidential even when they contain public source bytes.

Existing source-set limits remain: 400 mappings, 64 MiB selected artifacts/output
content, 25,000 assertion evidence links and 32 MiB private proof bytes. This slice
does not establish five-job throughput, peak memory, cancellation or large-corpus
latency. Restricted audience serving, same-release authorization renewal, real
source/legal/privacy qualification and a populated corpus remain open. Restores
retain the existing epoch invalidation rule; historical approvals cannot revive
automatically after restoration.
